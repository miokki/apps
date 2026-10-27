"""Tools exposed to Claude. Each one is a typed function; the SDK builds its JSON schema from the signature."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Optional

from anthropic.lib.tools import ToolError, beta_tool

from .analysis import (
    assess_risk,
    category_histogram,
    comparison_table,
    listing_line,
    price_stats,
    render_listing_details,
    render_price_stats,
)
from .config import Config
from .guides import GuideTopic, get_guide
from .images import ImageBudget, ImageError, PreparedImage, prepare_image
from .listing import Listing
from .olx_client import Condition, OlxClient, OlxError, Sort, normalize_name, offer_id_from_ref
from .tracker import Direction, Status, Tracker

_LOCAL_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".tif", ".tiff"}

tool = partial(beta_tool, eager_input_streaming=True)


@dataclass
class ToolContext:
    config: Config
    olx: OlxClient
    tracker: Tracker
    images: ImageBudget

    def listing(self, ref: str) -> Listing:
        try:
            return self.olx.resolve_listing(ref)
        except OlxError as exc:
            raise ToolError(str(exc)) from exc

    def listing_id(self, ref: str) -> str:
        return offer_id_from_ref(ref) or self.listing(ref).id

    def budget_note(self) -> str:
        left_mb = self.images.remaining() / (1024 * 1024)
        return f"(pozostały budżet obrazów w tej rozmowie: ~{left_mb:.1f} MB)"


def _photo_blocks(
    ctx: ToolContext, listing: Listing, indices: list[int], max_edge: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Download and prepare the given 1-based photo indices in parallel; returns content blocks and problems."""

    def fetch(index: int) -> tuple[int, PreparedImage | Exception]:
        photo = listing.photos[index - 1]
        try:
            try:
                raw, _ = ctx.olx.download(photo.url(max_edge))
            except OlxError:
                raw, _ = ctx.olx.download(photo.original_url())
            return index, prepare_image(raw, max_edge=max_edge, quality=ctx.config.jpeg_quality)
        except (OlxError, ImageError) as exc:
            return index, exc

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, indices))

    blocks: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, result in results:
        if isinstance(result, Exception):
            problems.append(f"zdjęcie {index}: {result}")
            continue
        if not ctx.images.fits(result.encoded_bytes):
            problems.append(
                f"zdjęcie {index}: pominięte — wyczerpany budżet obrazów tej rozmowy. "
                "Zaproponuj użytkownikowi /nowa (tracker zostaje zachowany)."
            )
            continue
        ctx.images.add(result.encoded_bytes)
        blocks.append({"type": "text", "text": f"Zdjęcie {index}/{len(listing.photos)} ({result.width}×{result.height} px):"})
        blocks.append(result.block())
    return blocks, problems


def _matches_words(listing: Listing, include: list[str], exclude: list[str]) -> bool:
    title = normalize_name(listing.title)
    return all(normalize_name(w) in title for w in include) and not any(normalize_name(w) in title for w in exclude)


