@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0\.."

echo ============================================
echo  土衡 SoilFauna Measure — Windows 打包
echo  将生成自带 Python 运行时的独立程序
echo  用户电脑无需安装 Python
echo ============================================
echo.
echo  模式选择:
echo    [1] 文件夹版 onedir （推荐绿色分发）
echo        输出: dist\SoilFaunaMeasure\
echo    [2] 单文件版 onefile
echo        输出: dist\SoilFaunaMeasure.exe
echo    [3] 安装包 Setup.exe （推荐给最终用户）
echo        先打 onedir，再用 Inno Setup 生成安装器
echo        用户可选路径、桌面图标；安装后启动快
echo.
set MODE=3
set /p MODE="请选择 1 / 2 / 3 [默认 3]: "
if "%MODE%"=="" set MODE=3

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python。请先安装 Python 3.10+ 并勾选 Add to PATH。
  echo 下载: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo [1/4] 创建/使用虚拟环境 .venv ...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo [2/4] 安装项目依赖与 PyInstaller ...
python -m pip install -U pip setuptools wheel
pip install -e ".[packaging]"
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

echo [3/4] 开始打包（可能需要几分钟，体积约数百 MB）...
if "%MODE%"=="2" (
  python scripts\build_windows.py --onefile
) else if "%MODE%"=="3" (
  echo 安装包模式需要本机已安装 Inno Setup 6
  echo 下载: https://jrsoftware.org/isinfo.php
  echo.
  python scripts\build_windows.py --installer
) else (
  python scripts\build_windows.py
)
if errorlevel 1 (
  echo [错误] 打包失败
  pause
  exit /b 1
)

echo [4/4] 完成
echo.
if "%MODE%"=="2" (
  echo 单文件输出:
  echo   %CD%\dist\SoilFaunaMeasure.exe
) else if "%MODE%"=="3" (
  echo 安装包输出:
  echo   %CD%\dist\SoilFaunaMeasure-Setup-*.exe
  echo.
  echo 把该 Setup.exe 发给用户即可：
  echo   选择安装路径 → 释放程序文件 → 创建桌面快捷方式。
) else (
  echo 文件夹输出:
  echo   %CD%\dist\SoilFaunaMeasure\
  echo.
  echo 请将整个 SoilFaunaMeasure 文件夹压缩发给用户。
)
echo.
pause
endlocal
