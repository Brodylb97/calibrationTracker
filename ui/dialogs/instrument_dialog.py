# ui/dialogs/instrument_dialog.py - Instrument add/edit dialog

from datetime import datetime

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository
from ui.help_content import get_help_content, HelpDialog


class InstrumentDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument = instrument
        self.setWindowTitle("Instrument" + (" - Edit" if instrument else " - New"))

        form = QtWidgets.QFormLayout(self)
        self.resize(500, 500)

        # ID field
        self.id_edit = QtWidgets.QLineEdit()

        # Current location field
        self.location_edit = QtWidgets.QLineEdit()

        # Instrument type
        self.instrument_type_combo = QtWidgets.QComboBox()
        self.instrument_type_combo.addItem("", None)
        for t in self.repo.list_instrument_types():
            self.instrument_type_combo.addItem(t["name"], t["id"])

        # Calibration type (match DB CHECK constraint: 'SEND_OUT' / 'PULL_IN')
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["SEND_OUT", "PULL_IN"])

        # Destination
        self.dest_combo = QtWidgets.QComboBox()
        self.dest_combo.addItem("", None)
        for d in self.repo.list_destinations():
            self.dest_combo.addItem(d["name"], d["id"])

        # Last and next due dates
        self.last_cal_date = QtWidgets.QDateEdit(calendarPopup=True)
        self.last_cal_date.setDisplayFormat("yyyy-MM-dd")
        self.last_cal_date.setDate(QtCore.QDate.currentDate())

        self.next_due_date = QtWidgets.QDateEdit(calendarPopup=True)
        self.next_due_date.setDisplayFormat("yyyy-MM-dd")
        self.next_due_date.setDate(QtCore.QDate.currentDate())

        # Whenever last_cal_date changes, auto-set next_due_date = +1 year
        self.last_cal_date.dateChanged.connect(self._update_next_due_from_last)
        self._update_next_due_from_last()

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(["ACTIVE", "RETIRED", "OUT_FOR_CAL"])

        self.notes_edit = QtWidgets.QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Optional notes about this instrument")
        self.notes_edit.setMinimumHeight(100)
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.notes_edit.document().setDefaultTextOption(option)

        form.addRow("ID*", self.id_edit)
        self._id_error_label = QtWidgets.QLabel("ID is required")
        self._id_error_label.setStyleSheet("color: #d32f2f; font-size: 10px; margin-left: 4px;")
        self._id_error_label.hide()
        form.addRow("", self._id_error_label)
        form.addRow("Current location", self.location_edit)
        form.addRow("Instrument type", self.instrument_type_combo)
        self.type_combo.setToolTip("SEND_OUT: sent out for calibration; PULL_IN: calibration performed in-house")
        form.addRow("Calibration type", self.type_combo)
        form.addRow("Destination", self.dest_combo)
        form.addRow("Last cal date", self.last_cal_date)
        form.addRow("Next due date*", self.next_due_date)
        form.addRow("Status", self.status_combo)
        form.addRow("Notes", self.notes_edit)

        hint_label = QtWidgets.QLabel(
            "<small><i>Tip: Last calibration date automatically sets next due date to 1 year later</i></small>"
        )
        hint_label.setWordWrap(True)
        form.addRow("", hint_label)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)

        self.id_edit.textChanged.connect(self._validate_id_field)
        self.id_edit.editingFinished.connect(self._validate_id_field)

        if instrument:
            self._load_instrument()
        else:
            self.id_edit.setFocus()

    def _show_help(self):
        title, content = get_help_content("InstrumentDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _validate_id_field(self):
        text = self.id_edit.text().strip()
        is_valid = bool(text)
        if is_valid:
            self.id_edit.setStyleSheet("")
            self._id_error_label.hide()
        else:
            self.id_edit.setStyleSheet("border: 2px solid #d32f2f;")
            self._id_error_label.show()
        return is_valid

    def _on_ok_clicked(self):
        if self._validate_id_field():
            self.accept()
        else:
            self.id_edit.setFocus()

    def _update_next_due_from_last(self):
        qd = self.last_cal_date.date()
        next_qd = qd.addYears(1)
        self.next_due_date.setDate(next_qd)

    def _load_instrument(self):
        inst = self.instrument
        self.id_edit.setText(inst.get("tag_number", ""))
        self.location_edit.setText(inst.get("location", ""))

        inst_type_id = inst.get("instrument_type_id")
        if inst_type_id is not None:
            for i in range(self.instrument_type_combo.count()):
                if self.instrument_type_combo.itemData(i) == inst_type_id:
                    self.instrument_type_combo.setCurrentIndex(i)
                    break

        t = inst.get("calibration_type") or "SEND_OUT"
        idx = self.type_combo.findText(t)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        dest_id = inst.get("destination_id")
        if dest_id is not None:
            for i in range(self.dest_combo.count()):
                if self.dest_combo.itemData(i) == dest_id:
                    self.dest_combo.setCurrentIndex(i)
                    break

        def set_date(widget, value):
            if value:
                try:
                    d = datetime.strptime(value, "%Y-%m-%d").date()
                    widget.setDate(QtCore.QDate(d.year, d.month, d.day))
                except Exception:
                    pass

        set_date(self.last_cal_date, inst.get("last_cal_date"))
        set_date(self.next_due_date, inst.get("next_due_date"))

        st = inst.get("status", "ACTIVE")
        idx = self.status_combo.findText(st)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)

        self.notes_edit.setPlainText(inst.get("notes", ""))

    def get_data(self):
        if not self._validate_id_field():
            self.id_edit.setFocus()
            return None

        instrument_id = self.id_edit.text().strip()
        next_due_str = self.next_due_date.date().toString("yyyy-MM-dd")
        last_str = self.last_cal_date.date().toString("yyyy-MM-dd")

        data = {
            "tag_number": instrument_id,
            "serial_number": "",
            "description": "",
            "location": self.location_edit.text().strip(),
            "calibration_type": self.type_combo.currentText(),
            "destination_id": self.dest_combo.currentData(),
            "last_cal_date": last_str,
            "next_due_date": next_due_str,
            "frequency_months": 12,
            "status": self.status_combo.currentText(),
            "notes": self.notes_edit.toPlainText().strip(),
            "instrument_type_id": self.instrument_type_combo.currentData(),
        }
        if self.instrument:
            updated_at = self.instrument.get("updated_at") if hasattr(self.instrument, "get") else getattr(self.instrument, "updated_at", None)
            if updated_at:
                data["updated_at"] = updated_at
        return data
