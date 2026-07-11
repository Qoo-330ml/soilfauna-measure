# 土衡 / SoilFauna Measure — 规格摘要（已确认）

## 产品

离线桌面科研软件：土壤动物实例分割、人工修正、比例尺校准、投影面积、弯曲体长、分类与导出。

## 已确认决策

| 项 | 决定 |
|----|------|
| 仓库路径 | `~/Desktop/mywork/soilfauna-measure` |
| Python | `>=3.10`，兼容 3.12 / 3.13（当前开发 3.13） |
| 工作区源图 | 初始化时复制到 `workspace/images/`，原图不覆盖 |
| ISAT 导入 | 排入 M2/M3 |
| 比例尺默认 UI | µm；同时显示/读取实际校准单位 |
| UI 布局 | 经典三栏科研布局 |
| 对象 ID | `{image_id}_{seq:03d}`，删除不复用 |
| M1 缩略图 | 不做 |

## 工作区布局

```text
workspace/
  images/
  project.sfm.json      # M2
  annotations/
  masks/
  crops/
  thumbnails/
  exports/
  autosave/
```

## 比例尺

- 手动两点校准；`scale = real_length / pixel_length`
- 默认 UI 单位 **µm**，可切换 mm/cm（从对话框读取实际单位）
- 真实长度/面积：`length_real = length_px × scale`，`area_real = area_px × scale²`

## 里程碑

见 `docs/milestones.md`。当前完成 **Milestone 8**（版本 0.8.0）。
