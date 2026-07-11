# 土衡 / SoilFauna Measure 用户说明

**中文名称**：土衡  
**英文名称**：SoilFauna Measure  
**全称**：土壤动物图像分割与形态测量系统  

本文面向日常使用。软件完全离线运行，原始图片只读，测量结果保存在工作区项目文件中。

---

## 1. 安装与启动

### 开发环境运行

```bash
cd soilfauna-measure
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m soilfauna_measure
```

也可指定工作区：

```bash
python -m soilfauna_measure /path/to/workspace
```

### Windows 打包版

使用 `scripts/build_windows.py`（或 `build_windows.bat`）生成可执行文件后，双击运行。详见 `docs/PACKAGING.md`。

---

## 2. 工作区

1. **文件 → 打开工作区…**（`Ctrl+O`）选择文件夹。  
2. 软件会创建标准子目录，并把图片**复制**到 `images/`（不修改原图）。  
3. 项目文件：`project.sfm.json`。  
4. 自动保存：`autosave/project.sfm.autosave.json`。  
5. **文件 → 最近工作区** 可快速打开历史目录。

### 目录结构

```text
workspace/
  images/           # 源图副本（只读打开）
  project.sfm.json
  masks/            # 对象掩膜
  thumbnails/       # 缩略图缓存
  exports/          # 导出结果
  autosave/
  annotations/ crops/ ...
```

支持格式：`.tif` `.tiff` `.png` `.jpg` `.jpeg` `.bmp`

---

## 3. 推荐测量流程

1. 打开工作区，确认图片列表与缩略图。  
2. **`C` 比例尺校准**：点击比例尺两端，输入真实长度（默认 µm，如 1000）。  
3. **`A` 自动分割** 或 **`P` 多边形** 圈出个体。  
4. 用 **`B`/`E`** 修掩膜；**`M`** 合并、**`S`** 切割拆分。  
5. **`G` 自动体长建议**，再 **`L`** 微调节点。  
6. **`0`–`7`** 设置分类；切换对象「确认」状态。  
7. **`Ctrl+S` 保存**；**`Ctrl+E` 导出**。  

批处理：**`Ctrl+B`**（批量分割 / 套用比例尺 / 体长建议）。

---

## 4. 测量说明

| 量 | 说明 |
|----|------|
| 面积 | 掩膜非零像素数 `area_px`；真实面积 = 像素面积 × scale² |
| 体长 | 折线节点总长 `length_px`；真实体长 = 像素长 × scale |
| 比例尺 | scale = 真实长度 / 像素长度 |

所有结果同时保存像素值与 µm / mm（在已校准比例尺时）。

自动分割与自动体长均为**建议**，默认待确认，**不会覆盖已确认对象**（除非你选择允许的操作）。

---

## 5. 崩溃与恢复

- 编辑过程中会防抖自动保存。  
- 每 60 秒对未保存更改再刷写自动保存。  
- 若程序异常退出，重新打开工作区时若检测到较新的 autosave，会询问是否恢复。  
- 崩溃日志目录：用户主目录下 `.soilfauna-measure/logs/`（帮助菜单可打开）。  

---

## 6. 导出内容

`exports/时间戳/` 下可包含：

- `measurements.csv` / `measurements.xlsx`（每对象一行）  
- `masks/` 对象掩膜  
- `crops/` 个体裁剪图  
- `annotated/` 带标注整图  

---

## 7. 示例

仓库 `examples/HJ98.tif`：白底多体土壤动物，右下角 `1000μm` 比例尺，适合练习校准与分割。

可将 `examples` 或复制后的文件夹作为工作区打开。

---

## 8. 快捷键

按 **F1** 查看完整列表，或 **帮助 → 快捷键一览**。

常用：`C` 比例尺 · `A` 分割 · `P` 多边形 · `L` 体长 · `G` 自动体长 · `Ctrl+E` 导出 · `Ctrl+S` 保存。

---

## 9. 注意事项

1. 不要手动覆盖 `images/` 中正在使用的源文件。  
2. 完全重叠的个体请标记「重叠/无法拆分」并人工备注（后续版本可扩展字段）。  
3. 细附肢可能导致自动分割/骨架偏差，务必人工复核。  
4. 打包体积较大属正常（含 Qt 与科学计算库）。  
