# Windows 独立版打包说明

目标：生成**自带 Python 运行时**的程序，用户**不需要安装 Python**，解压后双击即可用。

> **全新 Windows、尚未装 Python？** 先看完整准备清单：  
> [WINDOWS_PACKAGING_SETUP.md](./WINDOWS_PACKAGING_SETUP.md)（系统软件 + 全部库 + 一条龙命令）。  
>
> **自动打包：** GitHub Actions 工作流 [`.github/workflows/build-windows.yml`](../.github/workflows/build-windows.yml)  
> 在 `windows-latest` 上构建绿色版 + Setup（若 Inno 安装成功）。见下文「CI 自动打包」。

支持三种输出：

| 模式 | 产物 | 适用 |
|------|------|------|
| **onedir** | `SoilFaunaMeasure\` 文件夹 = `.exe` + `_internal\` | 绿色版、启动快 |
| **onefile** | 单个 `SoilFaunaMeasure.exe` | 方便拷贝；首次启动较慢 |
| **installer（推荐给最终用户）** | `SoilFaunaMeasure-Setup-x.y.z.exe` | 选路径安装、桌面图标；安装后仍是 onedir，启动快 |

---

## 〇、CI 自动打包（GitHub Actions）

仓库已配置工作流：**Build Windows**。

| 触发 | Artifacts | GitHub Releases |
|------|-----------|-----------------|
| **Actions → Build Windows → Run workflow** | 有 | 更新 **`latest`** 滚动版 |
| 推送 **`v*`** 标签（如 `v0.8.0`） | 有 | 创建 **正式 Release**（该标签） |
| 推送到 **main**（改了源码/打包脚本） | 有 | 更新 **`latest`** 滚动版 |
| 对应路径的 **Pull Request** | 有 | 不发布 |

下载地址（构建成功后）：

- 滚动最新：https://github.com/Qoo-330ml/soilfauna-measure/releases/tag/latest  
- 全部发版：https://github.com/Qoo-330ml/soilfauna-measure/releases  
- 单次构建临时包：Actions 运行页 → Artifacts  

附件文件名示例：

- `SoilFaunaMeasure-0.8.0-windows-portable.zip`  
- `SoilFaunaMeasure-Setup-0.8.0.exe`  

打正式版标签：

```bash
git tag v0.8.0
git push origin v0.8.0
```
---

## 一、重要限制

| 项目 | 说明 |
|------|------|
| 打包机器 | **必须在 Windows 上打包** |
| 本机 macOS | **不能**可靠交叉编译出 Windows Qt 程序 |
| 用户环境 | 无需 Python；Windows 10/11 x64 即可 |
| 体积 | 通常约 **400MB～1GB**（含 PySide6、numpy、skimage 等） |

你在 Mac 上开发没问题，但**最终 Windows 包请在 Windows 电脑或 Windows 虚拟机里打**。

---

## 二、在 Windows 上打包

### 1. 准备环境（仅打包机需要）

1. 安装 [Python 3.10+ Windows 64-bit](https://www.python.org/downloads/windows/)  
   - 安装时勾选 **Add python.exe to PATH**
2. 把本项目拷到 Windows，例如：  
   `C:\work\soilfauna-measure`

### 2. 一键打包

双击：

```text
scripts\build_windows.bat
```

按提示选择：

- **1** → 文件夹版  
- **2** → 单文件 exe  
- **3** → **安装包 Setup.exe**（推荐；需先装 Inno Setup）

### 3. 安装包（推荐给最终用户）

安装包 = **onedir 内容压进一个 Setup.exe**，用户安装后仍是「exe + `_internal`」，**启动快**。

1. 安装免费工具 [Inno Setup 6](https://jrsoftware.org/isinfo.php)（勾选安装到默认路径即可）  
2. 打包：

```bat
python scripts\build_windows.py --installer
```

3. 产物：

```text
dist\SoilFaunaMeasure-Setup-0.8.0.exe
```

若 onedir 已打好，只重新编译安装器：

```bat
python scripts\build_windows.py --installer-only
```

自定义 ISCC 路径（可选）：

```bat
set SFM_ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
```

### 4. 手动命令（文件夹 / 单文件）

```bat
cd C:\work\soilfauna-measure
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -e ".[packaging]"

REM 文件夹版
python scripts\build_windows.py

