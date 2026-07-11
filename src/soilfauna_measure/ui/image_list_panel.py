"""Workspace image browser — horizontal thumbnail filmstrip."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.storage.workspace import Workspace
from soilfauna_measure.ui.theme import (
    SURFACE_MUTED,
    filmstrip_stylesheet,
    muted_label_style,
    secondary_label_style,
    title_label_style,
)

STATUS_LABEL = {
    "pending": "待处理",
    "in_progress": "进行中",
    "needs_review": "待确认",
    "done": "已完成",
}

STATUS_MARK = {
    "pending": "○",
    "in_progress": "◑",
    "needs_review": "◎",
    "done": "●",
}

# Filmstrip tile size (icon + caption)
THUMB_SIZE = 72
TILE_WIDTH = 96
TILE_HEIGHT = 104


class ImageListPanel(QWidget):
    """Horizontal filmstrip of workspace images; emits selection changes."""

    image_selected = Signal(int)  # index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setFlow(QListWidget.Flow.LeftToRight)
        self._list.setWrapping(False)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setUniformItemSizes(True)
        self._list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._list.setSpacing(6)
        self._list.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setWordWrap(True)
        self._list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._list.setStyleSheet(filmstrip_stylesheet())
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._counter = QLabel("0 / 0")
        self._counter.setStyleSheet(secondary_label_style())
        self._id_to_row: dict[str, int] = {}

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        title = QLabel("工作区图片")
        title.setStyleSheet(title_label_style())
        hint = QLabel("横向滚动 · 单击打开")
        hint.setStyleSheet(muted_label_style())
        header.addWidget(title)
        header.addWidget(hint)
        header.addStretch(1)
        header.addWidget(self._counter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self._list, stretch=1)

        self.setMinimumHeight(138)
        self.setMaximumHeight(158)
        self._block = False

    def set_workspace(self, workspace: Workspace | None) -> None:
        self._block = True
        self._list.clear()
        self._id_to_row.clear()
        if workspace is None:
            self._counter.setText("0 / 0")
            self._block = False
            return
        for i, img in enumerate(workspace.images):
            self._list.addItem(self._make_item(img))
            self._id_to_row[img.image_id] = i
        n = len(workspace.images)
        idx = workspace.current_index
        if 0 <= idx < n:
            self._list.setCurrentRow(idx)
            self._list.scrollToItem(
                self._list.item(idx),
                QListWidget.ScrollHint.PositionAtCenter,
            )
        self._update_counter(idx, n)
        self._block = False

    def set_current_index(self, index: int) -> None:
        if index < 0:
            return
        if self._list.currentRow() == index:
            self._update_counter(index, self._list.count())
            return
        self._block = True
        self._list.setCurrentRow(index)
        item = self._list.item(index)
        if item is not None:
            self._list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
        self._update_counter(index, self._list.count())
        self._block = False

    def refresh_item(self, index: int, record: ImageRecord) -> None:
        if 0 <= index < self._list.count():
            item = self._list.item(index)
            item.setText(self._item_text(record))
            item.setToolTip(self._item_tooltip(record))

    def set_thumbnail(self, image_id: str, thumb_path: str) -> None:
        row = self._id_to_row.get(image_id)
        if row is None or not (0 <= row < self._list.count()):
            return
        path = Path(thumb_path)
        if not path.is_file():
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            return
        # Keep aspect within thumb box
        scaled = pix.scaled(
            THUMB_SIZE,
            THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._list.item(row).setIcon(QIcon(scaled))

    def _item_text(self, img: ImageRecord) -> str:
        status = STATUS_MARK.get(img.status, "·")
        scale_mark = "📏" if img.scale and img.scale.confirmed else ""
        name = Path(img.relative_path).name
        # Keep caption short so tiles stay compact
        if len(name) > 14:
            stem = Path(name).stem
            suf = Path(name).suffix
            keep = 10 - len(suf)
            if keep < 4:
                keep = 4
            name = stem[:keep] + "…" + suf
        return f"{status}{scale_mark}\n{name}"

    def _item_tooltip(self, img: ImageRecord) -> str:
        status = STATUS_LABEL.get(img.status, img.status)
        scale = "已标定" if img.scale and img.scale.confirmed else "未标定"
        return f"{img.relative_path}\n状态: {status}\n比例尺: {scale}"

    def _make_item(self, img: ImageRecord) -> QListWidgetItem:
        item = QListWidgetItem(self._item_text(img))
        item.setToolTip(self._item_tooltip(img))
        item.setData(Qt.ItemDataRole.UserRole, img.image_id)
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        item.setSizeHint(QSize(TILE_WIDTH, TILE_HEIGHT))
        # Soft placeholder until thumbnails load
        placeholder = QPixmap(THUMB_SIZE, THUMB_SIZE)
        placeholder.fill(QColor(SURFACE_MUTED))
        item.setIcon(QIcon(placeholder))
        return item

    def _on_row_changed(self, row: int) -> None:
        self._update_counter(row, self._list.count())
        if self._block:
            return
        if row >= 0:
            self.image_selected.emit(row)

    def _update_counter(self, index: int, total: int) -> None:
        if total <= 0:
            self._counter.setText("0 / 0")
        else:
            human = index + 1 if index >= 0 else 0
            self._counter.setText(f"{human} / {total}")
