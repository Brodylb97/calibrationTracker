# ui/dialogs/instrument_info.py

from datetime import datetime, date

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository
from ui.help_content import get_help_content, HelpDialog
from ui.dialogs.audit_log import AuditLogDialog


class InstrumentInfoDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        inst = self.repo.get_instrument(instrument_id)
        if not inst:
            self.setWindowTitle("Instrument info")
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel("Instrument not found."))
            return

        tag = inst.get("tag_number", "")
        self.setWindowTitle(f"Instrument info - {tag}")

        layout = QtWidgets.QVBoxLayout(self)
        self.resize(500, 400)

        # Core fields
        location = inst.get("location", "") or ""
        cal_type = inst.get("calibration_type", "") or ""
        if cal_type == "SEND_OUT":
            cal_type_pretty = "Send out"
        elif cal_type == "PULL_IN":
            cal_type_pretty = "Pull in"
        else:
            cal_type_pretty = cal_type

        dest_name = self.repo.get_destination_name(inst.get("destination_id"))

        # Instrument type name
        inst_type_name = ""
        type_id = inst.get("instrument_type_id")
        if type_id:
            t = self.repo.get_instrument_type(type_id)
            if t:
                inst_type_name = t["name"]

        last_cal = inst.get("last_cal_date") or ""
        next_due = inst.get("next_due_date") or ""
        status = inst.get("status") or ""
        notes = inst.get("notes") or ""

        days_left_str = ""
        if next_due:
            try:
                d = datetime.strptime(next_due, "%Y-%m-%d").date()
                days_left = (d - date.today()).days
                if days_left < 0:
                    days_left_str = f"{days_left} days overdue"
                else:
                    days_left_str = f"{days_left} days remaining"
            except Exception:
                pass

        # Basic Info group
        basic_group = QtWidgets.QGroupBox("Basic Info")
        basic_form = QtWidgets.QFormLayout(basic_group)
        basic_form.addRow("ID:", QtWidgets.QLabel(tag))
        basic_form.addRow("Location:", QtWidgets.QLabel(location))
        basic_form.addRow("Calibration type:", QtWidgets.QLabel(cal_type_pretty))
        basic_form.addRow("Destination:", QtWidgets.QLabel(dest_name or ""))
        basic_form.addRow("Instrument type:", QtWidgets.QLabel(inst_type_name or "(none)"))
        layout.addWidget(basic_group)

        # Calibration Schedule group
        cal_group = QtWidgets.QGroupBox("Calibration Schedule")
        cal_form = QtWidgets.QFormLayout(cal_group)
        cal_form.addRow("Last cal:", QtWidgets.QLabel(last_cal))
        cal_form.addRow("Next due:", QtWidgets.QLabel(next_due))
        cal_form.addRow("Days left:", QtWidgets.QLabel(days_left_str))
        layout.addWidget(cal_group)

        # Status group
        status_group = QtWidgets.QGroupBox("Status")
        status_form = QtWidgets.QFormLayout(status_group)
        status_form.addRow("Status:", QtWidgets.QLabel(status))
        layout.addWidget(status_group)

        # Notes (read-only)
        if notes:
            layout.addWidget(QtWidgets.QLabel("Notes:"))
            notes_edit = QtWidgets.QPlainTextEdit()
            notes_edit.setPlainText(notes)
            notes_edit.setReadOnly(True)
            notes_edit.setMinimumHeight(80)
            option = QtGui.QTextOption()
            option.setWrapMode(QtGui.QTextOption.WordWrap)
            notes_edit.document().setDefaultTextOption(option)
            layout.addWidget(notes_edit)

        # Optional: attachments count
        try:
            atts = self.repo.list_attachments(instrument_id)
            layout.addWidget(QtWidgets.QLabel(f"Attachments: {len(atts)}"))
        except Exception:
            pass

        btn_history = QtWidgets.QPushButton("View audit log")
        btn_history.clicked.connect(self.on_history)
        layout.addWidget(btn_history)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

    def _show_help(self):
        title, content = get_help_content("InstrumentInfoDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def on_history(self):
        dlg = AuditLogDialog(self.repo, self.instrument_id, parent=self)
        dlg.exec_()
