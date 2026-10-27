from __future__ import annotations

import copy
import io
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional

import httpx2
import pytest
from PIL import Image

from olx_agent.config import Config
from olx_agent.olx_client import OlxClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_offer() -> dict[str, Any]:
    return json.loads((FIXTURES / "offer_iphone.json").read_text(encoding="utf-8"))["data"]


def make_offer(offer_id: int, title: str, price: Optional[float], **overrides: Any) -> dict[str, Any]:
    """An offer shaped like the OLX API, derived from the realistic fixture."""
    offer = copy.deepcopy(load_offer())
    offer["id"] = offer_id
    offer["title"] = title
    offer["url"] = f"https://www.olx.pl/d/oferta/item-CID99-ID{offer_id}.html"
    params = [p for p in offer["params"] if p["key"] != "price"]
    if price is not None:
        params.insert(
            0,
            {
                "key": "price",
                "name": "Cena",
                "type": "price",
                "value": {"value": price, "currency": "PLN", "negotiable": False, "label": f"{price} zł"},
            },
        )
    offer["params"] = params
    condition = overrides.pop("condition", None)
    if condition:
        for p in offer["params"]:
            if p["key"] == "state":
                p["value"] = {"key": condition, "label": {"new": "Nowe", "used": "Używane", "damaged": "Uszkodzone"}[condition]}
    for key, value in overrides.items():
        offer[key] = value
    return offer


def jpeg_bytes(size: tuple[int, int] = (1600, 1200), color: tuple[int, int, int] = (120, 30, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    # A distinct marker in the top-left quarter makes crops verifiable.
    for x in range(size[0] // 4):
        for y in range(size[1] // 4):
            img.putpixel((x, y), (255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class FakeOlx:
    """Routes httpx2 requests to canned OLX responses and records them."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.offers: dict[str, dict[str, Any]] = {}
        self.search_pages: list[dict[str, Any]] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.locations: dict[str, list[dict[str, Any]]] = {}
        self.pages: dict[str, str] = {}
        self.photo = jpeg_bytes()
        self.fail_next: list[int] = []
        self.handlers: list[Callable[[httpx2.Request], Optional[httpx2.Response]]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.fail_next:
            return httpx2.Response(self.fail_next.pop(0))
        for handler in self.handlers:
            response = handler(request)
            if response is not None:
                return response
        path = request.url.path
        if "olxcdn.com" in request.url.host:
            return httpx2.Response(200, content=self.photo, headers={"content-type": "image/jpeg"})
        if path == "/api/v1/offers/":
            page = self.search_pages.pop(0) if self.search_pages else {"data": [], "metadata": {}, "links": {}}
            return httpx2.Response(200, json=page)
        if m := re.fullmatch(r"/api/v1/offers/(\d+)/", path):
            offer = self.offers.get(m.group(1))
            return httpx2.Response(200, json={"data": offer}) if offer else httpx2.Response(404)
        if m := re.fullmatch(r"/api/v1/users/(\d+)/", path):
            user = self.users.get(m.group(1))
            return httpx2.Response(200, json={"data": user}) if user else httpx2.Response(404)
        if path == "/api/v1/geo-encoder/location-autocomplete/":
            return httpx2.Response(200, json={"data": self.locations.get(request.url.params.get("query", ""), [])})
        if path.startswith("/d/oferta/"):
            page = self.pages.get(path)
            return httpx2.Response(200, text=page) if page else httpx2.Response(404)
        return httpx2.Response(404)

    def search_params(self) -> list[dict[str, str]]:
        return [dict(r.url.params) for r in self.requests if r.url.path == "/api/v1/offers/"]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.home = tmp_path / "home"
    cfg.request_interval_s = 0.0
    return cfg


@pytest.fixture
def fake_olx() -> FakeOlx:
    return FakeOlx()


@pytest.fixture
def olx(config: Config, fake_olx: FakeOlx, monkeypatch: pytest.MonkeyPatch) -> OlxClient:
    monkeypatch.setattr("olx_agent.olx_client.time.sleep", lambda s: None)
    return OlxClient(config, http=httpx2.Client(transport=httpx2.MockTransport(fake_olx)))
