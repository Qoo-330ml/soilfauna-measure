"""Skeleton length path suggestion tests."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from soilfauna_measure.core.mask_operations import empty_mask, polygon_to_mask
from soilfauna_measure.core.measurement import polyline_length_px
from soilfauna_measure.core.skeleton import (
    PathSuggestionError,
    douglas_peucker,
    suggest_length_path,
)


def _bent_blob(h=80, w=120) -> np.ndarray:
    """Curved thick stroke as a body-like mask."""
    m = empty_mask(h, w)
    pil = Image.fromarray(m, mode="L")
    draw = ImageDraw.Draw(pil)
    # thick polyline approximating a curve
    pts = [(15, 40), (40, 25), (70, 30), (95, 50), (105, 65)]
    draw.line(pts, fill=255, width=10)
    return np.array(pil)


def test_suggest_path_on_bent_blob():
    mask = _bent_blob()
    sug = suggest_length_path(mask, min_branch_length=5, target_nodes=8)
    assert len(sug.points) >= 2
    assert len(sug.points) <= 10
    assert sug.length_px > 20
    assert sug.n_skeleton_pixels > 5
    # points are [x,y]
    for p in sug.points:
        assert 0 <= p[0] < 120
        assert 0 <= p[1] < 80


def test_suggest_empty_raises():
    m = empty_mask(40, 40)
    with pytest.raises(PathSuggestionError):
        suggest_length_path(m)


def test_douglas_peucker_reduces_points():
    # dense diagonal
    pts = [(float(i), float(i)) for i in range(50)]
    simple = douglas_peucker(pts, epsilon=0.5)
    assert len(simple) < len(pts)
    assert simple[0] == pts[0]
    assert simple[-1] == pts[-1]


def test_object_service_suggest(tmp_path):
    from pathlib import Path
    from PIL import Image as PILImage

    from soilfauna_measure.services.object_service import ObjectService
    from soilfauna_measure.storage.workspace import open_workspace

    root = tmp_path / "sk"
    root.mkdir()
    rgb = np.full((80, 120, 3), 250, dtype=np.uint8)
    PILImage.fromarray(rgb).save(root / "a.tif", format="TIFF")
    ws = open_workspace(root)
    rec = ws.images[0]
    rec.width, rec.height = 120, 80
    svc = ObjectService()
    svc.set_workspace(ws.root)
    svc.bind_image(rec, width=120, height=80)
    mask = _bent_blob()
    obj = svc.create_from_mask(rec, mask, None, confirmed=False)
    svc.suggest_length_for_object(obj, None)
    assert obj.length_source == "auto_suggested"
    assert obj.length_points
    assert obj.length_px == pytest.approx(polyline_length_px(obj.length_points))
    # refuse overwrite manual
    obj.length_source = "manual"
    with pytest.raises(ValueError):
        svc.suggest_length_for_object(obj, None, overwrite_manual=False)
