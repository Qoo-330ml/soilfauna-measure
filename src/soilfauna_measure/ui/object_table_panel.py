"""Table of specimen objects for the current image."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from soilfauna_measure.models.category import Category
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.ui.theme import secondary_label_style


class ObjectTablePanel(QWidget):
    """Lists objects; selection and delete actions."""

    object_selected = Signal(str)  # object_id (primary / last)
    objects_selected = Signal(object)  # list[str]
    delete_requested = Signal(str)
    selection_cleared = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["ID", "分类", "面积(px)", "面积(µm²)", "体长(px)", "确认"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Ensure cells paint text under global glass QSS
        self._table.setStyleSheet(
            """
            QTableWidget {
                color: #1c1c1e;
                background-color: rgba(255, 255, 255, 0.92);
            }
            QTableWidget::item {
                color: #1c1c1e;
            }
            QTableWidget::item:selected {
                color: #1c1c1e;
                background-color: rgba(0, 122, 255, 0.16);
            }
            """
        )
        self._table.itemSelectionChanged.connect(self._on_sel)

        self._btn_delete = QPushButton("删除")
        self._btn_delete.setMaximumHeight(28)
        self._btn_delete.clicked.connect(self._on_delete)
        self._count = QLabel("对象 0")
        self._count.setStyleSheet(secondary_label_style())

        bar = QHBoxLayout()
        bar.setContentsMargins(2, 0, 2, 0)
        bar.addWidget(self._count)
        bar.addStretch(1)
        bar.addWidget(self._btn_delete)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(bar)
        layout.addWidget(self._table, stretch=1)

        self._block = False
        self._object_ids: list[str] = []
        self._categories: dict[str, Category] = {}
        self._filter_category_id: str | None = None
        self._all_objects: list[SpecimenObject] = []

    def set_categories(self, categories: list[Category]) -> None:
        self._categories = {c.category_id: c for c in categories}
        # refresh labels if table has rows
        if self._all_objects:
            self._populate(self._all_objects)

    def set_filter_category(self, category_id: str | None) -> None:
        self._filter_category_id = category_id
        if self._all_objects:
            self._populate(self._all_objects)

    def clear(self) -> None:
        self._block = True
        self._table.setRowCount(0)
        self._object_ids = []
        self._count.setText("对象 0")
        self._block = False

    def set_image_record(self, record: ImageRecord | None) -> None:
        if record is None:
            self._all_objects = []
            self._populate([])
            return
        self._all_objects = list(record.objects)
        self._populate(self._all_objects)

    def _populate(self, objects: list[SpecimenObject]) -> None:
        self._block = True
        self._table.setRowCount(0)
        self._object_ids = []
        shown = objects
        if self._filter_category_id:
            shown = [
                o for o in objects if o.category_id == self._filter_category_id
            ]
        for obj in shown:
            self._append_row(obj)
        self._count.setText(
            f"对象 {len(shown)}"
            + (f" / {len(objects)}" if self._filter_category_id else "")
        )
        self._block = False

    def select_object(self, object_id: str | None) -> None:
        self._block = True
        self._table.clearSelection()
        if object_id is None:
            self._block = False
            return
        try:
            row = self._object_ids.index(object_id)
        except ValueError:
            self._block = False
            return
        self._table.selectRow(row)
        self._block = False

    def selected_object_ids(self) -> list[str]:
        rows = self._table.selectionModel().selectedRows()
        ids: list[str] = []
        for r in rows:
            i = r.row()
            if 0 <= i < len(self._object_ids):
                ids.append(self._object_ids[i])
        return ids

    def update_object_row(self, obj: SpecimenObject) -> None:
        if obj.object_id not in self._object_ids:
            self._append_row(obj)
            self._count.setText(f"对象 {len(self._object_ids)}")
            return
        row = self._object_ids.index(obj.object_id)
        self._set_row(row, obj)

    def remove_object_row(self, object_id: str) -> None:
        if object_id not in self._object_ids:
            return
        row = self._object_ids.index(object_id)
        self._block = True
        self._table.removeRow(row)
        self._object_ids.pop(row)
        self._count.setText(f"对象 {len(self._object_ids)}")
        self._block = False

    def _append_row(self, obj: SpecimenObject) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._object_ids.append(obj.object_id)
        self._set_row(row, obj)

    def _set_row(self, row: int, obj: SpecimenObject) -> None:
        from PySide6.QtGui import QBrush, QColor

        text_color = QColor("#1c1c1e")

        def item(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it.setForeground(QBrush(text_color))
            return it

        um2 = f"{obj.area_um2:.1f}" if obj.area_um2 is not None else "—"
        lp = f"{obj.length_px:.1f}" if obj.length_px is not None else "—"
        conf = "是" if obj.confirmed else "否"
        cat = self._categories.get(obj.category_id)
        cat_name = cat.name_zh if cat else obj.category_id
        self._table.setItem(row, 0, item(obj.object_id))
        cat_item = item(cat_name)
        if cat:
            # Soft pastel tint instead of full saturated cell fill
            base = QColor(cat.color)
            if base.isValid():
                r = int(base.red() * 0.22 + 255 * 0.78)
                g = int(base.green() * 0.22 + 255 * 0.78)
                b = int(base.blue() * 0.22 + 255 * 0.78)
                cat_item.setBackground(QBrush(QColor(r, g, b)))
                cat_item.setForeground(QBrush(text_color))
        self._table.setItem(row, 1, cat_item)
        self._table.setItem(row, 2, item(f"{obj.area_px:.0f}"))
        self._table.setItem(row, 3, item(um2))
        self._table.setItem(row, 4, item(lp))
        self._table.setItem(row, 5, item(conf))

    def _on_sel(self) -> None:
        if self._block:
            return
        ids = self.selected_object_ids()
        if not ids:
            self.selection_cleared.emit()
            return
        self.objects_selected.emit(ids)
        self.object_selected.emit(ids[-1])

    def _on_delete(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if 0 <= row < len(self._object_ids):
            self.delete_requested.emit(self._object_ids[row])
