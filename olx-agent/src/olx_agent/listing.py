"""Normalized listing model and parsers for OLX API payloads and listing-page HTML."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Photo:
    url_template: str
    width: Optional[int] = None
    height: Optional[int] = None

    def url(self, max_edge: int) -> str:
        """URL of the photo scaled by the CDN to fit a `max_edge` box (OLX links carry `{width}x{height}`)."""
        if "{width}" not in self.url_template and "{height}" not in self.url_template:
            return self.url_template
        w, h = self._fit(max_edge)
        return self.url_template.replace("{width}", str(w)).replace("{height}", str(h))

    def original_url(self) -> str:
        if self.width and self.height:
            return self.url_template.replace("{width}", str(self.width)).replace("{height}", str(self.height))
        return self.url(4000)

    def _fit(self, max_edge: int) -> tuple[int, int]:
        if not self.width or not self.height:
            return max_edge, max_edge
        scale = min(1.0, max_edge / max(self.width, self.height))
        return max(1, round(self.width * scale)), max(1, round(self.height * scale))


@dataclass
class Seller:
    id: Optional[str] = None
    name: Optional[str] = None
    created: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_business: bool = False
    company_name: Optional[str] = None
    about: Optional[str] = None
    other_ads_enabled: bool = False

    def account_age_days(self, now: Optional[datetime] = None) -> Optional[int]:
        if not self.created:
            return None
        now = now or datetime.now(timezone.utc)
        return max(0, (now - self.created).days)


@dataclass
class Listing:
    id: str
    title: str
    url: str = ""
    description: str = ""
    price: Optional[float] = None
    currency: Optional[str] = None
    price_label: Optional[str] = None
    negotiable: bool = False
    previous_price: Optional[float] = None
    condition_key: Optional[str] = None
    condition: Optional[str] = None
    params: list[tuple[str, str]] = field(default_factory=list)
    city: Optional[str] = None
    district: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    created_at: Optional[datetime] = None
    refreshed_at: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    category_id: Optional[int] = None
    delivery_available: bool = False
    is_business: bool = False
    promoted: bool = False
    status: Optional[str] = None
    seller: Seller = field(default_factory=Seller)
    photos: list[Photo] = field(default_factory=list)
    source: str = "api"

    @property
    def location(self) -> str:
        parts = [p for p in (self.city, self.district) if p]
        loc = ", ".join(parts)
        if self.region:
            loc = f"{loc} ({self.region})" if loc else self.region
        return loc or "?"

    def price_text(self) -> str:
        if self.price is None:
            return self.price_label or "brak ceny"
        amount = f"{self.price:,.0f}".replace(",", " ")
        text = f"{amount} {self.currency or 'PLN'}"
        if self.negotiable:
            text += " (do negocjacji)"
        if self.previous_price and self.previous_price != self.price:
            prev = f"{self.previous_price:,.0f}".replace(",", " ")
            text += f", wcześniej {prev}"
        return text

    def days_listed(self, now: Optional[datetime] = None) -> Optional[int]:
        if not self.created_at:
            return None
        now = now or datetime.now(timezone.utc)
        return max(0, (now - self.created_at).days)


# --- helpers -----------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*(br|/p|/li|/div|/h\d)\s*/?\s*>", re.IGNORECASE)


def html_to_text(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d,.]", "", value).replace(",", ".")
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def _param_value_label(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("label", "value", "key"):
            v = value.get(key)
            if v not in (None, ""):
                return str(v)
        return ""
    if isinstance(value, list):
        return ", ".join(_param_value_label(v) for v in value)
    return "" if value is None else str(value)


# --- API payload -------------------------------------------------------------


def parse_api_offer(data: dict[str, Any]) -> Listing:
    """Build a Listing from an offer object of `GET /api/v1/offers/...`."""
    listing = Listing(id=str(data.get("id", "")), title=str(data.get("title") or "").strip(), url=data.get("url") or "")
    listing.description = html_to_text(data.get("description"))
    listing.created_at = parse_dt(data.get("created_time"))
    listing.refreshed_at = parse_dt(data.get("last_refresh_time") or data.get("pushup_time"))
    listing.valid_to = parse_dt(data.get("valid_to_time"))
    listing.status = data.get("status")
    listing.is_business = bool(data.get("business"))
    listing.category_id = _get(data, "category", "id")

    promo = data.get("promotion") or {}
    listing.promoted = bool(promo.get("top_ad") or promo.get("highlighted") or promo.get("urgent"))

    for param in data.get("params") or []:
        key = param.get("key")
        value = param.get("value")
        if key == "price" or param.get("type") == "price":
            value = value or {}
            listing.price = _num(value.get("value"))
            listing.currency = value.get("currency") or "PLN"
            listing.negotiable = bool(value.get("negotiable"))
            listing.price_label = value.get("label")
            listing.previous_price = _num(value.get("previous_value"))
            continue
        label = _param_value_label(value)
        if key == "state":
            listing.condition_key = value.get("key") if isinstance(value, dict) else None
            listing.condition = label or None
        name = param.get("name") or key or "?"
        if label:
            listing.params.append((str(name), label))

    loc = data.get("location") or {}
    listing.city = _get(loc, "city", "name")
    listing.district = _get(loc, "district", "name")
    listing.region = _get(loc, "region", "name")
    map_ = data.get("map") or {}
    listing.lat = _num(map_.get("lat"))
    listing.lon = _num(map_.get("lon"))

    listing.delivery_available = bool(_get(data, "delivery", "rock", "active"))

    user = data.get("user") or {}
    listing.seller = Seller(
        id=str(user["id"]) if user.get("id") is not None else None,
        name=user.get("name"),
        created=parse_dt(user.get("created")),
        last_seen=parse_dt(user.get("last_seen")),
        is_business=listing.is_business or bool(user.get("company_name")),
        company_name=user.get("company_name") or None,
        about=html_to_text(user.get("about")) or None,
        other_ads_enabled=bool(user.get("other_ads_enabled")),
    )

    for photo in data.get("photos") or []:
        link = photo.get("link")
        if link:
            listing.photos.append(Photo(url_template=link, width=photo.get("width"), height=photo.get("height")))
    return listing


def parse_api_user(data: dict[str, Any]) -> Seller:
    return Seller(
        id=str(data["id"]) if data.get("id") is not None else None,
        name=data.get("name"),
        created=parse_dt(data.get("created")),
        last_seen=parse_dt(data.get("last_seen")),
        is_business=bool(data.get("company_name") or data.get("b2c_business_page")),
        company_name=data.get("company_name") or None,
        about=html_to_text(data.get("about")) or None,
        other_ads_enabled=bool(data.get("other_ads_enabled")),
    )


# --- listing page HTML (fallback) --------------------------------------------

_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_ID_PATTERNS = [
    re.compile(r'"sku"\s*:\s*"?(\d{6,})'),
    re.compile(r'\\?"ad_id\\?"\s*:\s*\\?"?(\d{6,})'),
    re.compile(r"\bID:\s*(\d{6,})"),
]


def extract_offer_id_from_html(page: str) -> Optional[str]:
    for pattern in _ID_PATTERNS:
        match = pattern.search(page)
        if match:
            return match.group(1)
    return None


def _iter_ld_objects(page: str):
    for block in _LD_JSON_RE.findall(page):
        try:
            payload = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            obj = stack.pop(0)
            if isinstance(obj, dict):
                yield obj
                graph = obj.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)


def parse_listing_html(page: str, url: str) -> Optional[Listing]:
    """Minimal listing parsed from schema.org Product JSON-LD, used when the API is unavailable."""
    product = next((o for o in _iter_ld_objects(page) if o.get("@type") == "Product"), None)
    if product is None:
        return None
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    images = product.get("image") or []
    if isinstance(images, str):
        images = [images]
    listing = Listing(
        id=str(product.get("sku") or extract_offer_id_from_html(page) or ""),
        title=str(product.get("name") or "").strip(),
        url=url,
        description=html_to_text(product.get("description")),
        price=_num(offers.get("price")),
        currency=offers.get("priceCurrency"),
        photos=[Photo(url_template=u) for u in images if isinstance(u, str)],
        source="html",
    )
    condition = str(product.get("itemCondition") or offers.get("itemCondition") or "")
    if "Used" in condition:
        listing.condition_key, listing.condition = "used", "Używane"
    elif "New" in condition:
        listing.condition_key, listing.condition = "new", "Nowe"
    elif "Damaged" in condition:
        listing.condition_key, listing.condition = "damaged", "Uszkodzone"
    area = _get(offers, "areaServed", "name")
    if isinstance(area, str):
        listing.city = area
    return listing
