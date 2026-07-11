# Windows 打包环境准备清单（全新机器）

本文面向：**一台全新 Windows、尚未安装 Python**，要在本机打出「土衡 / SoilFauna Measure」独立版（文件夹 / 安装包）。

> 打包**必须在 Windows 上完成**，不能在 macOS 上交叉编译 Qt 程序。  
> 更完整的产物说明见 [PACKAGING.md](./PACKAGING.md)。

---

## 一、系统软件（先装这些）

| 软件 | 是否必须 | 说明 |
|------|----------|------|
| Windows 10/11 **64 位** | 必须 | |
| 磁盘空间 | 必须 | 建议预留 **≥ 5 GB**（虚拟环境 + 依赖 + 打包产物） |
| 网络 | 必须 | 用于 `pip install` 下载依赖 |
| **Python 3.10+**（推荐 3.11 / 3.12，Windows 64-bit） | 必须 | [官网下载](https://www.python.org/downloads/windows/) |
| **pip** | 必须 | 随 Python 安装自带 |
| **Inno Setup 6** | 仅做安装包时必须 | [下载](https://jrsoftware.org/isinfo.php)；只要绿色文件夹可跳过 |

### Python 安装注意

安装时务必勾选：

- **Add python.exe to PATH**

装完后在 **cmd** 或 **PowerShell** 中验证：

```bat
python --version
pip --version
```

能显示版本即可。

### 不需要单独安装的

按当前默认打包流程，**不必**安装：

- Visual Studio / MSVC（一般不需要）
- Anaconda / Miniconda（可用官方 Python 即可）
- Node.js、Java 等

---

## 二、项目源码

将源码拷到本机，例如：

```text
C:\work\soilfauna-measure
```

**不要**从 Mac 拷带 `.venv` 的整夹（体积巨大且跨平台不可用）。源码本身通常只有数 MB。

可删除/忽略的本地垃圾（若存在）：

| 路径 | 说明 |
|------|------|
| `.venv/` | 虚拟环境（在 Windows 上重新建） |
| `.pytest_cache/` | 测试缓存 |
| `dist/`、`build/` | 旧打包产物 |
| `__pycache__/`、`*.egg-info/` | 缓存 |

---

## 三、Python 库（完整清单）

### 推荐：一条命令装齐（运行依赖 + 打包工具）

```bat
cd C:\work\soilfauna-measure
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
pip install -e ".[packaging]"
```

这对应 `pyproject.toml` 中的配置，具体如下。

### 1. 项目运行依赖（`dependencies`）

| 库 | 版本要求 | 用途 |
|----|----------|------|
| **PySide6_Essentials** | ≥ 6.6 | 图形界面（仅 Essentials，不含 WebEngine/3D 等 Addons） |
| **numpy** | ≥ 1.24 | 数组 / 图像数据 |
| **tifffile** | ≥ 2023.1.0 | 读取 TIFF |
| **Pillow** | ≥ 10.0 | 缩略图、图像处理 |
| **scikit-image** | ≥ 0.22 | 分割、形态学、骨架等 |
| **scipy** | ≥ 1.11 | 距离变换；且为 scikit-image 硬依赖 |
| **openpyxl** | ≥ 3.1 | Excel 导出（已不用 pandas） |

### 2. 打包专用（`[project.optional-dependencies] packaging`）

| 库 | 版本要求 | 用途 |
|----|----------|------|
| **pyinstaller** | ≥ 6.0 | 打成 exe / 文件夹，供安装器打包 |

### 3. 安装/构建辅助（建议显式升级）

| 库 | 用途 |
|----|------|
| **pip** | 包管理 |
| **setuptools** | `pip install -e .` 安装本项目 |
| **wheel** | 构建/安装辅助 |

### 4. 传递依赖（pip 自动安装，不必手写）

执行 `pip install -e ".[packaging]"` 时会自动拉取，例如：

| 来源 | 常见传递依赖（示例） |
|------|----------------------|
| PySide6_Essentials | `shiboken6` 等（勿再装完整 PySide6 / Addons） |
| scikit-image | `networkx`、`imageio`、`lazy_loader`、`packaging` 等 |
| PyInstaller | `altgraph`、`pefile`、`pywin32-ctypes` 等 |
| numpy / scipy | 平台二进制运行时 |

**无需**逐个 `pip install` 上述传递依赖。

---

## 四、可选库（打包默认不需要）

| 库 | 安装方式 | 何时需要 |
|----|----------|----------|
| **opencv-python-headless** | `pip install -e ".[full]"` | 使用 full 额外能力时 |
| **pytest** | `pip install -e ".[dev]"` | 开发跑单元测试 |
| **pytest-qt** | 同上 | Qt 相关测试 |

给最终用户打安装包 / 绿色版时：**不必装 dev / full**。

---

## 五、与「完整清单」对应关系

```text
【系统】
  Windows 10/11 x64
  Python 3.10+（勾选 PATH）
  Inno Setup 6          ← 仅生成 Setup 安装包时需要

【pip 必须】
  setuptools, wheel
  PySide6_Essentials
  numpy
  tifffile
  Pillow
  scikit-image
  scipy
  openpyxl
  pyinstaller

【一条命令】
  pip install -e ".[packaging]"
```

---

## 六、一条龙打包命令

### 方式 A：批处理（推荐）

```bat
cd C:\work\soilfauna-measure
scripts\build_windows.bat
```

按提示选择：

| 选项 | 产物 | 说明 |
|------|------|------|
| **1** | `dist\SoilFaunaMeasure\` | 绿色文件夹（exe + `_internal`） |
| **2** | `dist\SoilFaunaMeasure.exe` | 单文件（启动较慢） |
| **3** | `dist\SoilFaunaMeasure-Setup-*.exe` | **安装包（推荐）**，需已装 Inno Setup |

脚本会自动创建 `.venv` 并执行 `pip install -e ".[packaging]"`。

### 方式 B：手动命令

```bat
cd C:\work\soilfauna-measure

python -m venv .venv
.venv\Scripts\activate

python -m pip install -U pip setuptools wheel
pip install -e ".[packaging]"

REM 文件夹版
python scripts\build_windows.py

REM 或安装包（推荐）
python scripts\build_windows.py --installer

REM 或单文件版
python scripts\build_windows.py --onefile
```

若 Inno 不在默认路径：

```bat
set SFM_ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
python scripts\build_windows.py --installer
```

---

## 七、产物与发给用户什么

| 模式 | 路径 | 发给用户 |
|------|------|----------|
| 安装包 | `dist\SoilFaunaMeasure-Setup-0.x.x.exe` | **只发这一个 Setup** |
| 文件夹版 | `dist\SoilFaunaMeasure\` | **整个文件夹** zip（含 `_internal`） |
| 单文件 | `dist\SoilFaunaMeasure.exe` | 可只发 exe（启动慢） |

用户电脑**不需要**安装 Python。

安装包用户流程：双击 Setup → 选安装路径 →（可选）桌面快捷方式 → 启动。安装后仍是「exe + `_internal`」，启动快。

---

## 八、准备进度打勾表

| 步骤 | 必须？ | 完成 |
|------|--------|------|
| Win10/11 x64 | 是 | ☐ |
| 安装 Python 3.10+ 并勾选 PATH | 是 | ☐ |
| `python --version` / `pip --version` 正常 | 是 | ☐ |
| 拷贝项目源码（无旧 `.venv`） | 是 | ☐ |
| 能联网 | 是 | ☐ |
| `pip install -e ".[packaging]"` 成功 | 是 | ☐ |
| 安装 Inno Setup 6 | 仅安装包 | ☐ |
| 运行 `build_windows.bat` 或 `build_windows.py` | 是 | ☐ |
| 在干净环境试运行产物 | 建议 | ☐ |

---

## 九、常见问题

**Q: 还要一个个 `pip install` 哪些库？**  
A: 不用。只需：

```bat
pip install -e ".[packaging]"
```

**Q: 没勾选 Add to PATH？**  
A: 重装 Python 并勾选，或手动把 Python 安装目录和 `Scripts` 加入系统 PATH。

**Q: pip 很慢 / 超时？**  
A: 可使用国内镜像，例如：

```bat
pip install -e ".[packaging]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Q: 杀软拦截打包结果？**  
A: 对项目目录 / `dist` 加白名单；未签名的 PyInstaller 程序常见误报。

**Q: 能在 Mac 上打 Windows 包吗？**  
A: 不能可靠完成。请在 Windows 实体机或虚拟机上打包。

---

## 十、相关文档

| 文档 | 内容 |
|------|------|
| [PACKAGING.md](./PACKAGING.md) | 打包模式、产物结构、安装器说明 |
| [USER_GUIDE.md](./USER_GUIDE.md) | 最终用户操作说明 |
| 项目根目录 `README.md` | 总览与快速入口 |

---

*与 `pyproject.toml` 版本对应；依赖变更时请以 `pyproject.toml` 为准。*
