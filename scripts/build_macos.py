#!/usr/bin/env python3
"""Build macOS app directory with PyInstaller (unsigned)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "soilfauna_measure" / "main.py"
NAME = "SoilFaunaMeasure"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Please: pip install pyinstaller", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        NAME,
        "--paths",
        str(ROOT / "src"),
        "--collect-all",
        "PySide6",
        "--collect-all",
        "skimage",
        "--onedir",
        str(ENTRY),
    ]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
