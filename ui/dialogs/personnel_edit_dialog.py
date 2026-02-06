# ui/dialogs/personnel_edit_dialog.py - Add/edit personnel dialog

from PyQt5 import QtWidgets

from database import CalibrationRepository


class PersonnelEditDialog(QtWidgets.QDialog):
    """Add or edit a personnel record (name, role, qualifications, review expiry)."""

    def __init__(self, repo: CalibrationRepository, person=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.person = person if person and isinstance(person, dict) else {}
        is_edit = bool(self.person and self.person.get("id"))
        self.setWindowTitle("Personnel" + (" - Edit" if is_edit else " - New"))
        form = QtWidgets.QFormLayout(self)
        self.name_edit = QtWidgets.QLineEdit(self.person.get("name", ""))
        self.role_edit = QtWidgets.QLineEdit(self.person.get("role", ""))
        self.qualifications_edit = QtWidgets.QPlainTextEdit()
        self.qualifications_edit.setPlainText(self.person.get("qualifications", "") or "")
        self.review_expiry_edit = QtWidgets.QLineEdit(self.person.get("review_expiry", "") or "")
        self.review_expiry_edit.setPlaceholderText("YYYY-MM-DD (optional)")
        self.active_check = QtWidgets.QCheckBox("Active")
        self.active_check.setChecked(bool(int(self.person.get("active", 1))))
        form.addRow("Name*", self.name_edit)
        form.addRow("Role", self.role_edit)
        form.addRow("Qualifications", self.qualifications_edit)
        form.addRow("Review/expiry date", self.review_expiry_edit)
        form.addRow("", self.active_check)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        form.addRow(btn_box)

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Name is required.")
            return None
        return {
            "name": name,
            "role": self.role_edit.text().strip(),
            "qualifications": self.qualifications_edit.toPlainText().strip(),
            "review_expiry": self.review_expiry_edit.text().strip() or None,
            "active": self.active_check.isChecked(),
        }
