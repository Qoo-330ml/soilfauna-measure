"""App settings and thumbnail helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from soilfauna_measure.services.app_settings import (
    add_recent_workspace,
    clear_recent_workspaces,
    get_recent_workspaces,
)
from soilfauna_measure.services.thumbnail_service import (
    ensure_thumbnail,
    generate_thumbnail,
    is_thumbnail_fresh,
)


def test_recent_workspaces_roundtrip(tmp_path: Path, monkeypatch):
    # Isolate QSettings by using temp organization via env is hard;
    # just exercise list logic with clear + add.
    clear_recent_workspaces()
    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir()
    p2.mkdir()
    add_recent_workspace(p1)
    add_recent_workspace(p2)
    recent = get_recent_workspaces()
    assert str(p2.resolve()) in recent[0]
    assert str(p1.resolve()) in recent
    clear_recent_workspaces()
    assert get_recent_workspaces() == []


def test_thumbnail_generate(tmp_path: Path):
    src = tmp_path / "img.png"
    rgb = np.zeros((40, 60, 3), dtype=np.uint8)
    rgb[:, :] = (200, 100, 50)
    Image.fromarray(rgb).save(src)
    dest = tmp_path / "thumbs" / "img.jpg"
    generate_thumbnail(src, dest, size=32)
    assert dest.is_file()
    assert is_thumbnail_fresh(dest, src)
    # ensure from workspace layout
    ws = tmp_path / "ws"
    (ws / "images").mkdir(parents=True)
    img2 = ws / "images" / "x.png"
    Image.fromarray(rgb).save(img2)
    t = ensure_thumbnail(ws, img2, image_stem="x", size=32)
    assert t is not None and t.is_file()
