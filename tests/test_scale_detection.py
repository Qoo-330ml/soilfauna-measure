"""Automatic scale bar detection tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from soilfauna_measure.core.scale_detection import (
    detect_horizontal_scale_line,
    detect_scale,
    parse_scale_label_text,
)


def test_parse_scale_label_text():
    assert parse_scale_label_text("1000μm") == (1000.0, "um")
    assert parse_scale_label_text("1000 µm")[0] == 1000.0
    assert parse_scale_label_text("1mm") == (1.0, "mm")
    assert parse_scale_label_text("0.5 mm") == (0.5, "mm")
    assert parse_scale_label_text("no scale here") is None


def test_detect_line_on_synthetic():
    # white bg + black horizontal bar bottom-right
    img = np.full((200, 300, 3), 255, dtype=np.uint8)
    # bar from x=200..280 at y=180, thickness 3
    img[179:182, 200:280, :] = 0
    # end caps
    img[175:186, 200:203, :] = 0
    img[175:186, 277:280, :] = 0
    line = detect_horizontal_scale_line(img)
    assert line is not None
    start, end, length, region = line
    assert length >= 70
    assert region in {"bottom_right", "bottom", "bottom_left", "full_bottom"}


def test_detect_scale_hj98(repo_root: Path):
    path = repo_root / "examples" / "HJ98.tif"
    if not path.is_file():
        pytest.skip("HJ98 missing")
    from soilfauna_measure.core.image_loader import load_image

    loaded = load_image(path)
    det = detect_scale(loaded.raw, default_real=1000.0, default_unit="um")
    assert det.found, det.message
    assert det.pixel_length >= 100  # bar ~136 px
    assert det.pixel_length <= 300
    assert det.start_point is not None and det.end_point is not None
    # right-bottom-ish
    assert det.start_point[0] > 1000
    assert det.start_point[1] > 1000
    cal = det.to_calibration(confirmed=True)
    assert cal is not None
    assert cal.unit == "um"
    assert cal.real_length == 1000.0
    assert cal.real_per_pixel == pytest.approx(1000.0 / det.pixel_length)
