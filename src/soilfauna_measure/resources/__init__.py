"""Application resources (icons, etc.)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap


def resources_dir() -> Path:
    return Path(__file__).resolve().parent


def icons_dir() -> Path:
    return resources_dir() / "icons"


def icon_path(name: str = "logo.png") -> Path:
    return icons_dir() / name


def load_app_icon() -> QIcon:
    """Load multi-resolution application icon."""
    icon = QIcon()
    d = icons_dir()
    found = False
    for size in (16, 32, 48, 64, 128, 256, 512):
        p = d / f"app_icon_{size}.png"
        if p.is_file():
            icon.addFile(str(p), QSize(size, size))
            found = True
    logo = d / "logo.png"
    if logo.is_file():
        icon.addFile(str(logo), QSize(256, 256))
        found = True
    if not found:
        return QIcon()
    return icon


def load_logo_pixmap(max_side: int = 128) -> QPixmap | None:
    p = icon_path("logo.png")
    if not p.is_file():
        return None
    pix = QPixmap(str(p))
    if pix.isNull():
        return None
    if max(pix.width(), pix.height()) > max_side:
        pix = pix.scaled(
            max_side,
            max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pix
