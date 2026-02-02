# ui/theme/core.py - Theme definitions, font persistence, and global styling

import logging
import re
import sys
from pathlib import Path

from PyQt5 import QtCore, QtWidgets, QtGui

THEME_SETTINGS_KEY = "theme"
DEFAULT_THEME = "Fusion"

REQUIRED_THEME_KEYS = (
    "WINDOW_COLOR", "BASE_COLOR", "ALT_BASE_COLOR", "TEXT_COLOR",
    "DISABLED_TEXT", "BUTTON_COLOR", "BORDER_COLOR", "ACCENT_ORANGE",
    "HIGHLIGHT", "TOOLTIP_BASE", "TOOLTIP_TEXT",
)

_HEX_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

THEME_FUSION = {
    "WINDOW_COLOR": "#4F5875",
    "BASE_COLOR": "#262C3D",
    "ALT_BASE_COLOR": "#30374A",
    "TEXT_COLOR": "#F5F5F5",
    "DISABLED_TEXT": "#9299AE",
    "BUTTON_COLOR": "#333A4F",
    "BORDER_COLOR": "#1E3E62",
    "ACCENT_ORANGE": "#DC6D18",
    "HIGHLIGHT": "#DC6D18",
    "TOOLTIP_BASE": "#121C2A",
    "TOOLTIP_TEXT": "#F5F5F5",
}

THEME_TAYLOR = {
    "WINDOW_COLOR": "#003314",
    "BASE_COLOR": "#2C3227",
    "ALT_BASE_COLOR": "#1a1e16",
    "TEXT_COLOR": "#F2F3F4",
    "DISABLED_TEXT": "#8a8d90",
    "BUTTON_COLOR": "#427F80",
    "BORDER_COLOR": "#427F80",
    "ACCENT_ORANGE": "#C14404",
    "HIGHLIGHT": "#C9A0DC",
    "TOOLTIP_BASE": "#2C3227",
    "TOOLTIP_TEXT": "#F2F3F4",
}

THEME_TESS = {
    "WINDOW_COLOR": "#4F6A72",
    "BASE_COLOR": "#3d5560",
    "ALT_BASE_COLOR": "#5a7d88",
    "TEXT_COLOR": "#E9E2D6",
    "DISABLED_TEXT": "#9a958d",
    "BUTTON_COLOR": "#729AA7",
    "BORDER_COLOR": "#729AA7",
    "ACCENT_ORANGE": "#E6A175",
    "HIGHLIGHT": "#A4D5C2",
    "TOOLTIP_BASE": "#3d5560",
    "TOOLTIP_TEXT": "#E9E2D6",
}

THEME_RETINA_SEERING = {
    "WINDOW_COLOR": "#ffffff",
    "BASE_COLOR": "#fafafa",
    "ALT_BASE_COLOR": "#f5f5f5",
    "TEXT_COLOR": "#2c2c2c",
    "DISABLED_TEXT": "#9a9a9a",
    "BUTTON_COLOR": "#f0f0f0",
    "BORDER_COLOR": "#e0e0e0",
    "ACCENT_ORANGE": "#606060",
    "HIGHLIGHT": "#b8d4e8",
    "TOOLTIP_BASE": "#fafafa",
    "TOOLTIP_TEXT": "#2c2c2c",
}

THEME_VICE = {
    "WINDOW_COLOR": "#2A2773",
    "BASE_COLOR": "#2A2773",
    "ALT_BASE_COLOR": "#3d3a8c",
    "TEXT_COLOR": "#ffffff",
    "DISABLED_TEXT": "#8888aa",
    "BUTTON_COLOR": "#0bd3d3",
    "BORDER_COLOR": "#D96236",
    "ACCENT_ORANGE": "#D96236",
    "HIGHLIGHT": "#f890e7",
    "TOOLTIP_BASE": "#2A2773",
    "TOOLTIP_TEXT": "#ffffff",
}

THEMES = {
    "Fusion": THEME_FUSION,
    "Taylor's Theme": THEME_TAYLOR,
    "Tess's Theme": THEME_TESS,
    "Retina Seering": THEME_RETINA_SEERING,
    "Vice": THEME_VICE,
}

BUILT_IN_THEME_NAMES = frozenset(THEMES)


