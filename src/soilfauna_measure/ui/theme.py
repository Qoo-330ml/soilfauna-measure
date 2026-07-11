"""macOS 26–inspired Liquid Glass theme for SoilFauna Measure.

Approximates Tahoe / Liquid Glass within Qt limits:
  - luminous frosted surfaces
  - continuous large radii & capsule controls
  - soft specular edge highlights
  - airy spacing and layered chrome over content
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

# ---------------------------------------------------------------------------
# Design tokens — light Liquid Glass
# ---------------------------------------------------------------------------

# Base canvas behind glass layers (cool system gray)
BG = "#e8e8ed"
BG_GRADIENT_TOP = "#f2f2f7"
BG_GRADIENT_BOTTOM = "#e5e5ea"

# Frosted glass fills (solid approximations of vibrancy)
GLASS = "#fbfbfd"  # primary glass plate
GLASS_SOFT = "#f4f4f8"  # secondary / recessed glass
GLASS_ELEVATED = "#ffffff"  # floating chrome (toolbar pills)
GLASS_TINT = "rgba(255, 255, 255, 0.72)"
GLASS_SHEEN = "rgba(255, 255, 255, 0.92)"

# Legacy aliases used by panels
SURFACE = GLASS
SURFACE_MUTED = GLASS_SOFT

# Edges — outer hairline + inner specular
BORDER = "rgba(0, 0, 0, 0.08)"
BORDER_SOFT = "rgba(0, 0, 0, 0.05)"
BORDER_SPECULAR = "rgba(255, 255, 255, 0.85)"
DIVIDER = "rgba(0, 0, 0, 0.06)"

# Text — SF-like hierarchy
TEXT = "#1c1c1e"
TEXT_SECONDARY = "#636366"
TEXT_MUTED = "#8e8e93"
TEXT_INVERSE = "#ffffff"

# System accent (macOS blue, luminous)
ACCENT = "#007aff"
ACCENT_SOFT = "rgba(0, 122, 255, 0.12)"
ACCENT_HOVER = "rgba(0, 122, 255, 0.18)"
ACCENT_BORDER = "rgba(0, 122, 255, 0.45)"
ACCENT_PRESSED = "#0066d6"

# Interactive glass states
HOVER = "rgba(0, 0, 0, 0.04)"
SELECTED = "rgba(0, 122, 255, 0.14)"
SELECTED_BORDER = ACCENT
FOCUS = ACCENT

# Feedback
DANGER = "#ff3b30"
SUCCESS = "#34c759"
WARNING = "#ff9f0a"

# Image viewport
CANVAS_BG = "#1c1c1e"

# Annotation colors (calm, still readable on micrographs)
SELECTION_FILL = QColor(255, 69, 58)
SELECTION_OUTLINE = QColor(255, 255, 255)
LENGTH_PATH = QColor(10, 132, 255)
LENGTH_END = QColor(52, 199, 89)
LENGTH_MID = QColor(255, 69, 58)
LENGTH_ACTIVE = QColor(255, 204, 0)
CUT_TOOL = QColor(255, 149, 0)
SEED_TOOL = QColor(90, 200, 250)

# Typography — SF Pro stack
FONT_FAMILY = (
    ".AppleSystemUIFont, -apple-system, BlinkMacSystemFont, "
    "'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', "
    "'PingFang SC', 'Segoe UI', sans-serif"
)
FONT_SIZE = 13
FONT_SIZE_SM = 11
FONT_SIZE_TITLE = 13

# Continuous curves (Liquid Glass loves large radii)
RADIUS = 14
RADIUS_SM = 10
RADIUS_PILL = 999
RADIUS_CARD = 16
CONTROL_HEIGHT = 32
TOOLBAR_HEIGHT = 44


def _palette() -> QPalette:
    p = QPalette()
    bg = QColor(BG)
    surface = QColor(GLASS)
    text = QColor(TEXT)
    muted = QColor(TEXT_MUTED)
    accent = QColor(ACCENT)
    inverse = QColor(TEXT_INVERSE)

    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, surface)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(GLASS_SOFT))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
    p.setColor(QPalette.ColorRole.Button, surface)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, inverse)
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, inverse)
    p.setColor(QPalette.ColorRole.Link, accent)
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(GLASS_ELEVATED))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Midlight, QColor("#f2f2f7"))
    p.setColor(QPalette.ColorRole.Mid, QColor("#d1d1d6"))
    p.setColor(QPalette.ColorRole.Dark, QColor(TEXT_SECONDARY))
    p.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0, 40))
    return p


def stylesheet() -> str:
    """Global QSS — Liquid Glass approximation."""
    return f"""
    /* ---- Base ---- */
    * {{
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE}px;
        outline: none;
    }}

    QMainWindow {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {BG_GRADIENT_TOP},
            stop:1 {BG_GRADIENT_BOTTOM}
        );
        color: {TEXT};
    }}
    QDialog {{
        background-color: {BG_GRADIENT_TOP};
        color: {TEXT};
    }}

    QWidget {{
        background-color: transparent;
        color: {TEXT};
    }}

    QToolTip {{
        background-color: {GLASS_ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 7px 10px;
        border-radius: {RADIUS_SM}px;
    }}

    /* ---- Menu bar (near-transparent chrome) ---- */
    QMenuBar {{
        background-color: rgba(255, 255, 255, 0.55);
        color: {TEXT};
        border: none;
        border-bottom: 1px solid {BORDER_SOFT};
        padding: 3px 10px 2px 10px;
        spacing: 1px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 5px 11px;
        border-radius: {RADIUS_SM}px;
        margin: 1px 1px;
        color: {TEXT};
    }}
    QMenuBar::item:selected {{
        background-color: {HOVER};
    }}
    QMenuBar::item:pressed {{
        background-color: {SELECTED};
    }}

    QMenu {{
        background-color: rgba(255, 255, 255, 0.94);
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 30px 7px 14px;
        border-radius: {RADIUS_SM}px;
        margin: 1px 2px;
    }}
    QMenu::item:selected {{
        background-color: {SELECTED};
        color: {TEXT};
    }}
    QMenu::separator {{
        height: 1px;
        background: {DIVIDER};
        margin: 5px 10px;
    }}
    QMenu::indicator {{
        width: 14px;
        height: 14px;
        margin-left: 6px;
    }}

    /* ---- Toolbar — floating glass strip ---- */
    QToolBar {{
        background-color: rgba(255, 255, 255, 0.72);
        border: none;
        border-bottom: 1px solid {BORDER_SOFT};
        spacing: 3px;
        padding: 6px 12px;
        min-height: {TOOLBAR_HEIGHT}px;
    }}
    QToolBar::separator {{
        background: {DIVIDER};
        width: 1px;
        margin: 8px 7px;
    }}
    QToolButton {{
        background-color: rgba(255, 255, 255, 0.35);
        color: {TEXT};
        border: 1px solid {BORDER_SOFT};
        border-radius: {RADIUS_PILL}px;
        padding: 6px 12px;
        min-height: 22px;
    }}
    QToolButton:hover {{
        background-color: rgba(255, 255, 255, 0.88);
        border: 1px solid {BORDER};
    }}
    QToolButton:pressed, QToolButton:checked {{
        background-color: {SELECTED};
        border: 1px solid {ACCENT_BORDER};
        color: {TEXT};
    }}
    QToolButton::menu-indicator {{
        image: none;
        width: 0;
    }}

    /* ---- Status bar — thin glass footer ---- */
    QStatusBar {{
        background-color: rgba(255, 255, 255, 0.55);
        color: {TEXT_SECONDARY};
        border-top: 1px solid {BORDER_SOFT};
        min-height: 28px;
        padding: 0 10px;
    }}
    QStatusBar QLabel {{
        color: {TEXT_SECONDARY};
        padding: 0 7px;
        font-size: {FONT_SIZE_SM}px;
        letter-spacing: 0.1px;
    }}
    QStatusBar::item {{
        border: none;
    }}

    /* ---- Splitter — airy gap, not industrial rail ---- */
    QSplitter::handle {{
        background-color: transparent;
    }}
    QSplitter::handle:horizontal {{
        width: 8px;
        margin: 12px 0;
        border-radius: 4px;
        background: transparent;
    }}
    QSplitter::handle:vertical {{
        height: 8px;
    }}
    QSplitter::handle:hover {{
        background-color: {ACCENT_SOFT};
    }}

    /* ---- Buttons — capsule glass ---- */
    QPushButton {{
        background-color: rgba(255, 255, 255, 0.78);
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_PILL}px;
        padding: 6px 14px;
        min-height: 22px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.95);
        border: 1px solid rgba(0, 0, 0, 0.12);
    }}
    QPushButton:pressed {{
        background-color: {SELECTED};
    }}
    QPushButton:disabled {{
        color: {TEXT_MUTED};
        background-color: rgba(255, 255, 255, 0.4);
        border-color: {BORDER_SOFT};
    }}
    QPushButton:default, QPushButton[cssClass="primary"] {{
        background-color: {ACCENT};
        color: {TEXT_INVERSE};
        border: 1px solid rgba(255, 255, 255, 0.25);
        font-weight: 600;
    }}
    QPushButton:default:hover {{
        background-color: {ACCENT_PRESSED};
    }}

    /* ---- Inputs — inset glass wells ---- */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QAbstractSpinBox {{
        background-color: rgba(255, 255, 255, 0.65);
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 5px 10px;
        min-height: 22px;
        selection-background-color: {ACCENT};
        selection-color: {TEXT_INVERSE};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1.5px solid {ACCENT};
        background-color: rgba(255, 255, 255, 0.92);
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: rgba(255, 255, 255, 0.96);
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {SELECTED};
        selection-color: {TEXT};
        outline: none;
        padding: 4px;
    }}

    /* ---- Group boxes — frosted cards (dialogs etc.) ---- */
    QGroupBox {{
        background-color: rgba(255, 255, 255, 0.72);
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        margin-top: 18px;
        padding: 18px 14px 14px 14px;
        font-weight: 500;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        top: 2px;
        padding: 0 6px;
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
        background-color: transparent;
    }}

    /* ---- Lists & tables — soft plates ----
       NOTE: QTableWidget item text must set color explicitly;
       otherwise Fusion + global QSS often paints blank cells. */
    QListWidget, QTreeWidget {{
        background-color: rgba(255, 255, 255, 0.72);
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        padding: 4px;
        outline: none;
        selection-background-color: {SELECTED};
        selection-color: {TEXT};
    }}
    QListWidget::item, QTreeWidget::item {{
        color: {TEXT};
        padding: 7px 10px;
        border-radius: {RADIUS_SM}px;
        margin: 1px 2px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {SELECTED};
        color: {TEXT};
    }}
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {{
        background-color: {HOVER};
    }}

    QTableWidget, QTableView, QTreeView {{
        background-color: rgba(255, 255, 255, 0.88);
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        padding: 2px;
        outline: none;
        gridline-color: rgba(0, 0, 0, 0.04);
        alternate-background-color: rgba(0, 0, 0, 0.025);
        selection-background-color: rgba(0, 122, 255, 0.16);
        selection-color: {TEXT};
    }}
    QTableWidget::item, QTableView::item, QTreeView::item {{
        color: {TEXT};
        background-color: transparent;
        padding: 5px 8px;
        border: none;
    }}
    QTableWidget::item:selected, QTableView::item:selected, QTreeView::item:selected {{
        color: {TEXT};
        background-color: rgba(0, 122, 255, 0.16);
    }}
    QTableWidget::item:hover:!selected, QTableView::item:hover:!selected {{
        background-color: {HOVER};
    }}

    QHeaderView {{
        background-color: transparent;
    }}
    QHeaderView::section {{
        background-color: rgba(255, 255, 255, 0.55);
        color: {TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {DIVIDER};
        padding: 8px 10px;
        font-weight: 600;
        font-size: {FONT_SIZE_SM}px;
        letter-spacing: 0.15px;
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}

    /* ---- Scroll bars — floating pills ---- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(0, 0, 0, 0.18);
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(0, 0, 0, 0.28);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0;
        background: none;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(0, 0, 0, 0.18);
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(0, 0, 0, 0.28);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        width: 0;
        background: none;
    }}

    /* ---- Tabs ---- */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        background: rgba(255, 255, 255, 0.65);
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        padding: 8px 16px;
        margin-right: 3px;
        border-radius: {RADIUS_PILL}px;
    }}
    QTabBar::tab:selected {{
        color: {TEXT};
        background: rgba(255, 255, 255, 0.85);
        border: 1px solid {BORDER_SOFT};
    }}
    QTabBar::tab:hover:!selected {{
        background: {HOVER};
        color: {TEXT};
    }}

    /* ---- Progress ---- */
    QProgressBar {{
        border: none;
        border-radius: 6px;
        background: rgba(0, 0, 0, 0.06);
        text-align: center;
        color: {TEXT_SECONDARY};
        min-height: 8px;
        max-height: 8px;
    }}
    QProgressBar::chunk {{
        background-color: {ACCENT};
        border-radius: 6px;
    }}

    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {TEXT};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
    }}

    QLabel {{
        color: {TEXT};
        background: transparent;
    }}

    QMessageBox {{
        background-color: {BG_GRADIENT_TOP};
    }}
    QDialogButtonBox QPushButton {{
        min-width: 78px;
    }}

    QTextBrowser {{
        background-color: rgba(255, 255, 255, 0.7);
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        padding: 10px;
    }}

    /* Side panels sit on soft glass wells */
    QWidget#GlassPanel {{
        background-color: rgba(255, 255, 255, 0.48);
        border: 1px solid {BORDER_SOFT};
        border-radius: {RADIUS_CARD}px;
    }}
    """


def filmstrip_stylesheet() -> str:
    """Thumbnail strip — floating glass tiles."""
    return f"""
    QListWidget {{
        background: rgba(255, 255, 255, 0.42);
        border: 1px solid {BORDER_SOFT};
        border-radius: {RADIUS_CARD}px;
        outline: none;
        padding: 8px;
    }}
    QListWidget::item {{
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid {BORDER_SOFT};
        border-radius: 12px;
        padding: 4px;
        color: {TEXT_SECONDARY};
        margin: 0 3px;
    }}
    QListWidget::item:selected {{
        background: rgba(255, 255, 255, 0.98);
        border: 1.5px solid {ACCENT};
        color: {TEXT};
    }}
    QListWidget::item:hover:!selected {{
        border: 1px solid rgba(0, 0, 0, 0.12);
        background: rgba(255, 255, 255, 0.95);
    }}
    """


def title_label_style() -> str:
    return (
        f"font-weight: 600; font-size: {FONT_SIZE_TITLE}px; "
        f"color: {TEXT}; padding: 2px 0; letter-spacing: -0.1px;"
    )


def muted_label_style() -> str:
    return f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SM}px;"


def secondary_label_style() -> str:
    return f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"


def apply_macos_window_chrome(window: QMainWindow) -> None:
    """Best-effort native macOS Tahoe chrome (unified toolbar / title)."""
    if sys.platform != "darwin":
        return
    try:
        # Unified title + toolbar look
        window.setUnifiedTitleAndToolBarOnMac(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Slight translucency hint where supported
        window.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
    except Exception:  # noqa: BLE001
        pass


def apply_theme(app: QApplication) -> None:
    """Install Fusion + Liquid Glass palette / stylesheet."""
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(stylesheet())

    font = QFont()
    # Point size tracks macOS control text better than pixel size
    font.setPointSize(13)
    app.setFont(font)


def mark_glass_panel(widget: QWidget) -> None:
    """Tag a side panel for the GlassPanel QSS rule."""
    widget.setObjectName("GlassPanel")
    # Re-polish so objectName-based QSS applies
    widget.style().unpolish(widget)
    widget.style().polish(widget)
