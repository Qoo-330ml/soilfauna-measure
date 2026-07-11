"""Main application window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from soilfauna_measure import __app_name__, __version__
from soilfauna_measure.commands.base_command import CommandStack
from soilfauna_measure.commands.length_commands import SetLengthPointsCommand
from soilfauna_measure.core.calibration import (
    build_scale_calibration,
    compute_pixel_length,
    format_scale_summary,
)
from soilfauna_measure.core.image_loader import describe_image
from soilfauna_measure.core.measurement import apply_length_to_object, copy_points
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.services.image_service import ImageService
from soilfauna_measure.services.object_service import ObjectService
from soilfauna_measure.storage.autosave import AutosaveController
from soilfauna_measure.storage.project_io import ProjectIOError
from soilfauna_measure.storage.workspace import (
    Workspace,
    open_workspace,
    save_workspace,
)
from soilfauna_measure.ui.image_canvas import (
    MODE_BRUSH,
    MODE_ERASER,
    MODE_LENGTH,
    MODE_LENGTH_EDIT,
    MODE_NAVIGATE,
    MODE_POLYGON,
    MODE_SELECT,
    MODE_SPLIT_CUT,
    MODE_SPLIT_SEED,
    ImageCanvas,
)
from soilfauna_measure.services.app_settings import (
    add_recent_workspace,
    clear_recent_workspaces,
    get_recent_workspaces,
    set_last_workspace,
)
from soilfauna_measure.services.export_service import export_project
from soilfauna_measure.ui.batch_dialog import BatchDialog
from soilfauna_measure.ui.category_panel import CategoryPanel
from soilfauna_measure.ui.export_dialog import ExportDialog
from soilfauna_measure.ui.image_list_panel import ImageListPanel
from soilfauna_measure.ui.object_table_panel import ObjectTablePanel
from soilfauna_measure.ui.properties_panel import PropertiesPanel
from soilfauna_measure.ui.scale_dialog import ScaleDialog
from soilfauna_measure.ui.segmentation_dialog import SegmentationDialog
from soilfauna_measure.ui.shortcuts_dialog import ShortcutsDialog
from soilfauna_measure.ui.theme import (
    apply_macos_window_chrome,
    mark_glass_panel,
    title_label_style,
)
from soilfauna_measure.workers.batch_worker import BatchController
from soilfauna_measure.workers.thumbnail_worker import start_thumbnail_batch

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1360, 860)
        try:
            from soilfauna_measure.resources import load_app_icon

            _ic = load_app_icon()
            if not _ic.isNull():
                self.setWindowIcon(_ic)
        except Exception:  # noqa: BLE001
            pass

        self._workspace: Workspace | None = None
        self._image_service = ImageService()
        self._object_service = ObjectService()
        self._autosave = AutosaveController(delay_ms=2500, parent=self)
        self._cmd_stack = CommandStack()
        self._batch = BatchController(self)
        self._batch_progress: QProgressDialog | None = None
        self._batch_seg_mode = "replace_unconfirmed"
        self._selected_object_id: str | None = None
        self._thumb_runnable = None

        self._canvas = ImageCanvas()
        self._image_list = ImageListPanel()
        self._properties = PropertiesPanel()
        self._object_table = ObjectTablePanel()
        self._category_panel = CategoryPanel()

        self._coord_label = QLabel("坐标: —")
        self._zoom_label = QLabel("缩放: —")
        self._workspace_label = QLabel("工作区: 未打开")
        self._save_label = QLabel("未保存: —")
        self._tool_label = QLabel("工具: 浏览")

        # Periodic safety autosave (in addition to debounced dirty saves)
        self._periodic_save = QTimer(self)
        self._periodic_save.setInterval(60_000)
        self._periodic_save.timeout.connect(self._periodic_autosave)

        self._build_layout()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        self._update_save_actions()
        self._rebuild_recent_menu()
        apply_macos_window_chrome(self)

    # --- UI construction ---

    def _build_layout(self) -> None:
        # Left glass column: categories + objects
        left = QWidget()
        mark_glass_panel(left)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 6, 4, 6)
        left_layout.setSpacing(6)
        left_layout.addWidget(self._category_panel, stretch=1)
        left_title = QLabel("对象列表")
        left_title.setStyleSheet(title_label_style() + " padding: 6px 12px 0 12px;")
        left_layout.addWidget(left_title)
        obj_wrap = QWidget()
        obj_layout = QVBoxLayout(obj_wrap)
        obj_layout.setContentsMargins(12, 4, 12, 10)
        obj_layout.setSpacing(0)
        obj_layout.addWidget(self._object_table, stretch=1)
        left_layout.addWidget(obj_wrap, stretch=2)
        left.setMinimumWidth(260)
        left.setMaximumWidth(400)

        # Center: canvas floats above soft chrome; filmstrip as glass dock
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 6, 4, 6)
        center_layout.setSpacing(8)
        center_layout.addWidget(self._canvas, stretch=1)
        center_layout.addWidget(self._image_list, stretch=0)

        # Right glass properties
        right = QWidget()
        mark_glass_panel(right)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._properties)
        right.setMinimumWidth(260)
        right.setMaximumWidth(380)

        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.addWidget(left)
        h_split.addWidget(center)
        h_split.addWidget(right)
        h_split.setStretchFactor(0, 0)
        h_split.setStretchFactor(1, 1)
        h_split.setStretchFactor(2, 0)
        h_split.setHandleWidth(10)
        h_split.setChildrenCollapsible(False)
        h_split.setSizes([280, 800, 300])

        # Outer breathing room around the three glass columns
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(10, 6, 10, 8)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(h_split)
        self.setCentralWidget(shell)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        self._act_open = QAction("打开工作区…", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self.open_workspace_dialog)
        file_menu.addAction(self._act_open)

        self._act_save = QAction("保存项目", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self.save_project)
        file_menu.addAction(self._act_save)

        self._recent_menu = file_menu.addMenu("最近工作区")
        self._act_clear_recent = QAction("清除最近列表", self)
        self._act_clear_recent.triggered.connect(self._clear_recent)

        file_menu.addSeparator()
        self._act_undo = QAction("撤销", self)
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._act_undo.triggered.connect(self.undo)
        file_menu.addAction(self._act_undo)

        self._act_redo = QAction("重做", self)
        self._act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._act_redo.triggered.connect(self.redo)
        file_menu.addAction(self._act_redo)

        # Quit is appended later after export/batch actions exist

        # --- Actions (shared by menus + toolbar dropdowns) ---
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)

        self._act_select = QAction("选择", self)
        self._act_select.setCheckable(True)
        self._act_select.setShortcut(QKeySequence("V"))
        self._act_select.triggered.connect(lambda: self._set_tool(MODE_SELECT))
        self._tool_group.addAction(self._act_select)

        self._act_polygon = QAction("多边形新建", self)
        self._act_polygon.setCheckable(True)
        self._act_polygon.setShortcut(QKeySequence("P"))
        self._act_polygon.triggered.connect(lambda: self._set_tool(MODE_POLYGON))
        self._tool_group.addAction(self._act_polygon)

        self._act_brush = QAction("画笔", self)
        self._act_brush.setCheckable(True)
        self._act_brush.setShortcut(QKeySequence("B"))
        self._act_brush.triggered.connect(lambda: self._set_tool(MODE_BRUSH))
        self._tool_group.addAction(self._act_brush)

        self._act_eraser = QAction("橡皮", self)
        self._act_eraser.setCheckable(True)
        self._act_eraser.setShortcut(QKeySequence("E"))
        self._act_eraser.triggered.connect(lambda: self._set_tool(MODE_ERASER))
        self._tool_group.addAction(self._act_eraser)

        self._act_length = QAction("体长路径（绘制）", self)
        self._act_length.setCheckable(True)
        self._act_length.setShortcut(QKeySequence("L"))
        self._act_length.setToolTip("绘制/追加体长节点（L）")
        self._act_length.triggered.connect(lambda: self._set_tool(MODE_LENGTH))
        self._tool_group.addAction(self._act_length)

        self._act_length_edit = QAction("小手调整体长", self)
        self._act_length_edit.setCheckable(True)
        self._act_length_edit.setShortcut(QKeySequence("H"))
        self._act_length_edit.setToolTip(
            "小手模式：拖动节点移动；选中后 Delete 删除；\n"
            "右键或双击节点删除；双击线段插点（H）"
        )
        self._act_length_edit.triggered.connect(lambda: self._set_tool(MODE_LENGTH_EDIT))
        self._tool_group.addAction(self._act_length_edit)

        self._act_length_reverse = QAction("反转体长方向", self)
        self._act_length_reverse.triggered.connect(self._reverse_length)

        self._act_length_clear = QAction("清空体长路径", self)
        self._act_length_clear.triggered.connect(self._clear_length)

        self._act_length_auto = QAction("自动体长建议", self)
        self._act_length_auto.setShortcut(QKeySequence("G"))
        self._act_length_auto.triggered.connect(self.suggest_length_path)

        self._act_auto_seg = QAction("自动分割…", self)
        self._act_auto_seg.setShortcut(QKeySequence("A"))
        self._act_auto_seg.triggered.connect(self.run_auto_segmentation)

        self._act_merge = QAction("合并选中对象", self)
        self._act_merge.setShortcut(QKeySequence("M"))
        self._act_merge.triggered.connect(self.merge_selected_objects)

        self._act_split_cut = QAction("切割线拆分", self)
        self._act_split_cut.setShortcut(QKeySequence("S"))
        self._act_split_cut.triggered.connect(lambda: self._set_tool(MODE_SPLIT_CUT))

        self._act_split_seed = QAction("种子点拆分", self)
        self._act_split_seed.triggered.connect(lambda: self._set_tool(MODE_SPLIT_SEED))

        self._act_confirm = QAction("切换确认状态", self)
        self._act_confirm.triggered.connect(self.toggle_confirm_selected)

        self._act_delete = QAction("删除对象", self)
        self._act_delete.setShortcuts(
            [QKeySequence.StandardKey.Delete, QKeySequence(Qt.Key.Key_Backspace)]
        )
        self._act_delete.triggered.connect(self.delete_selected_object)

        self._act_scale = QAction("手动校准比例尺…", self)
        self._act_scale.setShortcut(QKeySequence("C"))
        self._act_scale.triggered.connect(self.start_scale_calibration)

        self._act_scale_auto = QAction("自动识别比例尺…", self)
        self._act_scale_auto.setShortcut(QKeySequence("Shift+C"))
        self._act_scale_auto.triggered.connect(self.auto_detect_scale)

        self._act_batch = QAction("批处理…", self)
        self._act_batch.setShortcut(QKeySequence("Ctrl+B"))
        self._act_batch.triggered.connect(self.run_batch)

        self._act_export = QAction("导出结果…", self)
        self._act_export.setShortcut(QKeySequence("Ctrl+E"))
        self._act_export.triggered.connect(self.export_results)

        self._act_fit = QAction("适应窗口", self)
        self._act_fit.setShortcut(QKeySequence("Ctrl+0"))
        self._act_fit.triggered.connect(self._canvas.fit_to_window)

        self._act_100 = QAction("1:1 显示", self)
        self._act_100.setShortcut(QKeySequence("Ctrl+1"))
        self._act_100.triggered.connect(self._canvas.zoom_1_to_1)

        self._act_toggle_scale = QAction("显示比例尺标注", self)
        self._act_toggle_scale.setCheckable(True)
        self._act_toggle_scale.setChecked(True)
        self._act_toggle_scale.toggled.connect(self._canvas.set_show_scale_overlay)

        self._act_toggle_contours = QAction("显示轮廓", self)
        self._act_toggle_contours.setCheckable(True)
        self._act_toggle_contours.setChecked(True)
        self._act_toggle_contours.toggled.connect(self._canvas.set_show_contours)

        self._act_toggle_masks = QAction("显示掩膜", self)
        self._act_toggle_masks.setCheckable(True)
        self._act_toggle_masks.setChecked(True)
        self._act_toggle_masks.toggled.connect(self._canvas.set_show_masks)

        self._act_toggle_labels = QAction("显示编号", self)
        self._act_toggle_labels.setCheckable(True)
        self._act_toggle_labels.setChecked(True)
        self._act_toggle_labels.toggled.connect(self._canvas.set_show_labels)

        self._act_toggle_length = QAction("显示体长路径", self)
        self._act_toggle_length.setCheckable(True)
        self._act_toggle_length.setChecked(True)
        self._act_toggle_length.toggled.connect(self._canvas.set_show_length)

        self._act_prev = QAction("上一张", self)
        self._act_prev.setShortcut(QKeySequence(Qt.Key.Key_PageUp))
        self._act_prev.triggered.connect(self.prev_image)

        self._act_next = QAction("下一张", self)
        self._act_next.setShortcut(QKeySequence(Qt.Key.Key_PageDown))
        self._act_next.triggered.connect(self.next_image)

        self._act_mark_done = QAction("标记当前图为已完成", self)
        self._act_mark_done.triggered.connect(lambda: self._set_image_status("done"))
        self._act_mark_review = QAction("标记当前图为待确认", self)
        self._act_mark_review.triggered.connect(
            lambda: self._set_image_status("needs_review")
        )

        # --- Compact top menu bar ---
        # 文件：导出 / 批处理 / 退出
        file_menu.addSeparator()
        file_menu.addAction(self._act_export)
        file_menu.addAction(self._act_batch)
        file_menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 标注：工具 / 体长 / 分割 子菜单
        ann_menu = self.menuBar().addMenu("标注(&A)")
        tools_menu = ann_menu.addMenu("标注工具")
        tools_menu.addAction(self._act_select)
        tools_menu.addAction(self._act_polygon)
        tools_menu.addAction(self._act_brush)
        tools_menu.addAction(self._act_eraser)

        length_menu = ann_menu.addMenu("体长")
        length_menu.addAction(self._act_length)
        length_menu.addAction(self._act_length_edit)
        length_menu.addAction(self._act_length_auto)
        length_menu.addSeparator()
        length_menu.addAction(self._act_length_reverse)
        length_menu.addAction(self._act_length_clear)

        seg_menu = ann_menu.addMenu("分割与编辑")
        seg_menu.addAction(self._act_auto_seg)
        seg_menu.addSeparator()
        seg_menu.addAction(self._act_merge)
        seg_menu.addAction(self._act_split_cut)
        seg_menu.addAction(self._act_split_seed)
        seg_menu.addSeparator()
        seg_menu.addAction(self._act_confirm)
        seg_menu.addAction(self._act_delete)

        # 测量
        measure_menu = self.menuBar().addMenu("测量(&M)")
        measure_menu.addAction(self._act_scale)
        measure_menu.addAction(self._act_scale_auto)
        measure_menu.addSeparator()
        measure_menu.addAction(self._act_length)
        measure_menu.addAction(self._act_length_edit)
        measure_menu.addAction(self._act_length_auto)
        measure_menu.addSeparator()
        measure_menu.addAction(self._act_batch)

        # 视图
        view_menu = self.menuBar().addMenu("视图(&V)")
        view_menu.addAction(self._act_fit)
        view_menu.addAction(self._act_100)
        view_menu.addSeparator()
        view_menu.addAction(self._act_toggle_scale)
        view_menu.addAction(self._act_toggle_contours)
        view_menu.addAction(self._act_toggle_masks)
        view_menu.addAction(self._act_toggle_labels)
        view_menu.addAction(self._act_toggle_length)

        # 导航（含状态标记）
        nav_menu = self.menuBar().addMenu("导航(&N)")
        nav_menu.addAction(self._act_prev)
        nav_menu.addAction(self._act_next)
        nav_menu.addSeparator()
        nav_menu.addAction(self._act_mark_done)
        nav_menu.addAction(self._act_mark_review)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        act_shortcuts = QAction("快捷键一览…", self)
        act_shortcuts.setShortcut(QKeySequence("F1"))
        act_shortcuts.triggered.connect(self._show_shortcuts)
        help_menu.addAction(act_shortcuts)
        act_guide = QAction("打开用户说明…", self)
        act_guide.triggered.connect(self._open_user_guide)
        help_menu.addAction(act_guide)
        act_logs = QAction("打开日志目录…", self)
        act_logs.triggered.connect(self._open_log_dir)
        help_menu.addAction(act_logs)
        help_menu.addSeparator()
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

        self._act_select.setChecked(True)

        # Category shortcuts 0-7
        for digit in range(10):
            act = QAction(self)
            act.setShortcut(QKeySequence(str(digit)))
            act.triggered.connect(
                lambda checked=False, d=digit: self._assign_category_by_shortcut(str(d))
            )
            self.addAction(act)

    def _make_toolbar_dropdown(
        self,
        title: str,
        actions: list[QAction | None],
        *,
        tooltip: str = "",
    ) -> QToolButton:
        """Create a compact InstantPopup tool button with a menu of related actions."""
        btn = QToolButton(self)
        btn.setText(title)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setAutoRaise(True)
        if tooltip:
            btn.setToolTip(tooltip)
        menu = QMenu(btn)
        for act in actions:
            if act is None:
                menu.addSeparator()
            else:
                menu.addAction(act)
        btn.setMenu(menu)
        # Compact but comfortable hit area
        btn.setMinimumWidth(64)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        self._toolbar = tb

        # 常用直达
        tb.addAction(self._act_open)
        tb.addAction(self._act_save)
        tb.addSeparator()
        tb.addAction(self._act_prev)
        tb.addAction(self._act_next)
        tb.addSeparator()
        tb.addAction(self._act_undo)
        tb.addAction(self._act_redo)
        tb.addSeparator()

        # 同类功能收入下拉
        self._btn_tools = self._make_toolbar_dropdown(
            "标注工具 ▾",
            [
                self._act_select,
                self._act_polygon,
                self._act_brush,
                self._act_eraser,
            ],
            tooltip="选择 / 多边形 / 画笔 / 橡皮",
        )
        tb.addWidget(self._btn_tools)

        self._btn_length = self._make_toolbar_dropdown(
            "体长 ▾",
            [
                self._act_length,
                self._act_length_edit,
                self._act_length_auto,
                None,
                self._act_length_reverse,
                self._act_length_clear,
            ],
            tooltip="绘制、小手调整、自动建议体长",
        )
        tb.addWidget(self._btn_length)

        self._btn_seg = self._make_toolbar_dropdown(
            "分割 ▾",
            [
                self._act_auto_seg,
                None,
                self._act_merge,
                self._act_split_cut,
                self._act_split_seed,
                None,
                self._act_confirm,
                self._act_delete,
            ],
            tooltip="自动分割、合并、拆分、删除",
        )
        tb.addWidget(self._btn_seg)

        self._btn_scale = self._make_toolbar_dropdown(
            "比例尺 ▾",
            [self._act_scale, self._act_scale_auto],
            tooltip="手动校准 / 自动识别比例尺",
        )
        tb.addWidget(self._btn_scale)

        tb.addSeparator()
        tb.addAction(self._act_batch)
        tb.addAction(self._act_export)
        tb.addSeparator()

        self._btn_view = self._make_toolbar_dropdown(
            "视图 ▾",
            [
                self._act_fit,
                self._act_100,
                None,
                self._act_toggle_scale,
                self._act_toggle_contours,
                self._act_toggle_masks,
                self._act_toggle_labels,
                self._act_toggle_length,
            ],
            tooltip="缩放与图层显示开关",
        )
        tb.addWidget(self._btn_view)

        tb.addSeparator()
        self._brush_size_label = QLabel(" 粗细 ")
        self._brush_size_label.setToolTip("画笔 / 橡皮粗细（像素半径）")
        tb.addWidget(self._brush_size_label)
        self._btn_brush_smaller = QToolButton()
        self._btn_brush_smaller.setText("−")
        self._btn_brush_smaller.setToolTip("减小粗细  [")
        self._btn_brush_smaller.setAutoRaise(True)
        self._btn_brush_smaller.clicked.connect(
            lambda: self._nudge_brush_radius(-2)
        )
        tb.addWidget(self._btn_brush_smaller)
        self._brush_spin = QSpinBox()
        self._brush_spin.setRange(1, 200)
        self._brush_spin.setValue(8)
        self._brush_spin.setSuffix(" px")
        self._brush_spin.setToolTip(
            "画笔/橡皮粗细（像素半径）\n"
            "快捷键 [ ] 调节 · 画笔模式下 Ctrl/Shift/Alt+滚轮"
        )
        self._brush_spin.setMinimumWidth(78)
        self._brush_spin.valueChanged.connect(self._on_brush_radius)
        tb.addWidget(self._brush_spin)
        self._btn_brush_larger = QToolButton()
        self._btn_brush_larger.setText("+")
        self._btn_brush_larger.setToolTip("增大粗细  ]")
        self._btn_brush_larger.setAutoRaise(True)
        self._btn_brush_larger.clicked.connect(
            lambda: self._nudge_brush_radius(2)
        )
        tb.addWidget(self._btn_brush_larger)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.addWidget(self._workspace_label, stretch=1)
        sb.addPermanentWidget(self._tool_label)
        sb.addPermanentWidget(self._save_label)
        sb.addPermanentWidget(self._coord_label)
        sb.addPermanentWidget(self._zoom_label)

    def _connect_signals(self) -> None:
        self._image_list.image_selected.connect(self.show_image_at)
        self._canvas.cursor_image_pos.connect(self._on_cursor_pos)
        self._canvas.zoom_changed.connect(self._on_zoom)
        self._canvas.scale_points_chosen.connect(self._on_scale_points)
        self._canvas.status_message.connect(self._on_canvas_status)
        self._canvas.polygon_finished.connect(self._on_polygon_finished)
        self._canvas.brush_stroke_finished.connect(self._on_brush_stroke)
        self._canvas.brush_radius_changed.connect(self._sync_brush_spin)
        self._canvas.object_clicked.connect(self.select_object)
        self._canvas.empty_clicked.connect(lambda: self.select_object(None))
        self._canvas.tool_mode_changed.connect(self._on_tool_mode)
        self._canvas.length_live.connect(self._on_length_live)
        self._canvas.length_committed.connect(self._on_length_committed)
        self._canvas.split_cut_finished.connect(self._on_split_cut)
        self._canvas.split_seeds_finished.connect(self._on_split_seeds)
        self._object_table.object_selected.connect(self.select_object)
        self._object_table.delete_requested.connect(self._delete_object_id)
        self._category_panel.category_activated.connect(self.assign_category_to_selection)
        self._category_panel.categories_changed.connect(self._on_categories_changed)
        self._category_panel.filter_changed.connect(self._on_category_filter)
        self._properties.category_changed.connect(self.assign_category_to_selection)
        self._cmd_stack.set_on_change(self._update_undo_actions)
        self._update_undo_actions()

    def _set_tool(self, mode: str) -> None:
        self._canvas.set_tool_mode(mode)

    def _on_tool_mode(self, mode: str) -> None:
        names = {
            MODE_NAVIGATE: "浏览",
            MODE_SELECT: "选择",
            MODE_POLYGON: "多边形",
            MODE_BRUSH: "画笔",
            MODE_ERASER: "橡皮",
            MODE_LENGTH: "体长绘制",
            MODE_LENGTH_EDIT: "小手调整",
            MODE_SPLIT_CUT: "切割拆分",
            MODE_SPLIT_SEED: "种子拆分",
            "scale": "比例尺",
        }
        self._tool_label.setText(f"工具: {names.get(mode, mode)}")
        mapping = {
            MODE_SELECT: self._act_select,
            MODE_POLYGON: self._act_polygon,
            MODE_BRUSH: self._act_brush,
            MODE_ERASER: self._act_eraser,
            MODE_LENGTH: self._act_length,
            MODE_LENGTH_EDIT: self._act_length_edit,
        }
        act = mapping.get(mode)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        elif act is None:
            # Scale / navigate / split etc. — uncheck exclusive tool buttons
            checked = self._tool_group.checkedAction()
            if checked is not None:
                self._tool_group.setExclusive(False)
                checked.setChecked(False)
                self._tool_group.setExclusive(True)

        # Reflect active tool on compact toolbar dropdown labels
        ann_modes = {
            MODE_SELECT: "选择",
            MODE_POLYGON: "多边形",
            MODE_BRUSH: "画笔",
            MODE_ERASER: "橡皮",
        }
        if hasattr(self, "_btn_tools"):
            if mode in ann_modes:
                self._btn_tools.setText(f"{ann_modes[mode]} ▾")
            else:
                self._btn_tools.setText("标注工具 ▾")
        if hasattr(self, "_btn_length"):
            if mode == MODE_LENGTH:
                self._btn_length.setText("体长绘制 ▾")
            elif mode == MODE_LENGTH_EDIT:
                self._btn_length.setText("小手调整 ▾")
            else:
                self._btn_length.setText("体长 ▾")
        if hasattr(self, "_btn_seg"):
            if mode == MODE_SPLIT_CUT:
                self._btn_seg.setText("切割拆分 ▾")
            elif mode == MODE_SPLIT_SEED:
                self._btn_seg.setText("种子拆分 ▾")
            else:
                self._btn_seg.setText("分割 ▾")

        self._update_save_actions()

    def _on_brush_radius(self, value: int) -> None:
        self._canvas.set_brush_radius(float(value))

    def _sync_brush_spin(self, radius: float) -> None:
        if not hasattr(self, "_brush_spin"):
            return
        v = int(round(radius))
        if self._brush_spin.value() == v:
            return
        self._brush_spin.blockSignals(True)
        self._brush_spin.setValue(v)
        self._brush_spin.blockSignals(False)

    def _nudge_brush_radius(self, delta: int) -> None:
        if not hasattr(self, "_brush_spin"):
            return
        self._brush_spin.setValue(self._brush_spin.value() + int(delta))

    def _update_undo_actions(self) -> None:
        self._act_undo.setEnabled(self._cmd_stack.can_undo)
        self._act_redo.setEnabled(self._cmd_stack.can_redo)

    def _update_save_actions(self) -> None:
        has_ws = self._workspace is not None
        self._act_save.setEnabled(has_ws)
        has_imgs = has_ws and bool(self._workspace and self._workspace.images)
        self._act_scale.setEnabled(has_imgs)
        self._act_scale_auto.setEnabled(has_imgs)
        self._act_polygon.setEnabled(has_imgs)
        self._act_brush.setEnabled(has_imgs)
        self._act_eraser.setEnabled(has_imgs)
        self._act_select.setEnabled(has_imgs)
        self._act_length.setEnabled(has_imgs and self._selected_object_id is not None)
        self._act_length_edit.setEnabled(
            has_imgs and self._selected_object_id is not None
        )
        self._act_length_reverse.setEnabled(
            has_imgs and self._selected_object_id is not None
        )
        self._act_length_clear.setEnabled(
            has_imgs and self._selected_object_id is not None
        )
        self._act_length_auto.setEnabled(
            has_imgs and self._selected_object_id is not None
        )
        self._act_auto_seg.setEnabled(has_imgs and not self._batch.is_busy)
        self._act_batch.setEnabled(has_ws and not self._batch.is_busy)
        self._act_export.setEnabled(has_ws)
        multi = (
            len(self._object_table.selected_object_ids()) >= 2
            if has_imgs
            else False
        )
        self._act_merge.setEnabled(multi)
        self._act_split_cut.setEnabled(has_imgs and self._selected_object_id is not None)
        self._act_split_seed.setEnabled(has_imgs and self._selected_object_id is not None)
        self._act_confirm.setEnabled(has_imgs and self._selected_object_id is not None)
        # Delete object only when not in length tools (canvas handles node delete)
        in_length = self._canvas.mode in (MODE_LENGTH, MODE_LENGTH_EDIT)
        self._act_delete.setEnabled(
            has_imgs and self._selected_object_id is not None and not in_length
        )
        if self._workspace is None:
            self._save_label.setText("未保存: —")
        elif self._workspace.dirty:
            self._save_label.setText("未保存: 是")
        else:
            self._save_label.setText("未保存: 否")
        self._update_undo_actions()

    def _mark_dirty(self) -> None:
        if self._workspace is None:
            return
        self._workspace.mark_dirty()
        self._update_save_actions()
        self._autosave.mark_dirty()

    def undo(self) -> None:
        if self._cmd_stack.undo():
            self._refresh_after_history()
            self._mark_dirty()

    def redo(self) -> None:
        if self._cmd_stack.redo():
            self._refresh_after_history()
            self._mark_dirty()

    def _refresh_after_history(self) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        rec = self._workspace.current
        self._object_table.set_image_record(rec)
        self._sync_canvas_objects()
        if self._selected_object_id:
            obj = next(
                (o for o in rec.objects if o.object_id == self._selected_object_id),
                None,
            )
            self._properties.set_object(obj)
            self._canvas.sync_length_points_from_object(obj)

    # --- workspace / navigation ---

    def open_workspace_dialog(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "选择工作区文件夹",
            str(Path.home()),
        )
        if not path:
            return
        self.load_workspace(Path(path))

    def load_workspace(self, folder: Path) -> None:
        try:
            ws = open_workspace(folder)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to open workspace: %s", folder)
            QMessageBox.critical(
                self,
                "打开工作区失败",
                f"无法打开工作区：\n{folder}\n\n{exc}",
            )
            return

        if ws.loaded_from_autosave:
            auto = ws.root / "autosave" / "project.sfm.autosave.json"
            ans = QMessageBox.question(
                self,
                "发现自动保存",
                f"检测到较新的自动保存文件：\n{auto}\n\n"
                "是否使用自动保存恢复？（选“否”则使用主项目文件）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    ws = open_workspace(folder, prefer_autosave=True)
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "恢复失败", str(exc))
            else:
                try:
                    ws = open_workspace(folder, prefer_autosave=False)
                    ws.loaded_from_autosave = False
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "打开失败", str(exc))
                    return

        self._workspace = ws
        self._image_service.clear()
        self._object_service.set_workspace(ws.root)
        self._cmd_stack.clear()
        self._selected_object_id = None
        self._image_list.set_workspace(ws)
        self._object_table.clear()
        self._object_table.set_categories(ws.project.categories)
        self._properties.set_categories(ws.project.categories)
        self._refresh_category_panel()
        self._workspace_label.setText(f"工作区: {ws.root}")
        self._autosave.set_workspace(
            ws.root,
            lambda: None if self._workspace is None else self._workspace.project,
        )
        add_recent_workspace(ws.root)
        set_last_workspace(ws.root)
        self._rebuild_recent_menu()
        self._periodic_save.start()
        self._start_thumbnails(ws)
        self._update_save_actions()

        if not ws.images:
            self._canvas.clear_image()
            self._properties.clear()
            self.statusBar().showMessage("工作区中没有找到支持的图片", 5000)
            QMessageBox.information(
                self,
                "无图片",
                "该文件夹中未找到支持的图片。\n"
                "支持: .tif .tiff .png .jpg .jpeg .bmp",
            )
            return

        self.show_image_at(ws.current_index if ws.current_index >= 0 else 0)
        self.statusBar().showMessage(
            f"已加载 {len(ws.images)} 张图片 · 项目 {ws.project.project_name}",
            4000,
        )

    def save_project(self) -> bool:
        if self._workspace is None:
            return False
        try:
            rec = self._workspace.current
            if rec is not None:
                self._object_service.persist_all_dirty_masks(rec)
            save_workspace(self._workspace)
            self._autosave.flush_now()
            self._update_save_actions()
            self.statusBar().showMessage(
                f"已保存: {self._workspace.project_path}", 4000
            )
            return True
        except (ProjectIOError, OSError) as exc:
            logger.exception("Save failed")
            QMessageBox.critical(self, "保存失败", str(exc))
            return False

    def show_image_at(self, index: int) -> None:
        if self._workspace is None:
            return
        if index < 0 or index >= len(self._workspace.images):
            return

        prev = self._workspace.current_index
        if prev != index and self._workspace.dirty:
            # persist masks of previous image
            if 0 <= prev < len(self._workspace.images):
                self._object_service.persist_all_dirty_masks(
                    self._workspace.images[prev]
                )
            self._autosave.flush_now()

        self._canvas.cancel_active_tool()
        self._workspace.current_index = index
        img = self._workspace.images[index]
        self._image_list.set_current_index(index)
        self._selected_object_id = None

        abs_path = self._workspace.abs_path(img)
        loaded, err = self._image_service.try_get(abs_path)
        if err or loaded is None:
            self._canvas.clear_image()
            self._properties.clear()
            self._object_table.clear()
            QMessageBox.warning(
                self,
                "加载失败",
                f"无法加载图片：\n{abs_path}\n\n{err}",
            )
            return

        try:
            self._canvas.set_image_array(loaded.raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Display failed")
            QMessageBox.warning(self, "显示失败", f"图片已读取但无法显示：\n{exc}")
            return

        meta = loaded.meta
        changed_meta = False
        if img.width != meta.width or img.height != meta.height:
            img.width = meta.width
            img.height = meta.height
            img.channels = meta.channels
            img.dtype = meta.dtype
            changed_meta = True

        self._object_service.bind_image(
            img, width=meta.width, height=meta.height
        )
        self._cmd_stack.clear()
        # refresh areas/lengths with current scale
        self._object_service.recompute_all_metrics(img, img.scale)

        info = describe_image(loaded)
        self._properties.set_info(info)
        self._properties.set_scale(img.scale)
        self._properties.set_object(None)
        self._canvas.set_scale_calibration(img.scale)
        if img.scale is None:
            self.statusBar().showMessage(
                "当前图未校准比例尺：可按 Shift+C 自动识别，或 C 手动两点校准",
                6000,
            )
        self._object_table.set_categories(self._workspace.project.categories)
        self._object_table.set_image_record(img)
        self._properties.set_categories(self._workspace.project.categories)
        self._sync_canvas_objects()
        self._refresh_category_panel()

        self.setWindowTitle(
            f"{__app_name__} — {abs_path.name} "
            f"[{index + 1}/{len(self._workspace.images)}]"
        )
        if img.status == "pending":
            img.status = "in_progress"
            changed_meta = True
            self._image_list.refresh_item(index, img)

        if changed_meta:
            self._mark_dirty()
        self._update_save_actions()

    def _sync_canvas_objects(self) -> None:
        if self._workspace is None or self._workspace.current is None:
            self._canvas.set_objects([], {}, None)
            return
        rec = self._workspace.current
        masks = {
            o.object_id: m
            for o in rec.objects
            if (m := self._object_service.get_mask(o.object_id)) is not None
        }
        colors = {
            c.category_id: c.color for c in self._workspace.project.categories
        }
        self._canvas.set_objects(
            rec.objects, masks, self._selected_object_id, category_colors=colors
        )

    def _category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self._workspace is None:
            return counts
        for img in self._workspace.project.images:
            for obj in img.objects:
                counts[obj.category_id] = counts.get(obj.category_id, 0) + 1
        return counts

    def _refresh_category_panel(self) -> None:
        if self._workspace is None:
            self._category_panel.set_project(None)
            return
        self._category_panel.set_project(
            self._workspace.project, self._category_counts()
        )

    def _on_categories_changed(self) -> None:
        if self._workspace is None:
            return
        # Remap deleted categories to unclassified
        valid = {c.category_id for c in self._workspace.project.categories}
        for img in self._workspace.project.images:
            for obj in img.objects:
                if obj.category_id not in valid:
                    obj.category_id = "unclassified"
        self._object_table.set_categories(self._workspace.project.categories)
        self._properties.set_categories(self._workspace.project.categories)
        self._refresh_category_panel()
        if self._workspace.current:
            self._object_table.set_image_record(self._workspace.current)
            self._sync_canvas_objects()
            if self._selected_object_id:
                self._properties.set_object(self._find_object(self._selected_object_id))
        self._mark_dirty()

    def _on_category_filter(self, category_id: object) -> None:
        cid = str(category_id) if category_id else None
        self._object_table.set_filter_category(cid)

    def assign_category_to_selection(self, category_id: str) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        ids = self._object_table.selected_object_ids()
        if not ids and self._selected_object_id:
            ids = [self._selected_object_id]
        if not ids:
            self.statusBar().showMessage("请先选择对象再设置分类", 3000)
            return
        rec = self._workspace.current
        for oid in ids:
            obj = next((o for o in rec.objects if o.object_id == oid), None)
            if obj is not None:
                obj.category_id = category_id
                self._object_table.update_object_row(obj)
        self._sync_canvas_objects()
        if self._selected_object_id:
            self._properties.set_object(self._find_object(self._selected_object_id))
        self._refresh_category_panel()
        self._mark_dirty()
        cat = next(
            (
                c
                for c in self._workspace.project.categories
                if c.category_id == category_id
            ),
            None,
        )
        name = cat.name_zh if cat else category_id
        self.statusBar().showMessage(f"已将 {len(ids)} 个对象设为「{name}」", 3000)

    def _assign_category_by_shortcut(self, key: str) -> None:
        if self._workspace is None:
            return
        # Don't steal digits while typing in dialogs — only when canvas/table focused
        w = QApplication.focusWidget()
        if w is not None:
            from PySide6.QtWidgets import QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox

            if isinstance(w, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
                return
        cat = next(
            (
                c
                for c in self._workspace.project.categories
                if c.shortcut == key and c.enabled
            ),
            None,
        )
        if cat is None:
            return
        self.assign_category_to_selection(cat.category_id)

    def export_results(self) -> None:
        if self._workspace is None:
            return
        dlg = ExportDialog(self)
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        cur_id = (
            self._workspace.current.image_id if self._workspace.current else None
        )
        progress = QProgressDialog("正在导出…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            result = export_project(
                self._workspace,
                opts,
                current_image_id=cur_id,
            )
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        progress.close()
        msg = f"已导出到：\n{result.output_dir}\n\n文件数：{len(result.files)}"
        if result.errors:
            msg += "\n\n部分错误：\n" + "\n".join(result.errors[:8])
        QMessageBox.information(self, "导出完成", msg)
        self.statusBar().showMessage(f"导出完成: {result.output_dir}", 8000)

    def prev_image(self) -> None:
        if self._workspace is None or not self._workspace.images:
            return
        idx = self._workspace.current_index
        if idx <= 0:
            self.statusBar().showMessage("已经是第一张", 2000)
            return
        self.show_image_at(idx - 1)

    def next_image(self) -> None:
        if self._workspace is None or not self._workspace.images:
            return
        idx = self._workspace.current_index
        if idx >= len(self._workspace.images) - 1:
            self.statusBar().showMessage("已经是最后一张", 2000)
            return
        self.show_image_at(idx + 1)

    # --- objects ---

    def select_object(self, object_id: str | None) -> None:
        self._selected_object_id = object_id
        self._canvas.set_selected_object(object_id)
        self._object_table.select_object(object_id)
        obj = None
        if (
            object_id
            and self._workspace
            and self._workspace.current
        ):
            obj = next(
                (
                    o
                    for o in self._workspace.current.objects
                    if o.object_id == object_id
                ),
                None,
            )
        self._properties.set_object(obj)
        self._update_save_actions()

    def _find_object(self, object_id: str):
        if self._workspace is None or self._workspace.current is None:
            return None
        return next(
            (o for o in self._workspace.current.objects if o.object_id == object_id),
            None,
        )

    def _on_length_live(self, object_id: str, points: object) -> None:
        """Live update metrics while dragging a node (no undo entry)."""
        obj = self._find_object(object_id)
        if obj is None or self._workspace is None or self._workspace.current is None:
            return
        scale = self._workspace.current.scale
        fields = apply_length_to_object(points, scale)  # type: ignore[arg-type]
        obj.length_points = fields["length_points"]
        obj.length_px = fields["length_px"]
        obj.length_um = fields["length_um"]
        obj.length_mm = fields["length_mm"]
        if obj.length_points:
            obj.length_source = "manual"
        self._properties.set_object(obj)
        self._object_table.update_object_row(obj)

    def _on_length_committed(
        self, object_id: str, old_points: object, new_points: object
    ) -> None:
        obj = self._find_object(object_id)
        if obj is None or self._workspace is None or self._workspace.current is None:
            return
        scale = self._workspace.current.scale
        # Ensure object currently holds old so command can capture; apply via command
        obj.length_points = copy_points(old_points)  # type: ignore[arg-type]

        def on_applied(o) -> None:
            self._properties.set_object(o)
            self._object_table.update_object_row(o)
            mask = self._object_service.get_mask(o.object_id)
            self._canvas.update_object_visual(o, mask)
            self._canvas.sync_length_points_from_object(o)

        cmd = SetLengthPointsCommand(
            obj,
            new_points,  # type: ignore[arg-type]
            scale,
            on_applied=on_applied,
            description="edit length path",
        )
        self._cmd_stack.push(cmd)
        self._mark_dirty()

    def _reverse_length(self) -> None:
        if self._canvas.mode not in (MODE_LENGTH, MODE_LENGTH_EDIT):
            self._set_tool(MODE_LENGTH_EDIT)
        self._canvas.reverse_length_path()

    def _clear_length(self) -> None:
        if self._canvas.mode not in (MODE_LENGTH, MODE_LENGTH_EDIT):
            self._set_tool(MODE_LENGTH_EDIT)
        self._canvas.clear_length_path()

    def suggest_length_path(self) -> None:
        """Skeleton-based auto length for the selected object (editable suggestion)."""
        if self._workspace is None or self._workspace.current is None:
            return
        if not self._selected_object_id:
            QMessageBox.information(self, "自动体长", "请先选择一个对象。")
            return
        rec = self._workspace.current
        obj = self._find_object(self._selected_object_id)
        if obj is None:
            return
        overwrite = False
        if obj.length_points and obj.length_source == "manual":
            ans = QMessageBox.question(
                self,
                "覆盖人工路径？",
                "该对象已有人工体长路径。是否用自动建议覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        try:
            self._object_service.suggest_length_for_object(
                obj, rec.scale, overwrite_manual=overwrite
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "自动体长失败", str(exc))
            return
        # Push as one undo unit from empty/old to new
        # (suggest already applied; record via command with before/after)
        self._object_table.update_object_row(obj)
        self._properties.set_object(obj)
        mask = self._object_service.get_mask(obj.object_id)
        self._canvas.update_object_visual(obj, mask)
        self._canvas.sync_length_points_from_object(obj)
        self._mark_dirty()
        self.statusBar().showMessage(
            f"自动体长建议已应用（{obj.length_source}）: "
            f"{obj.length_px:.1f} px · 可进入 L 模式修改",
            8000,
        )
        # Enter length mode so user can edit immediately
        self._set_tool(MODE_LENGTH)

    def run_batch(self) -> None:
        if self._workspace is None:
            return
        if self._batch.is_busy:
            QMessageBox.information(self, "批处理", "已有任务在运行。")
            return
        has_scale = bool(
            self._workspace.current and self._workspace.current.scale
        )
        dlg = BatchDialog(self, has_scale=has_scale)
        if dlg.exec() != BatchDialog.DialogCode.Accepted:
            return
        op = dlg.operation()
        scope = dlg.scope()
        images = self._select_images_for_scope(scope)
        if not images:
            QMessageBox.information(self, "批处理", "没有符合范围的图片。")
            return

        if op == BatchDialog.OP_SEGMENT:
            self._start_batch_segment(images, dlg.segment_params(), dlg.segment_mode())
        elif op == BatchDialog.OP_SCALE:
            self._start_batch_scale(images, dlg.skip_confirmed_scale())
        elif op == BatchDialog.OP_PATHS:
            self._start_batch_paths(
                images,
                dlg.path_params(),
                only_empty=dlg.only_empty_path(),
                overwrite_manual=dlg.overwrite_manual_path(),
            )

    def _select_images_for_scope(self, scope: str):
        if self._workspace is None:
            return []
        imgs = list(self._workspace.project.images)
        if scope == "current":
            cur = self._workspace.current
            return [cur] if cur else []
        if scope == "pending":
            return [i for i in imgs if i.status in ("pending", "")]
        return imgs

    def _open_batch_progress(self, title: str) -> QProgressDialog:
        prog = QProgressDialog(title, "取消", 0, 100, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)
        prog.setValue(0)
        prog.canceled.connect(self._batch.cancel)
        prog.show()
        self._batch_progress = prog
        return prog

    def _start_batch_segment(self, images, params, mode: str) -> None:
        assert self._workspace is not None
        self._batch_seg_mode = mode
        items = []
        for img in images:
            p = self._workspace.abs_path(img)
            if p.is_file():
                items.append((img.image_id, p))
        if not items:
            QMessageBox.warning(self, "批处理", "没有可读取的图片文件。")
            return
        prog = self._open_batch_progress("批量自动分割…")
        sig = self._batch.start_segment(items, params)
        sig.progress.connect(self._on_batch_progress)
        sig.item_finished.connect(self._on_batch_segment_item)
        sig.error.connect(self._on_batch_error)
        sig.finished.connect(self._on_batch_finished)
        self._update_save_actions()

    def _start_batch_scale(self, images, skip_confirmed: bool) -> None:
        assert self._workspace is not None
        cur = self._workspace.current
        if cur is None or cur.scale is None:
            QMessageBox.warning(
                self, "批处理", "请先在当前图片完成比例尺校准，再批量应用。"
            )
            return
        # Deep copy scale points
        src = cur.scale
        scale = ScaleCalibration(
            start_point=list(src.start_point),
            end_point=list(src.end_point),
            pixel_length=src.pixel_length,
            real_length=src.real_length,
            unit=src.unit,
            real_per_pixel=src.real_per_pixel,
            method="manual",
            confirmed=True,
        )
        ids = [i.image_id for i in images]
        prog = self._open_batch_progress("批量应用比例尺…")
        sig = self._batch.start_scale(
            ids, scale, skip_confirmed_scale=skip_confirmed
        )
        sig.progress.connect(self._on_batch_progress)
        sig.item_finished.connect(
            lambda iid, payload: self._on_batch_scale_item(
                iid, payload, skip_confirmed
            )
        )
        sig.finished.connect(self._on_batch_finished)
        self._update_save_actions()

    def _start_batch_paths(
        self,
        images,
        path_params: dict,
        *,
        only_empty: bool,
        overwrite_manual: bool,
    ) -> None:
        assert self._workspace is not None
        tasks = []
        for img in images:
            # bind masks for this image
            abs_path = self._workspace.abs_path(img)
            if not abs_path.is_file():
                continue
            loaded, err = self._image_service.try_get(abs_path)
            if err or loaded is None:
                continue
            self._object_service.bind_image(
                img,
                width=loaded.meta.width,
                height=loaded.meta.height,
            )
            for obj in img.objects:
                if only_empty and obj.length_points:
                    continue
                if (
                    obj.length_source == "manual"
                    and obj.length_points
                    and not overwrite_manual
                ):
                    continue
                mask = self._object_service.get_mask(obj.object_id)
                if mask is None:
                    continue
                # copy mask so worker owns data
                tasks.append((img.image_id, obj.object_id, mask.copy()))

        # re-bind current image for UI
        if self._workspace.current:
            cur = self._workspace.current
            p = self._workspace.abs_path(cur)
            loaded, _ = self._image_service.try_get(p)
            if loaded:
                self._object_service.bind_image(
                    cur, width=loaded.meta.width, height=loaded.meta.height
                )

        if not tasks:
            QMessageBox.information(self, "批处理", "没有需要建议体长的对象。")
            return
        prog = self._open_batch_progress("批量自动体长…")
        sig = self._batch.start_paths(tasks, **path_params)
        sig.progress.connect(self._on_batch_progress)
        sig.item_finished.connect(self._on_batch_path_item)
        sig.error.connect(self._on_batch_error)
        sig.finished.connect(self._on_batch_finished)
        self._update_save_actions()

    def _on_batch_progress(self, cur: int, total: int, msg: str) -> None:
        if self._batch_progress is not None:
            self._batch_progress.setMaximum(max(total, 1))
            self._batch_progress.setValue(cur)
            self._batch_progress.setLabelText(msg)
        self.statusBar().showMessage(f"批处理 {cur}/{total}: {msg}", 2000)

    def _on_batch_error(self, item_id: str, message: str) -> None:
        logger.warning("Batch item error %s: %s", item_id, message)

    def _on_batch_segment_item(self, image_id: str, payload: object) -> None:
        """Apply segmentation result on main thread (safe project mutation)."""
        if self._workspace is None or not isinstance(payload, dict):
            return
        rec = self._workspace.project.find_image(image_id)
        if rec is None:
            return
        try:
            w = int(payload.get("width") or rec.width or 0)
            h = int(payload.get("height") or rec.height or 0)
            if w > 0 and h > 0:
                rec.width, rec.height = w, h
            self._object_service.bind_image(rec, width=w, height=h)
            instances = payload.get("instances") or []
            self._object_service.apply_instance_masks(
                rec,
                instances,
                rec.scale,
                mode=self._batch_seg_mode,
                auto_length=True,
            )
            if rec.status == "pending":
                rec.status = "needs_review"
            self._mark_dirty()
            # refresh UI if this is current image
            if self._workspace.current and self._workspace.current.image_id == image_id:
                self._object_table.set_image_record(rec)
                self._sync_canvas_objects()
                self._refresh_category_panel()
                self._image_list.refresh_item(self._workspace.current_index, rec)
            else:
                # update list status mark
                for i, im in enumerate(self._workspace.images):
                    if im.image_id == image_id:
                        self._image_list.refresh_item(i, im)
                        break
        except Exception as exc:  # noqa: BLE001
            logger.exception("Apply batch segment failed %s", image_id)
            self.statusBar().showMessage(f"{image_id} 写入失败: {exc}", 5000)

    def _on_batch_scale_item(
        self, image_id: str, payload: object, skip_confirmed: bool
    ) -> None:
        if self._workspace is None or not isinstance(payload, dict):
            return
        rec = self._workspace.project.find_image(image_id)
        if rec is None:
            return
        scale = payload.get("scale")
        if scale is None:
            return
        if skip_confirmed and rec.scale is not None and rec.scale.confirmed:
            return
        # clone
        rec.scale = ScaleCalibration(
            start_point=list(scale.start_point),
            end_point=list(scale.end_point),
            pixel_length=scale.pixel_length,
            real_length=scale.real_length,
            unit=scale.unit,
            real_per_pixel=scale.real_per_pixel,
            method=scale.method,
            confirmed=True,
        )
        # recompute real units for objects (px values kept)
        self._object_service.recompute_all_metrics(rec, rec.scale)
        self._mark_dirty()
        if self._workspace.current and self._workspace.current.image_id == image_id:
            self._properties.set_scale(rec.scale)
            self._canvas.set_scale_calibration(rec.scale)
            if self._selected_object_id:
                self._properties.set_object(self._find_object(self._selected_object_id))
            self._object_table.set_image_record(rec)

    def _on_batch_path_item(self, object_id: str, payload: object) -> None:
        if self._workspace is None or not isinstance(payload, dict):
            return
        image_id = payload.get("image_id")
        points = payload.get("points")
        if not image_id or not points:
            return
        rec = self._workspace.project.find_image(str(image_id))
        if rec is None:
            return
        obj = next((o for o in rec.objects if o.object_id == object_id), None)
        if obj is None:
            return
        self._object_service.apply_length_points(
            obj, points, rec.scale, source="auto_suggested"
        )
        note = str(payload.get("message") or "auto length suggested")
        if note and note not in (obj.notes or ""):
            obj.notes = ((obj.notes + "; ") if obj.notes else "") + note
        self._mark_dirty()
        if self._workspace.current and self._workspace.current.image_id == image_id:
            self._object_table.update_object_row(obj)
            if self._selected_object_id == object_id:
                self._properties.set_object(obj)
                self._canvas.sync_length_points_from_object(obj)
                mask = self._object_service.get_mask(object_id)
                self._canvas.update_object_visual(obj, mask)

    def _on_batch_finished(self, summary: object) -> None:
        if self._batch_progress is not None:
            self._batch_progress.reset()
            self._batch_progress.close()
            self._batch_progress = None
        self._update_save_actions()
        # restore object service bind to current image
        if self._workspace and self._workspace.current:
            cur = self._workspace.current
            p = self._workspace.abs_path(cur)
            loaded, _ = self._image_service.try_get(p)
            if loaded:
                self._object_service.bind_image(
                    cur, width=loaded.meta.width, height=loaded.meta.height
                )
            self._object_table.set_image_record(cur)
            self._sync_canvas_objects()
            self._refresh_category_panel()

        cancelled = False
        completed = 0
        total = 0
        if isinstance(summary, dict):
            cancelled = bool(summary.get("cancelled"))
            completed = int(summary.get("completed") or 0)
            total = int(summary.get("total") or 0)
        if cancelled:
            QMessageBox.information(
                self,
                "批处理已取消",
                f"已取消。已完成 {completed}/{total} 项的结果已保留，未完成的已跳过。",
            )
        else:
            QMessageBox.information(
                self,
                "批处理完成",
                f"完成 {completed}/{total} 项。请检查并人工确认自动结果。",
            )
        self.statusBar().showMessage(
            f"批处理结束: {completed}/{total}" + ("（已取消）" if cancelled else ""),
            6000,
        )

    def run_auto_segmentation(self) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        rec = self._workspace.current
        dlg = SegmentationDialog(parent=self)
        if dlg.exec() != SegmentationDialog.DialogCode.Accepted:
            return
        mode = dlg.mode()
        params = dlg.params()
        do_length = dlg.auto_length()
        abs_path = self._workspace.abs_path(rec)
        loaded, err = self._image_service.try_get(abs_path)
        if err or loaded is None:
            QMessageBox.warning(self, "分割失败", f"无法读取图像：{err}")
            return

        progress = QProgressDialog(
            "正在自动分割并计算体长…" if do_length else "正在自动分割…",
            None,
            0,
            0,
            self,
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            created, result = self._object_service.apply_auto_segmentation(
                rec,
                loaded.raw,
                rec.scale,
                params,
                mode=mode,
                auto_length=do_length,
            )
        except Exception as exc:  # noqa: BLE001
            progress.close()
            logger.exception("Auto segmentation failed")
            QMessageBox.warning(
                self,
                "分割失败",
                f"自动分割未成功，项目未破坏。\n\n{exc}",
            )
            return
        progress.close()

        self._object_table.set_image_record(rec)
        self._sync_canvas_objects()
        self._image_list.refresh_item(self._workspace.current_index, rec)
        self._refresh_category_panel()
        if created:
            self.select_object(created[0].object_id)
        self._mark_dirty()
        n_len = sum(
            1
            for o in created
            if o.length_points and o.length_source == "auto_suggested"
        )
        extra = f"；体长建议 {n_len}/{len(created)}" if do_length else ""
        self.statusBar().showMessage(
            f"{result.message}；新建 {len(created)} 个对象（待确认）{extra}",
            8000,
        )
        if not created:
            QMessageBox.information(
                self,
                "分割完成",
                result.message or "未生成对象，请调整参数后重试。",
            )

    def merge_selected_objects(self) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        ids = self._object_table.selected_object_ids()
        if len(ids) < 2:
            QMessageBox.information(self, "合并", "请在对象表中多选至少 2 个对象（Ctrl/⌘+点击）。")
            return
        rec = self._workspace.current
        try:
            new_obj = self._object_service.merge_objects(rec, ids, rec.scale)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "合并失败", str(exc))
            return
        self._object_table.set_image_record(rec)
        self._sync_canvas_objects()
        self.select_object(new_obj.object_id)
        self._mark_dirty()
        self.statusBar().showMessage(f"已合并为 {new_obj.object_id}", 5000)

    def _on_split_cut(self, polyline: object) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        if not self._selected_object_id:
            return
        rec = self._workspace.current
        try:
            created = self._object_service.split_object_by_cut(
                rec,
                self._selected_object_id,
                polyline,  # type: ignore[arg-type]
                rec.scale,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "拆分失败", str(exc))
            return
        self._object_table.set_image_record(rec)
        self._sync_canvas_objects()
        if created:
            self.select_object(created[0].object_id)
        self._mark_dirty()
        self.statusBar().showMessage(f"切割拆分为 {len(created)} 个对象", 5000)

    def _on_split_seeds(self, seeds: object) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        if not self._selected_object_id:
            return
        rec = self._workspace.current
        try:
            created = self._object_service.split_object_by_seeds(
                rec,
                self._selected_object_id,
                seeds,  # type: ignore[arg-type]
                rec.scale,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "种子拆分失败", str(exc))
            return
        self._object_table.set_image_record(rec)
        self._sync_canvas_objects()
        if created:
            self.select_object(created[0].object_id)
        self._mark_dirty()
        self.statusBar().showMessage(f"种子拆分为 {len(created)} 个对象", 5000)

    def toggle_confirm_selected(self) -> None:
        if not self._selected_object_id or self._workspace is None:
            return
        rec = self._workspace.current
        if rec is None:
            return
        obj = self._find_object(self._selected_object_id)
        if obj is None:
            return
        obj.confirmed = not obj.confirmed
        self._object_service.set_confirmed(rec, obj.object_id, obj.confirmed)
        self._object_table.update_object_row(obj)
        self._properties.set_object(obj)
        self._mark_dirty()
        state = "已确认" if obj.confirmed else "待确认"
        self.statusBar().showMessage(f"{obj.object_id}: {state}", 3000)

    def _on_polygon_finished(self, points: list) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        rec = self._workspace.current
        try:
            obj = self._object_service.create_from_polygon(
                rec, points, rec.scale
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "创建对象失败", str(exc))
            return
        self._object_table.update_object_row(obj)
        mask = self._object_service.get_mask(obj.object_id)
        self._canvas.update_object_visual(obj, mask)
        self.select_object(obj.object_id)
        self._refresh_category_panel()
        self._mark_dirty()
        self._image_list.refresh_item(self._workspace.current_index, rec)
        self.statusBar().showMessage(
            f"已创建 {obj.object_id}，面积 {obj.area_px:.0f} px²", 5000
        )
        # stay in polygon mode for next object
        self._set_tool(MODE_POLYGON)

    def _on_brush_stroke(self, points: list, erase: bool) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        if not self._selected_object_id:
            return
        rec = self._workspace.current
        radius = self._canvas.brush_radius
        prev_id = self._selected_object_id
        result = self._object_service.paint_brush(
            rec,
            prev_id,
            points,
            radius,
            erase=erase,
            scale=rec.scale,
        )
        if result is None:
            return

        # Erase may delete or split into multiple independent objects
        if isinstance(result, list):
            created = result
            self._object_table.set_image_record(rec)
            self._sync_canvas_objects()
            self._refresh_category_panel()
            if not created:
                self._selected_object_id = None
                self._canvas.set_selected_object(None)
                self._properties.set_object(None)
                self._update_save_actions()
                self.statusBar().showMessage("对象已完全擦除", 4000)
                self._mark_dirty()
                return
            # New independent objects — select the first part
            first = created[0]
            self.select_object(first.object_id)
            n_len = sum(
                1
                for o in created
                if o.length_points and len(o.length_points) >= 2
            )
            ids = "、".join(o.object_id for o in created[:4])
            if len(created) > 4:
                ids += "…"
            self.statusBar().showMessage(
                f"已拆成 {len(created)} 个独立对象：{ids}"
                + (f"（{n_len} 段体长）" if n_len else ""),
                6000,
            )
            self._mark_dirty()
            return

        obj = result
        mask = self._object_service.get_mask(obj.object_id)
        self._canvas.update_object_visual(obj, mask)
        if erase:
            # Length path may have been clipped — refresh overlays + live path
            self._object_table.update_object_row(obj)
            self._sync_canvas_objects()
            self._canvas.sync_length_points_from_object(obj)
        else:
            self._object_table.update_object_row(obj)
        self._properties.set_object(obj)
        self._mark_dirty()

    def delete_selected_object(self) -> None:
        # In length mode, Delete removes a node (handled by canvas key); only
        # delete object when not editing length, or no node selected.
        if self._canvas.mode == MODE_LENGTH:
            if self._canvas.delete_selected_length_node():
                return
            self.statusBar().showMessage("体长模式：先选中节点再删除，或退出后删对象", 3000)
            return
        if self._selected_object_id:
            self._delete_object_id(self._selected_object_id)

    def _delete_object_id(self, object_id: str) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        rec = self._workspace.current
        ans = QMessageBox.question(
            self,
            "删除对象",
            f"确定删除对象 {object_id}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        if not self._object_service.delete_object(rec, object_id):
            return
        self._object_table.remove_object_row(object_id)
        self._canvas.remove_object_visual(object_id)
        if self._selected_object_id == object_id:
            self.select_object(None)
        self._mark_dirty()
        self.statusBar().showMessage(f"已删除 {object_id}", 3000)

    # --- scale calibration ---

    def start_scale_calibration(self) -> None:
        if self._workspace is None or self._workspace.current is None:
            QMessageBox.information(self, "比例尺", "请先打开工作区并选择图片。")
            return
        self._canvas.enter_scale_mode()

    def auto_detect_scale(self) -> None:
        """Detect scale bar from image (line + label guess), then confirm with user."""
        if self._workspace is None or self._workspace.current is None:
            QMessageBox.information(self, "比例尺", "请先打开工作区并选择图片。")
            return
        rec = self._workspace.current
        abs_path = self._workspace.abs_path(rec)
        loaded, err = self._image_service.try_get(abs_path)
        if err or loaded is None:
            QMessageBox.warning(self, "自动比例尺", f"无法读取图像：{err}")
            return

        from soilfauna_measure.core.scale_detection import detect_scale

        progress = QProgressDialog("正在识别比例尺…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            det = detect_scale(loaded.raw, default_real=1000.0, default_unit="um")
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.warning(self, "自动比例尺失败", str(exc))
            return
        progress.close()

        if not det.found or det.start_point is None or det.end_point is None:
            QMessageBox.information(
                self,
                "未识别到比例尺",
                det.message
                + "\n\n请改用手动校准（C）：在图上点击比例尺线段两端。",
            )
            return

        # Preview line on canvas
        self._canvas.set_scale_calibration(
            # temporary preview object-like via build
            None
        )
        from soilfauna_measure.core.calibration import build_scale_calibration

        preview_real = det.real_length if det.real_length is not None else 1000.0
        preview_unit = det.unit if det.unit is not None else "um"
        try:
            preview = build_scale_calibration(
                det.start_point,
                det.end_point,
                preview_real,
                preview_unit,
                method="auto_pending",
                confirmed=False,
            )
            self._canvas.set_scale_calibration(preview)
        except Exception:  # noqa: BLE001
            pass

        dlg = ScaleDialog(
            det.pixel_length,
            default_real=float(preview_real),
            default_unit=str(preview_unit),
            title="确认自动比例尺",
            hint_text=(
                det.message
                + "\n\n请核对真实长度与单位后确认。"
                "自动识别不能替代最终人工确认。"
            ),
            parent=self,
        )
        if dlg.exec() != ScaleDialog.DialogCode.Accepted:
            # restore previous scale overlay
            self._canvas.set_scale_calibration(rec.scale)
            self._properties.set_scale(rec.scale)
            return

        real_len, unit = dlg.result_values()
        try:
            scale = build_scale_calibration(
                det.start_point,
                det.end_point,
                real_len,
                unit,
                method="auto_confirmed",
                confirmed=True,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "比例尺无效", str(exc))
            self._canvas.set_scale_calibration(rec.scale)
            return

        rec.scale = scale
        if rec.status == "pending":
            rec.status = "in_progress"
        self._object_service.recompute_all_metrics(rec, scale)
        self._object_table.set_image_record(rec)
        if self._selected_object_id:
            self._properties.set_object(self._find_object(self._selected_object_id))
        self._properties.set_scale(scale)
        self._canvas.set_scale_calibration(scale)
        self._image_list.refresh_item(self._workspace.current_index, rec)
        self._mark_dirty()
        self.save_project()
        self.statusBar().showMessage(
            f"比例尺已自动识别并确认: {format_scale_summary(scale)}", 6000
        )

    def _on_scale_points(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        px_len = compute_pixel_length((x0, y0), (x1, y1))
        if px_len <= 0:
            QMessageBox.warning(self, "比例尺", "起点与终点不能重合。")
            self._canvas.cancel_scale_mode()
            return

        default_unit = str(
            self._workspace.project.settings.get("default_scale_unit", "um")
        )
        dlg = ScaleDialog(
            px_len,
            default_real=1000.0,
            default_unit=default_unit,
            parent=self,
        )
        if dlg.exec() != ScaleDialog.DialogCode.Accepted:
            self._canvas.cancel_scale_mode()
            self._canvas.set_scale_calibration(self._workspace.current.scale)
            return

        real_len, unit = dlg.result_values()
        try:
            scale = build_scale_calibration(
                (x0, y0),
                (x1, y1),
                real_len,
                unit,
                method="manual",
                confirmed=True,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "比例尺无效", str(exc))
            self._canvas.set_scale_calibration(self._workspace.current.scale)
            return

        rec = self._workspace.current
        rec.scale = scale
        if rec.status == "pending":
            rec.status = "in_progress"
        # update object real areas and lengths
        self._object_service.recompute_all_metrics(rec, scale)
        self._object_table.set_image_record(rec)
        if self._selected_object_id:
            obj = next(
                (o for o in rec.objects if o.object_id == self._selected_object_id),
                None,
            )
            self._properties.set_object(obj)
        self._properties.set_scale(scale)
        self._canvas.set_scale_calibration(scale)
        self._image_list.refresh_item(self._workspace.current_index, rec)
        self._mark_dirty()
        self.save_project()
        self.statusBar().showMessage(
            f"比例尺已校准: {format_scale_summary(scale)}", 6000
        )

    # --- status handlers ---

    def _on_cursor_pos(self, x: float, y: float) -> None:
        w, h = self._canvas.image_size
        if w <= 0:
            self._coord_label.setText("坐标: —")
            return
        inside = 0 <= x < w and 0 <= y < h
        mark = "" if inside else " (外)"
        self._coord_label.setText(f"坐标: {x:.1f}, {y:.1f}{mark}")

    def _on_zoom(self, z: float) -> None:
        self._zoom_label.setText(f"缩放: {z * 100:.1f}%")

    def _on_canvas_status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)

    def _confirm_discard_if_dirty(self) -> bool:
        if self._workspace is None or not self._workspace.dirty:
            return True
        ans = QMessageBox.question(
            self,
            "未保存的更改",
            "当前项目有未保存更改。是否先保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if ans == QMessageBox.StandardButton.Cancel:
            return False
        if ans == QMessageBox.StandardButton.Save:
            return self.save_project()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_if_dirty():
            event.ignore()
            return
        self._periodic_save.stop()
        if self._thumb_runnable is not None:
            try:
                self._thumb_runnable.cancel()
            except Exception:  # noqa: BLE001
                pass
        if self._workspace is not None:
            rec = self._workspace.current
            if rec is not None:
                self._object_service.persist_all_dirty_masks(rec)
            self._autosave.flush_now()
            try:
                save_workspace(self._workspace)
            except Exception:  # noqa: BLE001
                logger.exception("Final save on close failed")
        event.accept()

    def emergency_save(self) -> None:
        """Called from crash hook — best-effort flush without UI."""
        try:
            if self._workspace is None:
                return
            rec = self._workspace.current
            if rec is not None:
                self._object_service.persist_all_dirty_masks(rec)
            self._autosave.flush_now()
            if self._workspace.dirty:
                save_workspace(self._workspace)
            logger.critical("Emergency save completed for %s", self._workspace.root)
        except Exception:  # noqa: BLE001
            logger.exception("Emergency save failed")

    def _periodic_autosave(self) -> None:
        if self._workspace is None:
            return
        if self._workspace.dirty:
            self._autosave.flush_now()

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = get_recent_workspaces()
        if not recent:
            empty = QAction("（无）", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
        else:
            for path in recent:
                act = QAction(path, self)
                act.triggered.connect(
                    lambda checked=False, p=path: self._open_recent(p)
                )
                self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        self._recent_menu.addAction(self._act_clear_recent)

    def _open_recent(self, path: str) -> None:
        p = Path(path)
        if not p.is_dir():
            QMessageBox.warning(self, "最近工作区", f"目录不存在：\n{path}")
            self._rebuild_recent_menu()
            return
        if not self._confirm_discard_if_dirty():
            return
        self.load_workspace(p)

    def _clear_recent(self) -> None:
        clear_recent_workspaces()
        self._rebuild_recent_menu()

    def _start_thumbnails(self, ws: Workspace) -> None:
        items = []
        for img in ws.images:
            items.append((img.image_id, ws.abs_path(img)))
        if not items:
            return
        sig, run = start_thumbnail_batch(ws.root, items)
        self._thumb_runnable = run
        sig.ready.connect(self._image_list.set_thumbnail)

    def _set_image_status(self, status: str) -> None:
        if self._workspace is None or self._workspace.current is None:
            return
        rec = self._workspace.current
        rec.status = status
        self._image_list.refresh_item(self._workspace.current_index, rec)
        self._mark_dirty()
        self.statusBar().showMessage(f"图片状态: {status}", 3000)

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def _open_user_guide(self) -> None:
        # Prefer packaged docs next to package or repo docs/
        candidates = [
            Path(__file__).resolve().parents[3] / "docs" / "USER_GUIDE.md",
            Path(__file__).resolve().parents[2] / "docs" / "USER_GUIDE.md",
            Path.cwd() / "docs" / "USER_GUIDE.md",
        ]
        for p in candidates:
            if p.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                return
        QMessageBox.information(
            self,
            "用户说明",
            "未找到 docs/USER_GUIDE.md。\n请查看项目仓库中的文档。",
        )

    def _open_log_dir(self) -> None:
        from soilfauna_measure.crash_handler import default_log_dir

        d = default_log_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _show_about(self) -> None:
        from soilfauna_measure.resources import icon_path, load_app_icon, load_logo_pixmap

        box = QMessageBox(self)
        box.setWindowTitle("关于")
        logo = load_logo_pixmap(96)
        if logo is not None:
            box.setIconPixmap(logo)
        else:
            icon = load_app_icon()
            if not icon.isNull():
                box.setIconPixmap(icon.pixmap(96, 96))
        box.setText(
            f"<h3>{__app_name__}</h3>"
            f"<p>版本 {__version__}</p>"
            "<p>土壤动物图像分割与形态测量系统（离线）</p>"
            "<p>土衡：称量大地微生，计量土壤动物形态。</p>"
            "<p>F1 快捷键 · Ctrl+B 批处理 · Ctrl+E 导出</p>"
        )
        logo_file = icon_path("logo.png")
        if logo_file.is_file():
            box.setInformativeText(f"Logo：{logo_file.name}")
        box.exec()
