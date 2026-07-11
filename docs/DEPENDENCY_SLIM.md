# 依赖精简分析

对照源码实际引用与 `pyproject.toml` / PyInstaller 打包策略。

---

## 一、直接依赖是否必需

| 库 | 代码中是否使用 | 可否删除 | 说明 |
|----|----------------|----------|------|
| **PySide6 / Qt** | 是（整 UI） | **可换瘦身包** | 不能去掉 GUI；已改为只装 **PySide6_Essentials**（见下） |
| **numpy** | 是（掩膜/分割/画布） | **否** | 基础数组 |
| **scikit-image** | 是（分割、骨架、比例尺） | **否** | 核心算法；删除需重写大量形态学/分水岭 |
| **scipy** | 是（`ndi.distance_transform_edt`） | **否** | 自身在用；且 **skimage 硬依赖 scipy**，删了装不齐 skimage |
| **tifffile** | 是（显微镜 TIFF） | **否** | 专业 TIFF；Pillow 对部分 TIFF 支持不足 |
| **Pillow** | 是（缩略图、掩膜、绘制） | **否** | 轻量，值得保留 |
| **openpyxl** | 是（Excel 导出） | **否**（若要保留 xlsx） | 仅导出 xlsx 时需要；只要 CSV 可再砍 |
| **pandas** | 仅 Excel 一条可选路径 | **是（已删）** | 已有 openpyxl 实现，不必再装 pandas |
| **opencv-python-headless** | 可选 `[full]` | **默认不装** | 主路径未引用 |
| **pytest / pytest-qt** | 仅 `[dev]` | **打包不装** | 正确 |

---

## 二、体积大致构成（打包后）

经验上 onedir 体积排序：

1. **PySide6 / Qt**（Widgets + 一堆未用模块若被 collect 进来会暴涨）  
2. **scipy** + **scikit-image**  
3. **numpy**  
4. 其余（Pillow、tifffile、openpyxl、本项目代码）相对很小  

---

## 三、PySide6 能不能精简？

### 代码实际用到的模块

全项目只从这三处 import：

| 模块 | 用途 |
|------|------|
| `PySide6.QtCore` | 信号、定时器、设置、线程池… |
| `PySide6.QtGui` | 图标、画笔、快捷键、QAction… |
| `PySide6.QtWidgets` | 窗口、对话框、工具栏、画布… |

**没有**使用 WebEngine、多媒体、3D、Charts、QML 等。

### 官方拆分

| pip 包 | 内容 | 本项目 |
|--------|------|--------|
| `PySide6` | Essentials **+** Addons | ~~旧依赖~~ |
| **`PySide6_Essentials`** | Core/Gui/Widgets 等基础 | **当前依赖** |
| `PySide6_Addons` | WebEngine、3D、Multimedia… | **不装** |

import 写法不变，仍是 `from PySide6.QtWidgets import …`。

### 还能再瘦多少？

| 手段 | 预期 | 说明 |
|------|------|------|
| Essentials 代替 full PySide6 | **大**（常少一百多 MB 级 Addons） | 已做 |
| 打包 excludes 未用 Qt 模块 | **中** | 已做 |
| 删掉 Qt 换 Tk/webview | 不推荐 | 重写 UI，体验差 |
| 只保留 3 个 Qt DLL 手工裁剪 | 风险高 | 易缺插件导致黑屏/无法启动 |

**结论**：PySide6「整包」可以精简为 **Essentials**；**不能**去掉 Qt/Widgets 本身。剩余体积主要是 Qt 基础库，属于正常。

---

## 四、已做的精简

1. **移除 pandas**  
   - `export_xlsx` 只走 `openpyxl`  

2. **PySide6 → PySide6_Essentials**  
   - 不装 Addons（WebEngine / 3D / Multimedia 等）

3. **PyInstaller 不再 `collect_all(PySide6)`**  
   - 仅对 **skimage** 做 `collect_all`；Qt 走 hook + 排除列表  

4. **打包 excludes**  
   - Addons + 未用到的 Essentials 子模块（Qml/Quick/Sql/Designer…）  

5. **hiddenimports 去掉假依赖 `sklearn`**  


---

## 五、不建议再砍的

| 想法 | 原因 |
|------|------|
| 去掉 scipy | skimage 装不上；距离变换仍依赖它 |
| 去掉 skimage，改纯 numpy | 工作量大，分水岭/骨架/形态学都要重写 |
| 换成 OpenCV | 体积未必更小，且 API 与现逻辑不兼容 |
| 去掉 tifffile | 土壤动物显微 TIFF 风险高 |
| 用 PyQt 代替 PySide6 | 体积同级，授权更麻烦 |
| 去掉 Qt 改命令行 | 不符合桌面测量产品目标 |

---

## 六、若还要再瘦（可选后续）

