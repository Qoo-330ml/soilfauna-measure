"""Batch processing dialog: segment / scale / length suggestions."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from soilfauna_measure.core.segmentation import SegmentationParams
from soilfauna_measure.ui.segmentation_dialog import SegmentationDialog


class BatchDialog(QDialog):
    """Choose batch operation and options."""

    OP_SEGMENT = "segment"
    OP_SCALE = "scale"
    OP_PATHS = "paths"

    def __init__(self, parent=None, *, has_scale: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("批处理")
        self.setModal(True)
        self._has_scale = has_scale

        self._op = QComboBox()
        self._op.addItem("批量自动分割（未处理/全部图片）", self.OP_SEGMENT)
        self._op.addItem("批量应用当前图比例尺", self.OP_SCALE)
        self._op.addItem("批量自动体长建议（当前图或全部）", self.OP_PATHS)

        self._scope = QComboBox()
        self._scope.addItem("全部图片", "all")
        self._scope.addItem("仅当前图片", "current")
        self._scope.addItem("仅待处理图片 (pending)", "pending")

        self._seg_mode = QComboBox()
        self._seg_mode.addItem("替换未确认（保留已确认）", "replace_unconfirmed")
        self._seg_mode.addItem("追加", "append")

        self._skip_confirmed_scale = QCheckBox("跳过已有已确认比例尺的图片")
        self._skip_confirmed_scale.setChecked(True)

        self._overwrite_manual_path = QCheckBox("覆盖已有人工体长路径")
        self._overwrite_manual_path.setChecked(False)

        self._only_empty_path = QCheckBox("仅对无体长路径的对象建议")
        self._only_empty_path.setChecked(True)

        self._min_branch = QSpinBox()
        self._min_branch.setRange(1, 200)
        self._min_branch.setValue(10)

        self._nodes = QSpinBox()
        self._nodes.setRange(5, 10)
        self._nodes.setValue(8)

        # reuse default segmentation params (user can open advanced via note)
        self._params = SegmentationParams()

        form = QFormLayout()
        form.addRow("任务类型", self._op)
        form.addRow("范围", self._scope)
        form.addRow("分割模式", self._seg_mode)
        form.addRow(self._skip_confirmed_scale)
        form.addRow(self._only_empty_path)
        form.addRow(self._overwrite_manual_path)
        form.addRow("体长短枝剪除阈值", self._min_branch)
        form.addRow("体长目标节点数", self._nodes)

        self._btn_params = QLabel("分割参数使用默认值（可先在单图「自动分割」中试调）。")
        self._btn_params.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "批处理在后台线程运行，不会阻塞界面。\n"
                "取消后已写入的结果会保留，未完成的图片跳过。"
            )
        )
        layout.addLayout(form)
        layout.addWidget(self._btn_params)
        layout.addWidget(buttons)

        if not has_scale:
            # still allow selecting scale op; main window will warn
            pass

    def operation(self) -> str:
        return str(self._op.currentData())

    def scope(self) -> str:
        return str(self._scope.currentData())

    def segment_mode(self) -> str:
        return str(self._seg_mode.currentData())

    def skip_confirmed_scale(self) -> bool:
        return self._skip_confirmed_scale.isChecked()

    def overwrite_manual_path(self) -> bool:
        return self._overwrite_manual_path.isChecked()

    def only_empty_path(self) -> bool:
        return self._only_empty_path.isChecked()

    def path_params(self) -> dict:
        return {
            "min_branch_length": float(self._min_branch.value()),
            "target_nodes": int(self._nodes.value()),
        }

    def segment_params(self) -> SegmentationParams:
        return self._params