def normalize_hex(s: str) -> str | None:
    """Validate and normalize hex to #RRGGBB. Returns None if invalid."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    m = _HEX_PATTERN.match(s)
    if not m:
        return None
    raw = m.group(1)
    if len(raw) == 3:
        return f"#{raw[0]*2}{raw[1]*2}{raw[2]*2}".upper()
    return f"#{raw}".upper()


def validate_theme_colors(colors: dict) -> tuple[bool, str]:
    """
    Validate theme dict. Returns (True, "") if valid, else (False, error_message).
    """
    if not isinstance(colors, dict):
        return False, "Theme must be a dict"
    for key in REQUIRED_THEME_KEYS:
        if key not in colors:
            return False, f"Missing required key: {key}"
        val = colors[key]
        if not isinstance(val, str) or not val.strip():
            return False, f"Invalid value for {key}: must be non-empty string"
        if normalize_hex(val) is None:
            return False, f"Invalid hex for {key}: {val!r}"
    return True, ""


def validate_hex_input(text: str) -> tuple[bool, str]:
    """
    Validate hex input. Returns (valid, result).
    If valid: result is normalized hex (#RRGGBB).
    If invalid: result is error message.
    """
    n = normalize_hex(text)
    if n:
        return True, n
    if not text or not str(text).strip():
        return False, "Enter a hex color (e.g. #FF0000)"
    return False, "Invalid hex color"


def open_color_picker(initial_hex: str, parent=None) -> str | None:
    """Open QColorDialog. Returns selected color as #RRGGBB, or None if cancelled."""
    color = QtGui.QColor(initial_hex) if initial_hex else QtGui.QColor(QtGui.Qt.white)
    if not color.isValid() and initial_hex:
        n = normalize_hex(initial_hex)
        if n:
            color = QtGui.QColor(n)
    chosen = QtWidgets.QColorDialog.getColor(color, parent, "Choose color")
    if chosen.isValid():
        return chosen.name().upper()
    return None


def _lighten_hex(hex_color: str, factor: float = 1.15) -> str:
    """Lighten a hex color by factor (e.g. 1.15 = 15% brighter)."""
    h = normalize_hex(hex_color)
    if not h:
        return hex_color
    r = min(255, int(int(h[1:3], 16) * factor))
    g = min(255, int(int(h[3:5], 16) * factor))
    b = min(255, int(int(h[5:7], 16) * factor))
    return f"#{r:02X}{g:02X}{b:02X}"


def _load_custom_themes() -> dict[str, dict]:
    """Load custom themes from storage. Returns dict name -> colors (validated)."""
    try:
        from ui.theme.storage import load_custom_themes
        return load_custom_themes()
    except ImportError:
        return {}
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to load custom themes: %s", e)
        return {}


def get_all_themes() -> dict[str, dict]:
    """Merge built-in and custom themes. Built-in take precedence for name clashes."""
    custom = _load_custom_themes()
    result = dict(THEMES)
    for name, colors in custom.items():
        if name not in BUILT_IN_THEME_NAMES:
            result[name] = colors
    return result


def get_theme_colors(theme_name: str) -> dict | None:
    """Return validated colors dict for theme, or None if not found/invalid."""
    all_themes = get_all_themes()
    colors = all_themes.get(theme_name)
    if colors is None:
        return None
    valid, _ = validate_theme_colors(colors)
    return colors if valid else None


def get_saved_theme() -> str:
    """Return the last selected theme name (stored in QSettings)."""
    s = QtCore.QSettings("CalibrationTracker", "CalibrationTracker")
    name = s.value(THEME_SETTINGS_KEY, DEFAULT_THEME, type=str)
    all_themes = get_all_themes()
    return name if name in all_themes else DEFAULT_THEME


def set_saved_theme(theme_name: str) -> None:
    """Store the selected theme name in QSettings."""
    all_themes = get_all_themes()
    if theme_name not in all_themes:
        return
    s = QtCore.QSettings("CalibrationTracker", "CalibrationTracker")
    s.setValue(THEME_SETTINGS_KEY, theme_name)


# Font size
FONT_SIZE_SETTINGS_KEY = "font_size"
DEFAULT_FONT_SIZE = 9
FONT_SIZE_OPTIONS = [
    ("Small", 8),
    ("Medium", 9),
    ("Large", 10),
    ("Extra Large", 11),
]
FONT_SIZE_POINTS = {label: pt for label, pt in FONT_SIZE_OPTIONS}


def get_saved_font_size() -> int:
    """Return the last selected font size in points (stored in QSettings)."""
    s = QtCore.QSettings("CalibrationTracker", "CalibrationTracker")
    pt = s.value(FONT_SIZE_SETTINGS_KEY, DEFAULT_FONT_SIZE, type=int)
    valid = {opt[1] for opt in FONT_SIZE_OPTIONS}
    return pt if pt in valid else DEFAULT_FONT_SIZE


def set_saved_font_size(pt: int) -> None:
    """Store the selected font size in QSettings."""
    valid = {opt[1] for opt in FONT_SIZE_OPTIONS}
    if pt not in valid:
        return
    s = QtCore.QSettings("CalibrationTracker", "CalibrationTracker")
    s.setValue(FONT_SIZE_SETTINGS_KEY, pt)


def _app_icon_path() -> Path:
    """Path to cal_tracker.ico for window/taskbar icon. Works when run as script or frozen exe."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / "cal_tracker.ico"


def apply_global_style(app: QtWidgets.QApplication, theme_name: str | None = None) -> None:
    """
    Apply modern, user-friendly styling to the application.
    theme_name: one of get_all_themes() keys; if None, uses saved theme.
    """
    if theme_name is None:
        theme_name = get_saved_theme()
    all_themes = get_all_themes()
    if theme_name not in all_themes:
        theme_name = DEFAULT_THEME
    colors = all_themes[theme_name]
    valid, err = validate_theme_colors(colors)
    if not valid:
        logging.getLogger(__name__).warning("Invalid theme %r: %s", theme_name, err)
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                None, "Theme error",
                f"Theme '{theme_name}' is invalid: {err}\n\nUsing default theme.",
            )
        except Exception:
            pass
        theme_name = DEFAULT_THEME
        colors = THEMES[theme_name]
    _apply_colors_to_app(app, colors)


def apply_theme_from_colors(app: QtWidgets.QApplication, colors: dict) -> bool:
    """
    Apply a colors dict to the app. Validates first.
    Returns True if applied, False if invalid (caller should show error).
    """
    valid, _ = validate_theme_colors(colors)
    if not valid:
        return False
    _apply_colors_to_app(app, colors)
    return True


def _apply_colors_to_app(app: QtWidgets.QApplication, colors: dict) -> None:
    """Apply a validated colors dict to the app (palette + QSS)."""
    WINDOW_COLOR = colors["WINDOW_COLOR"]
    BASE_COLOR = colors["BASE_COLOR"]
    ALT_BASE_COLOR = colors["ALT_BASE_COLOR"]
    TEXT_COLOR = colors["TEXT_COLOR"]
    DISABLED_TEXT = colors["DISABLED_TEXT"]
    BUTTON_COLOR = colors["BUTTON_COLOR"]
    BORDER_COLOR = colors["BORDER_COLOR"]
    ACCENT_ORANGE = colors["ACCENT_ORANGE"]
    ACCENT_HOVER = _lighten_hex(ACCENT_ORANGE)
    HIGHLIGHT = colors["HIGHLIGHT"]
    TOOLTIP_BASE = colors["TOOLTIP_BASE"]
    TOOLTIP_TEXT = colors["TOOLTIP_TEXT"]

    app.setStyle("Fusion")

    palette = app.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(WINDOW_COLOR))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(BASE_COLOR))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(ALT_BASE_COLOR))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(TOOLTIP_BASE))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TOOLTIP_TEXT))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(BUTTON_COLOR))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(HIGHLIGHT))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(ACCENT_ORANGE))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(DISABLED_TEXT))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(DISABLED_TEXT))
    app.setPalette(palette)

    font_pt = get_saved_font_size()
    app.setFont(QtGui.QFont("Segoe UI", font_pt))

    qss = f"""
    * {{
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: {font_pt}pt;
    }}

    QMainWindow {{
        background-color: {WINDOW_COLOR};
    }}

    QDialog {{
        background-color: {WINDOW_COLOR};
    }}

    QToolBar {{
        background-color: {BASE_COLOR};
        border: none;
        border-bottom: 1px solid {BORDER_COLOR};
        padding: 4px;
        spacing: 4px;
    }}
    QToolBar QToolButton {{
        color: {TEXT_COLOR};
        padding: 6px 12px;
        border-radius: 4px;
        border: 1px solid transparent;
    }}
    QToolBar QToolButton:hover {{
        background-color: {ALT_BASE_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QToolBar QToolButton:pressed {{
        background-color: {BUTTON_COLOR};
    }}

    QStatusBar {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border-top: 1px solid {BORDER_COLOR};
        padding: 2px;
    }}

    QPushButton {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        padding: 6px 14px;
        min-width: 80px;
    }}
    QPushButton:hover {{
        background-color: {ALT_BASE_COLOR};
        border-color: {ACCENT_ORANGE};
    }}
    QPushButton:pressed {{
        background-color: {BASE_COLOR};
    }}
    QPushButton:default {{
        background-color: {ACCENT_ORANGE};
        color: {TEXT_COLOR};
        border-color: {ACCENT_ORANGE};
    }}
    QPushButton:default:hover {{
        background-color: {ACCENT_HOVER};
    }}
    QPushButton:disabled {{
        background-color: {BUTTON_COLOR};
        color: {DISABLED_TEXT};
        border-color: {BORDER_COLOR};
    }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 3px;
        padding: 4px 6px;
        selection-background-color: {HIGHLIGHT};
        selection-color: {TEXT_COLOR};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 2px solid {ACCENT_ORANGE};
        padding: 3px 5px;
    }}

    QComboBox, QDateEdit {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 3px;
        padding: 3px 6px;
        min-height: 20px;
    }}
    QComboBox:focus, QDateEdit:focus {{
        border: 2px solid {ACCENT_ORANGE};
        padding: 2px 5px;
    }}
    QComboBox::drop-down, QDateEdit::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid {BORDER_COLOR};
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BASE_COLOR};
        selection-background-color: {HIGHLIGHT};
        selection-color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}

    QLabel {{
        color: {TEXT_COLOR};
    }}

    QGroupBox {{
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
        color: {TEXT_COLOR};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0px 4px;
        color: {TEXT_COLOR};
    }}

    QTableView {{
        background-color: {BASE_COLOR};
        alternate-background-color: {ALT_BASE_COLOR};
        gridline-color: {BORDER_COLOR};
        color: {TEXT_COLOR};
        selection-background-color: {HIGHLIGHT};
        selection-color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QTableView::item:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QHeaderView::section {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        padding: 6px;
        border: none;
        border-right: 1px solid {BORDER_COLOR};
        border-bottom: 2px solid {BORDER_COLOR};
        font-weight: bold;
    }}
    QHeaderView::section:hover {{
        background-color: {ALT_BASE_COLOR};
    }}

    QScrollBar:vertical {{
        background-color: {BASE_COLOR};
        width: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BUTTON_COLOR};
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: {BASE_COLOR};
        height: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {BUTTON_COLOR};
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    QTabWidget::pane {{
        border: 1px solid {BORDER_COLOR};
        background-color: {WINDOW_COLOR};
    }}
    QTabBar::tab {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        padding: 8px 16px;
        border: 1px solid {BORDER_COLOR};
        border-bottom: none;
    }}
    QTabBar::tab:selected {{
        background-color: {WINDOW_COLOR};
        border-bottom: 2px solid {ACCENT_ORANGE};
    }}
    QTabBar::tab:hover {{
        background-color: {ALT_BASE_COLOR};
    }}

    QMenuBar {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border-bottom: 1px solid {BORDER_COLOR};
    }}
    QMenuBar::item {{
        background-color: transparent;
        padding: 4px 8px;
    }}
    QMenuBar::item:selected {{
        background-color: {ALT_BASE_COLOR};
    }}
    QMenu {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QMenu::item:selected {{
        background-color: {HIGHLIGHT};
    }}

    QToolTip {{
        background-color: {TOOLTIP_BASE};
        color: {TOOLTIP_TEXT};
        border: 1px solid {BORDER_COLOR};
        padding: 4px;
    }}
    """
    app.setStyleSheet(qss)
