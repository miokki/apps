from datetime import datetime, timezone

from olx_agent.listing import Photo, extract_offer_id_from_html, html_to_text, parse_api_offer, parse_listing_html

from conftest import load_offer


def test_parse_api_offer_maps_all_key_fields():
    listing = parse_api_offer(load_offer())

    assert listing.id == "912345678"
    assert listing.title == "iPhone 13 128GB Midnight, bateria 87%"
    assert listing.price == 1900
    assert listing.currency == "PLN"
    assert listing.negotiable is True
    assert listing.previous_price == 2100
    assert listing.condition_key == "used" and listing.condition == "Używane"
    assert ("Wbudowana pamięć", "128 GB") in listing.params
    assert listing.city == "Kraków" and listing.district == "Krowodrza" and listing.region == "Małopolskie"
    assert listing.delivery_available is True
    assert listing.is_business is False
    assert listing.category_id == 1689
    assert listing.seller.id == "1234567"
    assert listing.seller.created == datetime(2016, 5, 1, 8, 0, tzinfo=timezone.utc)
    assert len(listing.photos) == 3
    assert "Kondycja baterii 87%" in listing.description
    assert "<br" not in listing.description and "&amp;" not in listing.description
    assert listing.price_text() == "1 900 PLN (do negocjacji), wcześniej 2 100"


def test_html_to_text_handles_breaks_and_entities():
    assert html_to_text("a<br />b<br/><br/><br/>c &quot;x&quot;<p>p</p>") == 'a\nb\n\nc "x"p'


def test_photo_url_fits_box_and_keeps_aspect():
    photo = Photo("https://cdn/x/image;s={width}x{height}", width=3000, height=4000)
    assert photo.url(1000) == "https://cdn/x/image;s=750x1000"
    assert photo.original_url() == "https://cdn/x/image;s=3000x4000"
    assert Photo("https://cdn/plain.jpg").url(1000) == "https://cdn/plain.jpg"


def test_parse_listing_html_from_json_ld():
    page = """<html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Rower Kross",
    "description":"Rower w dobrym stanie<br>rama M","sku":"887766554","image":["https://cdn/a.jpg","https://cdn/b.jpg"],
    "itemCondition":"https://schema.org/UsedCondition",
    "offers":{"@type":"Offer","price":"1450","priceCurrency":"PLN","areaServed":{"name":"Gdańsk"}}}</script>
    </head></html>"""
    listing = parse_listing_html(page, "https://www.olx.pl/d/oferta/rower-CID767-IDx.html")

    assert listing is not None
    assert listing.id == "887766554"
    assert listing.title == "Rower Kross"
    assert listing.price == 1450 and listing.currency == "PLN"
    assert listing.condition_key == "used"
    assert listing.city == "Gdańsk"
    assert [p.url(800) for p in listing.photos] == ["https://cdn/a.jpg", "https://cdn/b.jpg"]
    assert listing.source == "html"


def test_extract_offer_id_from_html_variants():
    assert extract_offer_id_from_html('{"sku":"123456789"}') == "123456789"
    assert extract_offer_id_from_html('<span>ID: 987654321</span>') == "987654321"
    assert extract_offer_id_from_html("nothing here") is None
