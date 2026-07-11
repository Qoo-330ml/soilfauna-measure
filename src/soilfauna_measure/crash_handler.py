"""Crash logging and emergency autosave hooks."""

from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_emergency_save: Callable[[], None] | None = None
_log_dir: Path | None = None


def default_log_dir() -> Path:
    home = Path.home()
    # Prefer app support on macOS; generic on others
    base = home / ".soilfauna-measure" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def set_emergency_save(fn: Callable[[], None] | None) -> None:
    global _emergency_save
    _emergency_save = fn


def install_crash_handler(log_dir: Path | None = None) -> Path:
    """Install sys.excepthook that writes a crash log and tries emergency save."""
    global _log_dir
    _log_dir = Path(log_dir) if log_dir else default_log_dir()
    _log_dir.mkdir(parents=True, exist_ok=True)

    def _hook(exc_type, exc, tb):  # noqa: ANN001
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = _log_dir / f"crash_{stamp}.log"
            text = "".join(traceback.format_exception(exc_type, exc, tb))
            path.write_text(text, encoding="utf-8")
            logger.critical("Uncaught exception written to %s\n%s", path, text)
        except Exception:  # noqa: BLE001
            pass
        try:
            if _emergency_save is not None:
                _emergency_save()
        except Exception:  # noqa: BLE001
            pass
        # Chain to default
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    return _log_dir


def write_session_note(message: str, log_dir: Path | None = None) -> Path:
    d = Path(log_dir) if log_dir else default_log_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "session.log"
    stamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message}\n")
    return path
