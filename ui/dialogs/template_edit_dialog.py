# ui/dialogs/template_edit_dialog.py - Add/edit calibration template

from datetime import date

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository
from ui.help_content import get_help_content, HelpDialog


class TemplateEditDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, template=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        # Store template - ensure it's a dict
        self.template = template if template and isinstance(template, dict) else {}
        is_edit_mode = bool(self.template and self.template.get("id"))
        self.setWindowTitle("Template" + (" - Edit" if is_edit_mode else " - New"))

        form = QtWidgets.QFormLayout(self)

        # Get template values with fallbacks
        template_name = str(self.template.get("name", "") or "")
        try:
            template_version = int(self.template.get("version") or 1)
        except (ValueError, TypeError):
            template_version = 1
        template_is_active = bool(int(self.template.get("is_active", 1)))
        template_notes = str(self.template.get("notes", "") or "")

        self.name_edit = QtWidgets.QLineEdit(template_name)
        self.version_spin = QtWidgets.QSpinBox()
        self.version_spin.setRange(1, 999)
        self.version_spin.setValue(template_version)
        self.active_check = QtWidgets.QCheckBox("Active")
        # default active=True for new template
        self.active_check.setChecked(template_is_active)

        # Create notes editor and set word wrap, then set text
        self.notes_edit = QtWidgets.QPlainTextEdit()
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.notes_edit.document().setDefaultTextOption(option)
        # Set the text after configuring the document
        if template_notes:
            self.notes_edit.setPlainText(template_notes)

        form.addRow("Name*", self.name_edit)
        form.addRow("Version", self.version_spin)
        form.addRow("", self.active_check)
        form.addRow("Notes", self.notes_edit)
        # M8: Status, change reason, effective date (when columns exist)
        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(["Draft", "Approved", "Archived"])
        status = (self.template.get("status") or "Draft").strip()
        idx = self.status_combo.findText(status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        form.addRow("Status", self.status_combo)
        self.change_reason_edit = QtWidgets.QLineEdit(self.template.get("change_reason") or "")
        self.change_reason_edit.setPlaceholderText("Required when creating new revision")
        form.addRow("Change reason (for new revision)", self.change_reason_edit)
        self.effective_date_edit = QtWidgets.QLineEdit(self.template.get("effective_date") or "")
        self.effective_date_edit.setPlaceholderText("YYYY-MM-DD (optional)")
        form.addRow("Effective date", self.effective_date_edit)
        self._update_template_lock_state()

        # Authorized performers (M7): who can perform calibrations with this template
        form.addRow(QtWidgets.QLabel("<b>Authorized performers</b>"))
        select_active_btn = QtWidgets.QPushButton("Select all active")
        select_active_btn.setToolTip("Select only active personnel (reduces form filling for new templates)")
        form.addRow("", select_active_btn)
        self.authorized_list = QtWidgets.QListWidget()
        try:
            all_people = self.repo.list_personnel(active_only=False)
        except Exception:
            all_people = []
        self._personnel = all_people
        active_ids = {p["id"] for p in all_people if p.get("active", True)}
        try:
            auth_ids = self.repo.get_template_authorized_person_ids(self.template["id"]) if self.template.get("id") else []
        except Exception:
            auth_ids = []
        # New template: default to all active personnel so user doesn't have to fill form
        if not self.template.get("id") and not auth_ids and active_ids:
            auth_ids = list(active_ids)
        for p in all_people:
            item = QtWidgets.QListWidgetItem(p.get("name", "") + (f" ({p.get('role', '')})" if p.get("role") else ""))
            item.setData(QtCore.Qt.UserRole, p["id"])
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if p["id"] in auth_ids else QtCore.Qt.Unchecked)
            self.authorized_list.addItem(item)
        select_active_btn.clicked.connect(lambda: self._authorized_select_active(active_ids))
        form.addRow("Personnel who may perform this procedure:", self.authorized_list)
        self.status_combo.currentIndexChanged.connect(self._update_template_lock_state)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)

        # Ensure dialog is properly sized and visible
        self.setMinimumSize(400, 380)
        self.resize(500, 480)

        # Explicitly ensure values are set (in case of any initialization issues)
        if self.template:
            self._load_template_data()

    def _load_template_data(self):
        """Explicitly load template data into widgets."""
        if not self.template:
            return

        # Set name - try multiple possible key names
        name = self.template.get("name") or self.template.get("Name") or ""
        if name:
            self.name_edit.setText(str(name))
            self.name_edit.repaint()

        # Set version - handle both int and string
        version = self.template.get("version") or self.template.get("Version") or 1
        try:
            if isinstance(version, str):
                version = int(version)
            else:
                version = int(version)
            self.version_spin.setValue(version)
            self.version_spin.repaint()
        except (ValueError, TypeError):
            self.version_spin.setValue(1)

        # Set active status - handle both int and bool
        is_active = self.template.get("is_active") or self.template.get("IsActive")
        if is_active is None:
            is_active = 1  # Default to active
        is_active = bool(int(is_active)) if isinstance(is_active, (int, str)) else bool(is_active)
        self.active_check.setChecked(is_active)
        self.active_check.repaint()

        # Set notes
        notes = self.template.get("notes") or self.template.get("Notes") or ""
        if notes:
            self.notes_edit.setPlainText(str(notes))
            self.notes_edit.repaint()

    def showEvent(self, event):
        """Override showEvent to ensure dialog is properly displayed."""
        super().showEvent(event)
        # Force layout update and ensure widgets are visible
        self.adjustSize()
        self.updateGeometry()
        # Ensure all widgets are shown
        for widget in self.findChildren(QtWidgets.QWidget):
            widget.show()
        # Reload template data after dialog is shown to ensure values are displayed
        if self.template:
            QtCore.QTimer.singleShot(0, self._load_template_data)

    def _show_help(self):
        title, content = get_help_content("TemplateEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _on_ok_clicked(self):
        """Validate and accept only if all required fields are filled."""
        if self.get_data() is not None:
            self.accept()

    def _authorized_select_active(self, active_ids):
        for i in range(self.authorized_list.count()):
            item = self.authorized_list.item(i)
            item.setCheckState(QtCore.Qt.Checked if item.data(QtCore.Qt.UserRole) in active_ids else QtCore.Qt.Unchecked)

    def _update_template_lock_state(self):
        """M8: Lock version/notes when status is Approved; name stays editable so template is renameable."""
        status = self.status_combo.currentText() if hasattr(self, "status_combo") else "Draft"
        locked = status == "Approved"
        if hasattr(self, "name_edit"):
            self.name_edit.setReadOnly(False)
        if hasattr(self, "version_spin"):
            self.version_spin.setReadOnly(locked)
        if hasattr(self, "notes_edit"):
            self.notes_edit.setReadOnly(locked)
        if hasattr(self, "active_check"):
            self.active_check.setEnabled(not locked)

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Name is required.")
            return None
        new_version = self.version_spin.value()
        old_version = int(self.template.get("version") or 1) if self.template else 0
        change_reason = (self.change_reason_edit.text() or "").strip() if hasattr(self, "change_reason_edit") else ""
        effective_date = (self.effective_date_edit.text() or "").strip() if hasattr(self, "effective_date_edit") else ""
        if new_version > old_version and not change_reason:
            QtWidgets.QMessageBox.warning(
                self, "Change reason required",
                "You increased the version. Please enter a change reason (e.g. 'Updated tolerances').",
            )
            return None
        if new_version > old_version and not effective_date:
            effective_date = date.today().isoformat()
        return {
            "name": name,
            "version": new_version,
            "is_active": self.active_check.isChecked(),
            "notes": self.notes_edit.toPlainText().strip(),
            "status": self.status_combo.currentText() if hasattr(self, "status_combo") else "Draft",
            "change_reason": change_reason or None,
            "effective_date": effective_date or None,
        }

    def get_authorized_person_ids(self):
        """Return list of checked personnel IDs (authorized to perform this template)."""
        ids = []
        for i in range(self.authorized_list.count()):
            item = self.authorized_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                pid = item.data(QtCore.Qt.UserRole)
                if pid is not None:
                    ids.append(pid)
        return ids