def build_tools(ctx: ToolContext) -> list[Any]:
    @tool
    def search_listings(
        query: str,
        city: Optional[str] = None,
        radius_km: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        condition: Optional[Condition] = None,
        category_id: Optional[int] = None,
        private_only: bool = False,
        delivery_only: bool = False,
        sort: Sort = "relevance",
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Search active OLX.pl listings. Returns one compact line per listing: [id] title, price, location, condition, seller type, Przesyłka OLX availability, photo count, date, URL.

        Run several searches with different phrasings or model variants for good coverage. Results also show which category_id values appear, which helps filter out accessories or unrelated items.

        Args:
            query: Search phrase in Polish as a buyer would type it, e.g. "iphone 13 128gb".
            city: City name (e.g. "Kraków"); omit to search all of Poland.
            radius_km: Search radius around the city in km (e.g. 10, 30, 50, 100).
            price_min: Minimum price in PLN.
            price_max: Maximum price in PLN.
            condition: Item condition filter.
            category_id: OLX numeric category id (seen in earlier results).
            private_only: Only private sellers (no business accounts).
            delivery_only: Only listings with Przesyłka OLX (shipping with buyer protection).
            sort: Sort order.
            limit: Number of results (1-50).
            offset: Pagination offset (use the value suggested in the previous result).
        """
        try:
            page = ctx.olx.search(
                query,
                city=city,
                radius_km=radius_km,
                price_min=price_min,
                price_max=price_max,
                condition=condition,
                category_id=category_id,
                private_only=private_only,
                delivery_only=delivery_only,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        except OlxError as exc:
            raise ToolError(str(exc)) from exc
        header = f"Wyniki dla „{query}”: {len(page.listings)} ofert na tej stronie"
        if page.total is not None:
            header += f" (łącznie w OLX: ~{page.total})"
        lines = [header, *page.notes]
        if not page.listings:
            lines.append("Brak wyników — spróbuj krótszej frazy, synonimów albo szerszych filtrów.")
        lines += [listing_line(l, i) for i, l in enumerate(page.listings, start=offset + 1)]
        hist = category_histogram(page.listings)
        if hist:
            lines.append(hist)
        if page.next_offset is not None:
            lines.append(f"Kolejna strona: offset={page.next_offset}")
        return "\n".join(lines)

    @tool
    def get_listing(listing: str, market_median: Optional[float] = None) -> str:
        """Full details of one listing: description text, all parameters, price history, seller account (age, last activity, business or private), location, delivery and automatic risk signals.

        Always call this before judging or recommending a listing. Then look at its photos with view_listing_photos.

        Args:
            listing: Listing id (digits) or full olx.pl listing URL.
            market_median: Median price of comparable listings (from market_price_stats), if known; enables a price-versus-market signal.
        """
        item = ctx.listing(listing)
        return render_listing_details(item, assess_risk(item, reference_price=market_median))

    @tool
    def view_listing_photos(listing: str, photos: Optional[list[int]] = None, max_photos: int = 8) -> list[dict[str, Any]]:
        """Look at a listing's photos (returned as images you can see). Use it to verify the condition, authenticity and completeness of the item, read labels/screens/serial plates, and check that the photos match the description.

        Args:
            listing: Listing id (digits) or full olx.pl listing URL.
            photos: 1-based photo numbers to view (e.g. [1, 4, 5]); omit to view the first `max_photos`.
            max_photos: How many photos to view when `photos` is omitted (1-12).
        """
        item = ctx.listing(listing)
        if not item.photos:
            return [{"type": "text", "text": f"Ogłoszenie {item.id} nie ma zdjęć."}]
        total = len(item.photos)
        if photos:
            wanted = [p for p in dict.fromkeys(photos) if 1 <= p <= total]
            if not wanted:
                raise ToolError(f"Ogłoszenie ma {total} zdjęć; podaj numery od 1 do {total}.")
        else:
            wanted = list(range(1, min(total, max(1, min(max_photos, 12))) + 1))
        blocks, problems = _photo_blocks(ctx, item, wanted, ctx.config.image_max_edge)
        intro = (
            f"Ogłoszenie [{item.id}] „{item.title}” — {item.price_text()}; stan wg sprzedawcy: "
            f"{item.condition or 'nie podano'}. Pokazuję zdjęcia {', '.join(map(str, wanted))} z {total}. "
            f"Szczegóły możesz przybliżyć narzędziem zoom_listing_photo. {ctx.budget_note()}"
        )
        result: list[dict[str, Any]] = [{"type": "text", "text": intro}, *blocks]
        if problems:
            result.append({"type": "text", "text": "Problemy: " + "; ".join(problems)})
        if not blocks:
            raise ToolError(result)
        return result

    @tool
    def zoom_listing_photo(
        listing: str, photo: int, left: float = 0.0, top: float = 0.0, right: float = 1.0, bottom: float = 1.0
    ) -> list[dict[str, Any]]:
        """Zoom into a region of one listing photo at the highest available resolution, e.g. to read a label, serial number, battery-health screen or odometer, or to inspect a scratch, crack, stain or rust spot.

        Coordinates are fractions of the photo's width/height (0 = left/top edge, 1 = right/bottom edge). With the defaults it returns the whole photo in high resolution.

        Args:
            listing: Listing id (digits) or full olx.pl listing URL.
            photo: 1-based photo number.
            left: Left edge of the region (0-1).
            top: Top edge of the region (0-1).
            right: Right edge of the region (0-1).
            bottom: Bottom edge of the region (0-1).
        """
        item = ctx.listing(listing)
        if not 1 <= photo <= len(item.photos):
            raise ToolError(f"Ogłoszenie ma {len(item.photos)} zdjęć; podaj numer od 1 do {len(item.photos)}.")
        target = item.photos[photo - 1]
        try:
            raw, _ = ctx.olx.download(target.original_url())
            prepared = prepare_image(
                raw, max_edge=ctx.config.zoom_max_edge, quality=90, crop=(left, top, right, bottom)
            )
        except (OlxError, ImageError) as exc:
            raise ToolError(f"Nie udało się przybliżyć zdjęcia {photo}: {exc}") from exc
        if not ctx.images.fits(prepared.encoded_bytes):
            raise ToolError("Wyczerpany budżet obrazów tej rozmowy. Zaproponuj użytkownikowi /nowa (tracker zostaje).")
        ctx.images.add(prepared.encoded_bytes)
        return [
            {
                "type": "text",
                "text": f"Zdjęcie {photo}/{len(item.photos)} ogłoszenia [{item.id}], obszar "
                f"x {left:.2f}–{right:.2f}, y {top:.2f}–{bottom:.2f} (oryginał {prepared.source_width}×"
                f"{prepared.source_height} px, wycinek {prepared.width}×{prepared.height} px). {ctx.budget_note()}",
            },
            prepared.block(),
        ]

    @tool
    def view_image(
        source: str, left: float = 0.0, top: float = 0.0, right: float = 1.0, bottom: float = 1.0
    ) -> list[dict[str, Any]]:
        """Look at an image given by the user: a local file path or an http(s) URL, e.g. extra photos or screenshots the seller sent in chat, a receipt/invoice, a screenshot of a listing. Optionally zoom into a region (fractions 0-1).

        Args:
            source: Local image path (jpg/png/webp/...) or http(s) URL of an image.
            left: Left edge of the region (0-1).
            top: Top edge of the region (0-1).
            right: Right edge of the region (0-1).
            bottom: Bottom edge of the region (0-1).
        """
        crop = None if (left, top, right, bottom) == (0.0, 0.0, 1.0, 1.0) else (left, top, right, bottom)
        try:
            if re.match(r"https?://", source):
                raw, _ = ctx.olx.download(source)
            else:
                path = Path(source).expanduser()
                if path.suffix.lower() not in _LOCAL_IMAGE_SUFFIXES:
                    raise ToolError(f"{path.name}: obsługiwane są tylko pliki graficzne ({', '.join(sorted(_LOCAL_IMAGE_SUFFIXES))}).")
                if not path.is_file():
                    raise ToolError(f"Nie znaleziono pliku: {path}")
                raw = path.read_bytes()
            max_edge = ctx.config.zoom_max_edge if crop else ctx.config.image_max_edge
            prepared = prepare_image(raw, max_edge=max_edge, quality=ctx.config.jpeg_quality, crop=crop)
        except (OlxError, ImageError, OSError) as exc:
            raise ToolError(f"Nie udało się wczytać obrazu: {exc}") from exc
        if not ctx.images.fits(prepared.encoded_bytes):
            raise ToolError("Wyczerpany budżet obrazów tej rozmowy. Zaproponuj użytkownikowi /nowa (tracker zostaje).")
        ctx.images.add(prepared.encoded_bytes)
        return [
            {"type": "text", "text": f"Obraz {source} ({prepared.width}×{prepared.height} px). {ctx.budget_note()}"},
            prepared.block(),
        ]

    @tool
    def market_price_stats(
        query: str,
        condition: Optional[Condition] = None,
        city: Optional[str] = None,
        radius_km: Optional[int] = None,
        category_id: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        title_must_include: Optional[list[str]] = None,
        title_must_exclude: Optional[list[str]] = None,
        sample_size: int = 120,
    ) -> str:
        """Market price benchmark from many comparable active listings: median, typical range (P25-P75), P10/P90, breakdown by condition, cheapest and newest offers. Use it to judge whether a price is fair and to anchor negotiations. These are asking prices, not transaction prices.

        Make the sample comparable: same model/variant, use title_must_include for key variant words (e.g. ["128"]) and title_must_exclude for noise (e.g. ["etui", "szkło", "uszkodzony"]).

        Args:
            query: Search phrase for comparable items.
            condition: Restrict to one condition.
            city: Optional city to restrict the market (default: whole Poland).
            radius_km: Radius around the city in km.
            category_id: OLX category id to restrict to.
            price_min: Ignore listings below this price (PLN).
            price_max: Ignore listings above this price (PLN).
            title_must_include: Words that must all appear in the title (case/diacritics-insensitive).
            title_must_exclude: Listings whose title contains any of these words are skipped.
            sample_size: How many listings to sample (20-300).
        """
        sample_size = max(20, min(sample_size, 300))
        include, exclude = title_must_include or [], title_must_exclude or []
        collected: dict[str, Listing] = {}
        offset: Optional[int] = 0
        notes: list[str] = []
        scanned = 0
        try:
            while offset is not None and scanned < sample_size:
                page = ctx.olx.search(
                    query,
                    city=city,
                    radius_km=radius_km,
                    price_min=price_min,
                    price_max=price_max,
                    condition=condition,
                    category_id=category_id,
                    limit=50,
                    offset=offset,
                )
                notes += [n for n in page.notes if n not in notes and not n.startswith("Odrzucono")]
                scanned += 50
                for l in page.listings:
                    if _matches_words(l, include, exclude):
                        collected[l.id] = l
                offset = page.next_offset
        except OlxError as exc:
            if not collected:
                raise ToolError(str(exc)) from exc
            notes.append(f"Przerwano pobieranie po błędzie: {exc}")

        listings = list(collected.values())
        stats = price_stats(listings)
        if stats is None:
            raise ToolError("Brak porównywalnych ofert z ceną — poszerz zapytanie lub złagodź filtry słów.")
        in_range = sorted(
            (l for l in listings if l.price is not None and stats.minimum <= l.price <= stats.maximum),
            key=lambda l: l.price or 0,
        )
        newest = sorted((l for l in listings if l.created_at), key=lambda l: l.created_at, reverse=True)[:3]
        delivery = sum(1 for l in listings if l.delivery_available)
        lines = [
            f"Rynek dla „{query}”"
            + (f", stan={condition}" if condition else "")
            + (f", słowa+={include}" if include else "")
            + (f", słowa-={exclude}" if exclude else ""),
            *notes,
            render_price_stats(stats),
            f"Z Przesyłką OLX: {delivery} z {len(listings)}.",
            "Najtańsze (po odrzuceniu odstających):",
            *[listing_line(l) for l in in_range[:5]],
            "Najnowsze:",
            *[listing_line(l) for l in newest],
            "Uwaga: to ceny wywoławcze; realne ceny transakcyjne są zwykle nieco niższe.",
        ]
        return "\n".join(lines)

    @tool
    def get_seller_profile(user_id: str) -> str:
        """Seller account details (name, account creation date, last activity, business or private) and their other active listings. Useful for spotting resellers posing as private sellers, brand-new scam accounts, or bundle-deal opportunities.

        Args:
            user_id: Seller's user_id (shown by get_listing).
        """
        try:
            seller = ctx.olx.get_user(user_id)
        except OlxError as exc:
            raise ToolError(str(exc)) from exc
        age = seller.account_age_days()
        account_type = "prywatne"
        if seller.is_business:
            account_type = f"firmowe ({seller.company_name})" if seller.company_name else "firmowe"
        lines = [
            f"Sprzedawca: {seller.name or '?'} (user_id={user_id})",
            f"Typ konta: {account_type}",
            f"Na OLX od: {seller.created:%Y-%m-%d} ({age} dni)" if seller.created else "Na OLX od: ?",
            f"Ostatnio aktywny: {seller.last_seen:%Y-%m-%d %H:%M}" if seller.last_seen else "Ostatnio aktywny: ?",
        ]
        if seller.about:
            lines.append(f"Opis profilu (dane od sprzedawcy): {seller.about[:500]}")
        try:
            page = ctx.olx.search(None, user_id=user_id, limit=25, sort="newest")
            total = page.total if page.total is not None else len(page.listings)
            lines.append(f"Inne aktywne ogłoszenia: {total}")
            lines += [listing_line(l) for l in page.listings]
        except OlxError as exc:
            lines.append(f"Nie udało się pobrać innych ogłoszeń: {exc}")
        return "\n".join(lines)

    @tool
    def compare_listings(listings: list[str], market_median: Optional[float] = None) -> str:
        """Side-by-side comparison table of 2-8 listings (price, versus market, condition, location, delivery, seller account age, days listed, photos, all parameters, risk-signal counts) plus each listing's risk signals and a description excerpt.

        Args:
            listings: Listing ids or olx.pl URLs to compare (2-8).
            market_median: Median market price of comparable items (from market_price_stats), if known.
        """
        refs = list(dict.fromkeys(listings))
        if not 2 <= len(refs) <= 8:
            raise ToolError("Podaj od 2 do 8 różnych ogłoszeń.")
        items = [ctx.listing(ref) for ref in refs]
        risks = [assess_risk(l, reference_price=market_median) for l in items]
        lines = [comparison_table(items, risks, reference_price=market_median), "", "Sygnały i fragmenty opisów:"]
        for item, risk in zip(items, risks):
            excerpt = item.description[:350].replace("\n", " ")
            lines += [f"[{item.id}] {item.title}", risk.render(), f"Opis: {excerpt}{'…' if len(item.description) > 350 else ''}", ""]
        lines.append("Stan wizualny oceniaj po obejrzeniu zdjęć (view_listing_photos) — tabela go nie obejmuje.")
        return "\n".join(lines)

    @tool
    def buying_guide(topic: GuideTopic) -> str:
        """Curated checklist for a product category or a stage of the purchase: what to verify in photos, questions for the seller, in-person inspection steps, typical scams, delivery and paperwork.

        Args:
            topic: Category or stage of the purchase.
        """
        return get_guide(topic)

    @tool
    def track_listing(
        listing: str,
        status: Optional[Status] = None,
        note: Optional[str] = None,
        my_offer: Optional[float] = None,
        agreed_price: Optional[float] = None,
    ) -> str:
        """Add a listing to the user's persistent purchase tracker or update it: status of the purchase process, notes (e.g. findings from photos, seller answers), the user's latest offer and the agreed price. Persists across sessions.

        Args:
            listing: Listing id (digits) or full olx.pl listing URL.
            status: New status in the purchase process.
            note: Short note to append.
            my_offer: The user's current offer in PLN.
            agreed_price: Price agreed with the seller in PLN.
        """
        try:
            item = ctx.olx.resolve_listing(listing)
            listing_id, title, url, price = item.id, item.title, item.url, item.price
        except OlxError:
            listing_id = offer_id_from_ref(listing)
            if not listing_id:
                raise ToolError("Nie udało się ustalić ID ogłoszenia — podaj numeryczne ID.") from None
            title = url = price = None
        entry = ctx.tracker.upsert(
            listing_id,
            title=title,
            url=url,
            asking_price=price,
            status=status,
            note=note,
            my_offer=my_offer,
            agreed_price=agreed_price,
        )
        return f"Zapisano. {ctx.tracker.render_item(entry['listing_id'])}"

    @tool
    def log_conversation(listing: str, direction: Direction, text: str, price: Optional[float] = None) -> str:
        """Record a message in the negotiation log of a tracked listing: a message the user sent (or will send) to the seller, or the seller's reply pasted by the user. Returns the full conversation so far.

        Args:
            listing: Listing id (digits) or olx.pl URL.
            direction: "to_seller" for the user's message, "from_seller" for the seller's reply.
            text: Message text, verbatim.
            price: Price amount proposed in this message, if any (PLN).
        """
        listing_id = ctx.listing_id(listing)
        if ctx.tracker.get(listing_id) is None:
            try:
                item = ctx.olx.resolve_listing(listing_id)
                ctx.tracker.upsert(listing_id, title=item.title, url=item.url, asking_price=item.price)
            except OlxError:
                pass
        ctx.tracker.log_message(listing_id, direction, text, price)
        return ctx.tracker.render_item(listing_id)

    @tool
    def show_tracker(listing: Optional[str] = None) -> str:
        """Show the purchase tracker: buyer preferences and all tracked listings with status and offers, or the full notes and negotiation log of one listing.

        Args:
            listing: Listing id to show in detail; omit for the overview.
        """
        if listing:
            return ctx.tracker.render_item(ctx.listing_id(listing))
        return ctx.tracker.render_summary()

    @tool
    def remember_preferences(text: str) -> str:
        """Persist a durable buyer preference or constraint (budget, location, must-haves, deal-breakers, preferred delivery) so it is available in future sessions.

        Args:
            text: The preference, stated concisely in the user's language.
        """
        ctx.tracker.add_preference(text)
        return "Zapamiętano. Aktualne preferencje:\n" + "\n".join(f"- {p}" for p in ctx.tracker.preferences())

    return [
        search_listings,
        get_listing,
        view_listing_photos,
        zoom_listing_photo,
        view_image,
        market_price_stats,
        get_seller_profile,
        compare_listings,
        buying_guide,
        track_listing,
        log_conversation,
        show_tracker,
        remember_preferences,
    ]

