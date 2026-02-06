# ui/dialogs/personnel_dialog.py - Manage personnel list

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository
from services import personnel_service
from ui.dialogs.personnel_edit_dialog import PersonnelEditDialog


class PersonnelDialog(QtWidgets.QDialog):
    """Manage personnel (technicians authorized to perform calibrations)."""

    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Personnel")
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Role", "Qualifications", "Review expiry"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_add.clicked.connect(self.on_add)
        btn_layout.addWidget(self.btn_add)
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_edit.clicked.connect(self.on_edit)
        btn_layout.addWidget(self.btn_edit)
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_delete.clicked.connect(self.on_delete)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)
        self.resize(800, 500)
        self._load()

    def _load(self):
        people = self.repo.list_personnel(active_only=False)
        self.table.setRowCount(len(people))
        for row, p in enumerate(people):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(p.get("name", "")))
            self.table.item(row, 0).setData(QtCore.Qt.UserRole, p["id"])
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(p.get("role", "") or ""))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem((p.get("qualifications") or "")[:80]))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(p.get("review_expiry") or ""))

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(QtCore.Qt.UserRole) if item else None

    def on_add(self):
        dlg = PersonnelEditDialog(self.repo, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                personnel_service.add_personnel(
                    self.repo,
                    data["name"], data["role"], data["qualifications"],
                    data.get("review_expiry"), data.get("active", True),
                )
                self._load()

    def on_edit(self):
        pid = self._selected_id()
        if not pid:
            return
        person = self.repo.get_personnel(pid)
        if not person:
            return
        dlg = PersonnelEditDialog(self.repo, person, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                personnel_service.update_personnel(
                    self.repo,
                    pid, data["name"], data["role"], data["qualifications"],
                    data.get("review_expiry"), data.get("active", True),
                )
                self._load()

    def on_delete(self):
        pid = self._selected_id()
        if not pid:
            return
        if QtWidgets.QMessageBox.question(
            self, "Delete", "Remove this person from the list?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        ) != QtWidgets.QMessageBox.Yes:
            return
        try:
            personnel_service.delete_personnel(self.repo, pid)
            self._load()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
