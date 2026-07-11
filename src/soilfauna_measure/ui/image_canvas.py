"""Central image canvas: zoom/pan, scale, polygon, brush, length path."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from soilfauna_measure.core.image_loader import array_to_display_rgb
from soilfauna_measure.core.measurement import (
    copy_points,
    nearest_point_index,
    nearest_segment_insert,
    polyline_length_px,
)
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.ui.theme import (
    CANVAS_BG,
    CUT_TOOL,
    LENGTH_ACTIVE,
    LENGTH_END,
    LENGTH_MID,
    LENGTH_PATH,
    SEED_TOOL,
    SELECTION_FILL,
    SELECTION_OUTLINE,
)

logger = logging.getLogger(__name__)

MIN_ZOOM = 0.05
MAX_ZOOM = 40.0
ZOOM_STEP = 1.15

MODE_NAVIGATE = "navigate"
MODE_SCALE = "scale"
MODE_SELECT = "select"
MODE_POLYGON = "polygon"
MODE_BRUSH = "brush"
MODE_ERASER = "eraser"
MODE_LENGTH = "length"
MODE_LENGTH_EDIT = "length_edit"  # hand tool: drag / delete nodes only
MODE_SPLIT_CUT = "split_cut"
MODE_SPLIT_SEED = "split_seed"

# Modes that edit the selected object's length polyline
LENGTH_TOOL_MODES = frozenset({MODE_LENGTH, MODE_LENGTH_EDIT})

NODE_HIT_PX = 10.0
NODE_HIT_EDIT_PX = 14.0  # larger grab area for hand tool
SEG_HIT_PX = 8.0


def numpy_rgb_to_qimage(rgb: np.ndarray) -> QImage:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"Expected HxWx3 uint8, got {rgb.shape} {rgb.dtype}")
    if rgb.dtype != np.uint8:
        raise ValueError(f"Expected uint8, got {rgb.dtype}")
    rgb = np.ascontiguousarray(rgb)
    h, w, _ = rgb.shape
    bytes_per_line = 3 * w
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return qimg.copy()


def _mask_to_rgba_qimage(mask: np.ndarray, color: QColor, alpha: int = 80) -> QImage:
    h, w = mask.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    fg = mask > 0
    rgba[fg, 0] = color.red()
    rgba[fg, 1] = color.green()
    rgba[fg, 2] = color.blue()
    rgba[fg, 3] = alpha
    qimg = QImage(rgba.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    return qimg.copy()


class ImageCanvas(QGraphicsView):
    """Scene unit = 1 image pixel; origin top-left."""

    cursor_image_pos = Signal(float, float)
    zoom_changed = Signal(float)
    brush_radius_changed = Signal(float)
    status_message = Signal(str)
    scale_points_chosen = Signal(float, float, float, float)
    scale_mode_changed = Signal(bool)
    tool_mode_changed = Signal(str)

    polygon_finished = Signal(object)
    brush_stroke_finished = Signal(object, bool)
    object_clicked = Signal(str)
    empty_clicked = Signal()

    # length: object_id, new_points (live preview metrics)
    length_live = Signal(str, object)
    # length: object_id, old_points, new_points (commit for undo)
    length_committed = Signal(str, object, object)
    length_node_changed = Signal(int)  # selected node index or -1

    # split tools
    split_cut_finished = Signal(object)  # polyline points
    split_seeds_finished = Signal(object)  # list[(x,y)]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._image_width = 0
        self._image_height = 0
        self._panning = False
        self._pan_start = QPoint()
        self._pan_origin = QPoint()  # press point for click-vs-drag threshold
        self._pan_moved = False
        self._pan_click_empty = False  # empty-area pan: release may mean deselect
        self._space_pan = False

        self._mode = MODE_NAVIGATE
        self._scale_start: tuple[float, float] | None = None
        self._scale_preview_line: QGraphicsLineItem | None = None
        self._scale_markers: list = []
        self._scale_overlay_items: list = []
        self._show_scale_overlay = True
        self._current_scale: ScaleCalibration | None = None

        self._objects: list[SpecimenObject] = []
        self._masks: dict[str, np.ndarray] = {}
        self._category_colors: dict[str, str] = {}
        self._selected_id: str | None = None
        self._show_contours = True
        self._show_masks = True
        self._show_labels = True
        self._show_length = True
        self._object_items: list = []
        self._mask_items: dict[str, QGraphicsPixmapItem] = {}
        self._length_items: list = []

        self._poly_points: list[list[float]] = []
        self._poly_items: list = []

        self._brush_radius = 8.0
        self._brushing = False
        self._stroke: list[list[float]] = []
        self._brush_cursor: QGraphicsEllipseItem | None = None

        # Length edit
        self._length_points: list[list[float]] = []
        self._length_selected_node: int | None = None
        self._length_dragging = False
        self._length_drag_index: int | None = None
        self._length_drag_before: list[list[float]] | None = None

        # Split tools
        self._cut_points: list[list[float]] = []
        self._cut_items: list = []
        self._seed_points: list[tuple[float, float]] = []
        self._seed_items: list = []

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QColor(CANVAS_BG))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)

    # --- public API ---

    @property
    def image_size(self) -> tuple[int, int]:
        return self._image_width, self._image_height

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def brush_radius(self) -> float:
        return self._brush_radius

    @property
    def length_points(self) -> list[list[float]]:
        return copy_points(self._length_points)

    @property
    def length_selected_node(self) -> int | None:
        return self._length_selected_node

    def _in_length_tool(self) -> bool:
        return self._mode in LENGTH_TOOL_MODES

    def _length_hit_radius(self) -> float:
        z = max(self.current_zoom(), 0.05)
        if self._mode == MODE_LENGTH_EDIT:
            return max(NODE_HIT_EDIT_PX / z, 5.0)
        return max(NODE_HIT_PX / z, 4.0)

    def set_brush_radius(self, r: float) -> None:
        new_r = max(1.0, min(200.0, float(r)))
        if abs(new_r - self._brush_radius) < 1e-6:
            self._update_brush_cursor_pos()
            return
        self._brush_radius = new_r
        self._update_brush_cursor_pos()
        self.brush_radius_changed.emit(self._brush_radius)

    def clear_image(self) -> None:
        self._clear_all_overlays()
        self._scene.clear()
        self._pixmap_item = None
        self._image_width = 0
        self._image_height = 0
        self._current_scale = None
        self._objects = []
        self._masks = {}
        self._selected_id = None
        self._length_points = []
        self._length_selected_node = None
        self.resetTransform()
        self.zoom_changed.emit(self.current_zoom())

    def set_image_array(self, raw: np.ndarray) -> None:
        rgb = array_to_display_rgb(raw)
        self.set_qimage(numpy_rgb_to_qimage(rgb))

    def set_qimage(self, qimg: QImage) -> None:
        self._clear_all_overlays()
        self._scene.clear()
        self._pixmap_item = None
        self._mask_items.clear()
        self._object_items.clear()
        self._length_items.clear()
        pix = QPixmap.fromImage(qimg)
        self._image_width = pix.width()
        self._image_height = pix.height()
        item = self._scene.addPixmap(pix)
        item.setZValue(0)
        self._pixmap_item = item
        self._scene.setSceneRect(0, 0, self._image_width, self._image_height)
        self.fit_to_window()
        self._redraw_object_overlays()
        if self._current_scale is not None:
            self._draw_scale_overlay(self._current_scale)

    def set_scale_calibration(self, scale: ScaleCalibration | None) -> None:
        self._current_scale = scale
        self._clear_scale_overlay()
        if scale is not None and self._show_scale_overlay and self._image_width > 0:
            self._draw_scale_overlay(scale)

    def set_show_scale_overlay(self, show: bool) -> None:
        self._show_scale_overlay = show
        self._clear_scale_overlay()
        if show and self._current_scale is not None and self._image_width > 0:
            self._draw_scale_overlay(self._current_scale)

    def set_show_contours(self, show: bool) -> None:
        self._show_contours = show
        self._redraw_object_overlays()

    def set_show_masks(self, show: bool) -> None:
        self._show_masks = show
        self._redraw_object_overlays()

    def set_show_labels(self, show: bool) -> None:
        self._show_labels = show
        self._redraw_object_overlays()

    def set_show_length(self, show: bool) -> None:
        self._show_length = show
        self._redraw_object_overlays()

    def set_objects(
        self,
        objects: list[SpecimenObject],
        masks: dict[str, np.ndarray],
        selected_id: str | None = None,
        category_colors: dict[str, str] | None = None,
    ) -> None:
        self._objects = list(objects)
        self._masks = dict(masks)
        self._selected_id = selected_id
        if category_colors is not None:
            self._category_colors = dict(category_colors)
        if self._in_length_tool() and selected_id:
            obj = next((o for o in self._objects if o.object_id == selected_id), None)
            if obj is not None and not self._length_dragging:
                self._length_points = copy_points(obj.length_points)
        self._redraw_object_overlays()

    def set_category_colors(self, colors: dict[str, str]) -> None:
        self._category_colors = dict(colors)
        self._redraw_object_overlays()

    def set_selected_object(self, object_id: str | None) -> None:
        self._selected_id = object_id
        if self._in_length_tool():
            if object_id:
                obj = next((o for o in self._objects if o.object_id == object_id), None)
                self._length_points = copy_points(obj.length_points if obj else [])
            else:
                self._length_points = []
            self._length_selected_node = None
        self._redraw_object_overlays()

    def sync_length_points_from_object(self, obj: SpecimenObject | None) -> None:
        """Refresh working length path after undo/external change."""
        if obj is None:
            self._length_points = []
        else:
            self._length_points = copy_points(obj.length_points)
        self._redraw_object_overlays()

    def update_object_visual(
        self,
        obj: SpecimenObject,
        mask: np.ndarray | None,
    ) -> None:
        found = False
        for i, o in enumerate(self._objects):
            if o.object_id == obj.object_id:
                self._objects[i] = obj
                found = True
                break
        if not found:
            self._objects.append(obj)
        if mask is not None:
            self._masks[obj.object_id] = mask
        if self._in_length_tool() and obj.object_id == self._selected_id:
            if not self._length_dragging:
                self._length_points = copy_points(obj.length_points)
        self._redraw_object_overlays()

    def remove_object_visual(self, object_id: str) -> None:
        self._objects = [o for o in self._objects if o.object_id != object_id]
        self._masks.pop(object_id, None)
        if self._selected_id == object_id:
            self._selected_id = None
            self._length_points = []
        self._redraw_object_overlays()

    def set_tool_mode(self, mode: str) -> None:
        if mode == MODE_SCALE:
            self.enter_scale_mode()
            return
        self.cancel_scale_mode(silent=True)
        self._finish_polygon_preview_clear()
        self._clear_cut_preview()
        self._clear_seed_preview()
        self._length_dragging = False
        self._length_drag_before = None

        if mode in LENGTH_TOOL_MODES:
            if not self._selected_id:
                self.status_message.emit("请先选择一个对象再编辑体长")
                mode = MODE_SELECT
            else:
                obj = next(
                    (o for o in self._objects if o.object_id == self._selected_id),
                    None,
                )
                self._length_points = copy_points(obj.length_points if obj else [])
                self._length_selected_node = None
                if mode == MODE_LENGTH_EDIT and not self._length_points:
                    self.status_message.emit(
                        "当前对象尚无体长节点，请先用「体长路径 L」绘制或「G」自动建议"
                    )
        elif mode in (MODE_SPLIT_CUT, MODE_SPLIT_SEED):
            if not self._selected_id:
                self.status_message.emit("请先选择要拆分的对象")
                mode = MODE_SELECT

        self._mode = mode
        if mode == MODE_LENGTH_EDIT:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode in (
            MODE_BRUSH,
            MODE_ERASER,
            MODE_POLYGON,
            MODE_LENGTH,
            MODE_SPLIT_CUT,
            MODE_SPLIT_SEED,
        ):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.tool_mode_changed.emit(mode)
        hints = {
            MODE_NAVIGATE: "浏览：拖动平移 · 滚轮缩放",
            MODE_SELECT: "选择：点对象选中 · 空白处拖动平移",
            MODE_POLYGON: "多边形：左键加点，Enter/双击完成，Esc 取消",
            MODE_BRUSH: "画笔：涂抹增加掩膜 · [ ] 或 Ctrl+滚轮调粗细",
            MODE_ERASER: "橡皮：擦除掩膜（切断体会拆对象/体长）· [ ] 调粗细",
            MODE_LENGTH: (
                "体长：左键追加节点；拖动节点；双击线段插点；"
                "Delete 删节点；R 反转；X 清空"
            ),
            MODE_LENGTH_EDIT: (
                "小手调整体长：拖动节点移动；单击选中；"
                "Delete/右键/双击节点删除；双击线段插点；Esc 退出"
            ),
            MODE_SPLIT_CUT: "切割拆分：在对象上画切割线，Enter 确认，Esc 取消",
            MODE_SPLIT_SEED: "种子拆分：在各子体上点击种子，Enter 确认（≥2点）",
        }
        # Avoid overwriting the "no nodes yet" message for hand tool
        if not (
            mode == MODE_LENGTH_EDIT
            and self._selected_id
            and not self._length_points
        ):
            self.status_message.emit(hints.get(mode, mode))
        self._redraw_object_overlays()
        self.setFocus()

    def enter_scale_mode(self) -> None:
        if self._image_width <= 0:
            self.status_message.emit("请先打开图片")
            return
        self._finish_polygon_preview_clear()
        self._mode = MODE_SCALE
        self._scale_start = None
        self._clear_scale_tool_graphics()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.scale_mode_changed.emit(True)
        self.tool_mode_changed.emit(MODE_SCALE)
        self.status_message.emit("比例尺校准：点击起点")
        self.setFocus()

    def cancel_scale_mode(self, silent: bool = False) -> None:
        was = self._mode == MODE_SCALE
        if was:
            self._mode = MODE_NAVIGATE
            self._scale_start = None
            self._clear_scale_tool_graphics()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.scale_mode_changed.emit(False)
            self.tool_mode_changed.emit(MODE_NAVIGATE)
            if not silent:
                self.status_message.emit("已取消比例尺校准")

    def cancel_active_tool(self) -> None:
        if self._mode == MODE_SCALE:
            self.cancel_scale_mode()
        elif self._mode == MODE_POLYGON:
            self._finish_polygon_preview_clear()
            self._mode = MODE_SELECT
            self.tool_mode_changed.emit(MODE_SELECT)
            self.status_message.emit("已取消多边形")
        elif self._brushing:
            self._brushing = False
            self._stroke = []
        elif self._in_length_tool():
            self._mode = MODE_SELECT
            self._length_selected_node = None
            self._length_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.tool_mode_changed.emit(MODE_SELECT)
            self.status_message.emit("退出体长编辑")
            self._redraw_object_overlays()
        elif self._mode == MODE_SPLIT_CUT:
            self._clear_cut_preview()
            self._mode = MODE_SELECT
            self.tool_mode_changed.emit(MODE_SELECT)
            self.status_message.emit("已取消切割")
        elif self._mode == MODE_SPLIT_SEED:
            self._clear_seed_preview()
            self._mode = MODE_SELECT
            self.tool_mode_changed.emit(MODE_SELECT)
            self.status_message.emit("已取消种子拆分")

    def reverse_length_path(self) -> None:
        if not self._in_length_tool() or not self._selected_id:
            return
        before = copy_points(self._length_points)
        after = list(reversed(before))
        self._length_points = after
        self._length_selected_node = None
        self._emit_commit(before, after)
        self._redraw_object_overlays()

    def clear_length_path(self) -> None:
        if not self._in_length_tool() or not self._selected_id:
            return
        before = copy_points(self._length_points)
        if not before:
            return
        after: list[list[float]] = []
        self._length_points = after
        self._length_selected_node = None
        self._emit_commit(before, after)
        self._redraw_object_overlays()

    def delete_selected_length_node(self) -> bool:
        """Delete selected length node. Returns True if handled."""
        if not self._in_length_tool() or not self._selected_id:
            return False
        if self._length_selected_node is None:
            return False
        return self._delete_length_node_at(self._length_selected_node)

    def _delete_length_node_at(self, idx: int) -> bool:
        """Delete node at index; returns True if deleted."""
        if not self._in_length_tool() or not self._selected_id:
            return False
        if not (0 <= idx < len(self._length_points)):
            return False
        before = copy_points(self._length_points)
        after = copy_points(self._length_points)
        after.pop(idx)
        self._length_points = after
        # Keep selection near the removed index when possible
        if after:
            self._length_selected_node = min(idx, len(after) - 1)
        else:
            self._length_selected_node = None
        self._emit_commit(before, after)
        self.length_node_changed.emit(
            self._length_selected_node if self._length_selected_node is not None else -1
        )
        self._redraw_object_overlays()
        n = len(after)
        L = polyline_length_px(after) if n >= 2 else 0.0
        self.status_message.emit(f"已删除节点，剩余 {n} 个" + (f"，长度 {L:.2f} px" if n >= 2 else ""))
        return True

    def current_zoom(self) -> float:
        return float(self.transform().m11())

    def fit_to_window(self) -> None:
        if self._image_width <= 0 or self._image_height <= 0:
            return
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        z = self.current_zoom()
        if z < MIN_ZOOM or z > MAX_ZOOM:
            self._set_zoom(max(MIN_ZOOM, min(MAX_ZOOM, z)))
        self.zoom_changed.emit(self.current_zoom())

    def zoom_1_to_1(self) -> None:
        if self._image_width <= 0:
            return
        self._set_zoom(1.0)
        self.centerOn(self._image_width / 2.0, self._image_height / 2.0)

    def view_to_image(self, view_pos: QPoint | QPointF) -> tuple[float, float]:
        scene_pos = self.mapToScene(QPoint(int(view_pos.x()), int(view_pos.y())))
        return float(scene_pos.x()), float(scene_pos.y())

    # --- overlays ---

    def _clear_all_overlays(self) -> None:
        self._clear_scale_tool_graphics()
        self._clear_scale_overlay()
        self._clear_object_overlays()
        self._finish_polygon_preview_clear()
        self._clear_cut_preview()
        self._clear_seed_preview()
        self._remove_brush_cursor()

    def _clear_cut_preview(self) -> None:
        for it in self._cut_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._cut_items.clear()
        self._cut_points.clear()

    def _clear_seed_preview(self) -> None:
        for it in self._seed_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._seed_items.clear()
        self._seed_points.clear()

    def _redraw_cut_preview(self) -> None:
        for it in self._cut_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._cut_items.clear()
        pen = QPen(QColor(CUT_TOOL))
        pen.setCosmetic(True)
        pen.setWidth(2)
        for i, (x, y) in enumerate(self._cut_points):
            r = 3.0
            ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            ell.setBrush(QBrush(QColor(CUT_TOOL)))
            ell.setPen(pen)
            ell.setZValue(28)
            self._scene.addItem(ell)
            self._cut_items.append(ell)
            if i > 0:
                x0, y0 = self._cut_points[i - 1]
                line = QGraphicsLineItem(x0, y0, x, y)
                line.setPen(pen)
                line.setZValue(27)
                self._scene.addItem(line)
                self._cut_items.append(line)

    def _redraw_seed_preview(self) -> None:
        for it in self._seed_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._seed_items.clear()
        for i, (x, y) in enumerate(self._seed_points):
            r = 5.0
            ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            ell.setBrush(QBrush(QColor(SEED_TOOL)))
            pen = QPen(QColor(255, 255, 255, 220))
            pen.setCosmetic(True)
            ell.setPen(pen)
            ell.setZValue(28)
            self._scene.addItem(ell)
            self._seed_items.append(ell)
            text = QGraphicsSimpleTextItem(str(i + 1))
            text.setBrush(QBrush(QColor(SEED_TOOL)))
            text.setPos(x + 6, y - 6)
            text.setZValue(29)
            sc = 1.0 / max(self.current_zoom(), 0.01)
            text.setScale(sc)
            self._scene.addItem(text)
            self._seed_items.append(text)

    def _clear_scale_overlay(self) -> None:
        for it in self._scale_overlay_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._scale_overlay_items.clear()

    def _clear_scale_tool_graphics(self) -> None:
        if self._scale_preview_line is not None:
            if self._scale_preview_line.scene() is self._scene:
                self._scene.removeItem(self._scale_preview_line)
            self._scale_preview_line = None
        for it in self._scale_markers:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._scale_markers.clear()

    def _clear_object_overlays(self) -> None:
        for it in self._object_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._object_items.clear()
        for it in self._mask_items.values():
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._mask_items.clear()
        for it in self._length_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._length_items.clear()

    def _object_color(self, obj: SpecimenObject, selected: bool) -> QColor:
        if selected:
            # Soft high-visibility selection (independent of category)
            return QColor(SELECTION_FILL)
        hex_c = self._category_colors.get(obj.category_id)
        if hex_c:
            color = QColor(hex_c)
            if not color.isValid():
                color = QColor("#007aff")
        else:
            h = abs(hash(obj.object_id)) % 360
            color = QColor.fromHsv(h, 120, 200)
        return color

    def _hit_radius(self) -> float:
        # roughly constant screen size
        z = max(self.current_zoom(), 0.05)
        return max(NODE_HIT_PX / z, 4.0)

    def _redraw_object_overlays(self) -> None:
        if self._image_width <= 0:
            return
        self._clear_object_overlays()
        for obj in self._objects:
            selected = obj.object_id == self._selected_id
            color = self._object_color(obj, selected)
            mask = self._masks.get(obj.object_id)
            if self._show_masks and mask is not None and np.any(mask):
                # Selected: readable fill; others: light tint
                alpha = 140 if selected else 48
                qimg = _mask_to_rgba_qimage(mask, color, alpha=alpha)
                pix = QPixmap.fromImage(qimg)
                item = self._scene.addPixmap(pix)
                item.setZValue(6 if selected else 5)
                self._mask_items[obj.object_id] = item

            if self._show_contours and obj.contour and len(obj.contour) >= 2:
                poly = QPolygonF([QPointF(p[0], p[1]) for p in obj.contour])
                if obj.contour[0] != obj.contour[-1]:
                    poly.append(QPointF(obj.contour[0][0], obj.contour[0][1]))
                gpoly = QGraphicsPolygonItem(poly)
                if selected:
                    pen = QPen(QColor(SELECTION_OUTLINE))
                    pen.setWidth(3)
                else:
                    pen = QPen(color)
                    pen.setWidth(2)
                pen.setCosmetic(True)
                gpoly.setPen(pen)
                gpoly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                gpoly.setZValue(10 if selected else 8)
                self._scene.addItem(gpoly)
                self._object_items.append(gpoly)

            if self._show_labels and obj.contour:
                xs = [p[0] for p in obj.contour]
                ys = [p[1] for p in obj.contour]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                text = QGraphicsSimpleTextItem(obj.object_id)
                text.setBrush(QBrush(color))
                text.setPos(cx, cy)
                text.setZValue(12)
                sc = 1.0 / max(self.current_zoom(), 0.01)
                text.setScale(sc)
                self._scene.addItem(text)
                self._object_items.append(text)

            # length path (non-editing objects, or live path while length tool active)
            if self._show_length:
                if self._in_length_tool() and obj.object_id == self._selected_id:
                    pts = self._length_points
                    editing = True
                else:
                    pts = obj.length_points or []
                    editing = False
                if pts:
                    self._draw_length_path(pts, editing=editing)

        if self._current_scale is not None and self._show_scale_overlay:
            self._clear_scale_overlay()
            self._draw_scale_overlay(self._current_scale)

    def _draw_length_path(self, points: list[list[float]], *, editing: bool) -> None:
        if len(points) >= 2:
            pen = QPen(QColor(LENGTH_PATH))
            pen.setCosmetic(True)
            pen.setWidth(3 if editing else 2)
            for i in range(len(points) - 1):
                x0, y0 = points[i]
                x1, y1 = points[i + 1]
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(pen)
                line.setZValue(18)
                self._scene.addItem(line)
                self._length_items.append(line)

        hand = editing and self._mode == MODE_LENGTH_EDIT
        for i, (x, y) in enumerate(points):
            is_end = i == 0 or i == len(points) - 1
            if is_end:
                color = QColor(LENGTH_END)
            else:
                color = QColor(LENGTH_MID)
            if editing and self._length_selected_node == i:
                color = QColor(LENGTH_ACTIVE)
            r = 6.5 if hand else (5.0 if editing else 3.5)
            ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            ell.setBrush(QBrush(color))
            p = QPen(QColor(255, 255, 255, 220))
            p.setCosmetic(True)
            p.setWidth(2 if hand else 1)
            ell.setPen(p)
            ell.setZValue(19)
            self._scene.addItem(ell)
            self._length_items.append(ell)
            # Hand mode: show node index for precise delete/drag
            if hand:
                label = QGraphicsSimpleTextItem(str(i + 1))
                label.setBrush(QBrush(QColor(255, 255, 255)))
                label.setZValue(20)
                sc = 1.0 / max(self.current_zoom(), 0.01)
                label.setScale(sc * 0.9)
                label.setPos(x + r + 1, y - r - 2)
                self._scene.addItem(label)
                self._length_items.append(label)

    def _add_marker(self, x: float, y: float, color: QColor) -> None:
        r = 4.0
        ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
        ell.setBrush(QBrush(color))
        pen = QPen(QColor(255, 255, 255))
        pen.setCosmetic(True)
        pen.setWidth(1)
        ell.setPen(pen)
        ell.setZValue(20)
        self._scene.addItem(ell)
        self._scale_markers.append(ell)

    def _draw_scale_overlay(self, scale: ScaleCalibration) -> None:
        x0, y0 = scale.start_point
        x1, y1 = scale.end_point
        pen = QPen(QColor(LENGTH_END))
        pen.setCosmetic(True)
        pen.setWidth(2)
        line = QGraphicsLineItem(x0, y0, x1, y1)
        line.setPen(pen)
        line.setZValue(10)
        self._scene.addItem(line)
        self._scale_overlay_items.append(line)
        for x, y in ((x0, y0), (x1, y1)):
            r = 3.5
            ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            ell.setBrush(QBrush(QColor(LENGTH_END)))
            p = QPen(QColor(255, 255, 255, 220))
            p.setCosmetic(True)
            ell.setPen(p)
            ell.setZValue(11)
            self._scene.addItem(ell)
            self._scale_overlay_items.append(ell)

    def _finish_polygon_preview_clear(self) -> None:
        for it in self._poly_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._poly_items.clear()
        self._poly_points.clear()

    def _redraw_polygon_preview(self) -> None:
        for it in self._poly_items:
            if it.scene() is self._scene:
                self._scene.removeItem(it)
        self._poly_items.clear()
        if not self._poly_points:
            return
        pen = QPen(QColor(LENGTH_ACTIVE))
        pen.setCosmetic(True)
        pen.setWidth(2)
        for i, (x, y) in enumerate(self._poly_points):
            r = 3.0
            ell = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            ell.setBrush(QBrush(QColor(LENGTH_ACTIVE)))
            ell.setPen(pen)
            ell.setZValue(25)
            self._scene.addItem(ell)
            self._poly_items.append(ell)
            if i > 0:
                x0, y0 = self._poly_points[i - 1]
                line = QGraphicsLineItem(x0, y0, x, y)
                line.setPen(pen)
                line.setZValue(24)
                self._scene.addItem(line)
                self._poly_items.append(line)

    def _remove_brush_cursor(self) -> None:
        if self._brush_cursor is not None:
            if self._brush_cursor.scene() is self._scene:
                self._scene.removeItem(self._brush_cursor)
            self._brush_cursor = None

    def _update_brush_cursor_pos(self, x: float | None = None, y: float | None = None) -> None:
        if self._mode not in (MODE_BRUSH, MODE_ERASER):
            self._remove_brush_cursor()
            return
        if x is None or y is None:
            return
        r = self._brush_radius
        if self._brush_cursor is None:
            self._brush_cursor = QGraphicsEllipseItem(0, 0, 1, 1)
            pen = QPen(
                QColor(255, 255, 255)
                if self._mode == MODE_BRUSH
                else QColor(255, 100, 100)
            )
            pen.setCosmetic(True)
            pen.setWidth(1)
            self._brush_cursor.setPen(pen)
            self._brush_cursor.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._brush_cursor.setZValue(30)
            self._scene.addItem(self._brush_cursor)
        self._brush_cursor.setRect(x - r, y - r, 2 * r, 2 * r)

    def _set_zoom(self, scale: float) -> None:
        scale = max(MIN_ZOOM, min(MAX_ZOOM, float(scale)))
        self.resetTransform()
        self.scale(scale, scale)
        self.zoom_changed.emit(self.current_zoom())
        self._redraw_object_overlays()

    def _zoom_by(self, factor: float) -> None:
        if self._image_width <= 0:
            return
        new_zoom = self.current_zoom() * factor
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        factor = new_zoom / max(self.current_zoom(), 1e-12)
        self.scale(factor, factor)
        self.zoom_changed.emit(self.current_zoom())
        self._redraw_object_overlays()

    def _clamp_image(self, x: float, y: float) -> tuple[float, float]:
        return (
            min(max(x, 0.0), float(self._image_width)),
            min(max(y, 0.0), float(self._image_height)),
        )

    def _emit_live(self) -> None:
        if self._selected_id:
            self.length_live.emit(self._selected_id, copy_points(self._length_points))

    def _emit_commit(self, before: list, after: list) -> None:
        if self._selected_id:
            self.length_committed.emit(
                self._selected_id, copy_points(before), copy_points(after)
            )
            n = len(after)
            L = polyline_length_px(after)
            self.status_message.emit(f"体长节点 {n}，长度 {L:.2f} px")

    # --- events ---

    def _object_at(self, ix: float, iy: float) -> str | None:
        """Topmost object whose mask covers image point (ix, iy), or None."""
        if self._image_width <= 0:
            return None
        px, py = int(ix), int(iy)
        if not (0 <= px < self._image_width and 0 <= py < self._image_height):
            return None
        for obj in reversed(self._objects):
            m = self._masks.get(obj.object_id)
            if m is None:
                continue
            h, w = m.shape[:2]
            if 0 <= px < w and 0 <= py < h and m[py, px]:
                return obj.object_id
        return None

    def _begin_pan(self, pos: QPoint, *, from_empty: bool = False) -> None:
        self._panning = True
        self._pan_start = pos
        self._pan_origin = pos
        self._pan_moved = False
        self._pan_click_empty = from_empty
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan_cursor(self) -> None:
        if self._mode == MODE_LENGTH_EDIT:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._mode in (
            MODE_SCALE,
            MODE_POLYGON,
            MODE_BRUSH,
            MODE_ERASER,
            MODE_LENGTH,
            MODE_SPLIT_CUT,
            MODE_SPLIT_SEED,
        ):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._space_pan
                else Qt.CursorShape.ArrowCursor
            )

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._image_width <= 0:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            return
        # Brush/eraser: Alt or Shift + wheel adjusts size; plain wheel zooms.
        # Also: while in brush/eraser, Ctrl+wheel adjusts size (zoom uses plain).
        size_mod = bool(
            event.modifiers()
            & (
                Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.ShiftModifier
            )
        )
        if self._mode in (MODE_BRUSH, MODE_ERASER) and (
            size_mod
            or event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            step = 2.0 if delta > 0 else -2.0
            # Larger jumps when already thick
            if self._brush_radius >= 40:
                step *= 2
            self.set_brush_radius(self._brush_radius + step)
            self.status_message.emit(f"笔刷/橡皮粗细: {self._brush_radius:.0f}px")
            event.accept()
            return
        # Backward compatible: Alt+wheel always size even outside brush mode
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            step = 2.0 if delta > 0 else -2.0
            self.set_brush_radius(self._brush_radius + step)
            self.status_message.emit(f"笔刷/橡皮粗细: {self._brush_radius:.0f}px")
            event.accept()
            return
        factor = ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP
        self._zoom_by(factor)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and (
                self._space_pan
                or event.modifiers() & Qt.KeyboardModifier.ControlModifier
            )
        ):
            self._begin_pan(event.position().toPoint(), from_empty=False)
            event.accept()
            return

        if self._image_width <= 0:
            # Still allow panning empty canvas chrome
            if event.button() == Qt.MouseButton.LeftButton:
                self._begin_pan(event.position().toPoint(), from_empty=False)
                event.accept()
                return
            super().mousePressEvent(event)
            return

        raw_ix, raw_iy = self.view_to_image(event.position())
        ix, iy = self._clamp_image(raw_ix, raw_iy)

        if self._mode == MODE_SCALE and event.button() == Qt.MouseButton.LeftButton:
            if self._scale_start is None:
                self._scale_start = (ix, iy)
                self._add_marker(ix, iy, QColor(LENGTH_END))
                self.status_message.emit("比例尺校准：点击终点")
            else:
                x0, y0 = self._scale_start
                self._add_marker(ix, iy, QColor(LENGTH_END))
                if self._scale_preview_line is not None:
                    if self._scale_preview_line.scene() is self._scene:
                        self._scene.removeItem(self._scale_preview_line)
                    self._scale_preview_line = None
                self._mode = MODE_NAVIGATE
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.scale_mode_changed.emit(False)
                self.tool_mode_changed.emit(MODE_NAVIGATE)
                self.scale_points_chosen.emit(x0, y0, ix, iy)
                self._scale_start = None
            event.accept()
            return

        if self._in_length_tool() and event.button() == Qt.MouseButton.LeftButton:
            self._handle_length_press(ix, iy, edit_only=(self._mode == MODE_LENGTH_EDIT))
            event.accept()
            return

        # Hand tool: right-click deletes the nearest node
        if (
            self._mode == MODE_LENGTH_EDIT
            and event.button() == Qt.MouseButton.RightButton
        ):
            hit_r = self._length_hit_radius()
            ni = nearest_point_index(self._length_points, ix, iy, max_dist=hit_r)
            if ni is not None:
                self._delete_length_node_at(ni)
            else:
                self.status_message.emit("右键请点在节点上以删除")
            event.accept()
            return

        if self._mode == MODE_SPLIT_CUT and event.button() == Qt.MouseButton.LeftButton:
            self._cut_points.append([ix, iy])
            self._redraw_cut_preview()
            self.status_message.emit(
                f"切割线顶点 {len(self._cut_points)}（Enter 确认）"
            )
            event.accept()
            return

        if self._mode == MODE_SPLIT_SEED and event.button() == Qt.MouseButton.LeftButton:
            self._seed_points.append((ix, iy))
            self._redraw_seed_preview()
            self.status_message.emit(
                f"种子点 {len(self._seed_points)}（≥2，Enter 确认）"
            )
            event.accept()
            return

        if self._mode == MODE_POLYGON and event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._try_finish_polygon()
            else:
                self._poly_points.append([ix, iy])
                self._redraw_polygon_preview()
                self.status_message.emit(
                    f"多边形顶点 {len(self._poly_points)}（Enter/双击完成）"
                )
            event.accept()
            return

        if self._mode in (MODE_BRUSH, MODE_ERASER) and event.button() == Qt.MouseButton.LeftButton:
            if not self._selected_id:
                self.status_message.emit("请先选择一个对象再使用画笔/橡皮")
                event.accept()
                return
            self._brushing = True
            self._stroke = [[ix, iy]]
            event.accept()
            return

        if self._mode in (MODE_SELECT, MODE_NAVIGATE) and event.button() == Qt.MouseButton.LeftButton:
            # Use unclamped coords so drag outside the image still pans
            hit = self._object_at(raw_ix, raw_iy)
            if hit:
                self.object_clicked.emit(hit)
            else:
                # Blank / non-mask area: drag to pan (click without move deselects)
                self._begin_pan(event.position().toPoint(), from_empty=True)
            event.accept()
            return

        super().mousePressEvent(event)

    def _handle_length_press(
        self, ix: float, iy: float, *, edit_only: bool = False
    ) -> None:
        if not self._selected_id:
            self.status_message.emit("请先选择对象")
            return
        hit_r = self._length_hit_radius()
        ni = nearest_point_index(self._length_points, ix, iy, max_dist=hit_r)
        if ni is not None:
            self._length_selected_node = ni
            self._length_dragging = True
            self._length_drag_index = ni
            self._length_drag_before = copy_points(self._length_points)
            self.length_node_changed.emit(ni)
            if edit_only:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._redraw_object_overlays()
            return
        if edit_only:
            # Hand tool: empty click only deselects — never appends
            self._length_selected_node = None
            self.length_node_changed.emit(-1)
            self._redraw_object_overlays()
            self.status_message.emit("单击节点可拖动；右键/Delete/双击节点可删除")
            return
        # Draw mode: append new node
        before = copy_points(self._length_points)
        after = copy_points(self._length_points)
        after.append([ix, iy])
        self._length_points = after
        self._length_selected_node = len(after) - 1
        self._emit_commit(before, after)
        self.length_node_changed.emit(self._length_selected_node)
        self._redraw_object_overlays()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._mode == MODE_POLYGON and event.button() == Qt.MouseButton.LeftButton:
            self._try_finish_polygon()
            event.accept()
            return
        if self._in_length_tool() and event.button() == Qt.MouseButton.LeftButton:
            ix, iy = self._clamp_image(*self.view_to_image(event.position()))
            hit_r = self._length_hit_radius()
            ni = nearest_point_index(self._length_points, ix, iy, max_dist=hit_r)
            # Hand tool: double-click node deletes it
            if ni is not None and self._mode == MODE_LENGTH_EDIT:
                self._delete_length_node_at(ni)
                event.accept()
                return
            if ni is not None:
                event.accept()
                return
            seg = nearest_segment_insert(
                self._length_points, ix, iy, max_dist=max(SEG_HIT_PX, hit_r)
            )
            if seg is not None:
                insert_at, px, py = seg
                before = copy_points(self._length_points)
                after = copy_points(self._length_points)
                # insert at click position (or projection)
                after.insert(insert_at, [ix, iy])
                self._length_points = after
                self._length_selected_node = insert_at
                self._emit_commit(before, after)
                self._redraw_object_overlays()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            pos = event.position().toPoint()
            delta = pos - self._pan_start
            if not self._pan_moved:
                total = pos - self._pan_origin
                if abs(total.x()) + abs(total.y()) >= 3:
                    self._pan_moved = True
            self._pan_start = pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        if self._image_width > 0:
            ix, iy = self.view_to_image(event.position())
            self.cursor_image_pos.emit(ix, iy)
            cix, ciy = self._clamp_image(ix, iy)

            if self._mode == MODE_SCALE and self._scale_start is not None:
                x0, y0 = self._scale_start
                if self._scale_preview_line is None:
                    pen = QPen(QColor(LENGTH_END))
                    pen.setCosmetic(True)
                    pen.setWidth(2)
                    self._scale_preview_line = QGraphicsLineItem(x0, y0, cix, ciy)
                    self._scale_preview_line.setPen(pen)
                    self._scale_preview_line.setZValue(15)
                    self._scene.addItem(self._scale_preview_line)
                else:
                    self._scale_preview_line.setLine(x0, y0, cix, ciy)

            if self._mode in (MODE_BRUSH, MODE_ERASER):
                self._update_brush_cursor_pos(cix, ciy)
                if self._brushing:
                    self._stroke.append([cix, ciy])

            if (
                self._in_length_tool()
                and self._length_dragging
                and self._length_drag_index is not None
            ):
                i = self._length_drag_index
                if 0 <= i < len(self._length_points):
                    self._length_points[i] = [cix, ciy]
                    self._emit_live()
                    self._redraw_object_overlays()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            was_empty_click = self._pan_click_empty and not self._pan_moved
            self._panning = False
            self._pan_click_empty = False
            self._pan_moved = False
            self._end_pan_cursor()
            if was_empty_click and self._mode in (MODE_SELECT, MODE_NAVIGATE):
                self.empty_clicked.emit()
            event.accept()
            return

        if self._brushing and event.button() == Qt.MouseButton.LeftButton:
            self._brushing = False
            stroke = list(self._stroke)
            self._stroke = []
            if stroke:
                erase = self._mode == MODE_ERASER
                self.brush_stroke_finished.emit(stroke, erase)
            event.accept()
            return

        if (
            self._length_dragging
            and event.button() == Qt.MouseButton.LeftButton
            and self._in_length_tool()
        ):
            self._length_dragging = False
            before = self._length_drag_before
            after = copy_points(self._length_points)
            self._length_drag_before = None
            self._length_drag_index = None
            if self._mode == MODE_LENGTH_EDIT:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            if before is not None and before != after:
                self._emit_commit(before, after)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_active_tool()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._mode == MODE_POLYGON:
                self._try_finish_polygon()
                event.accept()
                return
            if self._in_length_tool():
                self.cancel_active_tool()
                event.accept()
                return
            if self._mode == MODE_SPLIT_CUT:
                if len(self._cut_points) < 2:
                    self.status_message.emit("切割线至少需要 2 个点")
                else:
                    pts = [list(p) for p in self._cut_points]
                    self._clear_cut_preview()
                    self.split_cut_finished.emit(pts)
                    self._mode = MODE_SELECT
                    self.tool_mode_changed.emit(MODE_SELECT)
                event.accept()
                return
            if self._mode == MODE_SPLIT_SEED:
                if len(self._seed_points) < 2:
                    self.status_message.emit("至少 2 个种子点")
                else:
                    seeds = list(self._seed_points)
                    self._clear_seed_preview()
                    self.split_seeds_finished.emit(seeds)
                    self._mode = MODE_SELECT
                    self.tool_mode_changed.emit(MODE_SELECT)
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.delete_selected_length_node():
                event.accept()
                return
        if self._in_length_tool() and event.key() == Qt.Key.Key_R:
            self.reverse_length_path()
            event.accept()
            return
        if self._in_length_tool() and event.key() == Qt.Key.Key_X:
            self.clear_length_path()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        if event.key() == Qt.Key.Key_BracketLeft:
            step = 4.0 if self._brush_radius >= 40 else 2.0
            self.set_brush_radius(self._brush_radius - step)
            self.status_message.emit(f"笔刷/橡皮粗细: {self._brush_radius:.0f}px")
            event.accept()
            return
        if event.key() == Qt.Key.Key_BracketRight:
            step = 4.0 if self._brush_radius >= 40 else 2.0
            self.set_brush_radius(self._brush_radius + step)
            self.status_message.emit(f"笔刷/橡皮粗细: {self._brush_radius:.0f}px")
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            if not self._panning:
                if self._mode == MODE_LENGTH_EDIT:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                elif self._mode in (
                    MODE_SCALE,
                    MODE_POLYGON,
                    MODE_BRUSH,
                    MODE_ERASER,
                    MODE_LENGTH,
                    MODE_SPLIT_CUT,
                    MODE_SPLIT_SEED,
                ):
                    self.setCursor(Qt.CursorShape.CrossCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _try_finish_polygon(self) -> None:
        if len(self._poly_points) < 3:
            self.status_message.emit("至少需要 3 个顶点")
            return
        pts = [list(p) for p in self._poly_points]
        self._finish_polygon_preview_clear()
        self.polygon_finished.emit(pts)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
