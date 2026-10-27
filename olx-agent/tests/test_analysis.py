from datetime import datetime, timedelta, timezone

from olx_agent.analysis import assess_risk, comparison_table, percentile, price_stats
from olx_agent.listing import Listing, Photo, Seller, parse_api_offer

from conftest import load_offer, make_offer

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def _priced(*prices, condition="Używane"):
    return [Listing(id=str(i), title="x", price=p, condition=condition) for i, p in enumerate(prices)]


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.9) == 10


def test_price_stats_drops_accessories_and_extremes():
    listings = _priced(1700, 1800, 1850, 1900, 1950, 2000, 2050, 2100, 89, 120, 9999)
    stats = price_stats(listings)

    assert stats.count_all == 11
    assert stats.excluded_low == 2 and stats.excluded_high == 1
    assert stats.minimum == 1700 and stats.maximum == 2100
    assert stats.median == 1925


def test_price_stats_keeps_small_samples_untouched():
    stats = price_stats(_priced(100, 5000))
    assert stats.count == 2 and stats.excluded_low == 0


def test_risk_flags_offplatform_contact_new_account_and_low_price():
    listing = Listing(
        id="1",
        title="iPhone 15 Pro nowy",
        description="Kontakt tylko WhatsApp +48 600 700 800, wysyłka po zaliczce",
        price=1500,
        photos=[Photo("u")],
        seller=Seller(created=NOW - timedelta(days=3)),
    )
    report = assess_risk(listing, reference_price=4000, now=NOW)
    messages = " ".join(m for _, m in report.signals)

    assert report.high_count() >= 4
    assert "WhatsApp" in messages
    assert "zaliczkę" in messages
    assert "3 dni temu" in messages
    assert "mediany" in messages
    assert "Tylko jedno zdjęcie" in messages


def test_risk_positives_for_solid_listing():
    report = assess_risk(parse_api_offer(load_offer()), reference_price=2000, now=NOW)
    assert report.high_count() == 0
    assert any("Przesyłka OLX" in p for p in report.positives)
    assert any("paragon" in p for p in report.positives)
    assert any("od 10 lat" in p for p in report.positives)


def test_comparison_table_has_column_per_listing_and_param_rows():
    a = parse_api_offer(load_offer())
    b = parse_api_offer(make_offer(2, "iPhone 13 drugi", 1700))
    table = comparison_table([a, b], [assess_risk(a, now=NOW), assess_risk(b, now=NOW)], reference_price=1800, now=NOW)
    lines = table.splitlines()

    assert lines[0] == "| Cecha | [912345678] | [2] |"
    assert any(line.startswith("| vs mediana | +6% | -6% |") for line in lines)
    assert any(line.startswith("| Wbudowana pamięć | 128 GB | 128 GB |") for line in lines)