| 措施 | 预期收益 | 代价 |
|------|----------|------|
| 导出只保留 CSV，去掉 openpyxl | 小 | 无 xlsx |
| 更激进的 Qt 插件过滤（只留 platforms/imageformats） | 中 | 需在 Win 上实测启动 |
| 用 `opencv` 重写部分形态学、弱化 skimage | 不确定 | 大改代码、回归成本高 |
| UPX 压缩 | 中 | 易被杀软误报，不推荐 |

---

## 七、其它库有没有「装了全家桶、只用一部分」？

和 PySide6 一样：**功能上往往只用子集**；但**能否像 Essentials 那样官方瘦身**，差别很大。

### 对照表

| 库 | 代码实际用到的 | 是否还有大量未用 | 有没有官方瘦身包？ | 能否再砍？ |
|----|----------------|------------------|--------------------|------------|
| **PySide6** | 仅 `QtCore` / `QtGui` / `QtWidgets` | 是（Web/3D/多媒体…） | **有**：`PySide6_Essentials` | **已做** |
| **scipy** | 基本只有 `scipy.ndimage.distance_transform_edt`（及 skimage 间接用） | 是（optimize/linalg/sparse/…） | **无**（一体安装） | 很难：skimage **硬依赖** scipy 整包 |
| **scikit-image** | `filters` / `measure` / `morphology` / `segmentation` / `color` / `util` / `feature.peak_local_max` | 是（io/registration/restoration/…） | **无** | 很难：pip 只提供整包；拆模块风险大 |
| **numpy** | 数组/掩膜/统计，用法面广 | 核心都在用 | 无必要 | **不必砍**（本身就是底座） |
| **Pillow** | `Image` / `ImageDraw` / `ImageFont` | 部分编解码器未用 | 无独立「精简版」 | **收益极小**（包本身不大） |
| **tifffile** | `TiffFile` 读显微 TIFF | 高级写/OME 等未用 | 无 | **不必砍**（已经很轻） |
| **openpyxl** | 仅 `Workbook` 写 xlsx | 读复杂格式/图表未用 | 无 | **小**：若只要 CSV 可整库去掉 |
| **pandas** | 曾只为 Excel | 整库几乎未用 | — | **已删除** |

### 为何不像 PySide6？

```text
PySide6  = 官方拆成 Essentials + Addons  →  pip 层就能少装半边
scipy    = 一个大 wheel，子模块在磁盘上都在
skimage  = 一个大 wheel，没有 “morphology-only” 发行版
numpy    = 底座，用不到「半个 numpy」
```

所以：

- **有「类似情况」**：scipy / skimage 确实远没用全。  
- **没有「类似解法」**：不能 `pip install scipy-ndimage-only` 或 `skimage-morphology-only`。  
- 打包时用 PyInstaller `excludes` **理论上**可丢掉部分子模块，但对 **scipy/skimage 容易漏依赖导致运行崩溃**，不推荐为省几十 MB 去赌。

### 各库未用部分举例（帮助理解体积）

| 库 | 我们用的 | 典型没用到的（仍在安装目录里） |
|----|----------|--------------------------------|
| scipy | `ndimage` 距离变换 | `optimize`、`integrate`、`signal`、`sparse`、`linalg` 大部分… |
| skimage | 形态学 / 标签 / 分水岭 / 骨架 / 阈值 | `io` 全套、`registration`、`restoration`、`transform` 大部… |
| Pillow | 读写常见图、缩略图、画多边形 | 大量冷门编解码插件 |
| openpyxl | 写一张测量表 | 数据透视、图表、完整 OOXML 能力 |

### 若还要抠体积，现实选项

| 优先级 | 做法 | 预期 |
|--------|------|------|
| 已做 | Essentials、去 pandas、Qt excludes | 最大收益段 |
| 可选 | 不要 xlsx，去掉 openpyxl，只导出 CSV | 再少几～十几 MB |
| 不推荐 | 手写距离变换去掉对 scipy 的直接 import | **仍装 skimage→仍装 scipy**，几乎白做 |
| 大改 | 用 OpenCV 重写分割/骨架，去掉 skimage | 工作量大，体积未必更小 |
| 打包微调 | 排除更多未引用的 skimage/scipy 子模块 | 需 Win 上充分回归 |

---

## 八、结论

- **PySide6**：可以精简 → 用 **`PySide6_Essentials`**（已做）。  
- **其它库**：多数也是「只用一部分」，但 **没有官方半包**，不能指望再砍出和 Qt Addons 同级的体积。  
- **真正剩下的大头**：numpy + **整包 scipy** + **整包 skimage** + Qt Core/Gui/Widgets。  
- 继续抠性价比最高的是：确认 Win 打包产物里没有误打进 Addons / pandas / collect_all 全家桶；而不是拆 scipy。