REM 单文件版
python scripts\build_windows.py --onefile
```

---

## 三、打包产物长什么样

### 安装包（推荐分发）

```text
dist\SoilFaunaMeasure-Setup-0.8.0.exe
```

用户双击后：

1. 选择安装路径（默认如 `C:\Program Files\SoilFaunaMeasure`）  
2. 勾选「创建桌面快捷方式」（默认勾选）  
3. 释放 `SoilFaunaMeasure.exe` + `_internal` + 说明文件  
4. 开始菜单 + 桌面图标；可选「立即运行」  
5. 控制面板可卸载  

### 文件夹版 onedir

```text
dist\SoilFaunaMeasure\
  SoilFaunaMeasure.exe     ← 用户双击这个
  _internal\               ← 内嵌的 Python + 库（不要删）
  使用前请读.txt
  用户说明.md
```

发给用户：整个文件夹打 zip。

### 单文件版 onefile

```text
dist\SoilFaunaMeasure.exe
```

**注意**：onefile 冷启动慢；需要「又快又好发」请用**安装包**而不是 onefile。

---

## 四、用户侧说明（可复制）

**安装包：**

> 双击 `SoilFaunaMeasure-Setup-….exe` 安装。  
> 可自选安装目录；建议勾选「创建桌面快捷方式」。  
> 安装完成后从桌面图标启动，**无需安装 Python**。  
> 首次使用：菜单「文件 → 打开工作区」，选择放图片的文件夹。

**文件夹版：**

> 绿色免安装版，已内置运行环境。  
> 解压后双击 `SoilFaunaMeasure.exe`（请勿删除同目录的 `_internal`）。

**单文件版：**

> 双击 `SoilFaunaMeasure.exe` 即可。第一次启动可能稍慢。
---

## 五、打包后自测清单

在**另一台干净的 Windows**（或虚拟机）上：

1. [ ] 能启动，无黑框闪退  
2. [ ] 窗口图标显示正常  
3. [ ] 打开工作区，能显示 TIFF  
4. [ ] 自动分割 / 比例尺 / 导出可用  
5. [ ] 杀毒软件未拦截（若拦截，添加信任）

若双击闪退：

- 用命令行运行查看报错  
- 或暂时把 `scripts/SoilFaunaMeasure.spec` 里 `console=False` 改成 `True` 再打一包看日志  

---

## 六、安装器脚本位置

- Inno 脚本：`scripts/installer/SoilFaunaMeasure.iss`  
- 图标：`src/soilfauna_measure/resources/icons/app_icon.ico`  
- 版本号会与 `pyproject.toml` 的 `version` 同步  

也可用 Inno 图形界面打开 `.iss` 点 Compile。

---

## 七、macOS 打包（可选）

仅给 Mac 用户：

```bash
pip install -e ".[packaging]"
python scripts/build_macos.py
```

Windows 用户**不要**用 Mac 打的包。

---

## 八、原理简述

```text
源码 + 依赖
    ↓  PyInstaller（在 Windows 上执行）
嵌入式 Python + PySide6 / numpy / skimage / ...
    ↓
onedir:     SoilFaunaMeasure.exe + _internal\     ← 启动快
onefile:    单文件 .exe（启动时解压到临时目录）  ← 启动慢
installer:  Setup.exe → 安装时释放 onedir 到所选路径 ← 分发方便且启动快
```

安装器**没有**用 onefile 当安装内容，而是把 onedir 整包写进用户目录，所以桌面图标启动的程序与文件夹版一样快。
---

## 九、常见问题

**Q: 为什么 exe 旁边还有一个文件夹？**  
A: 默认是 **onedir**。`.exe` 只是启动器，真正的 Python、Qt、numpy 等在 `_internal` 里。  
这样启动快、调试容易。发用户时要发**整个文件夹**，不能只发 exe。

**Q: 能不能只要一个 exe？**  
A: 两种理解：

1. **安装包一个 Setup.exe**（推荐）：`python scripts\build_windows.py --installer`  
   安装后程序仍是文件夹结构，启动快，有桌面图标。  
2. **绿色单文件**（启动慢）：`python scripts\build_windows.py --onefile`

**Q: 为什么默认不用绿色单文件？**  
A: 依赖重（Qt + 科学计算）。onefile 冷启动慢。要「发一个文件」请用**安装包**。
**Q: 能在 Mac 上直接打 Windows 包吗？**  
A: 不推荐、通常不可行。请用 Windows 虚拟机或实体机。

**Q: 体积太大？**  
A: 正常（内嵌 Qt + 科学计算库）。已做的瘦身：去掉 pandas、打包时排除未用 Qt 模块、不再 `collect_all(PySide6)`。  
大头仍是 **PySide6 + scipy/skimage + numpy**，难以再砍而不改功能。

**Q: 杀软报毒？**  
A: 未代码签名的 PyInstaller 程序常见误报。可签名或加白名单。
