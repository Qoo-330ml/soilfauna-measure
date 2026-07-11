"""Left panel: category list, counts, CRUD."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from soilfauna_measure.models.category import Category
from soilfauna_measure.models.project import Project
from soilfauna_measure.ui.theme import muted_label_style, title_label_style


def _color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Soft rounded-looking swatch (square fill; Qt icon clip is square)."""
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    from PySide6.QtGui import QPainter

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(hex_color or "#9a9a9a"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pix)


class CategoryPanel(QWidget):
    """Manage categories and filter/assign."""

    category_activated = Signal(str)  # category_id for assign to selection
    categories_changed = Signal()
    filter_changed = Signal(object)  # category_id or None for all

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._project: Project | None = None
        self._counts: dict[str, int] = {}

        title = QLabel("分类")
        title.setStyleSheet(title_label_style())

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_double)
        self._list.itemClicked.connect(self._on_click)

        self._btn_add = QPushButton("新增")
        self._btn_rename = QPushButton("重命名")
        self._btn_color = QPushButton("颜色")
        self._btn_del = QPushButton("删除")
        self._btn_all = QPushButton("全部")

        for b in (
            self._btn_add,
            self._btn_rename,
            self._btn_color,
            self._btn_del,
            self._btn_all,
        ):
            b.setMaximumHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_add.clicked.connect(self._add)
        self._btn_rename.clicked.connect(self._rename)
        self._btn_color.clicked.connect(self._recolor)
        self._btn_del.clicked.connect(self._delete)
        self._btn_all.clicked.connect(lambda: self.filter_changed.emit(None))

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(self._btn_add)
        row1.addWidget(self._btn_rename)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(self._btn_color)
        row2.addWidget(self._btn_del)
        row2.addWidget(self._btn_all)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        hint = QLabel("双击赋给选中对象 · 0–7 快捷分类")
        hint.setWordWrap(True)
        hint.setStyleSheet(muted_label_style())
        layout.addWidget(hint)

    def set_project(self, project: Project | None, counts: dict[str, int] | None = None) -> None:
        self._project = project
        self._counts = counts or {}
        self._rebuild()

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = counts
        self._rebuild()

    def _rebuild(self) -> None:
        self._list.clear()
        if self._project is None:
            return
        for cat in self._project.categories:
            if not cat.enabled:
                continue
            n = self._counts.get(cat.category_id, 0)
            sc = f" [{cat.shortcut}]" if cat.shortcut else ""
            text = f"{cat.name_zh}{sc}  ({n})"
            item = QListWidgetItem(_color_icon(cat.color), text)
            item.setData(Qt.ItemDataRole.UserRole, cat.category_id)
            item.setToolTip(
                f"{cat.name_zh} / {cat.name_en}\nid={cat.category_id}\n{cat.measurement_note}"
            )
            self._list.addItem(item)

    def _current_id(self) -> str | None:
        item = self._list.currentItem()
        if not item:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _on_double(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.category_activated.emit(str(cid))

    def _on_click(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.filter_changed.emit(str(cid))

    def _add(self) -> None:
        if self._project is None:
            return
        name, ok = QInputDialog.getText(self, "新增分类", "中文名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        base = "cat"
        # generate id
        n = 1
        existing = {c.category_id for c in self._project.categories}
        cid = f"{base}_{n}"
        while cid in existing:
            n += 1
            cid = f"{base}_{n}"
        en, ok2 = QInputDialog.getText(self, "新增分类", "英文名称（可选）：")
        en = en.strip() if ok2 else ""
        cat = Category(
            category_id=cid,
            name_zh=name,
            name_en=en or name,
            color="#af52de",
            shortcut=None,
        )
        self._project.categories.append(cat)
        self._rebuild()
        self.categories_changed.emit()

    def _rename(self) -> None:
        if self._project is None:
            return
        cid = self._current_id()
        if not cid:
            return
        cat = next((c for c in self._project.categories if c.category_id == cid), None)
        if cat is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名", "中文名称：", text=cat.name_zh
        )
        if not ok or not name.strip():
            return
        cat.name_zh = name.strip()
        self._rebuild()
        self.categories_changed.emit()

    def _recolor(self) -> None:
        if self._project is None:
            return
        cid = self._current_id()
        if not cid:
            return
        cat = next((c for c in self._project.categories if c.category_id == cid), None)
        if cat is None:
            return
        color = QColorDialog.getColor(QColor(cat.color), self, "选择颜色")
        if not color.isValid():
            return
        cat.color = color.name()
        self._rebuild()
        self.categories_changed.emit()

    def _delete(self) -> None:
        if self._project is None:
            return
        cid = self._current_id()
        if not cid:
            return
        if cid == "unclassified":
            QMessageBox.information(self, "删除", "不能删除「未分类」。")
            return
        n = self._counts.get(cid, 0)
        if n > 0:
            ans = QMessageBox.question(
                self,
                "删除分类",
                f"分类下有 {n} 个对象，删除后将改回「未分类」。继续？",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        self._project.categories = [
            c for c in self._project.categories if c.category_id != cid
        ]
        self._rebuild()
        self.categories_changed.emit()
