"""Image / view coordinate helpers (pure functions)."""

from __future__ import annotations

from typing import Tuple


def clamp_to_image(
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    inclusive_max: bool = False,
) -> Tuple[float, float]:
    """Clamp continuous coordinates to the image bounds.

    By default x in [0, width-eps], y in [0, height-eps] for pixel sampling
    friendliness when converting to integer indices later.
    If ``inclusive_max`` is True, clamp to [0, width] / [0, height].
    """
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    if inclusive_max:
        cx = min(max(float(x), 0.0), float(width))
        cy = min(max(float(y), 0.0), float(height))
    else:
        max_x = max(float(width) - 1e-6, 0.0)
        max_y = max(float(height) - 1e-6, 0.0)
        cx = min(max(float(x), 0.0), max_x)
        cy = min(max(float(y), 0.0), max_y)
    return cx, cy


def pixel_distance(x0: float, y0: float, x1: float, y1: float) -> float:
    """Euclidean distance between two image points."""
    dx = float(x1) - float(x0)
    dy = float(y1) - float(y0)
    return (dx * dx + dy * dy) ** 0.5
