"""Automatic scale-bar detection for microscope / stereoscope images.

Detects a dark horizontal scale line (typically bottom-right) and tries to
parse the printed real length (e.g. ``1000μm``). Results are suggestions
(``method=auto_pending``) and require user confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from skimage import filters, measure, morphology, util

from soilfauna_measure.core.calibration import (
    CalibrationError,
    build_scale_calibration,
    normalize_unit,
)
from soilfauna_measure.models.calibration import ScaleCalibration


@dataclass
class ScaleDetectionResult:
    """Outcome of automatic scale detection."""

    found: bool
    start_point: list[float] | None = None
    end_point: list[float] | None = None
    pixel_length: float = 0.0
    real_length: float | None = None
    unit: str | None = None
    label_text: str = ""
    confidence: float = 0.0  # 0..1
    message: str = ""
    method: str = "auto_line"

    def to_calibration(self, *, confirmed: bool = False) -> ScaleCalibration | None:
        if not self.found or self.start_point is None or self.end_point is None:
            return None
        if self.real_length is None or self.unit is None or self.pixel_length <= 0:
            return None
        try:
            return build_scale_calibration(
                self.start_point,
                self.end_point,
                float(self.real_length),
                str(self.unit),
                method="auto_pending" if not confirmed else "auto_confirmed",
                confirmed=confirmed,
            )
        except CalibrationError:
            return None


class ScaleDetectionError(Exception):
    """Controlled detection failure."""


_LABEL_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>μm|µm|um|mm|cm|μ|u|m)",
    re.IGNORECASE,
)


def _to_gray_float(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        g = image.astype(np.float64)
    elif image.ndim == 3:
        g = image[..., :3].astype(np.float64).mean(axis=2)
    else:
        raise ScaleDetectionError(f"Unsupported image shape {image.shape}")
    # normalize to 0..1-ish
    if g.max() > 1.5:
        g = g / 255.0
    return g


def _footprint_rect(h: int, w: int):
    try:
        return morphology.footprint_rectangle((h, w))
    except Exception:  # noqa: BLE001
        return morphology.rectangle(h, w)


def detect_horizontal_scale_line(
    image: np.ndarray,
    *,
    search_regions: list[str] | None = None,
) -> tuple[list[float], list[float], float, str] | None:
    """Find the best horizontal scale bar segment.

    Returns (start_xy, end_xy, length_px, region_name) or None.
    """
    gray = _to_gray_float(image)
    h, w = gray.shape
    regions = search_regions or ["bottom_right", "bottom", "bottom_left"]

    candidates: list[tuple[float, list[float], list[float], str]] = []

    def _scan_roi(y0: int, y1: int, x0: int, x1: int, name: str) -> None:
        if y1 <= y0 or x1 <= x0:
            return
        roi = gray[y0:y1, x0:x1]
        if roi.size < 50:
            return
        # dark on light
        try:
            thr = filters.threshold_otsu(roi)
        except ValueError:
            thr = float(np.median(roi))
        dark = roi < min(thr, 0.45 if thr <= 1.5 else thr)
        # enhance horizontal structures
        se = _footprint_rect(1, max(9, min(25, (x1 - x0) // 20)))
        try:
            horiz = morphology.opening(dark, se)
            horiz = morphology.closing(horiz, _footprint_rect(1, 5))
        except Exception:  # noqa: BLE001
            horiz = dark

        lab = measure.label(horiz)
        if lab.max() == 0:
            # fallback: longest dark run per row
            best_run = None
            for yy in range(horiz.shape[0]):
                row = dark[yy]
                i = 0
                while i < row.size:
                    if not row[i]:
                        i += 1
                        continue
                    j = i
                    while j < row.size and row[j]:
                        j += 1
                    length = j - i
                    if best_run is None or length > best_run[0]:
                        best_run = (length, yy, i, j)
                    i = j
            if best_run and best_run[0] >= 40:
                L, yy, xa, xb = best_run
                sx, sy = x0 + xa, y0 + yy
                ex, ey = x0 + xb - 1, y0 + yy
                score = float(L)
                candidates.append((score, [float(sx), float(sy)], [float(ex), float(ey)], name))
            return

        props = measure.regionprops(lab)
        for p in props:
            # prefer long thin nearly-horizontal
            try:
                maj = float(getattr(p, "axis_major_length", None) or p.major_axis_length)
                mnr = float(getattr(p, "axis_minor_length", None) or p.minor_axis_length)
            except Exception:  # noqa: BLE001
                continue
            if maj < 40 or mnr < 0.5:
                continue
            if mnr > 12:  # too thick — likely not a scale line
                continue
            aspect = maj / max(mnr, 1e-6)
            if aspect < 4.0:
                continue
            minr, minc, maxr, maxc = p.bbox
            # use bbox horizontal extent as pixel length (stable for bars)
            width = maxc - minc
            if width < 40:
                continue
            cy = (minr + maxr) / 2.0
            sx, sy = x0 + minc, y0 + cy
            ex, ey = x0 + maxc - 1, y0 + cy
            # score: long, thin, lower-right preference
            pos_bonus = 1.0
            if name == "bottom_right":
                pos_bonus = 1.4
            elif name == "bottom":
                pos_bonus = 1.15
            score = width * aspect * pos_bonus
            candidates.append(
                (score, [float(sx), float(sy)], [float(ex), float(ey)], name)
            )

    for name in regions:
        if name == "bottom_right":
            _scan_roi(int(h * 0.82), h, int(w * 0.55), w, name)
        elif name == "bottom_left":
            _scan_roi(int(h * 0.82), h, 0, int(w * 0.45), name)
        elif name == "bottom":
            _scan_roi(int(h * 0.88), h, int(w * 0.15), int(w * 0.85), name)
        elif name == "full_bottom":
            _scan_roi(int(h * 0.85), h, 0, w, name)

    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[0])
    _, start, end, reg = candidates[0]
    length = float(np.hypot(end[0] - start[0], end[1] - start[1]))
    return start, end, length, reg


def parse_scale_label_text(text: str) -> tuple[float, str] | None:
    """Parse strings like '1000μm', '1 mm', '0.5mm' into (value, unit)."""
    if not text:
        return None
    # normalize micro signs
    t = (
        text.replace("μ", "u")
        .replace("µ", "u")
        .replace("μ", "u")
        .replace(" ", "")
    )
    # common glued forms
    t = t.replace("um", "um").replace("μm", "um")
    m = _LABEL_RE.search(text.replace("μ", "u").replace("µ", "u"))
    if not m:
        # try digits only near um/mm keywords
        m2 = re.search(r"(\d+(?:\.\d+)?)", text)
        if m2 and re.search(r"u|μ|µ|mm|cm", text, re.I):
            num = float(m2.group(1))
            if re.search(r"mm", text, re.I):
                return num, "mm"
            if re.search(r"cm", text, re.I):
                return num, "cm"
            return num, "um"
        return None
    num = float(m.group("num"))
    unit_raw = m.group("unit").lower().replace("μ", "u").replace("µ", "u")
    if unit_raw in {"u", "um", "μm", "µm"}:
        unit = "um"
    elif unit_raw == "mm":
        unit = "mm"
    elif unit_raw == "cm":
        unit = "cm"
    elif unit_raw == "m":
        # ambiguous micron vs meter; prefer um if number large
        unit = "um" if num >= 10 else "m"
        if unit == "m":
            num = num * 100  # store as cm? better convert to um
            return num * 1_000_000, "um"
    else:
        unit = "um"
    try:
        unit = normalize_unit(unit)
    except Exception:  # noqa: BLE001
        unit = "um"
    if unit not in {"um", "mm", "cm"}:
        unit = "um"
    return num, unit


def _ocr_scale_label(
    image: np.ndarray,
    start: list[float],
    end: list[float],
) -> tuple[str, float]:
    """Optional OCR near the bar. Returns (text, confidence)."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", 0.0

    gray = _to_gray_float(image)
    h, w = gray.shape
    y = int(round((start[1] + end[1]) / 2))
    x0 = int(min(start[0], end[0]))
    x1 = int(max(start[0], end[0]))
    # crop band above/below bar
    pad_x = max(20, int((x1 - x0) * 0.15))
    y0 = max(0, y - 45)
    y1 = min(h, y + 55)
    xa = max(0, x0 - pad_x)
    xb = min(w, x1 + pad_x)
    crop = gray[y0:y1, xa:xb]
    if crop.size == 0:
        return "", 0.0
    # to uint8
    c8 = util.img_as_ubyte(np.clip(crop, 0, 1))
    # invert for dark text on white
    inv = 255 - c8
    pil = Image.fromarray(inv)
    try:
        text = pytesseract.image_to_string(
            pil,
            config="--psm 7 -c tessedit_char_whitelist=0123456789.umμmµmmcmUMμ",
        )
    except Exception:  # noqa: BLE001
        return "", 0.0
    text = (text or "").strip()
    conf = 0.7 if text else 0.0
    return text, conf


