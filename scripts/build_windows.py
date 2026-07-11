#!/usr/bin/env python3
"""Build a standalone Windows app with bundled Python runtime (PyInstaller).

IMPORTANT
---------
- Must run **on Windows** (PySide6/Qt cannot be reliably cross-built from macOS).
- Output does **not** require the end user to install Python.

Usage (on Windows):

    python -m venv .venv
    .venv\\Scripts\\activate
    python -m pip install -U pip
    pip install -e ".[packaging]"

    # Folder (exe + _internal, fast start):
    python scripts/build_windows.py

    # Single-file .exe (slower first launch):
    python scripts/build_windows.py --onefile

    # Setup installer (onedir + Inno Setup → one Setup.exe):
    #   1) Install Inno Setup 6: https://jrsoftware.org/isinfo.php
    #   2) Then:
    python scripts/build_windows.py --installer

Results:

    onedir:     dist\\SoilFaunaMeasure\\  (exe + _internal)
    onefile:    dist\\SoilFaunaMeasure.exe
    installer:  dist\\SoilFaunaMeasure-Setup-x.y.z.exe
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "scripts" / "SoilFaunaMeasure.spec"
ISS = ROOT / "scripts" / "installer" / "SoilFaunaMeasure.iss"
NAME = "SoilFaunaMeasure"
ICONS = ROOT / "src" / "soilfauna_measure" / "resources" / "icons"


def _app_version() -> str:
    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        if m:
            return m.group(1)
    return "0.8.0"


def _ensure_ico() -> Path | None:
    """Create app_icon.ico from PNG if Pillow available (Windows likes .ico)."""
    ico = ICONS / "app_icon.ico"
    if ico.is_file():
        return ico
    png = ICONS / "app_icon_256.png"
    if not png.is_file():
        png = ICONS / "logo.png"
    if not png.is_file():
        return None
    try:
        from PIL import Image

        im = Image.open(png).convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        im.save(ico, format="ICO", sizes=sizes)
        print("Created", ico)
        return ico
    except Exception as exc:  # noqa: BLE001
        print("ICO create skipped:", exc)
        return None


def _write_user_readme(path: Path, *, onefile: bool) -> None:
    lines = [
        "土衡 / SoilFauna Measure — Windows 独立版",
        "",
        "1. 双击 SoilFaunaMeasure.exe 启动（无需安装 Python）。",
        "2. 首次使用：文件 → 打开工作区，选择含图片的文件夹。",
        "3. 详细说明见「用户说明.md」（若随包提供）。",
    ]
    if onefile:
        lines += [
            "4. 本包为单文件版：首次启动可能稍慢（解压运行库到临时目录）。",
            "5. 杀毒软件若误报，请添加信任（未代码签名时较常见）。",
        ]
    else:
        lines += [
            "4. 请勿删除本目录下的 _internal 文件夹（程序运行依赖它）。",
            "5. 杀毒软件若误报，请添加信任（未代码签名时较常见）。",
        ]
    lines += [
        "",
        "示例图可从源码仓库 examples/HJ98.tif 复制使用。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _copy_release_extras(dist_dir: Path, *, onefile: bool) -> None:
    """Copy readme / guide into the release location."""
    extras = [
        (ROOT / "docs" / "USER_GUIDE.md", dist_dir / "用户说明.md"),
    ]
    for src, dst in extras:
        if src.is_file():
            shutil.copy2(src, dst)
    _write_user_readme(dist_dir / "使用前请读.txt", onefile=onefile)


def _find_iscc() -> Path | None:
    """Locate Inno Setup compiler ISCC.exe."""
    env = os.environ.get("SFM_ISCC") or os.environ.get("ISCC")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    which = shutil.which("ISCC") or shutil.which("iscc")
    if which:
        return Path(which)
    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 5\ISCC.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _sync_iss_version(version: str) -> None:
    """Write MyAppVersion in the .iss to match pyproject.toml."""
    if not ISS.is_file():
        return
    text = ISS.read_text(encoding="utf-8")
    new = re.sub(
        r'(#define\s+MyAppVersion\s+)"[^"]*"',
        rf'\1"{version}"',
        text,
        count=1,
    )
    if new != text:
        ISS.write_text(new, encoding="utf-8")
        print(f"Synced installer version → {version}")


def _build_installer() -> int:
    """Compile Inno Setup installer from onedir output."""
    dist_dir = ROOT / "dist" / NAME
    exe = dist_dir / f"{NAME}.exe"
    if not exe.is_file():
        print(
            f"Missing {exe}\n"
            "Run onedir build first, or use --installer (builds onedir automatically).",
            file=sys.stderr,
        )
        return 1
    if not ISS.is_file():
        print("Missing Inno script:", ISS, file=sys.stderr)
        return 1

    version = _app_version()
    _sync_iss_version(version)

    iscc = _find_iscc()
    if iscc is None:
        print(
            "未找到 Inno Setup 编译器 ISCC.exe。\n"
            "请安装 Inno Setup 6（免费）：\n"
            "  https://jrsoftware.org/isinfo.php\n"
            "安装后重新运行，或设置环境变量：\n"
            "  set SFM_ISCC=C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe\n",
            file=sys.stderr,
        )
        return 1

    print("Using ISCC:", iscc)
    cmd = [str(iscc), "/Q", str(ISS)]
    # Non-quiet if user wants logs — keep quiet for cleaner CI; print path after
    cmd = [str(iscc), str(ISS)]
    print("Running:", " ".join(cmd))
    r = subprocess.call(cmd)
    if r != 0:
        print("Inno Setup compile failed", file=sys.stderr)
        return r

    setup = ROOT / "dist" / f"SoilFaunaMeasure-Setup-{version}.exe"
    # Also match any Setup-*.exe if version string differs
    if not setup.is_file():
        candidates = sorted((ROOT / "dist").glob("SoilFaunaMeasure-Setup-*.exe"))
        if candidates:
            setup = candidates[-1]

    print("\n======== INSTALLER OK ========")
    if setup.is_file():
        size_mb = setup.stat().st_size / (1024 * 1024)
        print(f"Installer: {setup}")
        print(f"Size:      {size_mb:.1f} MB")
    else:
        print(f"Look for Setup exe under: {ROOT / 'dist'}")
    print(
        "\n用户侧流程：\n"
        "  1. 双击 Setup.exe\n"
        "  2. 选择安装路径\n"
        "  3. （可选）创建桌面快捷方式\n"
        "  4. 安装完成后从桌面/开始菜单启动\n"
        "安装后的程序仍是「exe + _internal」结构，启动速度快。\n"
    )
    return 0


def _run_pyinstaller(*, onefile: bool) -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Missing PyInstaller. Run:\n  pip install pyinstaller\n", file=sys.stderr)
        return 1

    _ensure_ico()

    if not SPEC.is_file():
        print("Missing spec:", SPEC, file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["SFM_ONEFILE"] = "1" if onefile else "0"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    mode = "onefile (single .exe)" if onefile else "onedir (exe + _internal folder)"
    print("Mode:", mode)
    print("Running:", " ".join(cmd))
    print("Working directory:", ROOT)
    r = subprocess.call(cmd, cwd=str(ROOT), env=env)
    if r != 0:
        return r

    if onefile:
        exe = ROOT / "dist" / f"{NAME}.exe"
        if exe.is_file():
            side = ROOT / "dist"
            _write_user_readme(side / "使用前请读.txt", onefile=True)
            guide = ROOT / "docs" / "USER_GUIDE.md"
            if guide.is_file():
                shutil.copy2(guide, side / "用户说明.md")
            print("\n======== BUILD OK (onefile) ========")
            print(f"Single executable: {exe}")
            print(
                "\nYou can send just SoilFaunaMeasure.exe "
                "(optionally zip with 使用前请读.txt).\n"
                "Note: first launch may be slower while libraries extract to a temp folder.\n"
            )
            return 0
        print("Build finished but exe not found:", exe, file=sys.stderr)
        return 1

    dist_dir = ROOT / "dist" / NAME
    if dist_dir.is_dir():
        _copy_release_extras(dist_dir, onefile=False)
        exe = dist_dir / f"{NAME}.exe"
        print("\n======== BUILD OK (onedir) ========")
        print(f"Folder: {dist_dir}")
        if exe.is_file():
            print(f"Launch: {exe}")
        print(
            "\nDistribute the WHOLE folder (or zip it), or build an installer:\n"
            "  python scripts\\build_windows.py --installer\n"
            "The _internal folder next to the .exe is required for onedir layout.\n"
        )
        return 0
    print("Build finished but dist folder not found:", dist_dir, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Windows standalone app")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single .exe (slower cold start). Default is onedir folder.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Build onedir then compile Inno Setup installer (Setup.exe + desktop icon).",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Only compile Inno Setup (requires existing dist\\SoilFaunaMeasure\\).",
    )
    args = parser.parse_args(argv)

    if args.onefile and (args.installer or args.installer_only):
        print("Cannot combine --onefile with --installer (installer uses onedir).", file=sys.stderr)
        return 2

    if sys.platform != "win32":
        print(
            "WARNING: You are not on Windows.\n"
            "PySide6 GUI apps should be packaged ON a Windows machine.\n"
            "Cross-build from macOS/Linux often fails or produces broken Qt apps.\n"
            "Continuing only if you know what you are doing...\n",
            file=sys.stderr,
        )

    if args.installer_only:
        return _build_installer()

    if args.installer:
        # Always onedir for installer (fast runtime start after install)
        r = _run_pyinstaller(onefile=False)
        if r != 0:
            return r
        return _build_installer()

    return _run_pyinstaller(onefile=args.onefile)


if __name__ == "__main__":
    raise SystemExit(main())
