import base64
import io

import pytest
from anthropic.lib.tools import ToolError
from PIL import Image

from olx_agent.images import ImageBudget
from olx_agent.tools import ToolContext, build_tools
from olx_agent.tracker import Tracker

from conftest import jpeg_bytes, load_offer, make_offer


@pytest.fixture
def tools(config, olx, fake_olx):
    fake_olx.offers["912345678"] = load_offer()
    ctx = ToolContext(config, olx, Tracker(config.state_path), ImageBudget(config.image_budget_bytes))
    by_name = {t.name: t for t in build_tools(ctx)}
    by_name["_ctx"] = ctx
    return by_name


def _images(blocks):
    return [b for b in blocks if b["type"] == "image"]


def test_view_listing_photos_returns_viewable_image_blocks(tools, fake_olx):
    blocks = tools["view_listing_photos"].call({"listing": "912345678"})

    images = _images(blocks)
    assert len(images) == 3
    for image in images:
        assert image["source"]["media_type"] == "image/jpeg"
        decoded = Image.open(io.BytesIO(base64.b64decode(image["source"]["data"])))
        assert max(decoded.size) <= 1024
    texts = [b["text"] for b in blocks if b["type"] == "text"]
    assert "iPhone 13 128GB" in texts[0] and "zdjęcia 1, 2, 3 z 3" in texts[0]
    assert texts[1].startswith("Zdjęcie 1/3")
    cdn_urls = [str(r.url) for r in fake_olx.requests if "olxcdn" in r.url.host]
    assert any("image;s=768x1024" in u for u in cdn_urls)  # 1200x1600 fitted into 1024
    assert tools["_ctx"].images.used > 0


def test_view_listing_photos_selected_and_out_of_range(tools):
    blocks = tools["view_listing_photos"].call({"listing": "912345678", "photos": [2, 2, 9]})
    assert len(_images(blocks)) == 1
    with pytest.raises(ToolError, match="od 1 do 3"):
        tools["view_listing_photos"].call({"listing": "912345678", "photos": [7]})


def test_photo_budget_is_enforced(tools):
    tools["_ctx"].images.limit = 1
    with pytest.raises(ToolError) as err:
        tools["view_listing_photos"].call({"listing": "912345678"})
    assert "budżet" in str(err.value)


def test_zoom_crops_original_resolution(tools, fake_olx):
    fake_olx.photo = jpeg_bytes((1600, 1200))
    blocks = tools["zoom_listing_photo"].call(
        {"listing": "912345678", "photo": 2, "left": 0, "top": 0, "right": 0.25, "bottom": 0.25}
    )
    img = Image.open(io.BytesIO(base64.b64decode(_images(blocks)[0]["source"]["data"])))
    r, g, b = img.getpixel((img.width // 2, img.height // 2))
    assert r > 200 and g > 200 and b < 80
    assert "image;s=1600x1200" in str(fake_olx.requests[-1].url)


def test_view_image_reads_local_files_only_if_images(tools, tmp_path):
    photo = tmp_path / "od_sprzedawcy.png"
    Image.new("RGB", (300, 200), (10, 200, 10)).save(photo)
    blocks = tools["view_image"].call({"source": str(photo)})
    assert len(_images(blocks)) == 1

    secret = tmp_path / "notes.txt"
    secret.write_text("secret")
    with pytest.raises(ToolError, match="tylko pliki graficzne"):
        tools["view_image"].call({"source": str(secret)})


def test_get_listing_renders_details_and_signals(tools):
    text = tools["get_listing"].call({"listing": "912345678", "market_median": 2000})
    assert "Cena: 1 900 PLN (do negocjacji)" in text
    assert "Kondycja baterii 87%" in text
    assert "user_id=1234567" in text
    assert "[plus] Dostępna Przesyłka OLX" in text
    assert "<<<OPIS" in text


def test_search_tool_lists_results_and_categories(tools, fake_olx):
    fake_olx.search_pages.append(
        {
            "data": [
                make_offer(11, "iPhone 13 128", 1800),
                make_offer(12, "Etui iPhone 13", 30, category={"id": 2000}),
            ],
            "metadata": {"visible_total_count": 2},
        }
    )
    text = tools["search_listings"].call({"query": "iphone 13", "limit": 10})
    assert "[11] iPhone 13 128 — 1 800 PLN" in text
    assert "category_id=1689" in text and "category_id=2000" in text


def test_market_price_stats_pages_and_filters_titles(tools, fake_olx):
    first = [make_offer(100 + i, f"iPhone 13 128GB #{i}", 1700 + 20 * i) for i in range(50)]
    second = [make_offer(200 + i, f"iPhone 13 128GB B{i}", 1800 + 10 * i) for i in range(10)]
    second += [make_offer(300, "Etui na iPhone 13 128GB", 40), make_offer(301, "iPhone 13 256GB", 2600)]
    fake_olx.search_pages += [{"data": first}, {"data": second}]

    text = tools["market_price_stats"].call(
        {"query": "iphone 13", "title_must_include": ["128"], "title_must_exclude": ["etui"], "sample_size": 100}
    )

    assert "Mediana:" in text and "Próbka: 60 ofert" in text
    offsets = [p["offset"] for p in fake_olx.search_params()]
    assert offsets == ["0", "50"]


def test_compare_listings_table(tools, fake_olx):
    fake_olx.offers["923456789"] = make_offer(923456789, "iPhone 13 inny", 1750)
    text = tools["compare_listings"].call({"listings": ["912345678", "923456789"], "market_median": 1800})
    assert text.startswith("| Cecha | [912345678] | [923456789] |")
    assert "vs mediana" in text
    with pytest.raises(ToolError):
        tools["compare_listings"].call({"listings": ["912345678"]})


def test_tracker_tools_round_trip(tools):
    tools["track_listing"].call({"listing": "912345678", "status": "shortlisted", "note": "rysa na ekranie"})
    tools["log_conversation"].call(
        {"listing": "912345678", "direction": "to_seller", "text": "Dzień dobry, czy 1700 zł?", "price": 1700}
    )
    log = tools["log_conversation"].call(
        {"listing": "912345678", "direction": "from_seller", "text": "Najniżej 1800.", "price": 1800}
    )
    assert "sprzedawca → JA [kwota: 1 800 zł]: Najniżej 1800." in log
    summary = tools["show_tracker"].call({})
    assert "[912345678] iPhone 13 128GB Midnight" in summary and "kontakt nawiązany" in summary
    tools["remember_preferences"].call({"text": "Tylko odbiór osobisty w Krakowie"})
    assert "Tylko odbiór osobisty" in tools["show_tracker"].call({})


def test_buying_guide_and_invalid_topic(tools):
    assert "IMEI" in tools["buying_guide"].call({"topic": "phones"})
    with pytest.raises(ValueError):
        tools["buying_guide"].call({"topic": "unknown"})
