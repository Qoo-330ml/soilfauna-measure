"""Export options dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from soilfauna_measure.services.export_service import ExportOptions


class ExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出结果")
        self.setModal(True)

        self._csv = QCheckBox("CSV 测量表")
        self._csv.setChecked(True)
        self._xlsx = QCheckBox("Excel (.xlsx) 测量表")
        self._xlsx.setChecked(True)
        self._masks = QCheckBox("对象掩膜 PNG")
        self._masks.setChecked(True)
        self._crops = QCheckBox("个体裁剪图")
        self._crops.setChecked(True)
        self._ann = QCheckBox("带标注整图")
        self._ann.setChecked(True)
        self._current = QCheckBox("仅当前图片的图像导出（表格仍含全部）")
        self._current.setChecked(False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选择导出内容（写入工作区 exports/ 时间戳目录）："))
        for w in (
            self._csv,
            self._xlsx,
            self._masks,
            self._crops,
            self._ann,
            self._current,
        ):
            layout.addWidget(w)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self) -> ExportOptions:
        return ExportOptions(
            csv=self._csv.isChecked(),
            xlsx=self._xlsx.isChecked(),
            masks=self._masks.isChecked(),
            crops=self._crops.isChecked(),
            annotated=self._ann.isChecked(),
            only_current_image=self._current.isChecked(),
        )
