"""Dialog for automatic segmentation parameters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
)

from soilfauna_measure.core.segmentation import SegmentationParams


class SegmentationDialog(QDialog):
    def __init__(self, params: SegmentationParams | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("自动实例分割")
        self.setModal(True)
        # Default: whole-organism friendly
        p = params or SegmentationParams.preset_whole()

        self._strategy = QComboBox()
        self._strategy.addItem("整虫优先（推荐，少拆开）", "whole")
        self._strategy.addItem("接触拆分（尝试拆开粘连）", "contact_split")
        idx = 0 if not p.enable_watershed else 1
        self._strategy.setCurrentIndex(idx)
        self._strategy.currentIndexChanged.connect(self._apply_strategy_preset)

        self._mode = QComboBox()
        self._mode.addItem("替换未确认对象（保留已确认）", "replace_unconfirmed")
        self._mode.addItem("追加（不删除现有）", "append")
        self._mode.addItem("全部替换（仅当无已确认时）", "replace_all")

        self._min_area = QSpinBox()
        self._min_area.setRange(10, 1_000_000)
        self._min_area.setValue(int(p.min_object_area))

        self._max_area = QSpinBox()
        self._max_area.setRange(0, 10_000_000)
        self._max_area.setValue(int(p.max_object_area))
        self._max_area.setSpecialValueText("不限制")

        self._open_r = QSpinBox()
        self._open_r.setRange(0, 20)
        self._open_r.setValue(int(p.open_radius))

        self._close_r = QSpinBox()
        self._close_r.setRange(0, 30)
        self._close_r.setValue(int(p.close_radius))
        self._close_r.setToolTip("增大可把半透明身体粘成整体，过大可能把两只粘在一起")

        self._hole = QSpinBox()
        self._hole.setRange(0, 100_000)
        self._hole.setValue(int(p.hole_area))

        self._ws_dist = QSpinBox()
        self._ws_dist.setRange(1, 200)
        self._ws_dist.setValue(int(p.watershed_min_distance))
        self._ws_dist.setToolTip("越大越不容易把一只虫拆成多块")

        self._blur = QDoubleSpinBox()
        self._blur.setRange(0.0, 10.0)
        self._blur.setSingleStep(0.5)
        self._blur.setValue(float(p.blur_sigma))
        self._blur.setToolTip("对 RGB 前景分数做模糊，有助于连接半透明缝隙")

        self._use_lab = QCheckBox("使用 Lab 颜色空间（推荐）")
        self._use_lab.setChecked(bool(getattr(p, "use_lab", True)))

        self._use_hsv = QCheckBox("使用 HSV 明度信息（推荐）")
        self._use_hsv.setChecked(bool(getattr(p, "use_hsv", True)))

        self._watershed = QCheckBox("启用分水岭拆分接触个体（易过拆，默认关）")
        self._watershed.setChecked(bool(p.enable_watershed))

        self._appendages = QCheckBox("保留足/触角等细长附肢（默认关闭，面积更贴近身体）")
        self._appendages.setChecked(bool(p.preserve_appendages))
        self._appendages.setToolTip(
            "关闭时：按每个个体身体厚度自适应开运算，去掉足/触角等细长附肢，\n"
            "面积以身体主体为主；开启时尽量保留附肢（面积会偏大）。"
        )

        self._append_r = QSpinBox()
        self._append_r.setRange(1, 15)
        self._append_r.setValue(int(getattr(p, "appendage_open_radius", 7)))
        self._append_r.setToolTip(
            "附肢剔除强度 1–15（默认 7）。越大开运算半径相对身体越厚，\n"
            "去掉的附肢越多；若身体边缘被啃掉可调小，若仍带腿可调大。"
        )

        self._auto_length = QCheckBox("同时自动计算弯曲体长（骨架建议，可编辑）")
        self._auto_length.setChecked(True)
        self._auto_length.setToolTip(
            "分割完成后对每个对象提取主体骨架最长路径，写入可编辑体长节点，"
            "标记为「自动建议」，需人工确认"
        )

        self._exclude_scale = QCheckBox("排除右下角比例尺区域（推荐）")
        self._exclude_scale.setChecked(bool(getattr(p, "exclude_scale_corner", True)))
        self._exclude_scale.setToolTip(
            "显微镜图比例尺多在右下角；开启后不把比例尺横线/文字当成虫子"
        )

        form = QFormLayout()
        form.addRow("分割策略", self._strategy)
        form.addRow("写入模式", self._mode)
        form.addRow("最小面积 (px)", self._min_area)
        form.addRow("最大面积 (px)", self._max_area)
        form.addRow("开运算半径", self._open_r)
        form.addRow("闭运算半径", self._close_r)
        form.addRow("填孔面积", self._hole)
        form.addRow("分水岭最小距离", self._ws_dist)
        form.addRow("模糊 σ", self._blur)
        form.addRow(self._use_lab)
        form.addRow(self._use_hsv)
        form.addRow(self._watershed)
        form.addRow(self._appendages)
        form.addRow("附肢剔除半径", self._append_r)
        form.addRow(self._exclude_scale)
        form.addRow(self._auto_length)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "默认用 RGB/Lab/HSV 识别整体，闭运算连接半透明身体；默认关闭分水岭防过拆。\n"
            "默认同时生成弯曲体长建议（骨架路径），可在 L 模式中修改确认。\n"
            "若两只虫粘在一起，可用 S 切割拆分，或切换「接触拆分」策略。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _apply_strategy_preset(self) -> None:
        key = str(self._strategy.currentData())
        p = (
            SegmentationParams.preset_whole()
            if key == "whole"
            else SegmentationParams.preset_contact_split()
        )
        self._min_area.setValue(int(p.min_object_area))
        self._open_r.setValue(int(p.open_radius))
        self._close_r.setValue(int(p.close_radius))
        self._hole.setValue(int(p.hole_area))
        self._ws_dist.setValue(int(p.watershed_min_distance))
        self._blur.setValue(float(p.blur_sigma))
        self._watershed.setChecked(bool(p.enable_watershed))
        self._appendages.setChecked(bool(p.preserve_appendages))
        self._append_r.setValue(int(getattr(p, "appendage_open_radius", 7)))
        self._use_lab.setChecked(True)
        self._use_hsv.setChecked(True)

    def mode(self) -> str:
        return str(self._mode.currentData())

    def auto_length(self) -> bool:
        return self._auto_length.isChecked()

    def params(self) -> SegmentationParams:
        strategy = str(self._strategy.currentData())
        return SegmentationParams(
            blur_sigma=float(self._blur.value()),
            use_lab=self._use_lab.isChecked(),
            use_hsv=self._use_hsv.isChecked(),
            open_radius=int(self._open_r.value()),
            close_radius=int(self._close_r.value()),
            hole_area=int(self._hole.value()),
            min_object_area=int(self._min_area.value()),
            max_object_area=int(self._max_area.value()),
            watershed_min_distance=int(self._ws_dist.value()),
            enable_watershed=self._watershed.isChecked(),
            preserve_appendages=self._appendages.isChecked(),
            appendage_open_radius=int(self._append_r.value()),
            appendage_restore_radius=max(1, int(self._append_r.value()) // 2),
            exclude_scale_corner=self._exclude_scale.isChecked(),
            filter_scale_like=self._exclude_scale.isChecked(),
            strategy=strategy,
            merge_thin_splits=True,
            watershed_min_peak_height=6.0 if self._watershed.isChecked() else 4.0,
        )
