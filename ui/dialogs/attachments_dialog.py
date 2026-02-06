# ui/dialogs/attachments_dialog.py - Instrument attachments dialog

import tempfile
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository
from services import attachment_service
from ui.help_content import get_help_content, HelpDialog


class AttachmentsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id
        self.setWindowTitle("Attachments")

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Filename", "Path", "Uploaded"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_open = QtWidgets.QPushButton("Open")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.btn_add.clicked.connect(self._add_attachment)
        self.btn_open.clicked.connect(self._open_attachment)
        self.btn_delete.clicked.connect(self._delete_attachment)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self._load_attachments()

    def _show_help(self):
        title, content = get_help_content("AttachmentsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load_attachments(self):
        atts = self.repo.list_attachments(self.instrument_id)
        self.table.setRowCount(len(atts))
        for row, a in enumerate(atts):
            item_name = QtWidgets.QTableWidgetItem(a["filename"])
            item_path = QtWidgets.QTableWidgetItem(a["file_path"])
            item_upload = QtWidgets.QTableWidgetItem(a["uploaded_at"])
            item_name.setData(QtCore.Qt.UserRole, a["id"])
            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_path)
            self.table.setItem(row, 2, item_upload)

    def _add_attachment(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select file"
        )
        if not path:
            return
        try:
            attachment_service.add_attachment(self.repo, self.instrument_id, path)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error adding attachment", str(e)
            )

    def _open_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return

        item_name = self.table.item(row, 0)
        if not item_name:
            return

        att_id = item_name.data(QtCore.Qt.UserRole)
        if not att_id:
            return

        att = self.repo.get_attachment(att_id)
        if not att:
            return

        file_data = att.get("file_data")
        filename = att.get("filename") or "attachment.bin"
        stored_path = att.get("file_path")

        if file_data:
            temp_dir = Path(tempfile.gettempdir()) / "cal_tracker_attachments"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / filename
            try:
                with temp_path.open("wb") as f:
                    f.write(file_data)
                QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl.fromLocalFile(str(temp_path))
                )
                return
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error opening attachment", str(e)
                )
                return

        if stored_path:
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(stored_path)
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Attachment missing",
                "No stored file data or path available for this attachment.",
            )

    def _delete_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return

        item_name = self.table.item(row, 0)
        if not item_name:
            return

        att_id = item_name.data(QtCore.Qt.UserRole)
        if not att_id:
            return

        fname = item_name.text() or "this file"
        resp = QtWidgets.QMessageBox.question(
            self,
            "Delete attachment",
            f"Delete attachment '{fname}'?",
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return

        try:
            attachment_service.delete_attachment(self.repo, att_id)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error deleting attachment", str(e)
            )
