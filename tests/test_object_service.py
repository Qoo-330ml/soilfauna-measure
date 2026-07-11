"""Object service: create, paint, delete, persist masks."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from soilfauna_measure.core.calibration import build_scale_calibration
from soilfauna_measure.core.mask_operations import mask_area_px
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.services.object_service import ObjectService
from soilfauna_measure.storage.workspace import open_workspace, save_workspace


def _tiny_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "objws"
    ws.mkdir()
    rgb = np.zeros((80, 100, 3), dtype=np.uint8)
    rgb[:] = 240
    Image.fromarray(rgb).save(ws / "demo.tif", format="TIFF")
    return ws


def test_create_polygon_object_and_reload(tmp_path: Path):
    root = _tiny_ws(tmp_path)
    workspace = open_workspace(root)
    rec = workspace.images[0]
    rec.width, rec.height = 100, 80
    scale = build_scale_calibration((0, 0), (100, 0), 1000, "um")
    rec.scale = scale

    svc = ObjectService()
    svc.set_workspace(workspace.root)
    svc.bind_image(rec, width=100, height=80)

    pts = [[10, 10], [50, 10], [50, 40], [10, 40]]
    obj = svc.create_from_polygon(rec, pts, scale)
    assert obj.object_id == "demo_001"
    assert rec.next_object_seq == 2
    assert obj.area_px > 0
    assert obj.area_um2 is not None
    assert obj.area_mm2 is not None
    mask_path = workspace.root / obj.mask_path
    assert mask_path.is_file()

    # second object unique id
    obj2 = svc.create_from_polygon(
        rec, [[60, 10], [90, 10], [90, 30], [60, 30]], scale
    )
    assert obj2.object_id == "demo_002"
    assert obj.object_id != obj2.object_id

    save_workspace(workspace)

    # reopen
    ws2 = open_workspace(root)
    rec2 = ws2.images[0]
    assert len(rec2.objects) == 2
    svc2 = ObjectService()
    svc2.set_workspace(ws2.root)
    svc2.bind_image(rec2, width=100, height=80)
    m1 = svc2.get_mask(rec2.objects[0].object_id)
    m2 = svc2.get_mask(rec2.objects[1].object_id)
    assert m1 is not None and m2 is not None
    assert mask_area_px(m1) == pytest.approx(rec2.objects[0].area_px)
    assert np.count_nonzero((m1 > 0) & (m2 > 0)) == 0


def test_brush_updates_area(tmp_path: Path):
    root = _tiny_ws(tmp_path)
    workspace = open_workspace(root)
    rec = workspace.images[0]
    svc = ObjectService()
    svc.set_workspace(workspace.root)
    svc.bind_image(rec, width=100, height=80)
    obj = svc.create_from_polygon(
        rec, [[20, 20], [40, 20], [40, 40], [20, 40]], None
    )
    a0 = obj.area_px
    svc.paint_brush(rec, obj.object_id, [[50, 50]], 8, erase=False, scale=None)
    assert obj.area_px > a0
    svc.paint_brush(rec, obj.object_id, [[30, 30]], 20, erase=True, scale=None)
    assert obj.area_px < a0 + 500  # erased some


def test_delete_object(tmp_path: Path):
    root = _tiny_ws(tmp_path)
    workspace = open_workspace(root)
    rec = workspace.images[0]
    svc = ObjectService()
    svc.set_workspace(workspace.root)
    svc.bind_image(rec, width=100, height=80)
    obj = svc.create_from_polygon(
        rec, [[5, 5], [25, 5], [25, 25], [5, 25]], None
    )
    oid = obj.object_id
    path = workspace.root / obj.mask_path
    assert path.is_file()
    assert svc.delete_object(rec, oid)
    assert not any(o.object_id == oid for o in rec.objects)
    assert not path.is_file()
    # id not reused
    obj2 = svc.create_from_polygon(
        rec, [[5, 5], [25, 5], [25, 25], [5, 25]], None
    )
    assert obj2.object_id != oid
