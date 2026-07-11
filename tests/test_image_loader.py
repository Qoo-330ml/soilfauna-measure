"""Tests for image loading and scanning."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from soilfauna_measure.core.image_loader import (
    ImageLoadError,
    array_to_display_rgb,
    is_supported_image,
    load_image,
    scan_image_files,
)


def test_is_supported_image():
    assert is_supported_image(Path("a.tif"))
    assert is_supported_image(Path("a.TIFF"))
    assert is_supported_image(Path("a.png"))
    assert is_supported_image(Path("a.jpeg"))
    assert not is_supported_image(Path("a.txt"))
    assert not is_supported_image(Path("a.gif"))


def test_scan_image_files(tmp_image_dir: Path):
    files = scan_image_files(tmp_image_dir)
    names = {p.name.lower() for p in files}
    assert "sample.png" in names
    assert "sample.tif" in names
    assert "notes.txt" not in names
    assert len(files) == 2


def test_scan_missing_dir(tmp_path: Path):
    assert scan_image_files(tmp_path / "nope") == []


def test_load_png(tmp_image_dir: Path):
    loaded = load_image(tmp_image_dir / "sample.png")
    assert loaded.meta.width == 48
    assert loaded.meta.height == 32
    assert loaded.meta.channels == 3
    assert loaded.raw.shape == (32, 48, 3)
    assert loaded.raw.dtype == np.uint8


def test_load_tif(tmp_image_dir: Path):
    loaded = load_image(tmp_image_dir / "sample.tif")
    assert loaded.meta.width == 48
    assert loaded.meta.height == 32
    assert loaded.raw.ndim in (2, 3)


def test_load_missing(tmp_path: Path):
    with pytest.raises(ImageLoadError):
        load_image(tmp_path / "missing.tif")


def test_load_unsupported(tmp_path: Path):
    p = tmp_path / "x.txt"
    p.write_text("hi", encoding="utf-8")
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_array_to_display_rgb_uint8():
    raw = np.zeros((4, 5, 3), dtype=np.uint8)
    raw[:] = (10, 20, 30)
    out = array_to_display_rgb(raw)
    assert out.dtype == np.uint8
    assert out.shape == (4, 5, 3)
    assert out[0, 0, 0] == 10


def test_array_to_display_rgb_gray_uint16():
    raw = np.array([[0, 65535], [32767, 1000]], dtype=np.uint16)
    out = array_to_display_rgb(raw)
    assert out.shape == (2, 2, 3)
    assert out.dtype == np.uint8
    assert out[0, 0, 0] == 0
    assert out[0, 1, 0] == 255


def test_load_hj98_meta(example_hj98: Path):
    loaded = load_image(example_hj98)
    assert loaded.meta.width == 1600
    assert loaded.meta.height == 1200
    assert loaded.meta.channels == 3
    assert loaded.raw.shape == (1200, 1600, 3)
    assert loaded.raw.dtype == np.uint8
