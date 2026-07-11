"""Project JSON round-trip and atomic save tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soilfauna_measure.core.calibration import build_scale_calibration
from soilfauna_measure.models.project import SCHEMA_VERSION, Project
from soilfauna_measure.storage.project_io import (
    ProjectIOError,
    load_project,
    save_autosave,
    save_project,
)
from soilfauna_measure.storage.workspace import open_workspace, save_workspace


def test_project_roundtrip(tmp_path: Path):
    proj = Project.create_new("demo", app_version="0.1.0")
    scale = build_scale_calibration((10, 20), (234, 20), 1000, "um")
    from soilfauna_measure.models.image_record import ImageRecord

    proj.images.append(
        ImageRecord(
            image_id="HJ98",
            relative_path="images/HJ98.tif",
            width=1600,
            height=1200,
            channels=3,
            dtype="uint8",
            status="in_progress",
            scale=scale,
        )
    )
    path = tmp_path / "project.sfm.json"
    save_project(proj, path)
    assert path.is_file()
    assert (tmp_path / "project.sfm.json.bak").exists() is False  # first save no bak

    # second save creates bak
    proj.project_name = "demo2"
    save_project(proj, path)
    assert (tmp_path / "project.sfm.json.bak").is_file()

    loaded = load_project(path)
    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.project_name == "demo2"
    assert len(loaded.images) == 1
    img = loaded.images[0]
    assert img.image_id == "HJ98"
    assert img.scale is not None
    assert img.scale.pixel_length == pytest.approx(224.0)
    assert img.scale.unit == "um"
    assert img.scale.real_length == 1000
    assert img.scale.real_per_pixel == pytest.approx(1000 / 224)


def test_load_corrupt_json(tmp_path: Path):
    path = tmp_path / "project.sfm.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProjectIOError):
        load_project(path)


def test_schema_version_present(tmp_path: Path):
    proj = Project.create_new("x")
    path = tmp_path / "project.sfm.json"
    save_project(proj, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert "categories" in data
    assert "images" in data


def test_workspace_save_restore_scale(tmp_image_dir: Path, tmp_path: Path):
    import shutil

    ws_root = tmp_path / "ws_scale"
    ws_root.mkdir()
    shutil.copy2(tmp_image_dir / "sample.tif", ws_root / "sample.tif")

    ws = open_workspace(ws_root)
    assert len(ws.images) == 1
    assert ws.project_path.is_file()

    scale = build_scale_calibration((0, 0), (100, 0), 1000, "um")
    ws.images[0].scale = scale
    ws.images[0].status = "in_progress"
    save_workspace(ws)

    ws2 = open_workspace(ws_root)
    assert ws2.images[0].scale is not None
    assert ws2.images[0].scale.real_per_pixel == pytest.approx(10.0)
    assert ws2.images[0].scale.unit == "um"


def test_autosave_file(tmp_path: Path):
    proj = Project.create_new("auto")
    path = save_autosave(proj, tmp_path)
    assert path.is_file()
    assert path.name.endswith("autosave.json")
