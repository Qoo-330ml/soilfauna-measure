# 示例资源

## HJ98.tif

- 尺寸：1600×1200，RGB 8-bit TIFF  
- 白底、多个半透明土壤动物，部分接触  
- 右下角比例尺文字约 **1000μm**  
- 适合练习：比例尺校准、自动分割、体长路径  

### 快速试用

```bash
python -m soilfauna_measure examples
```

首次打开会在 `examples/` 下创建 `images/`、`project.sfm.json` 等工作区结构，并将 `HJ98.tif` 复制到 `images/`。

若不想污染 examples 目录，请复制到独立文件夹：

```bash
mkdir -p ~/Desktop/sfm_demo/images
cp examples/HJ98.tif ~/Desktop/sfm_demo/
python -m soilfauna_measure ~/Desktop/sfm_demo
```

## reference_ui.png

参考界面图（可选，若仓库中提供）。

## 说明

样例 TIFF 体积约 1.5MB；完整研究批次请使用自己的工作区，勿把大批量数据提交进 git。
