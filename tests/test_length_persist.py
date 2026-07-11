"""Body length path persists in project JSON."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from soilfauna_measure.core.calibration import build_scale_calibration
from soilfauna_measure.core.measurement import polyline_length_px
from soilfauna_measure.services.object_service import ObjectService
from soilfauna_measure.storage.workspace import open_workspace, save_workspace


def test_length_points_roundtrip(tmp_path: Path):
    root = tmp_path / "lenws"
    root.mkdir()
    rgb = np.zeros((60, 80, 3), dtype=np.uint8)
    rgb[:] = 250
    Image.fromarray(rgb).save(root / "bug.tif", format="TIFF")

    ws = open_workspace(root)
    rec = ws.images[0]
    rec.width, rec.height = 80, 60
    rec.scale = build_scale_calibration((0, 0), (80, 0), 800, "um")

    svc = ObjectService()
    svc.set_workspace(ws.root)
    svc.bind_image(rec, width=80, height=60)
    obj = svc.create_from_polygon(
        rec, [[10, 10], [40, 10], [40, 40], [10, 40]], rec.scale
    )
    pts = [[12, 15], [25, 20], [35, 30], [38, 38]]
    svc.apply_length_points(obj, pts, rec.scale, source="manual")
    expected = polyline_length_px(pts)
    assert obj.length_px == pytest.approx(expected)
    assert obj.length_um is not None

    save_workspace(ws)

    ws2 = open_workspace(root)
    rec2 = ws2.images[0]
    assert len(rec2.objects) == 1
    o2 = rec2.objects[0]
    assert o2.length_points == pts or [
        [float(a), float(b)] for a, b in o2.length_points
    ] == pts
    svc2 = ObjectService()
    svc2.set_workspace(ws2.root)
    svc2.bind_image(rec2, width=80, height=60)
    svc2.recompute_all_lengths(rec2, rec2.scale)
    assert rec2.objects[0].length_px == pytest.approx(expected)
