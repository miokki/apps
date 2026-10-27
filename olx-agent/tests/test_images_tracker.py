import base64
import io
import json

import pytest
from PIL import Image

from olx_agent.images import ImageError, prepare_image
from olx_agent.tracker import Tracker

from conftest import jpeg_bytes


def _decode(prepared):
    return Image.open(io.BytesIO(base64.b64decode(prepared.data_b64)))


def test_prepare_image_downscales_to_max_edge():
    prepared = prepare_image(jpeg_bytes((3000, 2000)), max_edge=1024)
    assert (prepared.width, prepared.height) == (1024, 683)
    assert prepared.media_type == "image/jpeg"
    assert prepared.block()["source"]["type"] == "base64"
    assert _decode(prepared).size == (1024, 683)


def test_prepare_image_crop_returns_requested_region():
    # The top-left quarter of the test image is yellow, the rest purple.
    prepared = prepare_image(jpeg_bytes((1600, 1200)), max_edge=1568, crop=(0.0, 0.0, 0.2, 0.2))
    img = _decode(prepared)
    r, g, b = img.getpixel((img.width // 2, img.height // 2))
    assert r > 200 and g > 200 and b < 80
    assert prepared.source_width == 1600
    assert img.width == 640  # 320 px crop upscaled 2x for legibility


def test_prepare_image_flattens_transparency_and_rejects_non_images():
    buf = io.BytesIO()
    Image.new("RGBA", (50, 40), (0, 0, 0, 0)).save(buf, format="PNG")
    prepared = prepare_image(buf.getvalue(), max_edge=1024)
    assert _decode(prepared).getpixel((10, 10)) == (255, 255, 255)

    with pytest.raises(ImageError):
        prepare_image(b"not an image", max_edge=100)
    with pytest.raises(ImageError):
        prepare_image(jpeg_bytes((100, 100)), max_edge=100, crop=(0.5, 0.5, 0.5, 0.9))


def test_tracker_persists_items_messages_and_preferences(tmp_path):
    path = tmp_path / "state.json"
    tracker = Tracker(path)
    tracker.add_preference("Budżet do 2000 zł, odbiór w Krakowie")
    tracker.upsert("123", title="iPhone 13", url="https://olx/x", asking_price=1900, note="rysa na ramce")
    tracker.log_message("123", "to_seller", "Czy zejdzie Pan do 1700?", 1700)
    tracker.log_message("123", "from_seller", "Mogę 1800.", 1800)
    tracker.upsert("123", status="negotiating")

    reloaded = Tracker(path)
    item = reloaded.get("123")
    assert item["status"] == "negotiating"
    assert item["my_offer"] == 1700
    assert [m["direction"] for m in item["messages"]] == ["to_seller", "from_seller"]
    assert "Budżet do 2000 zł" in reloaded.render_summary()
    detail = reloaded.render_item("123")
    assert "JA → sprzedawca [kwota: 1 700 zł]" in detail and "rysa na ramce" in detail


def test_tracker_keeps_unreadable_file_aside(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    tracker = Tracker(path)
    tracker.add_preference("x")
    assert json.loads(path.read_text(encoding="utf-8"))["preferences"][0]["text"] == "x"
    assert list(tmp_path.glob("state.broken-*.json"))
