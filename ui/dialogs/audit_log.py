# ui/dialogs/audit_log.py

from PyQt5 import QtWidgets

from database import CalibrationRepository
from ui.help_content import get_help_content, HelpDialog


class AuditLogDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        self.setWindowTitle("Change history")
        self.resize(800, 400)

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Action", "Field", "Old value", "New value", "Actor"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

        self._load()

    def _show_help(self):
        title, content = get_help_content("AuditLogDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load(self):
        rows = self.repo.get_audit_for_instrument(self.instrument_id)
        self.table.setRowCount(len(rows))
        for r_i, r in enumerate(rows):
            def mk(text):
                return QtWidgets.QTableWidgetItem(text or "")

            self.table.setItem(r_i, 0, mk(r.get("ts")))
            self.table.setItem(r_i, 1, mk(r.get("action")))
            self.table.setItem(r_i, 2, mk(r.get("field")))
            self.table.setItem(r_i, 3, mk(r.get("old_value")))
            self.table.setItem(r_i, 4, mk(r.get("new_value")))
            self.table.setItem(r_i, 5, mk(r.get("actor") or ""))