def _heuristic_label_from_dataset() -> tuple[float, str, float, str]:
    """Fallback when OCR unavailable: common soil-fauna plate labeling."""
    return 1000.0, "um", 0.35, "heuristic_1000um"


def detect_scale(
    image: np.ndarray,
    *,
    default_real: float | None = 1000.0,
    default_unit: str = "um",
) -> ScaleDetectionResult:
    """Detect scale bar line + label; return suggestion for user confirm."""
    line = detect_horizontal_scale_line(image)
    if line is None:
        return ScaleDetectionResult(
            found=False,
            message="未找到比例尺横线（请检查右下角/底部是否有清晰刻度线）",
            confidence=0.0,
        )
    start, end, px_len, region = line
    text, ocr_conf = _ocr_scale_label(image, start, end)
    parsed = parse_scale_label_text(text) if text else None

    real: float | None
    unit: str | None
    conf: float
    label_src: str

    if parsed is not None:
        real, unit = parsed
        conf = max(0.55, ocr_conf)
        label_src = f"ocr:{text}"
    elif default_real is not None:
        # line found but no OCR — use default suggestion (user must confirm)
        real, unit = float(default_real), normalize_unit(default_unit)
        conf = 0.45
        label_src = f"default:{real:g}{unit}"
        if not text:
            text = f"{real:g}{unit}"
    else:
        return ScaleDetectionResult(
            found=True,
            start_point=start,
            end_point=end,
            pixel_length=px_len,
            real_length=None,
            unit=None,
            label_text=text,
            confidence=0.4,
            message=f"找到比例尺线段 {px_len:.1f} px（{region}），但未能识别文字，请手动输入真实长度",
            method="auto_line",
        )

    msg = (
        f"识别到比例尺：{px_len:.1f} px ≈ {real:g} {unit} "
        f"（区域 {region}，置信度 {conf:.0%}，{label_src}）"
    )
    return ScaleDetectionResult(
        found=True,
        start_point=start,
        end_point=end,
        pixel_length=px_len,
        real_length=real,
        unit=unit,
        label_text=text or f"{real:g}{unit}",
        confidence=conf,
        message=msg,
        method="auto_line+label",
    )
