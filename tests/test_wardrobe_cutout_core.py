"""Cutout compositor checks. These use synthetic model masks, not a model.

No user image, cloud API or unlicensed model is required; an ONNX adapter
must be independently tested before this code may be advertised as available.
"""
import io
from pathlib import Path
import sys

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from wardrobe.cutout_core import CutoutRejected, render_showcase_preview


def source():
    buff = io.BytesIO()
    pic = Image.new("RGB", (600, 600), (238, 237, 233))
    ImageDraw.Draw(pic).rectangle((145, 60, 460, 565), fill=(19, 37, 63))
    pic.save(buff, "JPEG", quality=88)
    return buff.getvalue()


def mask():
    result = Image.new("L", (600, 600), 0)
    ImageDraw.Draw(result).rectangle((145, 60, 460, 565), fill=255)
    return result


def test_masked_clothing_looks_transparent_and_retains_source():
    src = source()
    preview = render_showcase_preview(src, mask())
    assert preview.quality == "requires_review"
    assert preview.source == "mask_supplied_by_separate_model"
    assert .04 < preview.coverage < .88
    assert src == source()  # No input mutation.
    with Image.open(io.BytesIO(preview.png)) as im:
        assert im.format == "PNG" and im.mode == "RGBA"
        assert im.size == (900, 900)
        assert im.getpixel((0, 0))[3] == 0
        assert im.getpixel((450, 450))[3] >= 240
        assert not im.info.get("exif")


def test_reject_empty_overfull_and_border_only_masks():
    src = source()
    for matte, status in (
        (Image.new("L", (600, 600), 0), "empty_mask"),
        (Image.new("L", (600, 600), 255), "foreground_too_large"),
    ):
        with pytest.raises(CutoutRejected) as captured:
            render_showcase_preview(src, matte)
        assert captured.value.code == status
    tiny = Image.new("L", (600, 600), 0)
    ImageDraw.Draw(tiny).rectangle((20, 20, 26, 26), fill=255)
    with pytest.raises(CutoutRejected, match="foreground_too_small"):
        render_showcase_preview(src, tiny)

    ring = Image.new("L", (600, 600), 0)
    draw = ImageDraw.Draw(ring)
    draw.rectangle((0, 0, 599, 599), outline=255, width=10)
    with pytest.raises(CutoutRejected, match="too_much_border_contact"):
        render_showcase_preview(src, ring)


def test_bad_source_or_mask_never_fakes_a_storefront_image():
    good = source()
    with pytest.raises(CutoutRejected, match="invalid_image"):
        render_showcase_preview(b"not an image", mask())
    with pytest.raises(CutoutRejected, match="invalid_mask"):
        render_showcase_preview(good, Image.new("L", (1, 1), 255))
    with pytest.raises(CutoutRejected, match="invalid_mask"):
        render_showcase_preview(good, None)
