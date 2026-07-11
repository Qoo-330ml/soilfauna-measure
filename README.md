# 土衡 / SoilFauna Measure

土壤动物图像分割与形态测量系统（离线桌面应用）。

**英文名**：SoilFauna Measure  
**仓库**：`soilfauna-measure`

## 当前进度

- **Milestone 1**：项目骨架 + 工作区图片查看器（缩放/平移/切图）
- **Milestone 2**：`project.sfm.json` 存盘恢复 + 手动比例尺校准（默认 µm）
- **Milestone 3**：多边形/画笔对象、掩膜、面积测量、对象表
- **Milestone 4**：弯曲体长折线编辑（节点拖动、撤销、持久化）
- **Milestone 5**：自动实例分割、合并/切割/种子拆分、确认保护
- **Milestone 6**：分类管理、快捷键分类、CSV/Excel/掩膜/裁剪/标注图导出
- **Milestone 7**：自动体长建议、后台批处理（分割/比例尺/体长）
- **Milestone 8**：缩略图、最近工作区、崩溃恢复、快捷键、打包脚本与用户说明

版本：**0.8.0**。里程碑总览见 `docs/milestones.md`，使用说明见 `docs/USER_GUIDE.md`。

### 常用操作

| 快捷键 | 功能 |
|--------|------|
| `C` | 比例尺校准 |
| `A` | 自动分割 |
| `G` | 当前对象自动体长建议 |
| `Ctrl+B` | 批处理 |
| `0`–`7` | 分类快捷键 |
| `Ctrl+E` | 导出结果 |
| `P` / `M` / `S` / `L` | 多边形 / 合并 / 切割 / 体长 |
| `Ctrl+S` | 保存项目 |
| `F1` | 快捷键一览 |

## 环境要求

- Python **3.10+**（开发机可用 3.13；推荐 3.12）
- 操作系统：Windows / macOS

## 快速开始

```bash
cd soilfauna-measure
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m soilfauna_measure
```

或：

```bash
soilfauna-measure
```

### 打开工作区

1. 菜单 **文件 → 打开工作区…**
2. 选择包含图片的文件夹（或空文件夹后放入图片）
3. 首次打开会初始化工作区结构，并将图片**复制**到 `images/`

支持格式：`.tif` `.tiff` `.png` `.jpg` `.jpeg` `.bmp`

示例图：`examples/HJ98.tif`

## 运行测试

```bash
pytest
```

## Windows 独立版打包（用户无需安装 Python）

使用 **PyInstaller** 内嵌 Python 运行时。  
**必须在 Windows 电脑上打包**（不能在 Mac 上交叉编译 Qt）。

```bat
scripts\build_windows.bat
```

| 模式 | 命令 / 选项 | 产物 |
|------|-------------|------|
| 文件夹版 | `python scripts\build_windows.py` | `dist\SoilFaunaMeasure\`（exe + `_internal`） |
| 单文件版 | `python scripts\build_windows.py --onefile` | `dist\SoilFaunaMeasure.exe`（启动较慢） |
| **安装包（推荐）** | `python scripts\build_windows.py --installer` | `dist\SoilFaunaMeasure-Setup-*.exe`（选路径、桌面图标；需 [Inno Setup 6](https://jrsoftware.org/isinfo.php)） |

- 打包流程与产物：[`docs/PACKAGING.md`](docs/PACKAGING.md)  
- **全新 Win 环境准备（软件 + 全部库）**：[`docs/WINDOWS_PACKAGING_SETUP.md`](docs/WINDOWS_PACKAGING_SETUP.md)

## 技术栈

- Python 3.10+ / PySide6-Essentials / NumPy / scikit-image / scipy / tifffile / Pillow / openpyxl

## 许可

MIT（可按项目需要调整）
