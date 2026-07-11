"""Dialog to enter real scale-bar length and unit."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from soilfauna_measure.core.calibration import DISPLAY_UNIT_LABELS, normalize_unit


class ScaleDialog(QDialog):
    """Ask user for real length and unit after two endpoints are chosen."""

    def __init__(
        self,
        pixel_length: float,
        *,
        default_real: float = 1000.0,
        default_unit: str = "um",
        hint_text: str | None = None,
        title: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "比例尺校准")
        self.setModal(True)

        self._pixel_label = QLabel(f"{pixel_length:.3f} px")
        self._real = QDoubleSpinBox()
        self._real.setRange(1e-9, 1e12)
        self._real.setDecimals(6)
        self._real.setValue(default_real)
        self._real.setMinimumWidth(140)

        self._unit = QComboBox()
        self._unit.addItem("µm (微米)", "um")
        self._unit.addItem("mm (毫米)", "mm")
        self._unit.addItem("cm (厘米)", "cm")
        try:
            unit = normalize_unit(default_unit)
        except Exception:  # noqa: BLE001
            unit = "um"
        idx = max(0, self._unit.findData(unit))
        self._unit.setCurrentIndex(idx)

        self._preview = QLabel("—")
        self._preview.setWordWrap(True)

        form = QFormLayout()
        form.addRow("像素长度", self._pixel_label)
        form.addRow("真实长度", self._real)
        form.addRow("单位", self._unit)
        form.addRow("换算结果", self._preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel(
            hint_text
            or (
                "请输入比例尺线段对应的真实长度。\n"
                "默认单位为 µm（与图上 1000µm 一致）；可按实际标注切换。"
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._pixel_length = float(pixel_length)
        self._real.valueChanged.connect(self._update_preview)
        self._unit.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self) -> None:
        real = float(self._real.value())
        unit = str(self._unit.currentData())
        label = DISPLAY_UNIT_LABELS.get(unit, unit)
        if self._pixel_length <= 0:
            self._preview.setText("无效像素长度")
            return
        rpp = real / self._pixel_length
        self._preview.setText(f"{rpp:.8g} {label}/px")

    def result_values(self) -> tuple[float, str]:
        """Return (real_length, unit_code)."""
        return float(self._real.value()), str(self._unit.currentData())
