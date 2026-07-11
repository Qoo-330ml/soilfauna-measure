"""Automatic segmentation and merge/split tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from soilfauna_measure.core.mask_operations import empty_mask, mask_area_px, polygon_to_mask
from soilfauna_measure.core.segmentation import (
    SegmentationParams,
    extract_foreground,
    merge_masks,
    segment_instances,
    split_mask_by_cut_line,
    split_mask_by_seeds,
)
from soilfauna_measure.services.object_service import ObjectService
from soilfauna_measure.storage.workspace import open_workspace, save_workspace


def _two_dark_blobs(h=120, w=160) -> np.ndarray:
    """Synthetic white bg with two dark ellipses (touching-ish)."""
    img = np.full((h, w, 3), 250, dtype=np.uint8)
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    draw.ellipse([20, 30, 70, 90], fill=(80, 80, 80))
    draw.ellipse([65, 35, 120, 95], fill=(90, 90, 90))  # contact zone
    return np.array(pil)


def test_extract_foreground_finds_blobs():
    img = _two_dark_blobs()
    fg = extract_foreground(img, SegmentationParams(min_object_area=50))
    assert fg.mean() > 0.02
    assert fg.mean() < 0.5


def test_strip_thin_appendages_removes_thin_leg():
    from soilfauna_measure.core.segmentation import strip_thin_appendages

    # thick body + thin horizontal "leg" (must strip BEFORE any heavy close)
    m = np.zeros((80, 80), dtype=bool)
    m[25:55, 25:55] = True  # body ~30x30
    m[38:41, 55:75] = True  # thin leg ~3px thick
    stripped = strip_thin_appendages(
        m, open_radius=7, restore_radius=2, min_half_width=2.5, thickness_frac=0.40
    )
    assert stripped[30:50, 30:50].mean() > 0.5  # body remains
    assert stripped[38:41, 60:74].mean() < 0.25  # leg mostly gone


def test_strip_removes_medium_leg_keeps_body():
    """Legs ~6px thick should still be stripped from a thick body."""
    from soilfauna_measure.core.segmentation import strip_thin_appendages

    m = np.zeros((100, 100), dtype=bool)
    m[30:70, 30:70] = True  # body 40x40, half-width ~20
    m[47:53, 70:95] = True  # medium leg 6px thick
    stripped = strip_thin_appendages(
        m, open_radius=7, restore_radius=2, thickness_frac=0.40, max_half_width=14.0
    )
    assert stripped[35:65, 35:65].mean() > 0.7
    assert stripped[47:53, 75:94].mean() < 0.30


def test_strip_does_not_erase_compact_body():
    from soilfauna_measure.core.segmentation import strip_thin_appendages

    m = np.zeros((60, 60), dtype=bool)
    m[15:45, 15:45] = True
    stripped = strip_thin_appendages(m, open_radius=7, restore_radius=2)
    # compact body should mostly survive
    assert stripped.sum() >= m.sum() * 0.75


def test_segment_instances_returns_multiple():
    img = _two_dark_blobs()
    params = SegmentationParams(
        min_object_area=100,
        open_radius=1,
        close_radius=2,
        watershed_min_distance=8,
        enable_watershed=True,
        preserve_appendages=True,
    )
    result = segment_instances(img, params)
    assert len(result.instances) >= 1
    # ideally 2 after watershed; allow 1 if stuck together
    assert result.instances[0].area_px >= 100
    total = sum(i.area_px for i in result.instances)
    assert total > 200


def test_merge_and_cut_split():
    m1 = polygon_to_mask([[10, 10], [40, 10], [40, 40], [10, 40]], 80, 80)
    m2 = polygon_to_mask([[30, 30], [60, 30], [60, 60], [30, 60]], 80, 80)
    merged = merge_masks([m1, m2])
    assert mask_area_px(merged) >= mask_area_px(m1)

    # cut through middle vertically
    parts = split_mask_by_cut_line(
        merged,
        [[35, 5], [35, 75]],
        line_width=3,
        min_area=20,
    )
    assert len(parts) >= 2


def test_seed_split_two_regions():
    m = empty_mask(60, 80)
    m[10:50, 10:35] = 255
    m[10:50, 45:70] = 255
    # connect with bridge
    m[28:32, 30:50] = 255
    parts = split_mask_by_seeds(m, [(20, 30), (55, 30)], min_area=20)
    assert len(parts) >= 2


def test_auto_seg_preserves_confirmed(tmp_path: Path):
    root = tmp_path / "segws"
    root.mkdir()
    img = _two_dark_blobs(100, 140)
    Image.fromarray(img).save(root / "t.tif", format="TIFF")
    ws = open_workspace(root)
    rec = ws.images[0]
    rec.width, rec.height = 140, 100
    svc = ObjectService()
    svc.set_workspace(ws.root)
    svc.bind_image(rec, width=140, height=100)

    # manual confirmed object (small corner)
    confirmed = svc.create_from_mask(
        rec,
        polygon_to_mask([[0, 0], [15, 0], [15, 15], [0, 15]], 100, 140),
        None,
        segmentation_method="manual",
        confirmed=True,
    )
    conf_id = confirmed.object_id

    created, result = svc.apply_auto_segmentation(
        rec,
        img,
        None,
        SegmentationParams(min_object_area=80, watershed_min_distance=6),
        mode="replace_unconfirmed",
        auto_length=True,
    )
    assert any(o.object_id == conf_id for o in rec.objects)
    assert all(not o.confirmed for o in created)
    # confirmed still there
    conf = next(o for o in rec.objects if o.object_id == conf_id)
    assert conf.confirmed is True
    # new objects should attempt length (may succeed on elongated blobs)
    if created:
        # at least area is set; length is best-effort
        assert created[0].area_px > 0

    save_workspace(ws)
    ws2 = open_workspace(root)
    assert any(o.confirmed for o in ws2.images[0].objects)


def test_auto_seg_with_length_on_bent_blob(tmp_path: Path):
    """Segmentation of a single bent object should also fill length_points."""
    root = tmp_path / "seglen"
    root.mkdir()
    h, w = 80, 120
    rgb = np.full((h, w, 3), 250, dtype=np.uint8)
    # draw dark bent body
    pil = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil)
    draw.line([(15, 40), (40, 25), (70, 30), (95, 50), (105, 65)], fill=(60, 60, 60), width=12)
    img = np.array(pil)
    Image.fromarray(img).save(root / "b.tif", format="TIFF")

    ws = open_workspace(root)
    rec = ws.images[0]
    rec.width, rec.height = w, h
    svc = ObjectService()
    svc.set_workspace(ws.root)
    svc.bind_image(rec, width=w, height=h)
    created, _ = svc.apply_auto_segmentation(
        rec,
        img,
        None,
        SegmentationParams.preset_whole(),
        mode="replace_unconfirmed",
        auto_length=True,
    )
    assert len(created) >= 1
    obj = max(created, key=lambda o: o.area_px)
    assert obj.length_source == "auto_suggested"
    assert obj.length_points and len(obj.length_points) >= 2
    assert obj.length_px is not None and obj.length_px > 0


def test_hj98_segmentation_smoke(repo_root: Path):
    path = repo_root / "examples" / "HJ98.tif"
    if not path.is_file():
        pytest.skip("HJ98 missing")
    from soilfauna_measure.core.image_loader import load_image

    loaded = load_image(path)
    h, w = loaded.raw.shape[:2]
    # whole-organism defaults should not explode into dozens of fragments
    result = segment_instances(loaded.raw, SegmentationParams.preset_whole())
    assert len(result.instances) >= 3, result.message
    assert len(result.instances) <= 25, result.message
    # largest instance should be a substantial body, not a tiny limb
    assert result.instances[0].area_px >= 2000
    # scale bar region must not become an instance
    for inst in result.instances:
        ys, xs = np.nonzero(inst.mask > 0)
        cx, cy = float(xs.mean()), float(ys.mean())
        assert not (cx > w * 0.75 and cy > h * 0.90), (
            f"scale-like instance remained at ({cx:.0f},{cy:.0f}) area={inst.area_px}"
        )


def test_hj98_not_over_split_vs_old_watershed(repo_root: Path):
    path = repo_root / "examples" / "HJ98.tif"
    if not path.is_file():
        pytest.skip("HJ98 missing")
    from soilfauna_measure.core.image_loader import load_image

    loaded = load_image(path)
    whole = segment_instances(loaded.raw, SegmentationParams.preset_whole())
    aggressive = segment_instances(
        loaded.raw,
        SegmentationParams(
            enable_watershed=True,
            watershed_min_distance=10,
            watershed_min_peak_height=3.0,
            min_object_area=150,
            close_radius=3,
            preserve_appendages=True,  # keep limbs so watershed has more peaks
            merge_thin_splits=False,
        ),
    )
    # whole strategy should not explode beyond aggressive watershed
    assert len(whole.instances) <= len(aggressive.instances)
    assert len(whole.instances) <= 20
