# ui/theme/editor.py - Theme customization dialog

import copy
from PyQt5 import QtCore, QtWidgets

from ui.theme.core import (
    BUILT_IN_THEME_NAMES,
    REQUIRED_THEME_KEYS,
    get_all_themes,
    get_saved_theme,
    set_saved_theme,
    validate_theme_colors,
    apply_theme_from_colors,
    apply_global_style,
    open_color_picker,
    validate_hex_input,
)
from ui.theme.storage import add_custom_theme, delete_custom_theme
from ui.theme.preview import ThemePreviewWidget

_COLOR_LABELS = {
    "WINDOW_COLOR": "Window background",
    "BASE_COLOR": "Base color",
    "ALT_BASE_COLOR": "Alternate base",
    "TEXT_COLOR": "Text color",
    "DISABLED_TEXT": "Disabled text",
    "BUTTON_COLOR": "Button color",
    "BORDER_COLOR": "Border color",
    "ACCENT_ORANGE": "Accent orange",
    "HIGHLIGHT": "Highlight",
    "TOOLTIP_BASE": "Tooltip base",
    "TOOLTIP_TEXT": "Tooltip text",
}


class ThemeEditorDialog(QtWidgets.QDialog):
    """Dialog to create, edit, and preview custom themes."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Theme Editor")
        self.setMinimumSize(750, 520)
        self.resize(830, 580)

        self._snapshot_theme: str = get_saved_theme()
        self._working_colors: dict = copy.deepcopy(get_all_themes().get(self._snapshot_theme, {}))
        self._selected_theme_name: str | None = self._snapshot_theme
        self._editing_custom: bool = False
        self._new_theme_name: str | None = None
        self._hex_edits: dict[str, QtWidgets.QLineEdit] = {}
        self._picker_buttons: dict[str, QtWidgets.QPushButton] = {}

        outer = QtWidgets.QVBoxLayout(self)
        outer.setSpacing(12)
        content = QtWidgets.QWidget()
        main = QtWidgets.QHBoxLayout(content)
        main.setSpacing(12)

        # Left: theme list
        left = QtWidgets.QVBoxLayout()
        left_label = QtWidgets.QLabel("Themes")
        left_label.setStyleSheet("font-weight: bold;")
        left.addWidget(left_label)
        self._list = QtWidgets.QListWidget()
        self._list.setMinimumWidth(180)
        self._list.itemSelectionChanged.connect(self._on_list_selection_changed)
        left.addWidget(self._list)
        btn_row = QtWidgets.QHBoxLayout()
        self._btn_create = QtWidgets.QPushButton("Create new from...")
        self._btn_create.clicked.connect(self._on_create_new)
        self._btn_delete = QtWidgets.QPushButton("Delete")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)
        btn_row.addWidget(self._btn_create)
        btn_row.addWidget(self._btn_delete)
        left.addLayout(btn_row)
        main.addLayout(left)

        # Right: color rows + preview
        right = QtWidgets.QVBoxLayout()
        right_label = QtWidgets.QLabel("Colors")
        right_label.setStyleSheet("font-weight: bold;")
        right.addWidget(right_label)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(scroll_widget)
        form.setSpacing(4)
        for key in REQUIRED_THEME_KEYS:
            row = QtWidgets.QHBoxLayout()
            hex_edit = QtWidgets.QLineEdit()
            hex_edit.setMinimumWidth(90)
            hex_edit.setPlaceholderText("#RRGGBB")
            hex_edit.textChanged.connect(lambda t, k=key: self._on_hex_changed(k))
            picker_btn = QtWidgets.QPushButton()
            picker_btn.setFixedSize(28, 24)
            picker_btn.setToolTip("Choose color")
            picker_btn.clicked.connect(lambda checked, k=key: self._on_picker_clicked(k))
            row.addWidget(hex_edit)
            row.addWidget(picker_btn)
            form.addRow(_COLOR_LABELS.get(key, key), row)
            self._hex_edits[key] = hex_edit
            self._picker_buttons[key] = picker_btn
        scroll.setWidget(scroll_widget)
        right.addWidget(scroll)

        preview_label = QtWidgets.QLabel("Live preview")
        preview_label.setStyleSheet("font-weight: bold;")
        right.addWidget(preview_label)
        self._preview = ThemePreviewWidget()
        self._preview.setMinimumHeight(140)
        right.addWidget(self._preview)
        main.addLayout(right, 1)

        outer.addWidget(content)

        # Buttons at bottom
        btn_box = QtWidgets.QDialogButtonBox()
        self._btn_apply = btn_box.addButton("Apply", QtWidgets.QDialogButtonBox.ActionRole)
        self._btn_save = btn_box.addButton("Save", QtWidgets.QDialogButtonBox.ActionRole)
        self._btn_revert = btn_box.addButton("Revert", QtWidgets.QDialogButtonBox.ActionRole)
        btn_box.addButton(QtWidgets.QDialogButtonBox.Cancel)
        btn_box.addButton(QtWidgets.QDialogButtonBox.Ok)
        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_save.clicked.connect(self._on_save)
        self._btn_revert.clicked.connect(self._on_revert)
        btn_box.rejected.connect(self._on_cancel)
        btn_box.accepted.connect(self._on_ok)
        outer.addWidget(btn_box)

        self._populate_list()
        self._sync_edits_from_working()
        self._update_preview()
        self._select_list_item(self._snapshot_theme)

    def _populate_list(self) -> None:
        self._list.clear()
        all_themes = get_all_themes()
        current = get_saved_theme()
        for name in sorted(all_themes.keys(), key=lambda n: (n not in BUILT_IN_THEME_NAMES, n.lower())):
            item = QtWidgets.QListWidgetItem(name)
            if name in BUILT_IN_THEME_NAMES:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self._list.addItem(item)
            if name == current:
                item.setText(name + " ✓")

    def _select_list_item(self, name: str | None) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            raw = item.text().replace(" ✓", "")
            if raw == (name or ""):
                self._list.setCurrentItem(item)
                return

    def _on_list_selection_changed(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        name = item.text().replace(" ✓", "")
        all_themes = get_all_themes()
        if name not in all_themes:
            return
        self._selected_theme_name = name
        self._editing_custom = name not in BUILT_IN_THEME_NAMES
        self._btn_delete.setEnabled(self._editing_custom)
        self._working_colors = copy.deepcopy(all_themes[name])
        self._new_theme_name = None
        self._sync_edits_from_working()
        self._update_preview()

    def _sync_edits_from_working(self) -> None:
        for key in REQUIRED_THEME_KEYS:
            val = self._working_colors.get(key, "")
            edit = self._hex_edits[key]
            edit.blockSignals(True)
            edit.setText(val)
            edit.blockSignals(False)
            self._update_hex_edit_style(edit, val)
            btn = self._picker_buttons[key]
            n = self._working_colors.get(key)
            if n:
                btn.setStyleSheet(f"background-color: {n}; border: 1px solid #666;")
            else:
                btn.setStyleSheet("")

    def _on_hex_changed(self, key: str) -> None:
        edit = self._hex_edits[key]
        text = edit.text().strip()
        valid, result = validate_hex_input(text)
        self._update_hex_edit_style(edit, text, valid)
        if valid:
            self._working_colors[key] = result
            self._picker_buttons[key].setStyleSheet(f"background-color: {result}; border: 1px solid #666;")
            self._update_preview()
        elif text:
            edit.setToolTip(result)

    def _update_hex_edit_style(self, edit: QtWidgets.QLineEdit, text: str, valid: bool | None = None) -> None:
        if valid is None:
            valid, _ = validate_hex_input(text)
        if valid or not text:
            edit.setStyleSheet("")
            edit.setToolTip("")
        else:
            edit.setStyleSheet("border: 2px solid #c00;")
            edit.setToolTip("Invalid hex color")

    def _on_picker_clicked(self, key: str) -> None:
        current = self._working_colors.get(key, "#FFFFFF")
        chosen = open_color_picker(current, self)
        if chosen:
            self._working_colors[key] = chosen
            edit = self._hex_edits[key]
            edit.blockSignals(True)
            edit.setText(chosen)
            edit.blockSignals(False)
            self._update_hex_edit_style(edit, chosen, True)
            self._picker_buttons[key].setStyleSheet(f"background-color: {chosen}; border: 1px solid #666;")
            self._update_preview()

    def _update_preview(self) -> None:
        self._preview.set_theme_colors(self._working_colors)

    def _on_create_new(self) -> None:
        base_name = self._selected_theme_name or "Custom"
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Create new theme",
            "Name for the new theme (based on " + base_name + "):",
            text=base_name + " (copy)",
        )
        if not ok or not name or not name.strip():
            return
        name = name.strip()
        if name in BUILT_IN_THEME_NAMES:
            QtWidgets.QMessageBox.warning(
                self, "Invalid name",
                f"'{name}' is a built-in theme. Choose a different name.",
            )
            return
        self._working_colors = copy.deepcopy(
            get_all_themes().get(base_name, get_all_themes().get("Fusion", {}))
        )
        self._selected_theme_name = None
        self._editing_custom = True
        self._new_theme_name = name
        self._sync_edits_from_working()
        self._update_preview()
        self._list.clearSelection()
        self._btn_delete.setEnabled(False)

    def _on_delete(self) -> None:
        name = self._selected_theme_name
        if not name or name in BUILT_IN_THEME_NAMES:
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Delete theme",
            f"Delete theme '{name}'? This cannot be undone.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        if delete_custom_theme(name):
            self._populate_list()
            if get_saved_theme() == name:
                set_saved_theme("Fusion")
                app = QtWidgets.QApplication.instance()
                if app:
                    apply_global_style(app, "Fusion")
            self._selected_theme_name = "Fusion"
            self._working_colors = copy.deepcopy(get_all_themes().get("Fusion", {}))
            self._sync_edits_from_working()
            self._update_preview()
            self._select_list_item("Fusion")

    def _on_apply(self) -> None:
        valid, err = validate_theme_colors(self._working_colors)
        if not valid:
            QtWidgets.QMessageBox.warning(self, "Invalid theme", err)
            return
        app = QtWidgets.QApplication.instance()
        if app and apply_theme_from_colors(app, self._working_colors):
            pass  # Applied; user can Save to persist

    def _on_save(self) -> None:
        valid, err = validate_theme_colors(self._working_colors)
        if not valid:
            QtWidgets.QMessageBox.warning(self, "Invalid theme", err)
            return
        name = self._new_theme_name or self._selected_theme_name
        if not name or not name.strip():
            QtWidgets.QMessageBox.warning(
                self, "Save",
                "Select or create a theme to save.",
            )
            return
        name = name.strip()
        if name in BUILT_IN_THEME_NAMES:
            QtWidgets.QMessageBox.warning(
                self, "Save",
                "Cannot overwrite built-in themes.",
            )
            return
        if add_custom_theme(name, self._working_colors):
            set_saved_theme(name)
            app = QtWidgets.QApplication.instance()
            if app:
                apply_theme_from_colors(app, self._working_colors)
            self._new_theme_name = None
            self._selected_theme_name = name
            self._populate_list()
            self._select_list_item(name)
            QtWidgets.QMessageBox.information(self, "Theme saved", f"Theme '{name}' saved.")
        else:
            QtWidgets.QMessageBox.warning(self, "Save failed", "Could not save theme.")

    def _on_revert(self) -> None:
        name = self._new_theme_name or self._selected_theme_name
        if name:
            all_themes = get_all_themes()
            self._working_colors = copy.deepcopy(all_themes.get(name, self._working_colors))
        self._sync_edits_from_working()
        self._update_preview()

    def _on_cancel(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app:
            apply_global_style(app, self._snapshot_theme)
        self.reject()

    def _on_ok(self) -> None:
        self.accept()
