# ui/theme/preview.py - Live theme preview widget

from PyQt5 import QtCore, QtWidgets

from ui.theme.core import _lighten_hex, normalize_hex


def _build_preview_qss(colors: dict) -> str:
    """Build minimal QSS for preview from colors dict. Uses default fallbacks if invalid."""
    def get(key: str, default: str = "#333333") -> str:
        v = colors.get(key)
        return v if v and normalize_hex(str(v)) else default

    W = get("WINDOW_COLOR")
    B = get("BASE_COLOR")
    A = get("ALT_BASE_COLOR")
    T = get("TEXT_COLOR")
    D = get("DISABLED_TEXT")
    BTN = get("BUTTON_COLOR")
    BD = get("BORDER_COLOR")
    ACC = get("ACCENT_ORANGE")
    ACC_H = _lighten_hex(ACC)
    H = get("HIGHLIGHT")
    return f"""
    QFrame#previewContainer {{
        background-color: {W};
        border: 1px solid {BD};
        border-radius: 4px;
    }}
    QLabel {{
        color: {T};
    }}
    QPushButton {{
        background-color: {BTN};
        color: {T};
        border: 1px solid {BD};
        border-radius: 4px;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        background-color: {A};
        border-color: {ACC};
    }}
    QPushButton:default {{
        background-color: {ACC};
        border-color: {ACC};
    }}
    QPushButton:default:hover {{
        background-color: {ACC_H};
    }}
    QLineEdit {{
        background-color: {B};
        color: {T};
        border: 1px solid {BD};
        border-radius: 3px;
        padding: 4px;
    }}
    QLineEdit:focus {{
        border: 2px solid {ACC};
    }}
    QTableWidget {{
        background-color: {B};
        alternate-background-color: {A};
        gridline-color: {BD};
        color: {T};
        selection-background-color: {H};
        selection-color: {T};
        border: 1px solid {BD};
    }}
    QHeaderView::section {{
        background-color: {BTN};
        color: {T};
        padding: 4px;
    }}
    """


class ThemePreviewWidget(QtWidgets.QFrame):
    """A small preview pane showing sample widgets with the given theme colors."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewContainer")
        self.setMinimumSize(200, 120)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._sample_widgets: list[QtWidgets.QWidget] = []

        # Sample row: label + line edit
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Sample:"))
        self._edit = QtWidgets.QLineEdit()
        self._edit.setPlaceholderText("Enter text...")
        self._edit.setMinimumWidth(120)
        row1.addWidget(self._edit)
        self._layout.addLayout(row1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        self._btn_normal = QtWidgets.QPushButton("Button")
        self._btn_default = QtWidgets.QPushButton("Default")
        self._btn_default.setDefault(True)
        btn_row.addWidget(self._btn_normal)
        btn_row.addWidget(self._btn_default)
        self._layout.addLayout(btn_row)

        # Tiny table
        self._table = QtWidgets.QTableWidget(2, 2)
        self._table.setHorizontalHeaderLabels(["Col A", "Col B"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setMaximumHeight(60)
        for r in range(2):
            for c in range(2):
                self._table.setItem(r, c, QtWidgets.QTableWidgetItem(f"Cell {r},{c}"))
        self._table.selectRow(0)
        self._layout.addWidget(self._table)

        self._sample_widgets = [self._edit, self._btn_normal, self._btn_default, self._table]

    def set_theme_colors(self, colors: dict) -> None:
        """Update preview with the given colors. Accepts partial dict; missing keys use fallbacks."""
        if not colors:
            return
        qss = _build_preview_qss(colors)
        self.setStyleSheet(qss)
