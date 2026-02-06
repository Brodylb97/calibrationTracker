# ui/dialogs/destinations_dialog.py - Manage destinations list

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository
from services import destination_service
from ui.help_content import get_help_content, HelpDialog
from ui.dialogs.destination_edit_dialog import DestinationEditDialog


class DestinationsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Destinations")

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Contact", "Email", "Phone", "Address"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        layout.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self._load_destinations()

    def _show_help(self):
        title, content = get_help_content("DestinationsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load_destinations(self):
        dests = self.repo.list_destinations_full()
        self.table.setRowCount(len(dests))
        for row, d in enumerate(dests):
            item_name = QtWidgets.QTableWidgetItem(d["name"])
            item_name.setData(QtCore.Qt.UserRole, d["id"])
            item_contact = QtWidgets.QTableWidgetItem(d.get("contact") or "")
            item_email = QtWidgets.QTableWidgetItem(d.get("email") or "")
            item_phone = QtWidgets.QTableWidgetItem(d.get("phone") or "")
            item_addr = QtWidgets.QTableWidgetItem(d.get("address") or "")

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_contact)
            self.table.setItem(row, 2, item_email)
            self.table.setItem(row, 3, item_phone)
            self.table.setItem(row, 4, item_addr)

    def _selected_row(self):
        idx = self.table.currentRow()
        return idx if idx >= 0 else None

    def _selected_dest_id(self):
        row = self._selected_row()
        if row is None:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        dlg = DestinationEditDialog(parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                destination_service.add_destination(self.repo, **data)
                self._load_destinations()

    def on_edit(self):
        row = self._selected_row()
        if row is None:
            return
        dest_id = self._selected_dest_id()
        if dest_id is None:
            return

        dest = {
            "id": dest_id,
            "name": self.table.item(row, 0).text(),
            "contact": self.table.item(row, 1).text(),
            "email": self.table.item(row, 2).text(),
            "phone": self.table.item(row, 3).text(),
            "address": self.table.item(row, 4).text(),
        }

        dlg = DestinationEditDialog(dest=dest, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                destination_service.update_destination(self.repo, dest_id, data)
                self._load_destinations()

    def on_delete(self):
        dest_id = self._selected_dest_id()
        row = self._selected_row()
        if dest_id is None or row is None:
            return
        name = self.table.item(row, 0).text()
        resp = QtWidgets.QMessageBox.question(
            self,
            "Delete destination",
            f"Delete destination '{name}'?",
        )
        if resp == QtWidgets.QMessageBox.Yes:
            try:
                destination_service.delete_destination(self.repo, dest_id)
                self._load_destinations()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
