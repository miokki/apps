"""Buying checklists, loaded on demand by the `buying_guide` tool.

The texts live in the skill's `references/guides/` folder, so the plugin skill (usable without the tools) and the
tool read the same files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args

SKILL_DIR = Path(__file__).parent / "skills" / "olx-zakupy"
GUIDES_DIR = SKILL_DIR / "references" / "guides"

GuideTopic = Literal[
    "general",
    "safety",
    "olx_delivery",
    "pickup",
    "negotiation",
    "buyer_rights",
    "phones",
    "laptops",
    "consoles",
    "cameras",
    "cars",
    "bikes",
    "furniture_appliances",
    "clothing_luxury",
    "tickets",
    "rentals",
]

TOPICS: tuple[str, ...] = get_args(GuideTopic)


def get_guide(topic: str) -> str:
    if topic not in TOPICS:
        topic = "general"
    return (GUIDES_DIR / f"{topic}.md").read_text(encoding="utf-8").strip()
