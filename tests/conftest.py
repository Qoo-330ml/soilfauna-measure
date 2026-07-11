"""Pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def example_hj98(repo_root: Path) -> Path:
    path = repo_root / "examples" / "HJ98.tif"
    if not path.is_file():
        pytest.skip("examples/HJ98.tif not present")
    return path


@pytest.fixture
def tmp_image_dir(tmp_path: Path) -> Path:
    """Create a temp folder with a small PNG and a small TIFF-like PNG named .tif via pillow."""
    rgb = np.zeros((32, 48, 3), dtype=np.uint8)
    rgb[..., 0] = 200
    rgb[..., 1] = 100
    rgb[..., 2] = 50
    png = tmp_path / "sample.png"
    Image.fromarray(rgb, mode="RGB").save(png)

    tif = tmp_path / "sample.tif"
    Image.fromarray(rgb, mode="RGB").save(tif, format="TIFF")

    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    return tmp_path
