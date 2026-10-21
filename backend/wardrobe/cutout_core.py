"""Isolated storefront-cutout compositor (EXPERIMENTAL, NO production model).

This module does not remove the background by itself: it needs a matte created
by a separately vetted and licensed segmentation model. Quality checks and
transparent PNG rendering run locally with Pillow; no uploaded photographs,
mask or resulting pixels leave the service. Caller must preserve the encrypted
reference image and separately obtain user acceptance before persisting output.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

MAX_SOURCE_BYTES = 800_000
MAX_MASK_BYTES = 600_000
MAX_OUTPUT_BYTES = 1_600_000
MAX_SOURCE_PIXELS = 3_000_000

class CutoutRejected(ValueError):
    def __init__(self, code: Literal[
        "invalid_image", "invalid_mask", "empty_mask", "foreground_too_large",
        "foreground_too_small", "too_much_border_contact", "output_too_large"]):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ShowcasePreview:
    """An unsaved preview requiring the garment owner's explicit acceptance."""
    png: bytes
    coverage: float
    quality: str = "requires_review"
    source: str = "mask_supplied_by_separate_model"


def _load_source(source: bytes) -> Image.Image:
    if not source or len(source) > MAX_SOURCE_BYTES:
        raise CutoutRejected("invalid_image")
    try:
        with Image.open(io.BytesIO(source), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > MAX_SOURCE_PIXELS:
                raise CutoutRejected("invalid_image")
            copied = ImageOps.exif_transpose(image)
            copied.load()
            return copied.convert("RGBA")
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise CutoutRejected("invalid_image") from exc


def render_showcase_preview(source: bytes, mask: Image.Image) -> ShowcasePreview:
    """Turn a separately produced saliency matte into an editable PNG preview.

    This never guesses foreground with flat-color rules: if no model-generated
    mask is available, no preview should be advertised or stored. It also
    rejects empty, nearly full-frame and border-dominated masks rather than
    cropping away white or dark clothing without user knowledge.
    """
    raw = _load_source(source)
    if not isinstance(mask, Image.Image) or mask.width < 16 or mask.height < 16:
        raise CutoutRejected("invalid_mask")
    if mask.width * mask.height > MAX_SOURCE_PIXELS:
        raise CutoutRejected("invalid_mask")
    try:
        alpha = mask.convert("L").resize(raw.size, Image.Resampling.BILINEAR)
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.55))
    except (OSError, ValueError) as exc:
        raise CutoutRejected("invalid_mask") from exc
    # Only a strong foreground mask is eligible for a premium-style preview.
    binary = alpha.point(lambda n: 255 if n >= 128 else 0)
    bbox = binary.getbbox()
    if bbox is None:
        raise CutoutRejected("empty_mask")
    foreground_fraction = binary.histogram()[255] / (raw.width * raw.height)
    if foreground_fraction < 0.045:
        raise CutoutRejected("foreground_too_small")
    if foreground_fraction > 0.88:
        raise CutoutRejected("foreground_too_large")

    # Reject a mask covering nearly every edge; likely model failure or a
    # strongly uncontained foreground, not a trustworthy background removal.
    margin = max(3, int(min(raw.size) * .015))
    outside = Image.new("L", raw.size, 255)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(outside)
    draw.rectangle(
        (margin, margin, raw.width - margin - 1, raw.height - margin - 1),
        fill=0,
    )
    # Count strong alpha only inside a thin edge ring.
    binary_border = binary.copy()
    from PIL import ImageChops
    binary_border = ImageChops.multiply(binary_border, outside)
    border_coverage = binary_border.histogram()[255] / max(1, outside.histogram()[255])
    if border_coverage > 0.35:
        raise CutoutRejected("too_much_border_contact")

    # Include a small non-destructive transparent margin around the matte.
    left, top, right, bottom = bbox
    pad = int(max(right - left, bottom - top) * .075) + 5
    crop_box = (
        max(0, left - pad), max(0, top - pad),
        min(raw.width, right + pad), min(raw.height, bottom + pad),
    )
    raw.putalpha(alpha)
    cropped = raw.crop(crop_box)
    cropped.thumbnail((830, 830), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    canvas.alpha_composite(cropped, ((900 - cropped.width)//2, (900 - cropped.height)//2))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    if output.tell() > MAX_OUTPUT_BYTES:
        # A failed quality budget is a safe fallback to the original, not a
        # silent lossy conversion pretending to be a transparent store image.
        raise CutoutRejected("output_too_large")
    return ShowcasePreview(png=output.getvalue(),
                           coverage=round(foreground_fraction, 4))
