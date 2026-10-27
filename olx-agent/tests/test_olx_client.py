import pytest

from olx_agent.olx_client import OlxError, normalize_name

from conftest import load_offer, make_offer


def test_search_sends_filters_and_rechecks_them_locally(olx, fake_olx):
    fake_olx.locations["Kraków"] = [
        {"city": {"id": 8959, "name": "Kraków"}, "region": {"id": 4, "name": "Małopolskie"}, "district": None}
    ]
    fake_olx.search_pages.append(
        {
            "data": [
                make_offer(1, "iPhone 13 ok", 1800, condition="used"),
                make_offer(2, "iPhone 13 za drogi", 2600, condition="used"),  # above price_max
                make_offer(3, "iPhone 13 nowy", 1700, condition="new"),  # wrong condition
                make_offer(4, "iPhone 13 firma", 1750, condition="used", business=True),  # business
                make_offer(1, "duplicate of 1", 1800, condition="used"),
            ],
            "metadata": {"visible_total_count": 321},
            "links": {"next": {"href": "..."}},
        }
    )

    page = olx.search(
        "iphone 13", city="Kraków", radius_km=30, price_max=2000, condition="used", private_only=True,
        sort="price_asc", limit=20,
    )

    params = fake_olx.search_params()[0]
    assert params["query"] == "iphone 13"
    assert params["city_id"] == "8959" and params["region_id"] == "4" and params["distance"] == "30"
    assert params["filter_float_price:to"] == "2000"
    assert params["filter_enum_state[0]"] == "used"
    assert params["sort_by"] == "filter_float_price:asc"
    assert params["owner_type"] == "private"
    assert [l.id for l in page.listings] == ["1"]
    assert page.total == 321
    assert page.next_offset == 20
    assert any("Odrzucono lokalnie 3" in n for n in page.notes)


def test_search_falls_back_to_city_name_filter_when_location_unknown(olx, fake_olx):
    fake_olx.search_pages.append(
        {
            "data": [
                make_offer(1, "a", 100, location={"city": {"name": "Łódź"}, "region": {"name": "Łódzkie"}}),
                make_offer(2, "b", 100, location={"city": {"name": "Kraków"}, "region": {"name": "Małopolskie"}}),
            ]
        }
    )
    page = olx.search("x", city="lodz")
    assert [l.id for l in page.listings] == ["1"]
    assert "city_id" not in fake_olx.search_params()[0]
    assert any("Nie rozpoznano lokalizacji" in n for n in page.notes)


def test_get_offer_retries_transient_errors_and_caches(olx, fake_olx):
    fake_olx.offers["912345678"] = load_offer()
    fake_olx.fail_next = [503]

    first = olx.get_offer("912345678")
    second = olx.get_offer("912345678")

    assert first is second
    offer_calls = [r for r in fake_olx.requests if r.url.path == "/api/v1/offers/912345678/"]
    assert len(offer_calls) == 2  # one 503 + one success, then served from cache


def test_missing_offer_raises_readable_error(olx):
    with pytest.raises(OlxError, match="404"):
        olx.get_offer("111111111")


def test_resolve_listing_from_url_reads_id_from_page_then_uses_api(olx, fake_olx):
    fake_olx.offers["912345678"] = load_offer()
    fake_olx.pages["/d/oferta/iphone-CID99-IDabc.html"] = '<script type="application/ld+json">{"@type":"Product","sku":"912345678"}</script>'

    listing = olx.resolve_listing("https://www.olx.pl/d/oferta/iphone-CID99-IDabc.html")

    assert listing.id == "912345678" and listing.source == "api"


def test_resolve_listing_falls_back_to_html_when_api_fails(olx, fake_olx):
    fake_olx.pages["/d/oferta/rower-CID767-IDx.html"] = (
        '<script type="application/ld+json">{"@type":"Product","name":"Rower","sku":"555555555",'
        '"offers":{"price":"900","priceCurrency":"PLN"}}</script>'
    )
    listing = olx.resolve_listing("https://www.olx.pl/d/oferta/rower-CID767-IDx.html")
    assert listing.source == "html" and listing.price == 900 and listing.id == "555555555"


def test_resolve_listing_rejects_garbage(olx):
    with pytest.raises(OlxError):
        olx.resolve_listing("iphone")


def test_normalize_name_strips_polish_diacritics():
    assert normalize_name("Łódź") == normalize_name("lodz") == "lodz"
    assert normalize_name("Kraków") == "krakow"
