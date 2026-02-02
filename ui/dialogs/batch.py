# ui/dialogs/batch.py

from datetime import date

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository


class BatchUpdateDialog(QtWidgets.QDialog):
    """Dialog to batch-update status or next due date for selected instruments."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch update instruments")
        self.count = count
        layout = QtWidgets.QVBoxLayout(self)

        summary = QtWidgets.QLabel(f"This will update {count} instrument(s). Click OK to confirm.")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        status_group = QtWidgets.QGroupBox("Update status")
        status_layout = QtWidgets.QVBoxLayout(status_group)
        self.radio_status = QtWidgets.QRadioButton("Update status")
        self.radio_status.setChecked(True)
        status_layout.addWidget(self.radio_status)
        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(["ACTIVE", "RETIRED", "OUT_FOR_CAL"])
        status_layout.addWidget(self.status_combo)
        layout.addWidget(status_group)

        date_group = QtWidgets.QGroupBox("Update next due date")
        date_layout = QtWidgets.QVBoxLayout(date_group)
        self.radio_date = QtWidgets.QRadioButton("Update next due date")
        date_layout.addWidget(self.radio_date)
        self.date_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QtCore.QDate.currentDate().addYears(1))
        date_layout.addWidget(self.date_edit)
        layout.addWidget(date_group)

        self.reason_edit = QtWidgets.QPlainTextEdit()
        self.reason_edit.setPlaceholderText("Reason for change (optional, for audit log)")
        self.reason_edit.setMaximumHeight(60)
        layout.addWidget(QtWidgets.QLabel("Reason (optional):"))
        layout.addWidget(self.reason_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_update(self):
        """Return (updates_dict, reason) or (None, None) if cancelled."""
        reason = self.reason_edit.toPlainText().strip() or None
        if self.radio_status.isChecked():
            return {"status": self.status_combo.currentText()}, reason
        return {"next_due_date": self.date_edit.date().toString("yyyy-MM-dd")}, reason


class BatchAssignInstrumentTypeDialog(QtWidgets.QDialog):
    """Dialog to assign the same instrument type to multiple selected instruments."""

    def __init__(self, repo: CalibrationRepository, count: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Batch assign instrument type")
        layout = QtWidgets.QVBoxLayout(self)

        summary = QtWidgets.QLabel(f"This will update {count} instrument(s). Click OK to confirm.")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addWidget(QtWidgets.QLabel("Instrument type:"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("(none)", None)
        for t in repo.list_instrument_types():
            self.type_combo.addItem(t["name"], t["id"])
        self.type_combo.setMinimumWidth(280)
        layout.addWidget(self.type_combo)

        self.reason_edit = QtWidgets.QPlainTextEdit()
        self.reason_edit.setPlaceholderText("Reason for change (optional, for audit log)")
        self.reason_edit.setMaximumHeight(60)
        layout.addWidget(QtWidgets.QLabel("Reason (optional):"))
        layout.addWidget(self.reason_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_result(self):
        """Return (instrument_type_id, reason) or (None, None) if cancelled."""
        type_id = self.type_combo.currentData()
        reason = self.reason_edit.toPlainText().strip() or None
        return type_id, reason


class CalDateDialog(QtWidgets.QDialog):
    """Dialog to choose a new 'last calibration date'."""

    def __init__(self, parent=None, initial_date=None):
        super().__init__(parent)
        self.setWindowTitle("Set last calibration date")

        layout = QtWidgets.QVBoxLayout(self)

        self.date_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        if initial_date is None:
            self.date_edit.setDate(QtCore.QDate.currentDate())
        else:
            self.date_edit.setDate(initial_date)

        layout.addWidget(QtWidgets.QLabel("Select last calibration date:"))
        layout.addWidget(self.date_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_date(self):
        """Return a Python date object."""
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())
