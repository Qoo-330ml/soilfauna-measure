"""Right-side image + selected object properties."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from soilfauna_measure.core.calibration import format_scale_summary
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.category import Category
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.ui.theme import muted_label_style, secondary_label_style


def _section_title(text: str) -> QLabel:
    """In-card section label — soft, not a border-floating GroupBox title."""
    lab = QLabel(text)
    lab.setStyleSheet(
        """
        QLabel {
            color: #8e8e93;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.6px;
            padding: 0 0 2px 0;
            background: transparent;
            border: none;
        }
        """
    )
    return lab


def _field_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(secondary_label_style() + " background: transparent;")
    lab.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    return lab


def _value_label() -> QLabel:
    lab = QLabel("—")
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setStyleSheet(
        """
        QLabel {
            color: #1c1c1e;
            font-size: 13px;
            background: transparent;
            padding: 1px 0;
        }
        """
    )
    lab.setWordWrap(True)
    return lab


def _make_card(*body_widgets: QWidget) -> QFrame:
    """Glass property card with comfortable internal padding."""
    card = QFrame()
    card.setObjectName("PropCard")
    card.setStyleSheet(
        """
        QFrame#PropCard {
            background-color: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(0, 0, 0, 0.06);
            border-radius: 14px;
        }
        """
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(10)
    for w in body_widgets:
        lay.addWidget(w)
    return card


def _make_form() -> QFormLayout:
    form = QFormLayout()
    form.setContentsMargins(0, 2, 0, 0)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    form.setLabelAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
    )
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
    return form


class PropertiesPanel(QWidget):
    """Display current image metadata, scale, and selected object."""

    category_changed = Signal(str)  # category_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._categories: list[Category] = []
        self._block_cat = False

        self._name = _value_label()
        self._size = _value_label()
        self._channels = _value_label()
        self._dtype = _value_label()
        self._format = _value_label()
        self._path = _value_label()
        self._stats = _value_label()

        self._scale_summary = _value_label()
        self._scale_px = _value_label()
        self._scale_real = _value_label()
        self._scale_rpp = _value_label()
        self._scale_method = _value_label()

        self._obj_id = _value_label()
        self._obj_cat = QComboBox()
        self._obj_cat.setMinimumHeight(28)
        self._obj_cat.currentIndexChanged.connect(self._on_cat_combo)
        self._obj_area_px = _value_label()
        self._obj_area_um2 = _value_label()
        self._obj_area_mm2 = _value_label()
        self._obj_len_nodes = _value_label()
        self._obj_len_px = _value_label()
        self._obj_len_um = _value_label()
        self._obj_len_mm = _value_label()
        self._obj_len_src = _value_label()
        self._obj_scope = _value_label()
        self._obj_confirmed = _value_label()
        self._obj_method = _value_label()

        # --- Image card ---
        img_form = _make_form()
        img_form.addRow(_field_label("文件名"), self._name)
        img_form.addRow(_field_label("尺寸"), self._size)
        img_form.addRow(_field_label("通道"), self._channels)
        img_form.addRow(_field_label("位深"), self._dtype)
        img_form.addRow(_field_label("格式"), self._format)
        img_form.addRow(_field_label("路径"), self._path)
        img_form.addRow(_field_label("统计"), self._stats)
        img_body = QWidget()
        img_body.setLayout(img_form)
        img_card = _make_card(_section_title("当前图片"), img_body)

        # --- Scale card ---
        scale_form = _make_form()
        scale_form.addRow(_field_label("摘要"), self._scale_summary)
        scale_form.addRow(_field_label("像素长"), self._scale_px)
        scale_form.addRow(_field_label("真实长"), self._scale_real)
        scale_form.addRow(_field_label("比例"), self._scale_rpp)
        scale_form.addRow(_field_label("方式"), self._scale_method)
        scale_body = QWidget()
        scale_body.setLayout(scale_form)
        scale_card = _make_card(_section_title("比例尺"), scale_body)

        # --- Object card ---
        obj_form = _make_form()
        obj_form.addRow(_field_label("对象 ID"), self._obj_id)
        obj_form.addRow(_field_label("分类"), self._obj_cat)
        obj_form.addRow(_field_label("面积 px"), self._obj_area_px)
        obj_form.addRow(_field_label("面积 µm²"), self._obj_area_um2)
        obj_form.addRow(_field_label("面积 mm²"), self._obj_area_mm2)
        obj_form.addRow(_field_label("体长节点"), self._obj_len_nodes)
        obj_form.addRow(_field_label("体长 px"), self._obj_len_px)
        obj_form.addRow(_field_label("体长 µm"), self._obj_len_um)
        obj_form.addRow(_field_label("体长 mm"), self._obj_len_mm)
        obj_form.addRow(_field_label("体长来源"), self._obj_len_src)
        obj_form.addRow(_field_label("测量范围"), self._obj_scope)
        obj_form.addRow(_field_label("已确认"), self._obj_confirmed)
        obj_form.addRow(_field_label("分割方式"), self._obj_method)
        obj_body = QWidget()
        obj_body.setLayout(obj_form)
        obj_card = _make_card(_section_title("当前对象"), obj_body)

        hint = QLabel(
            "空白拖动平移 · P 多边形 · B/E 画笔 · L 体长 · H 调节点\n"
            "体长：绿起止 · 红中间 · 蓝折线"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(muted_label_style() + " padding: 4px 2px 0 2px;")

        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(14)
        col.addWidget(img_card)
        col.addWidget(scale_card)
        col.addWidget(obj_card)
        col.addWidget(hint)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(scroll)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

    def clear(self) -> None:
        self._name.setText("—")
        self._size.setText("—")
        self._channels.setText("—")
        self._dtype.setText("—")
        self._format.setText("—")
        self._path.setText("—")
        self._stats.setText("—")
        self.set_scale(None)
        self.set_object(None)

    def set_info(self, info: dict[str, Any] | None) -> None:
        if not info:
            self.clear()
            return
        self._name.setText(str(info.get("name", "—")))
        w, h = info.get("width"), info.get("height")
        self._size.setText(f"{w} × {h}" if w and h else "—")
        self._channels.setText(str(info.get("channels", "—")))
        self._dtype.setText(str(info.get("dtype", "—")))
        self._format.setText(str(info.get("format", "—")))
        self._path.setText(str(info.get("path", "—")))
        mn, mx, mean = info.get("min"), info.get("max"), info.get("mean")
        if mn is not None and mx is not None and mean is not None:
            self._stats.setText(f"min={mn:.1f}, max={mx:.1f}, mean={mean:.2f}")
        else:
            self._stats.setText("—")

    def set_scale(self, scale: ScaleCalibration | None) -> None:
        self._scale_summary.setText(format_scale_summary(scale))
        if scale is None:
            self._scale_px.setText("—")
            self._scale_real.setText("—")
            self._scale_rpp.setText("—")
            self._scale_method.setText("—")
            return
        unit = scale.unit
        label = {"um": "µm", "mm": "mm", "cm": "cm"}.get(unit, unit)
        self._scale_px.setText(f"{scale.pixel_length:.4f} px")
        self._scale_real.setText(f"{scale.real_length:g} {label}")
        self._scale_rpp.setText(f"{scale.real_per_pixel:.8g} {label}/px")
        conf = "已确认" if scale.confirmed else "待确认"
        self._scale_method.setText(f"{scale.method} · {conf}")

    def set_categories(self, categories: list[Category]) -> None:
        self._categories = list(categories)
        self._block_cat = True
        self._obj_cat.clear()
        for c in categories:
            if c.enabled:
                self._obj_cat.addItem(c.name_zh, c.category_id)
        self._block_cat = False

    def _on_cat_combo(self, _idx: int) -> None:
        if self._block_cat:
            return
        cid = self._obj_cat.currentData()
        if cid:
            self.category_changed.emit(str(cid))

    def set_object(self, obj: SpecimenObject | None) -> None:
        if obj is None:
            self._obj_id.setText("—")
            self._block_cat = True
            self._obj_cat.setCurrentIndex(-1)
            self._block_cat = False
            self._obj_area_px.setText("—")
            self._obj_area_um2.setText("—")
            self._obj_area_mm2.setText("—")
            self._obj_len_nodes.setText("—")
            self._obj_len_px.setText("—")
            self._obj_len_um.setText("—")
            self._obj_len_mm.setText("—")
            self._obj_len_src.setText("—")
            self._obj_scope.setText("—")
            self._obj_confirmed.setText("—")
            self._obj_method.setText("—")
            return
        self._obj_id.setText(obj.object_id)
        self._block_cat = True
        idx = self._obj_cat.findData(obj.category_id)
        if idx < 0 and obj.category_id:
            self._obj_cat.addItem(obj.category_id, obj.category_id)
            idx = self._obj_cat.findData(obj.category_id)
        self._obj_cat.setCurrentIndex(max(0, idx))
        self._block_cat = False
        self._obj_area_px.setText(f"{obj.area_px:.0f} px²")
        self._obj_area_um2.setText(
            f"{obj.area_um2:.2f}" if obj.area_um2 is not None else "（需比例尺）"
        )
        self._obj_area_mm2.setText(
            f"{obj.area_mm2:.6g}" if obj.area_mm2 is not None else "（需比例尺）"
        )
        n_nodes = len(obj.length_points or [])
        self._obj_len_nodes.setText(str(n_nodes))
        self._obj_len_px.setText(
            f"{obj.length_px:.2f} px" if obj.length_px is not None else "—"
        )
        self._obj_len_um.setText(
            f"{obj.length_um:.2f}" if obj.length_um is not None else "（需比例尺）"
        )
        self._obj_len_mm.setText(
            f"{obj.length_mm:.6g}" if obj.length_mm is not None else "（需比例尺）"
        )
        src_map = {
            "none": "无",
            "manual": "人工",
            "auto_suggested": "自动建议",
        }
        self._obj_len_src.setText(src_map.get(obj.length_source, obj.length_source))
        self._obj_scope.setText(obj.measurement_scope)
        self._obj_confirmed.setText("是" if obj.confirmed else "否（待确认）")
        self._obj_method.setText(obj.segmentation_method)
