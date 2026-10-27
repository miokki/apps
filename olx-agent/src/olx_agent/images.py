"""Image preparation for Claude's vision input: decode, orient, crop, downscale and re-encode as JPEG."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Optional

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 80_000_000


class ImageError(Exception):
    pass


@dataclass
class PreparedImage:
    data_b64: str
    media_type: str
    width: int
    height: int
    source_width: int
    source_height: int

    @property
    def encoded_bytes(self) -> int:
        return len(self.data_b64)

    def block(self) -> dict[str, Any]:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": self.media_type, "data": self.data_b64},
        }


def prepare_image(
    raw: bytes,
    *,
    max_edge: int,
    quality: int = 82,
    crop: Optional[tuple[float, float, float, float]] = None,
) -> PreparedImage:
    """Decode `raw`, optionally crop to a relative (left, top, right, bottom) box, fit into `max_edge` px."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError("Plik nie jest obsługiwanym obrazem.") from exc

    img = ImageOps.exif_transpose(img)
    source_w, source_h = img.size

    if crop is not None:
        left, top, right, bottom = (min(1.0, max(0.0, v)) for v in crop)
        if right - left < 0.02 or bottom - top < 0.02:
            raise ImageError("Obszar przybliżenia jest pusty lub zbyt mały (użyj ułamków 0–1, lewo < prawo, góra < dół).")
        img = img.crop((round(left * source_w), round(top * source_h), round(right * source_w), round(bottom * source_h)))

    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode == "L":
        img = img.convert("RGB")

    w, h = img.size
    scale = max_edge / max(w, h)
    if scale < 1:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
    elif crop is not None and scale > 1:
        # A small crop is upscaled (at most 2x) so fine details stay legible to the model.
        factor = min(scale, 2.0)
        img = img.resize((round(w * factor), round(h * factor)), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return PreparedImage(
        data_b64=base64.standard_b64encode(buffer.getvalue()).decode("ascii"),
        media_type="image/jpeg",
        width=img.size[0],
        height=img.size[1],
        source_width=source_w,
        source_height=source_h,
    )


class ImageBudget:
    """Tracks the encoded size of images placed in the conversation (each turn re-sends them all)."""

    def __init__(self, limit_bytes: int) -> None:
        self.limit = limit_bytes
        self.used = 0

    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def fits(self, size: int) -> bool:
        return self.used + size <= self.limit

    def add(self, size: int) -> None:
        self.used += size

    def reset(self) -> None:
        self.used = 0
