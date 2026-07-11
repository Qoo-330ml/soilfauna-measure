# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows (and macOS) builds.

Default: **onedir** (folder with .exe + _internal) — recommended.

Single-file: set env SFM_ONEFILE=1 before running pyinstaller, or:

    python scripts/build_windows.py --onefile

Build on the TARGET OS:

    pyinstaller scripts/SoilFaunaMeasure.spec
    python scripts/build_windows.py
"""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent.parent  # scripts/ -> repo root
SRC = ROOT / "src"
ICONS = SRC / "soilfauna_measure" / "resources" / "icons"
ENTRY = SRC / "soilfauna_measure" / "main.py"
NAME = "SoilFaunaMeasure"

# onefile when SFM_ONEFILE=1 (set by build_windows.py --onefile)
ONEFILE = os.environ.get("SFM_ONEFILE", "0").strip() in ("1", "true", "True", "yes")

datas = []
binaries = []
hiddenimports = [
    "soilfauna_measure",
    "soilfauna_measure.main",
    # image / science stack often needs a few explicit names
    "skimage.filters",
    "skimage.measure",
    "skimage.morphology",
    "skimage.segmentation",
    "skimage.feature",
    "skimage.color",
    "skimage.util",
    "scipy.ndimage",
]

# Avoid collect_all("PySide6") — it pulls WebEngine/3D/Multimedia and bloats hundreds of MB.
# Only collect data files for skimage (algorithms + data assets); let PyInstaller hooks
# resolve the rest of numpy/scipy/PySide6.
for pkg in ("skimage",):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

if ICONS.is_dir():
    datas.append((str(ICONS), "soilfauna_measure/resources/icons"))

guide = ROOT / "docs" / "USER_GUIDE.md"
if guide.is_file():
    datas.append((str(guide), "docs"))

icon_file = None
for cand in (
    ICONS / "app_icon.ico",
    ICONS / "app_icon_256.png",
    ICONS / "logo.png",
):
    if cand.is_file():
        icon_file = str(cand)
        break

# App only imports: QtCore / QtGui / QtWidgets.
# Prefer PySide6_Essentials at pip time; still exclude leftover Addons + unused Essentials.
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "IPython",
    "notebook",
    "jupyter",
    "pytest",
    "pytest_qt",
    "pandas",
    "sklearn",
    "torch",
    "tensorflow",
    "cv2",
    "opencv",
    # --- Qt Addons (not needed; large if full PySide6 was installed) ---
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtRemoteObjects",
    "PySide6.QtTextToSpeech",
    "PySide6.QtHttpServer",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    # --- Essentials modules we do not import ---
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtXml",
    "PySide6.QtDBus",
    "PySide6.QtConcurrent",
]

block_cipher = None

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if ONEFILE:
    # Single .exe: all libs packed inside. First launch extracts to temp (slower).
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
else:
    # Folder layout: SoilFaunaMeasure.exe + _internal/  (recommended)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=NAME,
    )
