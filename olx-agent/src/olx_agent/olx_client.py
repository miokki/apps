"""Client for the public JSON API that the OLX.pl web app uses, with an HTML fallback for listing pages."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import httpx2

from .config import Config
from .listing import (
    Listing,
    Seller,
    extract_offer_id_from_html,
    parse_api_offer,
    parse_api_user,
    parse_listing_html,
)

Condition = Literal["new", "used", "damaged"]
Sort = Literal["relevance", "newest", "price_asc", "price_desc"]

_SORT_PARAM = {
    "newest": "created_at:desc",
    "price_asc": "filter_float_price:asc",
    "price_desc": "filter_float_price:desc",
}
_MAX_PAGE = 50
_MAX_OFFSET = 1000
_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class OlxError(Exception):
    pass


@dataclass
class Location:
    label: str
    city_id: Optional[int] = None
    region_id: Optional[int] = None
    district_id: Optional[int] = None


@dataclass
class SearchPage:
    listings: list[Listing]
    total: Optional[int]
    next_offset: Optional[int]
    notes: list[str] = field(default_factory=list)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def offer_id_from_ref(ref: str) -> Optional[str]:
    """A numeric offer id given directly, or `None` when `ref` is something else (e.g. a listing URL)."""
    ref = ref.strip()
    return ref if re.fullmatch(r"\d{5,}", ref) else None


class OlxClient:
    def __init__(self, config: Config, http: Optional[httpx2.Client] = None) -> None:
        self.config = config
        self.base_url = config.olx_base_url.rstrip("/")
        self._http = http or httpx2.Client(
            timeout=config.http_timeout_s,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.6",
            },
        )
        self._last_request = 0.0
        self._offer_cache: dict[str, tuple[float, Listing]] = {}
        self._location_cache: dict[str, Optional[Location]] = {}

    def close(self) -> None:
        self._http.close()

    # --- transport -----------------------------------------------------------

    def _throttle(self) -> None:
        wait = self.config.request_interval_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _request(
        self, url: str, *, params: Optional[dict[str, Any]] = None, accept: str, throttle: bool = True
    ) -> httpx2.Response:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            if throttle:
                self._throttle()
            try:
                response = self._http.get(url, params=params, headers={"Accept": accept})
            except httpx2.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = OlxError(f"OLX odpowiedział {response.status_code} dla {url}")
                elif response.status_code == 404:
                    raise OlxError(f"Nie znaleziono: {url} (404) — ogłoszenie mogło zostać usunięte.")
                elif response.status_code >= 400:
                    raise OlxError(f"OLX odpowiedział {response.status_code} dla {url}")
                else:
                    return response
            time.sleep(1.5 * (attempt + 1))
        raise OlxError(f"Nie udało się pobrać {url}: {last_error}")

    def _get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        response = self._request(f"{self.base_url}{path}", params=params, accept="application/json")
        try:
            return response.json()
        except ValueError as exc:
            raise OlxError(f"Niepoprawna odpowiedź JSON z {path}") from exc

    def download(self, url: str) -> tuple[bytes, str]:
        """Bytes and content type of `url` (photos come from a CDN, so these requests are not throttled)."""
        response = self._request(url, accept="image/webp,image/jpeg,image/png,image/*;q=0.8", throttle=False)
        content = response.content
        if len(content) > _MAX_DOWNLOAD_BYTES:
            raise OlxError(f"Plik jest za duży ({len(content) // 1024} KB): {url}")
        return content, response.headers.get("content-type", "")

    # --- locations -------------------------------------------------------------

    def resolve_location(self, name: str) -> Optional[Location]:
        key = normalize_name(name)
        if key in self._location_cache:
            return self._location_cache[key]
        location: Optional[Location] = None
        try:
            payload = self._get_json("/api/v1/geo-encoder/location-autocomplete/", {"query": name})
        except OlxError:
            payload = None
        candidates = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(candidates, list):
            best = None
            for item in candidates:
                city = item.get("city") or {}
                if city.get("id") is not None and normalize_name(str(city.get("name", ""))) == key:
                    best = item
                    break
                best = best or item
            if best:
                city, region = best.get("city") or {}, best.get("region") or {}
                district = best.get("district") or {}
                location = Location(
                    label=", ".join(str(x) for x in (city.get("name"), region.get("name")) if x) or name,
                    city_id=city.get("id"),
                    region_id=region.get("id"),
                    district_id=district.get("id"),
                )
        self._location_cache[key] = location
        return location

    # --- search ------------------------------------------------------------------

    def search(
        self,
        query: Optional[str] = None,
        *,
        category_id: Optional[int] = None,
        city: Optional[str] = None,
        radius_km: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        condition: Optional[Condition] = None,
        private_only: bool = False,
        delivery_only: bool = False,
        sort: Sort = "relevance",
        offset: int = 0,
        limit: int = 40,
        user_id: Optional[str] = None,
    ) -> SearchPage:
        limit = max(1, min(limit, _MAX_PAGE))
        offset = max(0, min(offset, _MAX_OFFSET - limit))
        params: dict[str, Any] = {"offset": offset, "limit": limit, "filter_refiners": "spell_checker"}
        notes: list[str] = []
        if query:
            params["query"] = query
        if category_id:
            params["category_id"] = category_id
        if user_id:
            params["user_id"] = user_id
        if sort in _SORT_PARAM:
            params["sort_by"] = _SORT_PARAM[sort]
        if price_min is not None:
            params["filter_float_price:from"] = int(price_min)
        if price_max is not None:
            params["filter_float_price:to"] = int(price_max)
        if condition:
            params["filter_enum_state[0]"] = condition
        if private_only:
            params["owner_type"] = "private"

        city_filter: Optional[str] = None
        if city:
            location = self.resolve_location(city)
            if location and (location.city_id or location.region_id):
                if location.city_id:
                    params["city_id"] = location.city_id
                if location.region_id:
                    params["region_id"] = location.region_id
                if location.district_id and not radius_km:
                    params["district_id"] = location.district_id
                if radius_km and location.city_id:
                    params["distance"] = radius_km
            else:
                city_filter = normalize_name(city)
                notes.append(
                    f"Nie rozpoznano lokalizacji „{city}” w OLX — wyniki filtrowane po nazwie miasta, bez promienia."
                )

        payload = self._get_json("/api/v1/offers/", params)
        raw_offers = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(raw_offers, list):
            raise OlxError("Nieoczekiwany format odpowiedzi wyszukiwania OLX.")

        listings: list[Listing] = []
        seen: set[str] = set()
        for raw in raw_offers:
            try:
                listing = parse_api_offer(raw)
            except Exception:  # one malformed offer must not break the page
                continue
            if not listing.id or listing.id in seen:
                continue
            seen.add(listing.id)
            self._offer_cache[listing.id] = (time.monotonic(), listing)
            listings.append(listing)

        # Re-check the filters locally: query parameter names are not a stable public contract.
        filtered = [
            l
            for l in listings
            if (price_min is None or l.price is None or l.price >= price_min)
            and (price_max is None or l.price is None or l.price <= price_max)
            and (condition is None or l.condition_key is None or l.condition_key == condition)
            and (not private_only or not l.is_business)
            and (not delivery_only or l.delivery_available)
            and (city_filter is None or (l.city and normalize_name(l.city) == city_filter))
        ]
        dropped = len(listings) - len(filtered)
        if dropped:
            notes.append(f"Odrzucono lokalnie {dropped} ofert niespełniających filtrów.")

        metadata = payload.get("metadata") or {}
        total = metadata.get("visible_total_count") or metadata.get("total_elements")
        has_next = bool((payload.get("links") or {}).get("next")) or len(raw_offers) >= limit
        next_offset = offset + limit if has_next and offset + limit < _MAX_OFFSET else None
        return SearchPage(listings=filtered, total=total, next_offset=next_offset, notes=notes)

    # --- offers & users ------------------------------------------------------------

    def get_offer(self, offer_id: str, *, max_age_s: float = 600) -> Listing:
        cached = self._offer_cache.get(offer_id)
        # Search results carry the full offer, but a short TTL keeps price and status fresh.
        if cached and time.monotonic() - cached[0] < max_age_s and cached[1].source == "api":
            return cached[1]
        payload = self._get_json(f"/api/v1/offers/{offer_id}/")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise OlxError(f"Nieoczekiwany format ogłoszenia {offer_id}.")
        listing = parse_api_offer(data)
        self._offer_cache[listing.id] = (time.monotonic(), listing)
        return listing

    def resolve_listing(self, ref: str) -> Listing:
        """Listing for a numeric id or an olx.pl listing URL."""
        ref = ref.strip()
        offer_id = offer_id_from_ref(ref)
        if offer_id:
            return self.get_offer(offer_id)
        if not re.match(r"https?://", ref):
            raise OlxError(f"„{ref}” nie wygląda na ID ani link do ogłoszenia OLX.")
        for _, listing in self._offer_cache.values():
            if listing.url and listing.url.split("?")[0] == ref.split("?")[0]:
                return self.get_offer(listing.id)
        page = self._request(ref, accept="text/html,application/xhtml+xml").text
        found_id = extract_offer_id_from_html(page)
        if found_id:
            try:
                return self.get_offer(found_id)
            except OlxError:
                pass
        listing = parse_listing_html(page, ref)
        if listing is None:
            raise OlxError(f"Nie udało się odczytać ogłoszenia ze strony {ref}.")
        if listing.id:
            self._offer_cache[listing.id] = (time.monotonic(), listing)
        return listing

    def get_user(self, user_id: str) -> Seller:
        payload = self._get_json(f"/api/v1/users/{user_id}/")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise OlxError(f"Nieoczekiwany format profilu sprzedawcy {user_id}.")
        return parse_api_user(data)
