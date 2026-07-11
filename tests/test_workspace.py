"""Workspace open / copy-into-images tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from soilfauna_measure.storage.workspace import (
    WORKSPACE_SUBDIRS,
    open_workspace,
)


def test_open_workspace_copies_images(tmp_image_dir: Path, tmp_path: Path):
    ws_root = tmp_path / "ws1"
    ws_root.mkdir()
    for p in tmp_image_dir.iterdir():
        if p.suffix.lower() in {".png", ".tif"}:
            shutil.copy2(p, ws_root / p.name)

    ws = open_workspace(ws_root)
    for name in WORKSPACE_SUBDIRS:
        assert (ws_root / name).is_dir()

    assert len(ws.images) == 2
    for img in ws.images:
        abs_path = ws.abs_path(img)
        assert abs_path.is_file()
        assert abs_path.parent.name == "images"
        assert img.relative_path.startswith("images/")

    assert ws.project_path.is_file()
    assert ws.project.schema_version


def test_open_workspace_already_in_images(tmp_image_dir: Path, tmp_path: Path):
    ws_root = tmp_path / "ws2"
    images = ws_root / "images"
    images.mkdir(parents=True)
    src = tmp_image_dir / "sample.png"
    shutil.copy2(src, images / "sample.png")

    ws = open_workspace(ws_root)
    assert len(ws.images) == 1
    assert ws.abs_path(ws.images[0]) == (images / "sample.png").resolve()


def test_open_empty_workspace(tmp_path: Path):
    ws_root = tmp_path / "empty"
    ws_root.mkdir()
    ws = open_workspace(ws_root)
    assert ws.images == []
    assert (ws_root / "images").is_dir()
    assert ws.project_path.is_file()
