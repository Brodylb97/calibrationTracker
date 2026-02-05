# ui/dialogs/all_dialogs.py - All dialog classes (extracted from ui_main)
# Some dialogs split into separate modules; re-exported here for backward compatibility.

from datetime import datetime, date
import logging
import os
import sqlite3
import sys
import tempfile
import csv
from pathlib import Path

logger = logging.getLogger(__name__)

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository, StaleDataError
from services import calibration_service
from ui.help_content import get_help_content, HelpDialog

# Re-export from split modules
from ui.dialogs.audit_log import AuditLogDialog

# Standard minimum width for form field inputs (template maker, cal history)
STANDARD_FIELD_WIDTH = 280
from ui.dialogs.instrument_info import InstrumentInfoDialog
from ui.dialogs.batch import BatchUpdateDialog, BatchAssignInstrumentTypeDialog, CalDateDialog


def _parse_float_optional(s: str):
    """Return float(s) or None if s is blank or invalid."""
    if not (s or "").strip():
        return None
    try:
        return float(str(s).strip())
    except ValueError:
        return None


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
        # Set word wrap to only break at word boundaries
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

        # Add helpful hints
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
            # Set focus to first field for new instruments
            self.id_edit.setFocus()
    
    def _show_help(self):
        title, content = get_help_content("InstrumentDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _validate_id_field(self):
        """Validate ID field and show inline error if invalid."""
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
        """Validate and accept only if ID is valid."""
        if self._validate_id_field():
            self.accept()
        else:
            self.id_edit.setFocus()

    def _update_next_due_from_last(self):
        """Set next_due_date to exactly 1 year after last_cal_date."""
        qd = self.last_cal_date.date()
        next_qd = qd.addYears(1)
        self.next_due_date.setDate(next_qd)

    def _load_instrument(self):
        inst = self.instrument
        self.id_edit.setText(inst.get("tag_number", ""))
        self.location_edit.setText(inst.get("location", ""))

        # Instrument type
        inst_type_id = inst.get("instrument_type_id")
        if inst_type_id is not None:
            for i in range(self.instrument_type_combo.count()):
                if self.instrument_type_combo.itemData(i) == inst_type_id:
                    self.instrument_type_combo.setCurrentIndex(i)
                    break

        # Calibration type
        t = inst.get("calibration_type") or "SEND_OUT"
        idx = self.type_combo.findText(t)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        # Destination
        dest_id = inst.get("destination_id")
        if dest_id is not None:
            for i in range(self.dest_combo.count()):
                if self.dest_combo.itemData(i) == dest_id:
                    self.dest_combo.setCurrentIndex(i)
                    break

        # Dates
        def set_date(widget, value):
            if value:
                try:
                    d = datetime.strptime(value, "%Y-%m-%d").date()
                    widget.setDate(QtCore.QDate(d.year, d.month, d.day))
                except Exception:
                    pass

        set_date(self.last_cal_date, inst.get("last_cal_date"))
        set_date(self.next_due_date, inst.get("next_due_date"))

        # Status
        st = inst.get("status", "ACTIVE")
        idx = self.status_combo.findText(st)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)

        # Notes
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
            "serial_number": "",  # not used
            "description": "",    # not used
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


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog with improved layout and tooltips."""
    """
    Simple settings: reminder window only (LAN broadcast doesn't need SMTP)
    """
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Settings")

        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # Reminders tab
        rem_widget = QtWidgets.QWidget()
        rem_form = QtWidgets.QFormLayout(rem_widget)

        self.reminder_days_spin = QtWidgets.QSpinBox()
        self.reminder_days_spin.setRange(1, 365)
        self.reminder_days_spin.setValue(
            int(self.repo.get_setting("reminder_days", 14))
        )

        self.operator_edit = QtWidgets.QLineEdit(
            self.repo.get_setting("operator_name", "")
        )

        hint = QtWidgets.QLabel(
            "Number of days ahead to include in LAN reminder broadcasts."
        )
        hint.setWordWrap(True)

        rem_form.addRow("Reminder days", self.reminder_days_spin)
        rem_form.addRow("Operator name", self.operator_edit)
        rem_form.addRow(hint)

        # Quiet hours: listener will not show popup during this time (still logs)
        quiet_layout = QtWidgets.QHBoxLayout()
        self.quiet_start_edit = QtWidgets.QTimeEdit()
        self.quiet_start_edit.setDisplayFormat("HH:mm")
        self.quiet_end_edit = QtWidgets.QTimeEdit()
        self.quiet_end_edit.setDisplayFormat("HH:mm")
        _qstart = self.repo.get_setting("quiet_start", "")
        _qend = self.repo.get_setting("quiet_end", "")
        if _qstart and len(_qstart) >= 5:
            try:
                h, m = int(_qstart[:2]), int(_qstart[3:5])
                self.quiet_start_edit.setTime(QtCore.QTime(h, m))
            except Exception:
                pass
        if _qend and len(_qend) >= 5:
            try:
                h, m = int(_qend[:2]), int(_qend[3:5])
                self.quiet_end_edit.setTime(QtCore.QTime(h, m))
            except Exception:
                pass
        quiet_layout.addWidget(self.quiet_start_edit)
        quiet_layout.addWidget(QtWidgets.QLabel("to"))
        quiet_layout.addWidget(self.quiet_end_edit)
        quiet_layout.addWidget(QtWidgets.QLabel("(leave 00:00–00:00 to disable)"))
        rem_form.addRow("Quiet hours (no popup):", quiet_layout)

        tabs.addTab(rem_widget, "Reminders")

        # Backup tab
        backup_widget = QtWidgets.QWidget()
        backup_layout = QtWidgets.QVBoxLayout(backup_widget)
        backup_desc = QtWidgets.QLabel(
            "Create a manual backup of the database. Automatic daily backups run on app startup."
        )
        backup_desc.setWordWrap(True)
        backup_layout.addWidget(backup_desc)
        self.btn_backup_now = QtWidgets.QPushButton("Backup now")
        self.btn_backup_now.setToolTip("Create a timestamped backup in the backups folder")
        self.btn_backup_now.clicked.connect(self._on_backup_now)
        backup_layout.addWidget(self.btn_backup_now)
        self.backup_status_label = QtWidgets.QLabel("")
        self.backup_status_label.setWordWrap(True)
        backup_layout.addWidget(self.backup_status_label)
        backup_layout.addStretch()
        tabs.addTab(backup_widget, "Backup")

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        layout.addWidget(btn_box)

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
    
    def _show_help(self):
        title, content = get_help_content("SettingsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _on_backup_now(self):
        from database import get_effective_db_path
        from database_backup import backup_database
        db_path = get_effective_db_path()
        result = backup_database(db_path)
        if result:
            self.backup_status_label.setText(f"Backup created: {result.name}")
            self.backup_status_label.setStyleSheet("color: #080;")
        else:
            self.backup_status_label.setText("Backup failed. Check the log for details.")
            self.backup_status_label.setStyleSheet("color: #c00;")

    def accept(self):
        ok_btn = self.btn_box.button(QtWidgets.QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setEnabled(False)
        try:
            self.repo.set_setting(
                "reminder_days", str(self.reminder_days_spin.value())
            )
            self.repo.set_setting(
                "operator_name", self.operator_edit.text().strip()
            )
            qstart = self.quiet_start_edit.time().toString("HH:mm")
            qend = self.quiet_end_edit.time().toString("HH:mm")
            self.repo.set_setting("quiet_start", qstart)
            self.repo.set_setting("quiet_end", qend)
            # Write quiet hours to file so standalone listener can read
            try:
                from file_utils import atomic_write_text
                base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
                path = Path(base) / "CalibrationTracker" / "quiet_hours.txt"
                atomic_write_text(path, qstart + "\n" + qend + "\n")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to write quiet_hours.txt: %s", e)
            super().accept()
        except Exception as e:
            if ok_btn:
                ok_btn.setEnabled(True)
            QtWidgets.QMessageBox.critical(self, "Error saving settings", str(e))

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
        
        # Add Help button
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
            self.repo.add_attachment(self.instrument_id, path)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error adding attachment", str(e)
            )

    def _open_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return

        # We stored the attachment id in the first column's UserRole
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
            # Write the blob to a temp file and open it
            temp_dir = Path(tempfile.gettempdir()) / "cal_tracker_attachments"
            temp_dir.mkdir(parents=True, exist_ok=True)

            temp_path = temp_dir / filename
            try:
                with temp_path.open("wb") as f:
                    f.write(file_data)

                QtGui = __import__("PyQt5.QtGui", fromlist=["QtGui"]).QtGui
                QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl.fromLocalFile(str(temp_path))
                )
                return
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error opening attachment", str(e)
                )
                return

        # Fallback: if for some reason file_data is NULL but we still have a path
        if stored_path:
            QtGui = __import__("PyQt5.QtGui", fromlist=["QtGui"]).QtGui
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
            self.repo.delete_attachment(att_id)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error deleting attachment", str(e)
            )


class DestinationEditDialog(QtWidgets.QDialog):
    def __init__(self, dest=None, parent=None):
        super().__init__(parent)
        self.dest = dest or {}
        self.setWindowTitle("Destination")

        form = QtWidgets.QFormLayout(self)

        self.name_edit = QtWidgets.QLineEdit(self.dest.get("name", ""))
        self.contact_edit = QtWidgets.QLineEdit(self.dest.get("contact", ""))
        self.email_edit = QtWidgets.QLineEdit(self.dest.get("email", ""))
        self.phone_edit = QtWidgets.QLineEdit(self.dest.get("phone", ""))
        self.addr_edit = QtWidgets.QPlainTextEdit(self.dest.get("address", ""))
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.addr_edit.document().setDefaultTextOption(option)

        form.addRow("Name*", self.name_edit)
        form.addRow("Contact", self.contact_edit)
        form.addRow("Email", self.email_edit)
        form.addRow("Phone", self.phone_edit)
        form.addRow("Address", self.addr_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)
    
    def _show_help(self):
        title, content = get_help_content("DestinationEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Name is required.")
            return None
        data = {
            "name": name,
            "contact": self.contact_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "address": self.addr_edit.toPlainText().strip(),
        }
        return data


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
        
        # Add Help button
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
                self.repo.add_destination(**data)
                self._load_destinations()

    def on_edit(self):
        row = self._selected_row()
        if row is None:
            return
        dest_id = self._selected_dest_id()
        if dest_id is None:
            return

        # Pull current values from the table
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
                self.repo.update_destination(dest_id, data)
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
                self.repo.delete_destination(dest_id)
                self._load_destinations()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))


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
                self.repo.add_personnel(
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
                self.repo.update_personnel(
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
            self.repo.delete_personnel(pid)
            self._load()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))


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

class FieldEditDialog(QtWidgets.QDialog):
    def __init__(self, field=None, existing_fields=None, parent=None):
        super().__init__(parent)
        self.field = field or {}
        self.existing_fields = existing_fields or []
        self.setWindowTitle("Field" + (" - Edit" if field else " - New"))

        # Use scroll area so Tolerance type / Equation option is reachable on smaller screens
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        content = QtWidgets.QWidget()
        content.setMinimumWidth(380)
        form = QtWidgets.QFormLayout(content)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        _min_field_w = STANDARD_FIELD_WIDTH
        self.name_edit = QtWidgets.QLineEdit(self.field.get("name", ""))
        self.name_edit.setMinimumWidth(_min_field_w)
        self.label_edit = QtWidgets.QLineEdit(self.field.get("label", ""))
        self.label_edit.setMinimumWidth(_min_field_w)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setMinimumWidth(_min_field_w)
        self.type_combo.addItems(["text", "number", "bool", "date", "signature", "reference", "tolerance", "convert", "stat", "plot"])
        self.type_combo.addItem("Non-affected Date", "non_affected_date")
        self.type_combo.addItem("Field Header", "field_header")
        dt = self.field.get("data_type") or "text"
        idx = self.type_combo.findData(dt) if dt in ("non_affected_date", "field_header") else self.type_combo.findText(dt)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        self.unit_edit = QtWidgets.QLineEdit(self.field.get("unit") or "")
        self.unit_edit.setMinimumWidth(_min_field_w)
        self.unit_label = QtWidgets.QLabel("Unit")
        self.required_check = QtWidgets.QCheckBox("Required")
        self.required_check.setChecked(bool(self.field.get("required", 0)))

        self.sort_spin = QtWidgets.QSpinBox()
        self.sort_spin.setRange(0, 9999)
        self.sort_spin.setValue(int(self.field.get("sort_order", 0)))

        self.group_edit = QtWidgets.QLineEdit(self.field.get("group_name") or "")
        self.group_edit.setMinimumWidth(_min_field_w)
        self.group_edit.textChanged.connect(self._refresh_value_combos)

        self.reference_value_edit = QtWidgets.QLineEdit(self.field.get("default_value") or "")
        self.reference_value_edit.setMinimumWidth(_min_field_w)
        self.reference_value_label = QtWidgets.QLabel("Reference value")

        self.ref1_combo = QtWidgets.QComboBox()
        self.ref2_combo = QtWidgets.QComboBox()
        self.ref3_combo = QtWidgets.QComboBox()
        self.ref4_combo = QtWidgets.QComboBox()
        self.ref5_combo = QtWidgets.QComboBox()
        self.ref6_combo = QtWidgets.QComboBox()
        self.ref7_combo = QtWidgets.QComboBox()
        self.ref8_combo = QtWidgets.QComboBox()
        self.ref9_combo = QtWidgets.QComboBox()
        self.ref10_combo = QtWidgets.QComboBox()
        self.ref11_combo = QtWidgets.QComboBox()
        self.ref12_combo = QtWidgets.QComboBox()
        self._populate_value_combos()

        def set_cb_from_name(cb, name):
            if not name:
                return
            for i in range(cb.count()):
                if cb.itemData(i) == name:
                    cb.setCurrentIndex(i)
                    break

        for i, cb in enumerate([self.ref1_combo, self.ref2_combo, self.ref3_combo, self.ref4_combo, self.ref5_combo,
                                 self.ref6_combo, self.ref7_combo, self.ref8_combo, self.ref9_combo, self.ref10_combo,
                                 self.ref11_combo, self.ref12_combo], 1):
            set_cb_from_name(cb, self.field.get(f"calc_ref{i}_name"))
        for cb in (self.ref6_combo, self.ref7_combo, self.ref8_combo, self.ref9_combo, self.ref10_combo,
                   self.ref11_combo, self.ref12_combo):
            cb.currentIndexChanged.connect(self._update_val_ref_visibility)

        self.tol_type_combo = QtWidgets.QComboBox()
        self.tol_type_combo.setMinimumWidth(_min_field_w)
        self.tol_type_combo.addItem("None", None)
        self.tol_type_combo.addItem("Equation", "equation")
        self.tol_type_combo.addItem("Boolean", "bool")
        tol_type = self.field.get("tolerance_type")
        if tol_type and tol_type not in ("equation", "bool"):
            tol_type = None
        tol_type = tol_type or None
        idx = self.tol_type_combo.findData(tol_type)
        if idx >= 0:
            self.tol_type_combo.setCurrentIndex(idx)
        else:
            self.tol_type_combo.setCurrentIndex(0)
        self.tol_type_combo.currentIndexChanged.connect(self._on_tolerance_type_changed)

        self.tol_equation_edit = QtWidgets.QLineEdit(self.field.get("tolerance_equation") or "")
        self.tol_equation_edit.setMinimumWidth(_min_field_w)
        self.tol_equation_edit.setPlaceholderText("e.g. reading <= 0.02 * nominal or val1 < val2 + 0.5")
        self.tol_equation_edit.setToolTip(
            "Must contain a pass/fail condition (<, >, <=, >=, or ==). "
            "Variables: nominal, reading, val1..val12 (see Help)."
        )
        self.tol_equation_label = QtWidgets.QLabel("Tolerance equation")
        # Boolean tolerance: pass when True or False
        self.tol_bool_pass_combo = QtWidgets.QComboBox()
        self.tol_bool_pass_combo.addItem("Pass when value is True", "true")
        self.tol_bool_pass_combo.addItem("Pass when value is False", "false")
        bool_pass = (self.field.get("tolerance_equation") or "true").strip().lower()
        idx_bool = self.tol_bool_pass_combo.findData("true" if bool_pass == "true" else "false")
        if idx_bool >= 0:
            self.tol_bool_pass_combo.setCurrentIndex(idx_bool)
        self.tol_bool_pass_label = QtWidgets.QLabel("Pass when value is")

        form.addRow("Name* (internal)", self.name_edit)
        form.addRow("Label* (shown)", self.label_edit)
        form.addRow("Type", self.type_combo)
        form.addRow(self.reference_value_label, self.reference_value_edit)
        form.addRow(self.unit_label, self.unit_edit)
        form.addRow("", self.required_check)
        form.addRow("Sort order", self.sort_spin)
        form.addRow("Group", self.group_edit)
        self.sig_figs_spin = QtWidgets.QSpinBox()
        self.sig_figs_spin.setRange(0, 4)
        self.sig_figs_spin.setValue(int(self.field.get("sig_figs") or 3))
        self.sig_figs_spin.setToolTip("Numbers after decimal (0–4) for displayed value. Applies to number, convert, reference, tolerance, and stat fields.")
        self.sig_figs_label = QtWidgets.QLabel("Numbers after decimal")
        form.addRow(self.sig_figs_label, self.sig_figs_spin)
        show_decimals = (dt or "").strip().lower() in ("number", "convert", "tolerance", "reference", "stat")
        self.sig_figs_spin.setVisible(show_decimals)
        self.sig_figs_label.setVisible(show_decimals)
        form.addRow("Tolerance type", self.tol_type_combo)
        form.addRow(self.tol_equation_label, self.tol_equation_edit)
        form.addRow(self.tol_bool_pass_label, self.tol_bool_pass_combo)
        self.val1_label = QtWidgets.QLabel("val1 field")
        self.val2_label = QtWidgets.QLabel("val2 field")
        self.val3_label = QtWidgets.QLabel("val3 field (optional)")
        self.val4_label = QtWidgets.QLabel("val4 field (optional)")
        self.val5_label = QtWidgets.QLabel("val5 field (optional)")
        self.val6_label = QtWidgets.QLabel("val6 (optional)")
        self.val7_label = QtWidgets.QLabel("val7 (optional)")
        self.val8_label = QtWidgets.QLabel("val8 (optional)")
        self.val9_label = QtWidgets.QLabel("val9 (optional)")
        self.val10_label = QtWidgets.QLabel("val10 (optional)")
        self.val11_label = QtWidgets.QLabel("val11 (optional)")
        self.val12_label = QtWidgets.QLabel("val12 (optional)")
        form.addRow(self.val1_label, self.ref1_combo)
        form.addRow(self.val2_label, self.ref2_combo)
        form.addRow(self.val3_label, self.ref3_combo)
        form.addRow(self.val4_label, self.ref4_combo)
        form.addRow(self.val5_label, self.ref5_combo)
        form.addRow(self.val6_label, self.ref6_combo)
        form.addRow(self.val7_label, self.ref7_combo)
        form.addRow(self.val8_label, self.ref8_combo)
        form.addRow(self.val9_label, self.ref9_combo)
        form.addRow(self.val10_label, self.ref10_combo)
        form.addRow(self.val11_label, self.ref11_combo)
        form.addRow(self.val12_label, self.ref12_combo)
        # Track which val6-val12 rows user has added (so they stay visible)
        self._added_val_indices = set()
        for i in range(6, 13):
            if self.field.get(f"calc_ref{i}_name"):
                self._added_val_indices.add(i)
        self.btn_add_value = QtWidgets.QPushButton("+ Add value")
        self.btn_add_value.setToolTip("Add another variable slot (val6, val7, … val12) for the equation.")
        self.btn_add_value.setMaximumWidth(110)
        self.btn_add_value.clicked.connect(self._on_add_value_clicked)
        form.addRow("", self.btn_add_value)
        # Plot options (visible when type is "plot")
        self.plot_group = QtWidgets.QGroupBox("Plot options")
        plot_layout = QtWidgets.QFormLayout(self.plot_group)
        self.plot_title_edit = QtWidgets.QLineEdit(self.field.get("plot_title") or "")
        self.plot_title_edit.setPlaceholderText("Chart title")
        self.plot_title_edit.setMinimumWidth(_min_field_w)
        self.plot_x_axis_edit = QtWidgets.QLineEdit(self.field.get("plot_x_axis_name") or "")
        self.plot_x_axis_edit.setPlaceholderText("X axis label")
        self.plot_x_axis_edit.setMinimumWidth(_min_field_w)
        self.plot_y_axis_edit = QtWidgets.QLineEdit(self.field.get("plot_y_axis_name") or "")
        self.plot_y_axis_edit.setPlaceholderText("Y axis label")
        self.plot_y_axis_edit.setMinimumWidth(_min_field_w)
        self.plot_x_min_edit = QtWidgets.QLineEdit("")
        self.plot_x_min_edit.setPlaceholderText("Min (blank = auto)")
        self.plot_x_min_edit.setMinimumWidth(_min_field_w)
        self.plot_x_max_edit = QtWidgets.QLineEdit("")
        self.plot_x_max_edit.setPlaceholderText("Max (blank = auto)")
        self.plot_x_max_edit.setMinimumWidth(_min_field_w)
        self.plot_y_min_edit = QtWidgets.QLineEdit("")
        self.plot_y_min_edit.setPlaceholderText("Min (blank = auto)")
        self.plot_y_min_edit.setMinimumWidth(_min_field_w)
        self.plot_y_max_edit = QtWidgets.QLineEdit("")
        self.plot_y_max_edit.setPlaceholderText("Max (blank = auto)")
        self.plot_y_max_edit.setMinimumWidth(_min_field_w)
        for attr, le in (("plot_x_min", "plot_x_min_edit"), ("plot_x_max", "plot_x_max_edit"), ("plot_y_min", "plot_y_min_edit"), ("plot_y_max", "plot_y_max_edit")):
            v = self.field.get(attr)
            if v is not None and str(v).strip() != "":
                getattr(self, le).setText(str(v))
        self.plot_best_fit_check = QtWidgets.QCheckBox("Show line of best fit")
        self.plot_best_fit_check.setChecked(bool(self.field.get("plot_best_fit", 0)))
        plot_layout.addRow("Title", self.plot_title_edit)
        plot_layout.addRow("X axis name", self.plot_x_axis_edit)
        plot_layout.addRow("Y axis name", self.plot_y_axis_edit)
        plot_layout.addRow("X range min", self.plot_x_min_edit)
        plot_layout.addRow("X range max", self.plot_x_max_edit)
        plot_layout.addRow("Y range min", self.plot_y_min_edit)
        plot_layout.addRow("Y range max", self.plot_y_max_edit)
        plot_layout.addRow("", self.plot_best_fit_check)
        form.addRow(self.plot_group)
        self.plot_group.setVisible(False)
        self._on_type_changed(self.type_combo.currentText())
        self.var_btn_layout = QtWidgets.QHBoxLayout()
        self.var_btn_layout.addWidget(QtWidgets.QLabel("Insert:"))
        for var_name in ("nominal", "reading", "val1", "val2", "val3", "val4", "val5", "val6", "val7", "val8", "val9", "val10", "val11", "val12"):
            btn = QtWidgets.QPushButton(var_name)
            btn.setMaximumWidth(52)
            btn.clicked.connect(lambda checked, v=var_name: self._insert_variable(v))
            self.var_btn_layout.addWidget(btn)
        self.var_btn_layout.addStretch()
        self.var_btn_widget = QtWidgets.QWidget()
        self.var_btn_widget.setLayout(self.var_btn_layout)
        form.addRow("", self.var_btn_widget)
        # M2: Inline validation message
        self.tol_validation_label = QtWidgets.QLabel("")
        self.tol_validation_label.setWordWrap(True)
        self.tol_validation_label.setStyleSheet("color: #c00; font-size: 0.9em;")
        form.addRow("", self.tol_validation_label)
        self.tol_equation_edit.textChanged.connect(self._on_equation_changed)
        # M3: Test equation panel
        self.test_group = QtWidgets.QGroupBox("Test equation")
        test_layout = QtWidgets.QFormLayout(self.test_group)
        self.test_nominal_spin = QtWidgets.QDoubleSpinBox()
        self.test_nominal_spin.setRange(-1e12, 1e12)
        self.test_nominal_spin.setValue(10.0)
        self.test_reading_spin = QtWidgets.QDoubleSpinBox()
        self.test_reading_spin.setRange(-1e12, 1e12)
        self.test_reading_spin.setValue(10.0)
        self.test_tolerance_label = QtWidgets.QLabel("—")
        self.test_passfail_label = QtWidgets.QLabel("—")
        test_layout.addRow("Nominal:", self.test_nominal_spin)
        test_layout.addRow("Reading:", self.test_reading_spin)
        test_layout.addRow("Tolerance:", self.test_tolerance_label)
        test_layout.addRow("Pass/Fail:", self.test_passfail_label)
        for w in (self.test_nominal_spin, self.test_reading_spin):
            w.valueChanged.connect(self._update_test_result)
        form.addRow(self.test_group)
        self._on_tolerance_type_changed(self.tol_type_combo.currentIndex())
        self._update_test_result()

        # Autofill option
        self.autofill_check = QtWidgets.QCheckBox("Autofill from previous group")
        self.autofill_check.setChecked(bool(self.field.get("autofill_from_first_group", 0)))
        form.addRow("", self.autofill_check)

        scroll.setWidget(content)
        scroll.setMinimumHeight(420)
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(scroll)
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        main_layout.addWidget(btn_box)
        self.setMinimumSize(460, 520)
        self.resize(540, 680)

    def reject(self):
        """Confirm before closing (Escape or Cancel) to avoid losing edits."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Discard changes?",
            "Are you sure you want to close? Unsaved changes will be lost.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            super().reject()

    def _on_ok_clicked(self):
        """Validate via get_data(); only close dialog if validation passes."""
        if self.get_data() is not None:
            self.accept()

    def _get_value_combo_group(self):
        """Group to filter value (ref) combos by. Stat and plot types have access to all variables (no filter)."""
        data_type = self.type_combo.currentText() if hasattr(self, "type_combo") else ""
        if data_type in ("stat", "plot"):
            return ""  # Stat/plot: show all template fields in val1..val12 dropdowns
        return (self.group_edit.text() or "").strip() if hasattr(self, "group_edit") else ""

    def _populate_value_combos(self):
        """Populate val1-val12 ref combos. Filtered by Group for tolerance/convert; stat shows all fields."""
        group = self._get_value_combo_group()
        fields = self.existing_fields
        if group:
            fields = [f for f in fields if (f.get("group_name") or "").strip() == group]
        ref_combos = [
            self.ref1_combo, self.ref2_combo, self.ref3_combo, self.ref4_combo, self.ref5_combo,
            self.ref6_combo, self.ref7_combo, self.ref8_combo, self.ref9_combo, self.ref10_combo,
            self.ref11_combo, self.ref12_combo,
        ]
        current_selections = [cb.currentData() for cb in ref_combos]
        for i, cb in enumerate(ref_combos):
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("", None)
            for f in fields:
                cb.addItem(f["name"], f["name"])
            name_to_restore = current_selections[i] if i < len(current_selections) else None
            if not name_to_restore and self.field:
                name_to_restore = self.field.get(f"calc_ref{i + 1}_name")
            if name_to_restore:
                for j in range(cb.count()):
                    if cb.itemData(j) == name_to_restore:
                        cb.setCurrentIndex(j)
                        break
            cb.blockSignals(False)

    def _refresh_value_combos(self):
        """Re-populate value combos when group changes."""
        self._populate_value_combos()

    def _on_type_changed(self, data_type: str):
        """Show/hide Unit (when number), Reference value (when reference). Show tolerance/convert/stat/plot section for bool, tolerance, convert, stat, plot."""
        is_number = (data_type == "number")
        is_reference = (data_type == "reference")
        is_tolerance = (data_type == "tolerance")
        is_convert = (data_type == "convert")
        is_stat = (data_type == "stat")
        is_plot = (data_type == "plot")
        is_field_header = (data_type in ("Field Header", "field_header"))
        is_bool = (data_type == "bool")
        show_unit = is_number or is_convert or is_tolerance or is_reference or is_stat
        if hasattr(self, "unit_edit") and hasattr(self, "unit_label"):
            self.unit_edit.setVisible(show_unit)
            self.unit_label.setVisible(show_unit)
        if hasattr(self, "sig_figs_spin") and hasattr(self, "sig_figs_label"):
            show_decimals = is_number or is_convert or is_tolerance or is_reference or is_stat
            self.sig_figs_spin.setVisible(show_decimals)
            self.sig_figs_label.setVisible(show_decimals)
        if hasattr(self, "reference_value_edit") and hasattr(self, "reference_value_label"):
            self.reference_value_edit.setVisible(is_reference)
            self.reference_value_label.setVisible(is_reference)
        # When type is bool: show tolerance section with Boolean selected so user can set pass when True/False
        if is_bool and hasattr(self, "tol_type_combo"):
            idx = self.tol_type_combo.findData("bool")
            if idx >= 0:
                self.tol_type_combo.setCurrentIndex(idx)
        # Tolerance type: show equation section (read-only display in calibration form)
        if is_tolerance and hasattr(self, "tol_type_combo"):
            self.tol_type_combo.setCurrentIndex(self.tol_type_combo.findData("equation"))
        # Stat type: show equation (e.g. LINEST), no pass/fail required; value dropdowns show all fields
        if is_stat:
            self._refresh_value_combos()
        if is_stat:
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setText("Stat equation")
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setPlaceholderText("e.g. LINEST([val1, val2], [ref1, ref2]) or STDEV([val1, val2, val3])")
                self.tol_equation_edit.setToolTip(
                    "Statistical formula. Functions: LINEST(ys,xs) slope, INTERCEPT(ys,xs), RSQ(ys,xs), CORREL(ys,xs), "
                    "STDEV([vals]), STDEVP([vals]), MEDIAN([vals]). Variables: nominal, reading, val1..val12 (see refs below)."
                )
        # Plot type: PLOT([x refs], [y refs]). For side-by-side X,Y columns use odd refs for X, even for Y.
        if is_plot:
            self._refresh_value_combos()
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setText("Plot data")
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setPlaceholderText("e.g. PLOT([val1, val3, val5], [val2, val4, val6])")
                self.tol_equation_edit.setToolTip(
                    "PLOT([x1, x2, ...], [y1, y2, ...]). Each point is (x1,y1), (x2,y2), etc. "
                    "If X and Y are side by side (e.g. Certified Weight then Balance Response), set ref1=X1, ref2=Y1, ref3=X2, ref4=Y2, ... "
                    "and use: PLOT([val1, val3, val5, ...], [val2, val4, val6, ...]). Charts appear in PDF export; ensure refs point to fields that have values for this record."
                )
            if hasattr(self, "plot_group"):
                self.plot_group.setVisible(True)
        elif hasattr(self, "plot_group"):
            self.plot_group.setVisible(False)
        # Convert type: show conversion equation and val1-val5 (no pass/fail required)
        if is_convert:
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setText("Conversion equation")
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setPlaceholderText("e.g. (val1-32)/1.8")
                self.tol_equation_edit.setToolTip("Expression using val1..val12 (see refs below). Use val1, val2, … in the equation; each maps to the field chosen above. Result is stored as this field's value.")
            if hasattr(self, "tol_type_combo"):
                self.tol_type_combo.setCurrentIndex(0)
        elif not is_stat:
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setText("Tolerance equation")
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setPlaceholderText("e.g. reading <= 0.02 * nominal or val1 < val2 + 0.5")
                self.tol_equation_edit.setToolTip(
                    "Must contain a pass/fail condition (<, >, <=, >=, or ==). "
                    "Variables: nominal, reading, val1..val12 (see Help)."
                )
        if hasattr(self, "tol_type_combo"):
            self._on_tolerance_type_changed(self.tol_type_combo.currentIndex())
        if hasattr(self, "tol_type_combo"):
            self.tol_type_combo.setVisible(not is_convert and not is_stat and not is_plot and not is_field_header)
        if is_tolerance and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_convert and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_stat and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_plot and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        # Tolerance-type, convert, stat, and plot fields: show equation + refs (val1-val5 always; val6-val12 only when used)
        if is_convert or is_stat or is_plot:
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setVisible(True)
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setVisible(True)
            for i in range(1, 6):
                lbl = getattr(self, f"val{i}_label", None)
                cb = getattr(self, f"ref{i}_combo", None)
                if lbl:
                    lbl.setVisible(True)
                if cb:
                    cb.setVisible(True)
            self._update_val_ref_visibility()
            if hasattr(self, "var_btn_widget"):
                self.var_btn_widget.setVisible(True)
            if hasattr(self, "tol_validation_label"):
                self.tol_validation_label.setVisible(True)
                self._on_equation_changed()
            if hasattr(self, "tol_bool_pass_combo"):
                self.tol_bool_pass_combo.setVisible(False)
            if hasattr(self, "tol_bool_pass_label"):
                self.tol_bool_pass_label.setVisible(False)
        # Field Header: label only, appears as header for the group. Hide equation, refs, unit, required.
        if is_field_header:
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setVisible(False)
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setVisible(False)
            if hasattr(self, "tol_type_combo"):
                self.tol_type_combo.setVisible(False)
            for i in range(1, 13):
                lbl = getattr(self, f"val{i}_label", None)
                cb = getattr(self, f"ref{i}_combo", None)
                if lbl:
                    lbl.setVisible(False)
                if cb:
                    cb.setVisible(False)
            if hasattr(self, "var_btn_widget"):
                self.var_btn_widget.setVisible(False)
            if hasattr(self, "test_group"):
                self.test_group.setVisible(False)
            if hasattr(self, "plot_group"):
                self.plot_group.setVisible(False)
            if hasattr(self, "required_check"):
                self.required_check.setVisible(False)
                self.required_check.setChecked(False)
        # Tolerance-type, convert, stat, and plot fields are display-only; hide Required.
        if hasattr(self, "required_check") and not is_field_header:
            self.required_check.setVisible(not is_tolerance and not is_convert and not is_stat and not is_plot)
            if is_tolerance or is_convert or is_stat or is_plot:
                self.required_check.setChecked(False)

    def _on_tolerance_type_changed(self, index: int):
        """Show equation edit and val1-val5 when Equation; val6-val12 only when used in equation or ref set. Bool pass combo for Boolean."""
        data_type = self.type_combo.currentText() if hasattr(self, "type_combo") else ""
        is_convert = (data_type == "convert")
        is_stat = (data_type == "stat")
        is_plot = (data_type == "plot")
        tol_type = self.tol_type_combo.currentData() if hasattr(self, "tol_type_combo") else None
        is_equation = (tol_type == "equation") or is_convert or is_stat or is_plot
        is_bool = (tol_type == "bool") and not is_convert
        if hasattr(self, "tol_equation_edit"):
            self.tol_equation_edit.setVisible(is_equation)
            self.tol_equation_label.setVisible(is_equation)
        if hasattr(self, "tol_bool_pass_combo"):
            self.tol_bool_pass_combo.setVisible(is_bool)
            self.tol_bool_pass_label.setVisible(is_bool)
        for i in range(1, 6):
            lbl = getattr(self, f"val{i}_label", None)
            cb = getattr(self, f"ref{i}_combo", None)
            if lbl:
                lbl.setVisible(is_equation)
            if cb:
                cb.setVisible(is_equation)
        if is_equation:
            self._update_val_ref_visibility()
        else:
            for i in range(6, 13):
                lbl = getattr(self, f"val{i}_label", None)
                cb = getattr(self, f"ref{i}_combo", None)
                if lbl:
                    lbl.setVisible(False)
                if cb:
                    cb.setVisible(False)
            if hasattr(self, "btn_add_value"):
                self.btn_add_value.setVisible(False)
        if hasattr(self, "var_btn_widget"):
            self.var_btn_widget.setVisible(is_equation)
        if hasattr(self, "tol_validation_label"):
            self.tol_validation_label.setVisible(is_equation)
            self._on_equation_changed()
        if hasattr(self, "test_group"):
            self.test_group.setVisible(is_equation)
            self._update_test_result()

    def _on_add_value_clicked(self):
        """Reveal the next val6-val12 row (user explicitly added it)."""
        added = getattr(self, "_added_val_indices", set())
        for i in range(6, 13):
            if i not in added:
                added.add(i)
                if hasattr(self, "_update_val_ref_visibility"):
                    self._update_val_ref_visibility()
                return
        self._update_val_ref_visibility()

    def _update_val_ref_visibility(self):
        """Show val6-val12 rows when added via button, or when equation uses them or ref has a selection."""
        data_type = self.type_combo.currentText() if hasattr(self, "type_combo") else ""
        tol_type = self.tol_type_combo.currentData() if hasattr(self, "tol_type_combo") else None
        is_equation = (data_type in ("tolerance", "convert", "stat", "plot") or tol_type == "equation")
        added = getattr(self, "_added_val_indices", set())
        if hasattr(self, "btn_add_value"):
            self.btn_add_value.setVisible(is_equation)
            self.btn_add_value.setEnabled(len(added) < 7)
        if not is_equation:
            return
        eq = self.tol_equation_edit.text().strip() if hasattr(self, "tol_equation_edit") else ""
        used = set()
        if eq:
            try:
                from tolerance_service import list_variables
                used = set(list_variables(eq))
            except Exception:
                pass
        num_shown = 0
        for i in range(6, 13):
            lbl = getattr(self, f"val{i}_label", None)
            cb = getattr(self, f"ref{i}_combo", None)
            show = (i in added) or (f"val{i}" in used or f"ref{i}" in used)
            if cb and cb.currentData() is not None:
                show = True
            if lbl:
                lbl.setVisible(show)
            if cb:
                cb.setVisible(show)
            if show:
                num_shown += 1
        if hasattr(self, "btn_add_value"):
            self.btn_add_value.setEnabled(num_shown < 7)

    def _insert_variable(self, var_name: str):
        """M2: Insert variable at cursor in equation edit."""
        if not hasattr(self, 'tol_equation_edit'):
            return
        self.tol_equation_edit.insert(var_name)
        self.tol_equation_edit.setFocus()

    def _on_equation_changed(self):
        """Inline validation (syntax, undefined vars; pass/fail required only for tolerance equation)."""
        if not hasattr(self, "tol_validation_label") or not self.tol_equation_edit.isVisible():
            return
        eq = self.tol_equation_edit.text().strip()
        if not eq:
            self.tol_validation_label.setText("")
            return
        is_convert = getattr(self, "type_combo", None) and self.type_combo.currentText() == "convert"
        is_stat = getattr(self, "type_combo", None) and self.type_combo.currentText() == "stat"
        is_plot = getattr(self, "type_combo", None) and self.type_combo.currentText() == "plot"
        try:
            if is_plot:
                from tolerance_service import parse_plot_equation
                parse_plot_equation(eq)
                self.tol_validation_label.setText("✓ Valid")
                self.tol_validation_label.setStyleSheet("color: #080; font-size: 0.9em;")
            else:
                from tolerance_service import (
                    parse_equation,
                    validate_equation_variables,
                    equation_has_pass_fail_condition,
                )
                parse_equation(eq)
                ok, unknown = validate_equation_variables(eq)
                if not ok:
                    self.tol_validation_label.setText(
                        f"Unknown variables: {', '.join(unknown)}. Allowed: nominal, reading, val1..val12 (see Help)."
                    )
                    self.tol_validation_label.setStyleSheet("color: #c00; font-size: 0.9em;")
                elif is_convert or is_stat:
                    self.tol_validation_label.setText("✓ Valid")
                    self.tol_validation_label.setStyleSheet("color: #080; font-size: 0.9em;")
                elif not equation_has_pass_fail_condition(eq):
                    self.tol_validation_label.setText(
                        "Equation must contain a pass/fail condition (<, >, <=, >=, or ==)."
                    )
                    self.tol_validation_label.setStyleSheet("color: #c00; font-size: 0.9em;")
                else:
                    self.tol_validation_label.setText("✓ Valid")
                    self.tol_validation_label.setStyleSheet("color: #080; font-size: 0.9em;")
        except (ValueError, SyntaxError) as e:
            self.tol_validation_label.setText(str(e))
            self.tol_validation_label.setStyleSheet("color: #c00; font-size: 0.9em;")
        if hasattr(self, "_update_val_ref_visibility"):
            self._update_val_ref_visibility()
        self._update_test_result()

    def _update_test_result(self):
        """M3: Live tolerance and pass/fail for sample nominal/reading."""
        if not hasattr(self, 'test_group') or not self.test_group.isVisible():
            return
        eq = self.tol_equation_edit.text().strip() if hasattr(self, 'tol_equation_edit') else ""
        nominal = self.test_nominal_spin.value()
        reading = self.test_reading_spin.value()
        if not eq:
            self.test_tolerance_label.setText("—")
            self.test_passfail_label.setText("—")
            return
        try:
            from tolerance_service import evaluate_tolerance_equation, evaluate_pass_fail
            v = {"nominal": nominal, "reading": reading}
            tol_val = evaluate_tolerance_equation(eq, v)
            self.test_tolerance_label.setText(f"{tol_val:.6g}")
            pass_, _, expl = evaluate_pass_fail("equation", None, eq, nominal, reading, v)
            # L4: Icon + text (not color-only) for accessibility
            self.test_passfail_label.setText(("\u2713 PASS" if pass_ else "\u2717 FAIL"))
            self.test_passfail_label.setStyleSheet("color: #080;" if pass_ else "color: #c00; font-weight: bold;")
        except Exception as e:
            self.test_tolerance_label.setText("—")
            self.test_passfail_label.setText(str(e)[:40])
            self.test_passfail_label.setStyleSheet("color: #c00;")

    def _show_help(self):
        title, content = get_help_content("FieldEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def get_data(self):
        name = self.name_edit.text().strip()
        label = self.label_edit.text().strip()
        if not name or not label:
            QtWidgets.QMessageBox.warning(
                self, "Validation", "Name and label are required."
            )
            return None

        data_type = self.type_combo.currentData() or self.type_combo.currentText()
        unit = self.unit_edit.text().strip() or None if data_type in ("number", "convert", "tolerance", "reference", "stat") else None
        default_value = None
        if data_type == "reference":
            default_value = self.reference_value_edit.text().strip() or None

        tol_type = self.tol_type_combo.currentData()
        tolerance_equation = None
        ref1_name = ref2_name = ref3_name = ref4_name = ref5_name = None
        ref6_name = ref7_name = ref8_name = ref9_name = ref10_name = None
        ref11_name = ref12_name = None

        # Stat type: equation (e.g. LINEST) + refs, no pass/fail required
        if data_type == "stat":
            tolerance_equation = self.tol_equation_edit.text().strip() or None
            if not tolerance_equation:
                QtWidgets.QMessageBox.warning(
                    self, "Validation",
                    "Stat equation is required for Stat type fields (e.g. LINEST([val1,val2],[ref1,ref2]) or STDEV([val1,val2,val3])).",
                )
                return None
            try:
                from tolerance_service import parse_equation, validate_equation_variables
                parse_equation(tolerance_equation)
                ok, unknown = validate_equation_variables(tolerance_equation)
                if not ok:
                    QtWidgets.QMessageBox.warning(
                        self, "Validation",
                        f"Equation uses unknown variables: {', '.join(unknown)}. Allowed: nominal, reading, val1..val12.",
                    )
                    return None
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, "Validation", f"Invalid equation: {e}")
                return None
            tol_type = "equation"
            ref1_name = self.ref1_combo.currentData()
            ref2_name = self.ref2_combo.currentData()
            ref3_name = self.ref3_combo.currentData()
            ref4_name = self.ref4_combo.currentData()
            ref5_name = self.ref5_combo.currentData()
            ref6_name = self.ref6_combo.currentData()
            ref7_name = self.ref7_combo.currentData()
            ref8_name = self.ref8_combo.currentData()
            ref9_name = self.ref9_combo.currentData()
            ref10_name = self.ref10_combo.currentData()
            ref11_name = self.ref11_combo.currentData()
            ref12_name = self.ref12_combo.currentData()
        # Plot type: PLOT([x refs], [y refs]) + refs; up to 12 total
        elif data_type == "plot":
            tolerance_equation = self.tol_equation_edit.text().strip() or None
            if not tolerance_equation:
                QtWidgets.QMessageBox.warning(
                    self, "Validation",
                    "Plot data is required (e.g. PLOT([val1, val2], [val3, val4])).",
                )
                return None
            try:
                from tolerance_service import parse_plot_equation
                parse_plot_equation(tolerance_equation)
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, "Validation", f"Invalid plot: {e}")
                return None
            ref1_name = self.ref1_combo.currentData()
            ref2_name = self.ref2_combo.currentData()
            ref3_name = self.ref3_combo.currentData()
            ref4_name = self.ref4_combo.currentData()
            ref5_name = self.ref5_combo.currentData()
            ref6_name = self.ref6_combo.currentData()
            ref7_name = self.ref7_combo.currentData()
            ref8_name = self.ref8_combo.currentData()
            ref9_name = self.ref9_combo.currentData()
            ref10_name = self.ref10_combo.currentData()
            ref11_name = self.ref11_combo.currentData()
            ref12_name = self.ref12_combo.currentData()
        # Convert type: equation + refs, numeric expression only (no pass/fail required)
        elif data_type == "convert":
            tolerance_equation = self.tol_equation_edit.text().strip() or None
            if not tolerance_equation:
                QtWidgets.QMessageBox.warning(
                    self, "Validation",
                    "Conversion equation is required for Convert type fields.",
                )
                return None
            try:
                from tolerance_service import parse_equation, validate_equation_variables
                parse_equation(tolerance_equation)
                ok, unknown = validate_equation_variables(tolerance_equation)
                if not ok:
                    QtWidgets.QMessageBox.warning(
                        self, "Validation",
                        f"Equation uses unknown variables: {', '.join(unknown)}. Allowed: nominal, reading, val1..val12.",
                    )
                    return None
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, "Validation", f"Invalid equation: {e}")
                return None
            ref1_name = self.ref1_combo.currentData()
            ref2_name = self.ref2_combo.currentData()
            ref3_name = self.ref3_combo.currentData()
            ref4_name = self.ref4_combo.currentData()
            ref5_name = self.ref5_combo.currentData()
            ref6_name = self.ref6_combo.currentData()
            ref7_name = self.ref7_combo.currentData()
            ref8_name = self.ref8_combo.currentData()
            ref9_name = self.ref9_combo.currentData()
            ref10_name = self.ref10_combo.currentData()
            ref11_name = self.ref11_combo.currentData()
            ref12_name = self.ref12_combo.currentData()
        # Tolerance type (read-only display field) requires equation like equation tolerance
        elif data_type == "tolerance":
            tol_type = "equation"
        if tol_type == "equation" and data_type not in ("convert", "stat"):
            tolerance_equation = self.tol_equation_edit.text().strip() or None
            if not tolerance_equation:
                QtWidgets.QMessageBox.warning(
                    self, "Validation",
                    "Tolerance equation is required for Equation tolerance and for Tolerance type fields.",
                )
                return None
            try:
                from tolerance_service import (
                    parse_equation,
                    validate_equation_variables,
                    equation_has_pass_fail_condition,
                )
                parse_equation(tolerance_equation)
                ok, unknown = validate_equation_variables(tolerance_equation)
                if not ok:
                    QtWidgets.QMessageBox.warning(
                        self, "Validation",
                        f"Equation uses unknown variables: {', '.join(unknown)}. Allowed: nominal, reading, val1..val12.",
                    )
                    return None
                if not equation_has_pass_fail_condition(tolerance_equation):
                    QtWidgets.QMessageBox.warning(
                        self, "Validation",
                        "Equation must contain a pass/fail condition (<, >, <=, >=, or ==).",
                    )
                    return None
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, "Validation", f"Invalid equation: {e}")
                return None
            ref1_name = self.ref1_combo.currentData()
            ref2_name = self.ref2_combo.currentData()
            ref3_name = self.ref3_combo.currentData()
            ref4_name = self.ref4_combo.currentData()
            ref5_name = self.ref5_combo.currentData()
            ref6_name = self.ref6_combo.currentData()
            ref7_name = self.ref7_combo.currentData()
            ref8_name = self.ref8_combo.currentData()
            ref9_name = self.ref9_combo.currentData()
            ref10_name = self.ref10_combo.currentData()
            ref11_name = self.ref11_combo.currentData()
            ref12_name = self.ref12_combo.currentData()
        elif tol_type == "bool":
            tolerance_equation = self.tol_bool_pass_combo.currentData() or "true"

        return {
            "name": name,
            "label": label,
            "data_type": data_type,
            "unit": unit,
            "required": self.required_check.isChecked(),
            "sort_order": self.sort_spin.value(),
            "group_name": self.group_edit.text().strip() or None,
            "calc_type": None,
            "calc_ref1_name": ref1_name,
            "calc_ref2_name": ref2_name,
            "calc_ref3_name": ref3_name,
            "calc_ref4_name": ref4_name,
            "calc_ref5_name": ref5_name,
            "calc_ref6_name": ref6_name,
            "calc_ref7_name": ref7_name,
            "calc_ref8_name": ref8_name,
            "calc_ref9_name": ref9_name,
            "calc_ref10_name": ref10_name,
            "calc_ref11_name": ref11_name,
            "calc_ref12_name": ref12_name,
            "tolerance": None,
            "tolerance_type": tol_type,
            "tolerance_equation": tolerance_equation,
            "nominal_value": None,
            "tolerance_lookup_json": None,
            "autofill_from_first_group": self.autofill_check.isChecked(),
            "default_value": default_value,
            "sig_figs": self.sig_figs_spin.value() if data_type in ("number", "convert", "tolerance", "reference", "stat") else 3,  # decimal places for display
            "stat_value_group": None,
            "plot_x_axis_name": self.plot_x_axis_edit.text().strip() or None if data_type == "plot" else None,
            "plot_y_axis_name": self.plot_y_axis_edit.text().strip() or None if data_type == "plot" else None,
            "plot_title": self.plot_title_edit.text().strip() or None if data_type == "plot" else None,
            "plot_x_min": _parse_float_optional(self.plot_x_min_edit.text()) if data_type == "plot" else None,
            "plot_x_max": _parse_float_optional(self.plot_x_max_edit.text()) if data_type == "plot" else None,
            "plot_y_min": _parse_float_optional(self.plot_y_min_edit.text()) if data_type == "plot" else None,
            "plot_y_max": _parse_float_optional(self.plot_y_max_edit.text()) if data_type == "plot" else None,
            "plot_best_fit": self.plot_best_fit_check.isChecked() if data_type == "plot" else False,
        }


class ExplainToleranceDialog(QtWidgets.QDialog):
    """H6: Read-only dialog showing how tolerance is calculated (plain language + technical)."""
    def __init__(self, field: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Explain tolerance")
        layout = QtWidgets.QVBoxLayout(self)
        label = field.get("label") or field.get("name") or "Field"
        layout.addWidget(QtWidgets.QLabel(f"<b>{label}</b>"))
        tol_type = field.get("tolerance_type") or "fixed"
        tol_fixed = field.get("tolerance")
        tol_eq = field.get("tolerance_equation")
        nominal_str = field.get("nominal_value") or ""
        unit = field.get("unit") or ""

        # Plain-language explanation
        if tol_type == "fixed" and tol_fixed is not None:
            try:
                t = float(tol_fixed)
                expl = f"Tolerance is a fixed value of ±{t} {unit}".strip()
                expl += ". Readings must be within this range of the nominal value to PASS."
            except (TypeError, ValueError):
                expl = "Tolerance: fixed (value not set)."
        elif tol_type == "percent" and tol_fixed is not None:
            try:
                p = float(tol_fixed)
                expl = f"Tolerance is {p}% of the nominal value. "
                expl += "The allowed deviation = |nominal| × " + str(p) + "%."
            except (TypeError, ValueError):
                expl = "Tolerance: percent (value not set)."
        elif tol_type == "equation" and tol_eq:
            expl = f"Tolerance is calculated by: {tol_eq}. "
            expl += "Formula is Excel-like: use ^ for power, < > <= >=, ABS(), MIN(), MAX(), ROUND(), AVERAGE(). "
            expl += "Variables: nominal = expected value (from Nominal value or reference), reading = computed value for this point, ref1..ref5 = values from Value 1–5 fields. "
            try:
                from tolerance_service import evaluate_tolerance_equation
                nominal = 10.0
                if nominal_str:
                    try:
                        nominal = float(nominal_str)
                    except (TypeError, ValueError):
                        pass
                v = evaluate_tolerance_equation(tol_eq, {"nominal": nominal, "reading": 0})
                expl += f"Example: with nominal = {nominal}, tolerance = {v}."
            except Exception as e:
                expl += f"(Example calculation failed: {e})"
        elif tol_type == "lookup":
            import json
            lookup_json = field.get("tolerance_lookup_json") or ""
            try:
                rows = json.loads(lookup_json) if lookup_json.strip() else []
                if rows:
                    expl = "Tolerance is chosen from the lookup table by nominal value. Ranges: "
                    expl += "; ".join(
                        f"[{r.get('range_low')}–{r.get('range_high')}] → ±{r.get('tolerance')}"
                        for r in rows if isinstance(r, dict)
                    )
                else:
                    expl = "Lookup table is empty."
            except (ValueError, TypeError):
                expl = "Lookup table (invalid or empty)."
        elif tol_type == "bool":
            pass_when = (tol_eq or "true").strip().lower()
            if pass_when == "true":
                expl = "PASS when the value is True (checked). FAIL when the value is False (unchecked)."
            else:
                expl = "PASS when the value is False (unchecked). FAIL when the value is True (checked)."
        else:
            expl = "No tolerance defined for this field, or type is not set."

        layout.addWidget(QtWidgets.QLabel("Plain-language explanation:"))
        expl_label = QtWidgets.QLabel(expl)
        expl_label.setWordWrap(True)
        expl_label.setStyleSheet("padding: 6px;")
        layout.addWidget(expl_label)
        layout.addWidget(QtWidgets.QLabel("Technical:"))
        tech = f"Type: {tol_type or 'fixed'}"
        if tol_fixed is not None:
            tech += f"  |  Value: {tol_fixed}"
        if tol_eq:
            tech += f"  |  Equation: {tol_eq}"
        if nominal_str:
            tech += f"  |  Nominal: {nominal_str}"
        if unit:
            tech += f"  |  Unit: {unit}"
        tech_label = QtWidgets.QLabel(tech)
        tech_label.setWordWrap(True)
        tech_label.setStyleSheet("padding: 6px; font-family: monospace;")
        layout.addWidget(tech_label)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)


class TemplateFieldsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, template_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.template_id = template_id

        tpl = self.repo.get_template(template_id)
        self.setWindowTitle(f"Fields - {tpl['name']} (v{tpl['version']})")
        # Resize to 75% of screen size
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.geometry()
            width = int(screen_geometry.width() * 0.75)
            height = int(screen_geometry.height() * 0.75)
            self.resize(width, height)
        else:
            self.resize(900, 500)  # Fallback to default size

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Label", "Type", "Unit", "Required", "Sort", "Group", "Calc", "Tolerance"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        # M5: Summary row
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.summary_label)

        btn_layout = QtWidgets.QGridLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_dup_group = QtWidgets.QPushButton("Duplicate group")
        self.btn_explain = QtWidgets.QPushButton("Explain tolerance")
        self.btn_batch_eq = QtWidgets.QPushButton("Batch change equation")
        self.btn_batch_unit = QtWidgets.QPushButton("Batch apply unit")
        self.btn_batch_decimal = QtWidgets.QPushButton("Batch set decimal")
        self.btn_explain.setToolTip("Show how tolerance is calculated (plain language + technical)")
        self.btn_batch_eq.setToolTip("Set tolerance equation for selected fields (equation type)")
        self.btn_batch_unit.setToolTip("Set unit for selected fields (e.g. °F, °C)")
        self.btn_batch_decimal.setToolTip("Set numbers after decimal (0-4) for selected number, convert, reference, tolerance, and stat fields")
        self.btn_batch_group = QtWidgets.QPushButton("Batch set group")
        self.btn_batch_group.setToolTip("Set group name for selected fields")
        for i, btn in enumerate([self.btn_add, self.btn_edit, self.btn_delete, self.btn_dup_group,
                                 self.btn_explain, self.btn_batch_eq, self.btn_batch_unit,
                                 self.btn_batch_decimal, self.btn_batch_group]):
            btn.setMinimumWidth(100)
            btn_layout.addWidget(btn, i // 4, i % 4)
        layout.addLayout(btn_layout)

        # Connect button signals BEFORE adding to layout
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_dup_group.clicked.connect(self.on_dup_group)
        self.btn_explain.clicked.connect(self.on_explain_tolerance)
        self.btn_batch_eq.clicked.connect(self.on_batch_change_equation)
        self.btn_batch_unit.clicked.connect(self.on_batch_apply_unit)
        self.btn_batch_decimal.clicked.connect(self.on_batch_set_decimal)
        self.btn_batch_group.clicked.connect(self.on_batch_set_group)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
        
        # Load fields immediately after setup
        self._load_fields()
    
    def showEvent(self, event):
        """Override showEvent to ensure table refreshes quickly when dialog opens."""
        super().showEvent(event)
        # Force immediate refresh of the table
        self.table.viewport().update()
        QtWidgets.QApplication.processEvents()
    
    def _show_help(self):
        title, content = get_help_content("TemplateFieldsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _db_error(self, e):
        QtWidgets.QMessageBox.critical(
            self,
            "Database error",
            "A database error occurred. If the database is on a network drive, check the connection and try again.\n\nDetails: " + str(e),
        )

    def _load_fields(self):
        # Remember current sort so we can reapply after reload (don't jump back to Sort column)
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        # Disable sorting and updates while loading for better performance
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        try:
            try:
                fields = self.repo.list_template_fields(self.template_id)
            except sqlite3.OperationalError as e:
                self._db_error(e)
                fields = []
            self._fields_cache = fields

            self.table.setRowCount(len(fields))
            
            # Helper function for creating table items
            def mk(text):
                return QtWidgets.QTableWidgetItem(text)
            
            for row, f in enumerate(fields):
                it_name = mk(f.get("name", ""))
                it_name.setData(QtCore.Qt.UserRole, f["id"])

                calc_desc = ""
                if f.get("calc_type") == "ABS_DIFF":
                    r1 = f.get("calc_ref1_name") or "?"
                    r2 = f.get("calc_ref2_name") or "?"
                    calc_desc = f"|{r1} - {r2}|"
                elif f.get("calc_type") == "PCT_ERROR":
                    r1 = f.get("calc_ref1_name") or "?"
                    r2 = f.get("calc_ref2_name") or "?"
                    calc_desc = f"|{r1} - {r2}| / |{r2}| * 100"
                elif f.get("calc_type") == "PCT_DIFF":
                    r1 = f.get("calc_ref1_name") or "?"
                    r2 = f.get("calc_ref2_name") or "?"
                    calc_desc = f"|{r1} - {r2}| / avg * 100"
                elif f.get("calc_type") == "MIN_OF":
                    refs = [f.get(f"calc_ref{i}_name") for i in range(1, 13) if f.get(f"calc_ref{i}_name")]
                    calc_desc = "min(" + ", ".join(refs or ["?"]) + ")"
                elif f.get("calc_type") == "MAX_OF":
                    refs = [f.get(f"calc_ref{i}_name") for i in range(1, 13) if f.get(f"calc_ref{i}_name")]
                    calc_desc = "max(" + ", ".join(refs or ["?"]) + ")"
                elif f.get("calc_type") == "RANGE_OF":
                    refs = [f.get(f"calc_ref{i}_name") for i in range(1, 13) if f.get(f"calc_ref{i}_name")]
                    calc_desc = "max-min(" + ", ".join(refs or ["?"]) + ")"
                elif f.get("calc_type") == "CUSTOM_EQUATION":
                    eq = (f.get("tolerance_equation") or "").strip()
                    calc_desc = "equation: " + (eq[:30] + "..." if len(eq) > 30 else eq) if eq else "equation (pass/fail)"

                tol = f.get("tolerance")
                tol_type = f.get("tolerance_type") or "fixed"
                if tol_type == "equation":
                    eq = (f.get("tolerance_equation") or "").strip()
                    tol_txt = f"equation: {eq[:40]}..." if len(eq) > 40 else ("equation: " + eq if eq else "")
                elif tol_type == "percent":
                    tol_txt = (str(tol) + "%") if tol is not None else ""
                elif tol_type == "bool":
                    pass_when = (f.get("tolerance_equation") or "true").strip().lower()
                    tol_txt = "pass when True" if pass_when == "true" else "pass when False"
                else:
                    tol_txt = "" if tol is None else str(tol)

                self.table.setItem(row, 0, it_name)
                self.table.setItem(row, 1, mk(f.get("label", "")))
                self.table.setItem(row, 2, mk(f.get("data_type", "")))
                self.table.setItem(row, 3, mk(f.get("unit") or ""))
                self.table.setItem(row, 4, mk("Yes" if f.get("required") else ""))
                # Sort column: use integer so table sorts 1, 2, 3... not 1, 10, 100, 2, 20
                sort_val = int(f.get("sort_order", 0)) if f.get("sort_order") is not None else 0
                sort_item = QtWidgets.QTableWidgetItem()
                sort_item.setData(QtCore.Qt.DisplayRole, sort_val)
                self.table.setItem(row, 5, sort_item)
                self.table.setItem(row, 6, mk(f.get("group_name") or ""))
                self.table.setItem(row, 7, mk(calc_desc))
                self.table.setItem(row, 8, mk(tol_txt))
            # M5: Summary row
            tolerances = []
            for f in fields:
                t = f.get("tolerance")
                if t is not None:
                    try:
                        tolerances.append(float(t))
                    except (TypeError, ValueError):
                        pass
            n = len(fields)
            if tolerances:
                self.summary_label.setText(
                    f"{n} point(s)  |  Min tolerance: {min(tolerances):.6g}  |  Max tolerance: {max(tolerances):.6g}"
                )
            else:
                self.summary_label.setText(f"{n} point(s)")
        finally:
            # Re-enable updates, enable sorting, reapply previous sort (or default Sort column ascending)
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(True)
            if sort_col >= 0 and sort_col < self.table.columnCount():
                self.table.sortItems(sort_col, sort_order)
                self.table.horizontalHeader().setSortIndicator(sort_col, sort_order)
            else:
                self.table.sortItems(5, QtCore.Qt.AscendingOrder)
                self.table.horizontalHeader().setSortIndicator(5, QtCore.Qt.AscendingOrder)
            self.table.viewport().update()
            QtWidgets.QApplication.processEvents()

    def _selected_field_ids(self):
        """Return list of field IDs for selected rows (M5 multi-select)."""
        ids = []
        seen_rows = set()
        for item in self.table.selectedItems():
            if item.column() != 0:
                continue
            row = item.row()
            if row in seen_rows:
                continue
            seen_rows.add(row)
            fid = item.data(QtCore.Qt.UserRole)
            if fid is not None:
                ids.append(fid)
        return ids

    def _selected_field_id(self):
        """Return field ID for current or first selected row (works when Delete/Edit gets focus)."""
        row = self.table.currentRow()
        if row < 0:
            # Focus moved to button; use first selected row if any
            rows = set()
            for item in self.table.selectedItems():
                if item.column() == 0:
                    rows.add(item.row())
            if not rows:
                return None
            row = min(rows)
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        try:
            fields = self.repo.list_template_fields(self.template_id)
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        dlg = FieldEditDialog(existing_fields=fields, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        try:
            self.repo.add_template_field(
                self.template_id,
                data["name"],
                data["label"],
                data["data_type"],
                data["unit"],
                data["required"],
                data["sort_order"],
                data["group_name"],
                data["calc_type"],
                data["calc_ref1_name"],
                data["calc_ref2_name"],
                data.get("calc_ref3_name"),
                data.get("calc_ref4_name"),
                data.get("calc_ref5_name"),
                data.get("calc_ref6_name"),
                data.get("calc_ref7_name"),
                data.get("calc_ref8_name"),
                data.get("calc_ref9_name"),
                data.get("calc_ref10_name"),
                data.get("calc_ref11_name"),
                data.get("calc_ref12_name"),
                data["tolerance"],
                data.get("autofill_from_first_group", False),
                data.get("default_value"),
                data.get("tolerance_type"),
                data.get("tolerance_equation"),
                data.get("nominal_value"),
                data.get("tolerance_lookup_json"),
                data.get("sig_figs", 3),
                data.get("stat_value_group"),
                data.get("plot_x_axis_name"),
                data.get("plot_y_axis_name"),
                data.get("plot_title"),
                data.get("plot_x_min"),
                data.get("plot_x_max"),
                data.get("plot_y_min"),
                data.get("plot_y_max"),
                data.get("plot_best_fit", False),
            )
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()

    def on_edit(self):
        field_id = self._selected_field_id()
        if not field_id:
            return
        fields = self.repo.list_template_fields(self.template_id)
        field = next((f for f in fields if f["id"] == field_id), None)
        if not field:
            return
        dlg = FieldEditDialog(field=field, existing_fields=fields, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        data["id"] = field_id
        self.repo.update_template_field(field_id, data)
        self._load_fields()

    def on_delete(self):
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select one or more field rows to delete.",
            )
            return
        n = len(ids)
        msg = f"Delete {n} field(s)?" if n > 1 else "Delete this field?"
        resp = QtWidgets.QMessageBox.question(
            self, "Delete field(s)", msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return
        try:
            for field_id in ids:
                self.repo.delete_template_field(field_id)
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()

    def on_explain_tolerance(self):
        """H6: Open Explain tolerance dialog for selected field."""
        field_id = self._selected_field_id()
        if not field_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Select a field to explain its tolerance.",
            )
            return
        try:
            fields = self.repo.list_template_fields(self.template_id)
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        field = next((f for f in fields if f["id"] == field_id), None)
        if not field:
            return
        dlg = ExplainToleranceDialog(field, parent=self)
        dlg.exec_()

    def on_batch_change_equation(self):
        """Batch set tolerance equation for selected fields (sets type to equation)."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select one or more rows to apply a tolerance equation to."
            )
            return
        tol_eq, ok = QtWidgets.QInputDialog.getText(
            self,
            "Batch change tolerance equation",
            "Equation (Excel-like, e.g. 0.02 * ABS(nominal)). Applied to selected fields with equation-compatible calc type:",
            QtWidgets.QLineEdit.Normal,
            "0.02 * ABS(nominal)",
        )
        if not ok or not tol_eq.strip():
            return
        tol_eq = tol_eq.strip()
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                if f.get("calc_type") not in ("ABS_DIFF", "PCT_ERROR", "PCT_DIFF", "MIN_OF", "MAX_OF", "RANGE_OF"):
                    continue
                data = dict(f)
                data["tolerance_type"] = "equation"
                data["tolerance_equation"] = tol_eq
                self.repo.update_template_field(fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied equation to {applied} field(s)."
        )

    def on_batch_apply_unit(self):
        """Set unit for selected fields."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select one or more rows to apply a unit to."
            )
            return
        unit, ok = QtWidgets.QInputDialog.getText(
            self,
            "Batch apply unit",
            "Unit to apply to selected fields (e.g. °F, °C, mm). Leave empty to clear:",
            QtWidgets.QLineEdit.Normal,
            "",
        )
        if not ok:
            return
        unit = unit.strip() or None
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                data = dict(f)
                data["unit"] = unit
                self.repo.update_template_field(fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied unit to {applied} field(s)."
        )

    def on_batch_set_decimal(self):
        """Set decimal places (0-4) for selected fields that support it (number, convert, reference, tolerance)."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select one or more rows to set decimal places for."
            )
            return
        decimals, ok = QtWidgets.QInputDialog.getInt(
            self,
            "Batch set numbers after decimal",
            "Numbers after decimal (0-4) for selected number, convert, reference, tolerance, and stat fields:",
            3,
            0,
            4,
        )
        if not ok:
            return
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            supported = ("number", "convert", "tolerance", "reference", "stat")
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                if (f.get("data_type") or "").strip().lower() not in supported:
                    continue
                data = dict(f)
                data["sig_figs"] = decimals
                self.repo.update_template_field(fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied {decimals} decimal place(s) to {applied} field(s)."
        )

    def on_batch_set_group(self):
        """Set group name for selected fields."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select one or more rows to set the group for."
            )
            return
        group_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Batch set group",
            "Group name to apply to selected fields (leave empty to clear):",
            QtWidgets.QLineEdit.Normal,
            "",
        )
        if not ok:
            return
        group_name = group_name.strip() or None
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                data = dict(f)
                data["group_name"] = group_name
                self.repo.update_template_field(fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied group to {applied} field(s)."
        )

    def on_dup_group(self):
        try:
            fields = self.repo.list_template_fields(self.template_id)
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        if not fields:
            return

        # All existing group names
        groups = sorted({f.get("group_name") or "" for f in fields})
        groups = [g for g in groups if g]

        if not groups:
            QtWidgets.QMessageBox.information(
                self,
                "No groups",
                "There are no group names defined to duplicate.",
            )
            return

        # Choose source group
        src_group, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Source group",
            "Duplicate which group?",
            groups,
            0,
            False,
        )
        if not ok or not src_group:
            return

        # New group name
        new_group, ok = QtWidgets.QInputDialog.getText(
            self,
            "New group name",
            "New group name:",
            text=f"{src_group} copy",
        )
        if not ok or not new_group.strip():
            return
        new_group = new_group.strip()

        # Optional suffix replacement for internal names (e.g. '_1' -> '_2')
        old_suffix, ok = QtWidgets.QInputDialog.getText(
            self,
            "Internal name suffix (optional)",
            "Replace this text in internal names (e.g. _1):",
            text="",
        )
        if not ok:
            return
        new_suffix = ""
        if old_suffix:
            new_suffix, ok = QtWidgets.QInputDialog.getText(
                self,
                "New suffix",
                "With this text (e.g. _2):",
                text="",
            )
            if not ok:
                return

        # Source fields in that group
        source_fields = [f for f in fields if (f.get("group_name") == src_group)]
        if not source_fields:
            return

        # Base of the source group (e.g. 100)
        group_min = min((f.get("sort_order") or 0) for f in source_fields)
        block_size = 100
        new_block_start = ((group_min // block_size) + 1) * block_size

        try:
            for f in source_fields:
                old_sort = f.get("sort_order") or 0
                offset = old_sort - group_min
                new_sort = new_block_start + offset

                name = f["name"]
                label = f["label"]
                if old_suffix and new_suffix:
                    name = name.replace(old_suffix, new_suffix)
                    label = label.replace(old_suffix, new_suffix)

                calc_type = f.get("calc_type")
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                tol = f.get("tolerance")

                ref3 = f.get("calc_ref3_name")
                ref4 = f.get("calc_ref4_name")
                ref5 = f.get("calc_ref5_name")
                ref6 = f.get("calc_ref6_name")
                ref7 = f.get("calc_ref7_name")
                ref8 = f.get("calc_ref8_name")
                ref9 = f.get("calc_ref9_name")
                ref10 = f.get("calc_ref10_name")
                ref11 = f.get("calc_ref11_name")
                ref12 = f.get("calc_ref12_name")
                if calc_type in ("ABS_DIFF", "PCT_ERROR", "PCT_DIFF", "MIN_OF", "MAX_OF", "RANGE_OF", "CUSTOM_EQUATION") and old_suffix and new_suffix:
                    if ref1:
                        ref1 = ref1.replace(old_suffix, new_suffix)
                    if ref2:
                        ref2 = ref2.replace(old_suffix, new_suffix)
                    if ref3:
                        ref3 = ref3.replace(old_suffix, new_suffix)
                    if ref4:
                        ref4 = ref4.replace(old_suffix, new_suffix)
                    if ref5:
                        ref5 = ref5.replace(old_suffix, new_suffix)
                    if ref6:
                        ref6 = ref6.replace(old_suffix, new_suffix)
                    if ref7:
                        ref7 = ref7.replace(old_suffix, new_suffix)
                    if ref8:
                        ref8 = ref8.replace(old_suffix, new_suffix)
                    if ref9:
                        ref9 = ref9.replace(old_suffix, new_suffix)
                    if ref10:
                        ref10 = ref10.replace(old_suffix, new_suffix)
                    if ref11:
                        ref11 = ref11.replace(old_suffix, new_suffix)
                    if ref12:
                        ref12 = ref12.replace(old_suffix, new_suffix)

                self.repo.add_template_field(
                    self.template_id,
                    name,
                    label,
                    f["data_type"],
                    f.get("unit"),
                    bool(f.get("required")),
                    new_sort,
                    new_group,
                    calc_type,
                    ref1,
                    ref2,
                    ref3,
                    ref4,
                    ref5,
                    ref6,
                    ref7,
                    ref8,
                    ref9,
                    ref10,
                    ref11,
                    ref12,
                    tol,
                    bool(f.get("autofill_from_first_group", 0)),
                    f.get("default_value"),
                    f.get("tolerance_type"),
                    f.get("tolerance_equation"),
                    f.get("nominal_value"),
                    f.get("tolerance_lookup_json"),
                    f.get("sig_figs", 3),
                    f.get("stat_value_group"),
                    f.get("plot_x_axis_name"),
                    f.get("plot_y_axis_name"),
                    f.get("plot_title"),
                    f.get("plot_x_min"),
                    f.get("plot_x_max"),
                    f.get("plot_y_min"),
                    f.get("plot_y_max"),
                    bool(f.get("plot_best_fit", 0)),
                )
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return

        self._load_fields()


class CalibrationHistoryDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        inst = self.repo.get_instrument(instrument_id)
        tag = inst.get("tag_number", str(instrument_id)) if inst else str(instrument_id)
        self.setWindowTitle(f"Calibration History - {tag}")
        # Size to ~80% of available screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            w = int(geom.width() * 0.8)
            h = int(geom.height() * 0.8)
            self.resize(w, h)
        else:
            self.resize(900, 600)

        layout = QtWidgets.QVBoxLayout(self)

        # Instrument info label
        info = []
        if inst:
            info.append(f"ID: {inst.get('tag_number', '')}")
            if inst.get("location"):
                info.append(f"Location: {inst['location']}")
            if inst.get("last_cal_date"):
                info.append(f"Last cal: {inst['last_cal_date']}")
        info_label = QtWidgets.QLabel(" | ".join(info))
        layout.addWidget(info_label)

        # Show archived checkbox
        self.show_archived_check = QtWidgets.QCheckBox("Show archived")
        self.show_archived_check.setToolTip("Include archived (soft-deleted) calibration records")
        self.show_archived_check.toggled.connect(self._load_records)
        layout.addWidget(self.show_archived_check)

        # Table of records (Date, Template, Performed by, Result, State)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Template", "Performed by", "Result", "State"]
        )
        
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.table)

        # Details area: tolerance values as table, pass/fail per point; groups highlighted green/red
        self.details_label = QtWidgets.QLabel("Tolerance values (pass/fail):")
        self.details_label.setToolTip("Pass/fail per tolerance point. Point, Tolerance, and Result columns. Groups highlighted green (pass) or red (fail).")
        layout.addWidget(self.details_label)
        self.details_table = QtWidgets.QTableWidget()
        self.details_table.setColumnCount(3)
        self.details_table.setHorizontalHeaderLabels(["Point", "Tolerance", "Result"])
        header = self.details_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)   # Point
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)            # Tolerance - fills remaining space
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)   # Result
        self.details_table.setAlternatingRowColors(False)  # we color by group
        self.details_table.setWordWrap(False)
        self.details_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.details_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.details_table, 1)  # stretch so table takes space
        self.details_notes_label = QtWidgets.QLabel("")
        self.details_notes_label.setWordWrap(True)
        self.details_notes_label.setStyleSheet("color: gray; margin-top: 4px;")
        layout.addWidget(self.details_notes_label)

        # Buttons with better organization and tooltips (grid allows wrapping)
        btn_layout = QtWidgets.QGridLayout()
        
        # Primary actions
        self.btn_new = QtWidgets.QPushButton("➕ New Calibration")
        self.btn_new.setToolTip("Create a new calibration record")
        self.btn_new.setMinimumWidth(120)
        self.btn_view = QtWidgets.QPushButton("✏️ View/Edit")
        self.btn_view.setToolTip("View or edit the selected calibration")
        self.btn_view.setMinimumWidth(100)
        self.btn_export_pdf = QtWidgets.QPushButton("📄 Export PDF")
        self.btn_export_pdf.setToolTip("Export selected calibration to PDF")
        self.btn_export_pdf.setMinimumWidth(100)
        
        # Secondary actions
        self.btn_open_file = QtWidgets.QPushButton("📎 Open File")
        self.btn_open_file.setToolTip("Open attached calibration file")
        self.btn_open_file.setMinimumWidth(110)
        self.btn_delete_file = QtWidgets.QPushButton("🗑️ Delete")
        self.btn_delete_file.setToolTip("Archive (recommended) or delete permanently")
        self.btn_delete_file.setMinimumWidth(80)
        
        # Close and Help buttons
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.setDefault(True)
        self.btn_close.setMinimumWidth(80)
        self.btn_help = QtWidgets.QPushButton("?")
        self.btn_help.setToolTip("Help")
        self.btn_help.setMaximumWidth(36)
        self.btn_help.clicked.connect(self._show_help)

        btn_layout.addWidget(self.btn_new, 0, 0)
        btn_layout.addWidget(self.btn_view, 0, 1)
        btn_layout.addWidget(self.btn_export_pdf, 0, 2)
        btn_layout.addWidget(self.btn_open_file, 0, 3)
        btn_layout.addWidget(self.btn_delete_file, 0, 4)
        btn_layout.addWidget(self.btn_close, 1, 0)
        btn_layout.addWidget(self.btn_help, 1, 1)
        layout.addLayout(btn_layout)

        self.btn_new.clicked.connect(self.on_new_cal)
        self.btn_view.clicked.connect(self.on_view_edit)
        self.btn_export_pdf.clicked.connect(self.on_export_pdf)
        self.btn_open_file.clicked.connect(self.on_open_file)
        self.btn_delete_file.clicked.connect(self.on_delete_file)
        self.btn_close.clicked.connect(self.accept)

        self.table.itemSelectionChanged.connect(self._update_details)

        self._load_records()

    def _show_help(self):
        title, content = get_help_content("CalibrationHistoryDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()
    
    def on_open_file(self):
        atts = self._attachments_for_selected_record()
        if not atts:
            QtWidgets.QMessageBox.information(
                self,
                "No file",
                "No external calibration file is attached to this record.",
            )
            return

        # If multiple, just open the first; you can fancy it up later
        att = atts[0]
        path = att.get("file_path")
        if not path:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing file",
                "This attachment has no stored file path.",
            )
            return

        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def on_delete_file(self):
        """Archive (recommended) or delete permanently the selected calibration record."""
        rec_id = self._selected_record_id()
        if not rec_id:
            return

        rec = self.repo.get_calibration_record(rec_id)
        if not rec:
            return

        row = self.table.currentRow()
        cal_date = ""
        tpl_name = ""
        if row >= 0:
            item_date = self.table.item(row, 0)
            item_tpl = self.table.item(row, 1)
            if item_date:
                cal_date = item_date.text()
            if item_tpl:
                tpl_name = item_tpl.text()

        desc = cal_date or f"Record #{rec_id}"
        if tpl_name:
            desc += f" ({tpl_name})"

        is_already_archived = bool(rec.get("deleted_at"))

        if is_already_archived:
            resp = QtWidgets.QMessageBox.question(
                self,
                "Delete permanently",
                f"Calibration entry:\n\n{desc}\n\n"
                "This record is archived. Delete permanently?\n"
                "This will remove all data and attached files. Cannot be undone.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if resp != QtWidgets.QMessageBox.Yes:
                return
            try:
                reason, ok = QtWidgets.QInputDialog.getText(
                    self, "Reason for deletion", "Reason (optional, for audit log):",
                    QtWidgets.QLineEdit.Normal, "",
                )
                if not ok:
                    return
                self.repo.delete_calibration_record(rec_id, reason=(reason or "").strip() or None)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error deleting", str(e))
                return
        else:
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("Delete calibration entry")
            box.setText(f"Calibration entry:\n\n{desc}\n\nChoose an action:")
            box.setInformativeText(
                "• Archive: Hide from list but keep data (recommended)\n"
                "• Delete permanently: Remove completely (cannot be undone)"
            )
            archive_btn = box.addButton("Archive", QtWidgets.QMessageBox.ActionRole)
            delete_btn = box.addButton("Delete permanently", QtWidgets.QMessageBox.DestructiveRole)
            cancel_btn = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(archive_btn)
            delete_btn.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; }")
            box.exec_()

            clicked = box.clickedButton()
            if clicked == cancel_btn:
                return
            if clicked == archive_btn:
                try:
                    self.repo.archive_calibration_record(rec_id, reason="Archived from history dialog")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Archive failed", str(e))
                    return
            else:
                reason, ok = QtWidgets.QInputDialog.getText(
                    self, "Reason for deletion", "Reason (optional, for audit log):",
                    QtWidgets.QLineEdit.Normal, "",
                )
                if not ok:
                    return
                try:
                    self.repo.delete_calibration_record(rec_id, reason=(reason or "").strip() or None)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Delete failed", str(e))
                    return

        self._load_records()
        self._update_details()

    def _attachments_for_selected_record(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            return []
        return self.repo.list_attachments_for_record(rec_id)


    def _ensure_external_template(self, instrument_type_id: int) -> dict | None:
        """
        Ensure a simple 'External calibration (file only)' template exists
        for this instrument type. Return the template row as dict.
        """
        templates = self.repo.list_templates_for_type(instrument_type_id, active_only=False)
        for t in templates:
            if t["name"] == "External calibration (file only)":
                return t

        tpl_id = self.repo.create_template(
            instrument_type_id,
            "External calibration (file only)",
            version=1,
            is_active=True,
            notes="Template used for out-of-house calibrations with attached file only.",
        )
        return self.repo.get_template(tpl_id)

    def _load_records(self):
        include_archived = getattr(self, "show_archived_check", None) and self.show_archived_check.isChecked()
        recs = self.repo.list_calibration_records_for_instrument(
            self.instrument_id, include_archived=include_archived
        )
        self.table.setRowCount(len(recs))
        for row, r in enumerate(recs):
            item_date = QtWidgets.QTableWidgetItem(r.get("cal_date", ""))
            tpl_name = r.get("template_name", "")
            tpl_ver = r.get("template_version")
            if tpl_ver is not None:
                tpl_name = f"{tpl_name} (v{tpl_ver})" if tpl_name else f"v{tpl_ver}"
            item_tpl = QtWidgets.QTableWidgetItem(tpl_name)
            item_perf = QtWidgets.QTableWidgetItem(r.get("performed_by", "") or "")
            item_result = QtWidgets.QTableWidgetItem(r.get("result", "") or "")
            state = r.get("record_state") or "Draft"
            if r.get("deleted_at"):
                state = "[archived]"
            item_state = QtWidgets.QTableWidgetItem(state)

            item_date.setData(QtCore.Qt.UserRole, r["id"])  # store record_id

            self.table.setItem(row, 0, item_date)
            self.table.setItem(row, 1, item_tpl)
            self.table.setItem(row, 2, item_perf)
            self.table.setItem(row, 3, item_result)
            self.table.setItem(row, 4, item_state)

        if recs:
            self.table.selectRow(0)
        else:
            self.details_table.setRowCount(0)
            self.details_notes_label.setText("")
        self._update_record_buttons()

    def _selected_record_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def _update_record_buttons(self):
        """Enable/disable View/Edit and Delete based on record state."""
        rec_id = self._selected_record_id()
        if not rec_id:
            self.btn_view.setEnabled(True)
            self.btn_delete_file.setEnabled(True)
            return
        rec = self.repo.get_calibration_record(rec_id)
        state = (rec or {}).get("record_state") or "Draft"
        is_archived = bool((rec or {}).get("deleted_at"))
        workflow_locked = state in ("Approved", "Archived")
        self.btn_view.setEnabled(True)
        self.btn_delete_file.setEnabled(is_archived or not workflow_locked)
        if workflow_locked and not is_archived:
            self.btn_delete_file.setToolTip("This record is locked (Approved/Archived) and cannot be archived or deleted.")
        else:
            self.btn_delete_file.setToolTip("Archive (recommended) or delete permanently")

    def _update_details(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            self.details_table.setRowCount(0)
            self.details_notes_label.setText("")
            self._update_record_buttons()
            return

        vals = self.repo.get_calibration_values(rec_id)
        rec = self.repo.get_calibration_record_with_template(rec_id)
        self._update_record_buttons()

        # Merge template field metadata so tolerance_type/equation are always available
        template_fields_by_id = {}
        template_fields = []
        if rec and rec.get("template_id"):
            try:
                template_fields = self.repo.list_template_fields(rec["template_id"])
                for tf in template_fields:
                    template_fields_by_id[tf["id"]] = tf
            except Exception:
                pass

        # Partition values by group (preserve order of first occurrence)
        groups_order = []
        groups_vals = {}
        for v in vals:
            gname = v.get("group_name") or ""
            if gname not in groups_vals:
                groups_order.append(gname)
                groups_vals[gname] = []
            groups_vals[gname].append(v)

        try:
            from tolerance_service import evaluate_pass_fail
        except ImportError:
            evaluate_pass_fail = None

        table_rows = []
        last_group = None

        def _add_row(grp, point, value, tolerance, result):
            """Append a row for the tolerance table. result is PASS/FAIL/Pass/Fail or empty."""
            table_rows.append({
                "group": grp,
                "point": str(point or ""),
                "value": str(value or ""),
                "tolerance": str(tolerance or ""),
                "result": str(result or "").strip(),
            })

        def _add_key(values_by_name, key, val_text):
            """Add a key and its lowercase variant so ref lookup is case-insensitive."""
            if not key:
                return
            values_by_name[key] = val_text
            kl = key.lower()
            if kl != key:
                values_by_name[kl] = val_text

        def _build_values_for_group(group_vals):
            """Build values_by_name from this group's vals only (so refs resolve per-point)."""
            values_by_name = {}
            for v in group_vals:
                val_text = v.get("value_text")
                fn = (v.get("field_name") or "").strip()
                if fn:
                    _add_key(values_by_name, fn, val_text)
                lbl = (v.get("label") or "").strip()
                if lbl and lbl != fn:
                    _add_key(values_by_name, lbl, val_text)
                tf = template_fields_by_id.get(v.get("field_id"))
                if tf:
                    tname = (tf.get("name") or "").strip()
                    tlabel = (tf.get("label") or "").strip()
                    if tname:
                        _add_key(values_by_name, tname, val_text)
                    if tlabel and tlabel != tname:
                        _add_key(values_by_name, tlabel, val_text)
            return values_by_name

        def _default_parse_num(v, u):
            if v is None or v == "":
                return None
            try:
                return float(str(v).strip())
            except (TypeError, ValueError):
                return None

        def _convert_pass_for_group(values_by_name, group_name, _get_value, _get_ref_value_and_unit=None, _parse_numeric=None):
            """Compute convert-type fields for this group and merge into values_by_name."""
            try:
                from tolerance_service import evaluate_tolerance_equation, format_calculation_display
            except ImportError:
                return
            get_ref_and_unit = _get_ref_value_and_unit or (lambda n: (_get_value(n), ""))
            parse_num = _parse_numeric or _default_parse_num
            for tf in template_fields_by_id.values():
                if (tf.get("group_name") or "") != group_name:
                    continue
                if (tf.get("data_type") or "").strip().lower() != "convert":
                    continue
                eq = (tf.get("tolerance_equation") or "").strip()
                if not eq:
                    continue
                vars_map = {"nominal": 0.0, "reading": 0.0}
                for i in range(1, 13):
                    ref_name = tf.get(f"calc_ref{i}_name")
                    if ref_name:
                        rv, runit = get_ref_and_unit(ref_name)
                        if rv not in (None, ""):
                            try:
                                num = parse_num(rv, runit)
                                if num is not None:
                                    vars_map[f"ref{i}"] = num
                                    vars_map[f"val{i}"] = num
                            except (TypeError, ValueError):
                                pass
                try:
                    result = evaluate_tolerance_equation(eq, vars_map)
                    decimals = max(0, min(4, int(tf.get("sig_figs") or 3)))
                    formatted = format_calculation_display(result, decimal_places=decimals)
                    tname = (tf.get("name") or "").strip()
                    tlabel = (tf.get("label") or "").strip()
                    if tname:
                        _add_key(values_by_name, tname, formatted)
                    if tlabel:
                        _add_key(values_by_name, tlabel, formatted)
                except (ValueError, TypeError):
                    pass

        for group_name in groups_order:
            group_vals = groups_vals[group_name]
            values_by_name = _build_values_for_group(group_vals)

            def _get_value(name, _vb=values_by_name):
                if not name:
                    return None
                v = _vb.get(name)
                if v is not None:
                    return v
                s = (name or "").strip()
                v = _vb.get(s)
                if v is not None:
                    return v
                v = _vb.get(s.lower())
                return v

            def _get_ref_value(ref_name, _gv=group_vals):
                """Resolve ref to value: try _get_value first, then match any field in this group by name or label (case-insensitive)."""
                rv = _get_value(ref_name)
                if rv is not None:
                    return rv
                ref_clean = (ref_name or "").strip()
                if not ref_clean:
                    return None
                ref_lower = ref_clean.lower()
                for v in _gv:
                    tf = template_fields_by_id.get(v.get("field_id"))
                    if not tf:
                        continue
                    fn = (tf.get("name") or "").strip()
                    fl = (tf.get("label") or "").strip()
                    if fn.lower() == ref_lower or fl.lower() == ref_lower:
                        return v.get("value_text")
                return None

            def _get_ref_value_and_unit(ref_name, _gv=group_vals):
                """Like _get_ref_value but also return the ref field's unit (for stripping when parsing). Returns (value_text, unit)."""
                rv = _get_value(ref_name)
                if rv is not None:
                    ref_clean = (ref_name or "").strip()
                    ref_lower = ref_clean.lower() if ref_clean else ""
                    for v in _gv:
                        tf = template_fields_by_id.get(v.get("field_id"))
                        if not tf:
                            continue
                        fn = (tf.get("name") or "").strip()
                        fl = (tf.get("label") or "").strip()
                        if fn.lower() == ref_lower or fl.lower() == ref_lower:
                            return (rv, (tf.get("unit") or "").strip())
                    return (rv, "")
                ref_clean = (ref_name or "").strip()
                if not ref_clean:
                    return (None, "")
                ref_lower = ref_clean.lower()
                for v in _gv:
                    tf = template_fields_by_id.get(v.get("field_id"))
                    if not tf:
                        continue
                    fn = (tf.get("name") or "").strip()
                    fl = (tf.get("label") or "").strip()
                    if fn.lower() == ref_lower or fl.lower() == ref_lower:
                        return (v.get("value_text"), (tf.get("unit") or "").strip())
                return (None, "")

            def _parse_numeric_stripping_unit(val_text, unit):
                """Parse value as float, stripping trailing unit (e.g. '122.0 °F' with unit '°F' -> 122.0)."""
                if val_text is None or val_text == "":
                    return None
                s = str(val_text).strip()
                if not s:
                    return None
                u = (unit or "").strip()
                if u:
                    if s.endswith(u):
                        s = s[:-len(u)].strip()
                    elif s.endswith(" " + u):
                        s = s[:-len(" " + u)].strip()
                try:
                    return float(s)
                except (TypeError, ValueError):
                    return None

            _convert_pass_for_group(values_by_name, group_name, lambda n: _get_ref_value(n), _get_ref_value_and_unit, _parse_numeric_stripping_unit)

            def _point_prefix(ref1_name, ref2_name):
                """Label and value of the two refs used to calculate this point. Replaces group name."""
                def _find_label(rn):
                    if not (rn or "").strip():
                        return None
                    rc = (rn or "").strip()
                    rl = rc.lower()
                    for tf in template_fields:
                        n = (tf.get("name") or "").strip()
                        l = (tf.get("label") or "").strip()
                        if n.lower() == rl or l.lower() == rl:
                            return l if l else n
                    return rc
                parts = []
                for rn in ((ref1_name or "").strip(), (ref2_name or "").strip()):
                    if not rn:
                        continue
                    lbl = _find_label(rn)
                    val = _get_value(rn)
                    val_str = str(val).strip() if val not in (None, "") else "—"
                    parts.append(f"{lbl or rn} ({val_str})")
                return ", ".join(parts) + ": " if parts else ""

            by_field_id = {v.get("field_id"): v for v in group_vals}
            fields_in_group = [f for f in template_fields_by_id.values() if (f.get("group_name") or "") == group_name]
            fields_in_group.sort(key=lambda x: (x.get("sort_order") or 0, x.get("id") or 0))

            for f in fields_in_group:
                # Plot fields: data is stored but not shown here; chart appears in PDF export only
                if (f.get("data_type") or "").strip().lower() == "plot":
                    continue
                # Field header: display-only header for the group; no value to show in details
                if (f.get("data_type") or "").strip().lower() == "field_header":
                    continue
                fid = f.get("id")
                v = by_field_id.get(fid)
                if v is None:
                    v = {}
                tf = template_fields_by_id.get(fid) or f
                v_merged = dict(v)
                for key in ("group_name", "label", "unit", "calc_type", "data_type", "tolerance_type",
                            "tolerance_equation", "tolerance", "nominal_value", "tolerance_lookup_json",
                            "calc_ref1_name", "calc_ref2_name", "calc_ref3_name", "calc_ref4_name", "calc_ref5_name"):
                    if (v_merged.get(key) is None or v_merged.get(key) == "") and tf.get(key) not in (None, ""):
                        v_merged[key] = tf[key]
                v_merged["field_id"] = fid
                v = v_merged
                label = v.get("label") or v.get("field_name") or ""
                unit = v.get("unit") or ""
                val_txt = v.get("value_text")
                if val_txt is None and fid and _get_value((f.get("name") or "").strip()):
                    val_txt = _get_value((f.get("name") or "").strip())
                if val_txt is None and (f.get("data_type") or "").strip().lower() == "convert":
                    val_txt = _get_value((f.get("label") or f.get("name") or "").strip())
                calc_type = v.get("calc_type")
                data_type = v.get("data_type") or ""
                tol_type = v.get("tolerance_type") or "fixed"

                last_group = group_name

                unit_str = f" {unit}" if unit else ""

                # Cal history shows only tolerance values (pass/fail results)

                # 1) Computed difference fields (ABS_DIFF, etc.) with tolerance
                if calc_type in ("ABS_DIFF", "PCT_ERROR", "PCT_DIFF", "MIN_OF", "MAX_OF", "RANGE_OF"):
                    if not val_txt:
                        continue
                    try:
                        diff = abs(float(str(val_txt).strip()))
                    except Exception:
                        diff = None
                    if diff is None:
                        continue

                    tol_raw = v.get("tolerance")
                    tol_fixed = None
                    if tol_raw not in (None, ""):
                        try:
                            tol_fixed = float(str(tol_raw))
                        except Exception:
                            pass

                    status = ""
                    tol_used = ""
                    display_parts = None  # (lhs, op, rhs, pass) for equation comparison display
                    if evaluate_pass_fail and (tol_fixed is not None or v.get("tolerance_equation") or v.get("tolerance_lookup_json")):
                        ref1_name = v.get("calc_ref1_name")
                        ref2_name = v.get("calc_ref2_name")
                        ref3_name = v.get("calc_ref3_name")
                        ref4_name = v.get("calc_ref4_name")
                        ref5_name = v.get("calc_ref5_name")
                        nominal = 0.0
                        nominal_str = v.get("nominal_value")
                        if nominal_str not in (None, ""):
                            try:
                                nominal = float(str(nominal_str).strip())
                            except Exception:
                                pass
                        vars_map = {"nominal": nominal, "reading": diff}
                        for i, r in enumerate((ref1_name, ref2_name, ref3_name, ref4_name, ref5_name), 1):
                            if r:
                                rv = _get_value(r)
                                if rv is not None:
                                    try:
                                        vars_map[f"ref{i}"] = float(rv or 0)
                                    except (TypeError, ValueError):
                                        vars_map[f"ref{i}"] = 0.0
                        # Equation tolerance: show "calculated op compared, PASS/FAIL"
                        if tol_type == "equation" and v.get("tolerance_equation"):
                            try:
                                from tolerance_service import equation_tolerance_display
                                display_parts = equation_tolerance_display(v.get("tolerance_equation"), vars_map)
                            except ImportError:
                                pass
                        if display_parts is None:
                            try:
                                pass_, tol_val, _ = evaluate_pass_fail(
                                    tol_type,
                                    tol_fixed,
                                    v.get("tolerance_equation"),
                                    nominal,
                                    diff,
                                    vars_map=vars_map,
                                    tolerance_lookup_json=v.get("tolerance_lookup_json"),
                                )
                                status = "\u2713 PASS" if pass_ else "\u2717 FAIL"
                                # Only show "tol ±X" when it's a tolerance band, not a comparison (0/1)
                                if tol_val is not None and tol_val != 0 and not (abs(tol_val - round(tol_val)) < 1e-9 and 0 <= tol_val <= 1):
                                    tol_used = f" (tol ±{tol_val})"
                            except Exception:
                                if tol_fixed is not None:
                                    status = "\u2713 PASS" if diff <= tol_fixed else "\u2717 FAIL"
                    elif tol_fixed is not None:
                        status = "\u2713 PASS" if diff <= tol_fixed else "\u2717 FAIL"

                    pt = _point_prefix(ref1_name, ref2_name)
                    point_str = f"{pt}{label}"
                    if display_parts is not None:
                        lhs, op_str, rhs, pass_ = display_parts
                        from tolerance_service import format_calculation_display
                        _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                        val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                        _add_row(group_name, point_str, val_str, "", "PASS" if pass_ else "FAIL")
                    else:
                        try:
                            num_val = float(str(val_txt).strip())
                            from tolerance_service import format_calculation_display
                            _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                            val_display = format_calculation_display(num_val, decimal_places=_dec)
                        except (TypeError, ValueError):
                            val_display = val_txt
                        res = ("\u2713 PASS" if "PASS" in (status or "") else "\u2717 FAIL") if status else ""
                        _add_row(group_name, point_str, f"{val_display}{unit_str}", tol_used, res)
                    continue

                # 2) Convert-type fields: do not display in tolerance (pass/fail) section
                if (f.get("data_type") or "").strip().lower() == "convert":
                    continue

                # 3) Bool fields with bool tolerance — display single "Pass" or "Fail" (not "True ✓ PASS" / "Pass, Pass")
                if data_type == "bool" and tol_type == "bool":
                    pass_when = (v.get("tolerance_equation") or "true").strip().lower()
                    reading_bool = val_txt in ("1", "true", "yes", "on")
                    pt = _point_prefix(None, None)  # bool has no two refs
                    point_str = f"{pt}{label}"
                    if pass_when not in ("true", "false"):
                        _add_row(group_name, point_str, "Pass" if reading_bool else "Fail", "", "")
                        continue
                    reading_float = 1.0 if reading_bool else 0.0
                    result = "Fail"
                    if evaluate_pass_fail:
                        try:
                            pass_, _, _ = evaluate_pass_fail(
                                "bool", None, pass_when, 0.0, reading_float,
                                vars_map={}, tolerance_lookup_json=None,
                            )
                            result = "Pass" if pass_ else "Fail"
                        except Exception:
                            pass
                    _add_row(group_name, point_str, "", "", result)
                    continue

                # 4) Tolerance-type (data_type "tolerance") fields: not stored; evaluate from this group's values (in sort order)
                if (f.get("data_type") or "").strip().lower() == "tolerance":
                    eq = (f.get("tolerance_equation") or "").strip()
                    if eq:
                        nominal = 0.0
                        nominal_str = f.get("nominal_value")
                        if nominal_str not in (None, ""):
                            try:
                                nominal = float(str(nominal_str).strip())
                            except (TypeError, ValueError):
                                pass
                        vars_map = {"nominal": nominal, "reading": 0.0}
                        for i in range(1, 13):
                            ref_name = f.get(f"calc_ref{i}_name")
                            if ref_name:
                                rv, runit = _get_ref_value_and_unit(ref_name)
                                if rv not in (None, ""):
                                    num = _parse_numeric_stripping_unit(rv, runit)
                                    if num is not None:
                                        vars_map[f"ref{i}"] = num
                                        vars_map[f"val{i}"] = num
                                    else:
                                        vars_map[f"ref{i}"] = 0.0
                                        vars_map[f"val{i}"] = 0.0
                        try:
                            from tolerance_service import list_variables
                            if "reading" in list_variables(eq):
                                ref1 = f.get("calc_ref1_name")
                                if ref1:
                                    rv1, runit1 = _get_ref_value_and_unit(ref1)
                                    if rv1 not in (None, ""):
                                        num1 = _parse_numeric_stripping_unit(rv1, runit1)
                                        vars_map["reading"] = num1 if num1 is not None else 0.0
                        except ImportError:
                            pass
                        for i in range(1, 13):
                            rk, vk = f"ref{i}", f"val{i}"
                            if rk in vars_map and vk not in vars_map:
                                vars_map[vk] = vars_map[rk]
                            elif vk in vars_map and rk not in vars_map:
                                vars_map[rk] = vars_map[vk]
                        try:
                            from tolerance_service import equation_tolerance_display, list_variables, format_calculation_display
                            required = list_variables(eq)
                            ref1 = f.get("calc_ref1_name")
                            ref2 = f.get("calc_ref2_name")
                            pt = _point_prefix(ref1, ref2)
                            if any(var not in vars_map for var in required):
                                missing = [var for var in required if var not in vars_map]
                                _add_row(group_name, f"{pt}{label}", f"— (need: {', '.join(missing)})", "", "")
                            else:
                                parts = equation_tolerance_display(eq, vars_map)
                                if parts is not None:
                                    lhs, op_str, rhs, pass_ = parts
                                    _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                                    val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                                    _add_row(group_name, f"{pt}{label}", val_str, "", "PASS" if pass_ else "FAIL")
                                elif evaluate_pass_fail:
                                    try:
                                        reading = vars_map.get("reading", 0.0)
                                        pass_, _, _ = evaluate_pass_fail(
                                            "equation", None, eq, nominal, reading,
                                            vars_map=vars_map, tolerance_lookup_json=None,
                                        )
                                        _add_row(group_name, f"{pt}{label}", "", "", "PASS" if pass_ else "FAIL")
                                    except Exception:
                                        pass
                        except (ImportError, ValueError, TypeError):
                            pass
                    continue

                # 4b) Stat-type (data_type "stat") fields: not stored; evaluate equation (e.g. LINEST) and show value
                if (f.get("data_type") or "").strip().lower() == "stat":
                    eq = (f.get("tolerance_equation") or "").strip()
                    if eq:
                        nominal = 0.0
                        nominal_str = f.get("nominal_value")
                        if nominal_str not in (None, ""):
                            try:
                                nominal = float(str(nominal_str).strip())
                            except (TypeError, ValueError):
                                pass
                        vars_map = {"nominal": nominal, "reading": 0.0}
                        for i in range(1, 13):
                            ref_name = f.get(f"calc_ref{i}_name")
                            if ref_name:
                                rv, runit = _get_ref_value_and_unit(ref_name)
                                if rv not in (None, ""):
                                    num = _parse_numeric_stripping_unit(rv, runit)
                                    if num is not None:
                                        vars_map[f"ref{i}"] = num
                                        vars_map[f"val{i}"] = num
                                    else:
                                        vars_map[f"ref{i}"] = 0.0
                                        vars_map[f"val{i}"] = 0.0
                        for i in range(1, 13):
                            rk, vk = f"ref{i}", f"val{i}"
                            if rk in vars_map and vk not in vars_map:
                                vars_map[vk] = vars_map[rk]
                            elif vk in vars_map and rk not in vars_map:
                                vars_map[rk] = vars_map[vk]
                        try:
                            from tolerance_service import evaluate_tolerance_equation, list_variables, format_calculation_display
                            required = list_variables(eq)
                            ref1 = f.get("calc_ref1_name")
                            ref2 = f.get("calc_ref2_name")
                            pt = _point_prefix(ref1, ref2)
                            if any(var not in vars_map for var in required):
                                missing = [var for var in required if var not in vars_map]
                                _add_row(group_name, f"{pt}{label}", f"— (need: {', '.join(missing)})", "", "")
                            else:
                                result = evaluate_tolerance_equation(eq, vars_map)
                                _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                                _add_row(group_name, f"{pt}{label}", format_calculation_display(result, decimal_places=_dec), "", "")
                        except (ImportError, ValueError, TypeError):
                            pt = _point_prefix(f.get("calc_ref1_name"), f.get("calc_ref2_name"))
                            _add_row(group_name, f"{pt}{label}", "—", "", "")
                    continue

                # 5) Other fields with value and tolerance (number, reference, equation, percent, lookup)
                if val_txt is not None and val_txt != "" and (v.get("tolerance_equation") or v.get("tolerance") is not None or tol_type in ("equation", "percent", "lookup")):
                    reading = 0.0
                    try:
                        reading = float(str(val_txt).strip())
                    except (TypeError, ValueError):
                        pass
                    nominal = 0.0
                    nominal_str = v.get("nominal_value")
                    if nominal_str not in (None, ""):
                        try:
                            nominal = float(str(nominal_str).strip())
                        except (TypeError, ValueError):
                            pass
                    vars_map = {"nominal": nominal, "reading": reading}
                    for i in range(1, 13):
                        r = v.get(f"calc_ref{i}_name")
                        if r:
                            rv = _get_value(r)
                            if rv is not None:
                                try:
                                    vars_map[f"ref{i}"] = float(rv or 0)
                                    vars_map[f"val{i}"] = vars_map[f"ref{i}"]
                                except (TypeError, ValueError):
                                    vars_map[f"ref{i}"] = 0.0
                                    vars_map[f"val{i}"] = 0.0
                    display_parts = None
                    if tol_type == "equation" and v.get("tolerance_equation"):
                        try:
                            from tolerance_service import equation_tolerance_display
                            display_parts = equation_tolerance_display(v.get("tolerance_equation"), vars_map)
                        except (ImportError, ValueError, TypeError):
                            pass
                    ref1 = v.get("calc_ref1_name")
                    ref2 = v.get("calc_ref2_name")
                    pt = _point_prefix(ref1, ref2)
                    point_str = f"{pt}{label}"
                    if display_parts is not None:
                        lhs, op_str, rhs, pass_ = display_parts
                        from tolerance_service import format_calculation_display
                        _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                        val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                        _add_row(group_name, point_str, val_str, "", "PASS" if pass_ else "FAIL")
                    else:
                        try:
                            from tolerance_service import format_calculation_display
                            _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                            val_display = format_calculation_display(reading, decimal_places=_dec)
                        except (TypeError, ValueError):
                            val_display = val_txt
                        res = ""
                        if evaluate_pass_fail and (v.get("tolerance_equation") or v.get("tolerance") is not None or v.get("tolerance_lookup_json")):
                            try:
                                tol_fixed = None
                                tol_raw = v.get("tolerance")
                                if tol_raw not in (None, ""):
                                    try:
                                        tol_fixed = float(str(tol_raw))
                                    except (TypeError, ValueError):
                                        pass
                                pass_, _, _ = evaluate_pass_fail(
                                    tol_type,
                                    tol_fixed,
                                    v.get("tolerance_equation"),
                                    nominal,
                                    reading,
                                    vars_map=vars_map,
                                    tolerance_lookup_json=v.get("tolerance_lookup_json"),
                                )
                                res = "\u2713 PASS" if pass_ else "\u2717 FAIL"
                            except Exception:
                                pass
                        _add_row(group_name, point_str, f"{val_display}{unit_str}", "", res)
                    continue

        # Which groups have any FAIL (for row highlighting)
        group_failed = {}
        for row in table_rows:
            r = (row.get("result") or "").upper()
            if "FAIL" in r or row.get("result") == "Fail":
                group_failed[row["group"]] = True
            elif row["group"] not in group_failed:
                group_failed[row["group"]] = False

        if not table_rows:
            self.details_table.setRowCount(1)
            self.details_table.setRowHeight(0, 60)
            if rec and not vals:
                msg = "No data recorded for this calibration.\n\nOpen View/Edit, enter values, and save to see tolerance (equation/boolean) pass/fail results here."
            else:
                msg = "No tolerance (pass/fail) values recorded for this calibration.\n\nTemplates must have equation or boolean tolerance fields (or tolerance on number/computed fields) to show results here."
            self.details_table.setItem(0, 0, QtWidgets.QTableWidgetItem(msg))
            self.details_table.setSpan(0, 0, 1, 3)
            self.details_notes_label.setText("")
        else:
            self.details_table.setRowCount(len(table_rows))
            pass_brush = QtGui.QBrush(QtGui.QColor(220, 255, 220))   # light green
            fail_brush = QtGui.QBrush(QtGui.QColor(255, 220, 220))   # light red
            black_brush = QtGui.QBrush(QtCore.Qt.black)

            for r, row in enumerate(table_rows):
                failed = group_failed.get(row["group"], False) if row["group"] else None
                for c, key in enumerate(["point", "value", "result"]):
                    item = QtWidgets.QTableWidgetItem(row.get(key, ""))
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                    if failed is not None:
                        item.setBackground(fail_brush if failed else pass_brush)
                        item.setForeground(black_brush)
                    self.details_table.setItem(r, c, item)
            self.details_table.resizeRowsToContents()
            template_notes = (rec or {}).get("template_notes", "").strip()
            self.details_notes_label.setText(template_notes if template_notes else "")

    def on_new_cal(self):
        inst = self.repo.get_instrument(self.instrument_id)
        if not inst:
            return

        # Ask: template-based or external-file calibration
        choice, ok = QtWidgets.QInputDialog.getItem(
            self,
            "New calibration",
            "Choose calibration type:",
            ["Use template", "External file (out-of-house)"],
            0,
            False,
        )
        if not ok:
            return

        # Normal internal calibration (existing behavior)
        if choice.startswith("Use"):
            dlg = CalibrationFormDialog(self.repo, inst, parent=self)
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                self._load_records()
                self._update_details()
            return

        # External file calibration
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select external calibration file",
            "",
            "All files (*.*)",
        )
        if not path:
            return

        inst_type_id = inst.get("instrument_type_id")
        if not inst_type_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No instrument type",
                "This instrument does not have an instrument type selected, "
                "so an external calibration cannot be recorded.",
            )
            return

        # Ensure an 'External calibration file' template exists for this instrument type
        templates = self.repo.list_templates_for_type(inst_type_id, active_only=False)
        ext_tpl = None
        for t in templates:
            if t["name"] == "External calibration file":
                ext_tpl = t
                break

        if ext_tpl is None:
            tpl_id = self.repo.create_template(
                inst_type_id,
                name="External calibration file",
                version=1,
                is_active=True,
                notes="Placeholder template for external (file-only) calibrations.",
            )
            tpl_version = 1
        else:
            tpl_id = ext_tpl["id"]
            tpl_version = ext_tpl.get("version", 1)

        today_str = date.today().isoformat()
        performed_by = ""
        result = "PASS"  # can be changed later in edit if needed
        notes = "External calibration file attached."

        # Create a record with no fields
        rec_id = calibration_service.create_calibration_record(
            self.repo,
            inst["id"],
            tpl_id,
            today_str,
            performed_by,
            result,
            notes,
            field_values={},
            template_version=tpl_version,
        )

        # Attach file directly to this record
        try:
            self.repo.add_attachment(self.instrument_id, path, record_id=rec_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error adding attachment",
                f"Calibration record created, but attaching file failed:\n{e}",
            )

        self._load_records()
        self._update_details()

    def on_view_edit(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            return
        inst = self.repo.get_instrument(self.instrument_id)
        rec = self.repo.get_calibration_record_with_template(rec_id)
        state = (rec or {}).get("record_state") or "Draft"
        read_only = state in ("Approved", "Archived")
        dlg = CalibrationFormDialog(
            self.repo, inst, record_id=rec_id, parent=self, read_only=read_only
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self._load_records()
            self._update_details()
    
    def on_export_pdf(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select a calibration record to export.",
            )
            return
        
        # Get default filename
        rec = self.repo.get_calibration_record_with_template(rec_id)
        inst = self.repo.get_instrument(rec["instrument_id"]) if rec else None
        tag = inst.get("tag_number", "calibration") if inst else "calibration"
        cal_date = rec.get("cal_date", "") if rec else ""
        default_name = f"{tag}_{cal_date}.pdf" if cal_date else f"{tag}.pdf"
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export calibration to PDF",
            default_name,
            "PDF files (*.pdf);;All files (*)",
        )
        if not path:
            return
        
        try:
            from pdf_export import export_calibration_to_pdf
            export_calibration_to_pdf(self.repo, rec_id, path)
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Calibration record exported to:\n{path}",
            )
        except PermissionError as e:
            # Handle permission errors with a user-friendly message
            QtWidgets.QMessageBox.warning(
                self,
                "Export failed - Permission denied",
                str(e),
            )
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"PDF Export Error:\n{error_details}")  # Print to console for debugging
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Error exporting to PDF:\n{str(e)}\n\nSee console for details.",
            )
       
class TemplatesDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Calibration Templates")

        layout = QtWidgets.QVBoxLayout(self)

        # Instrument type selector
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Instrument type:"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("", None)
        for t in self.repo.list_instrument_types():
            self.type_combo.addItem(t["name"], t["id"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_layout.addWidget(self.type_combo)
        top_layout.addStretch(1)
        layout.addLayout(top_layout)

        # Templates list
        self.list = QtWidgets.QListWidget()
        layout.addWidget(self.list)

        btn_layout = QtWidgets.QGridLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_clone = QtWidgets.QPushButton("Clone")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_fields = QtWidgets.QPushButton("Fields...")
        for i, btn in enumerate([self.btn_add, self.btn_edit, self.btn_clone, self.btn_delete, self.btn_fields]):
            btn.setMinimumWidth(80)
            btn_layout.addWidget(btn, i // 4, i % 4)
        layout.addLayout(btn_layout)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_clone.clicked.connect(self.on_clone)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_fields.clicked.connect(self.on_fields)

        # auto-select first type if present
        if self.type_combo.count() > 1:
            self.type_combo.setCurrentIndex(1)

    def _current_type_id(self):
        return self.type_combo.currentData()

    def _on_type_changed(self, index):
        self._load_templates()

    def _load_templates(self):
        self.list.clear()
        type_id = self._current_type_id()
        if not type_id:
            return
        templates = self.repo.list_templates_for_type(type_id, active_only=False)
        for t in templates:
            text = f"{t['name']} (v{t['version']})"
            if not t["is_active"]:
                text += " [inactive]"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, t["id"])
            self.list.addItem(item)

    def _current_template_id(self):
        item = self.list.currentItem()
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        type_id = self._current_type_id()
        if not type_id:
            QtWidgets.QMessageBox.warning(
                self, "Instrument type", "Select an instrument type first."
            )
            return
        dlg = TemplateEditDialog(self.repo, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        new_id = self.repo.create_template(
            type_id,
            data["name"],
            data["version"],
            data["is_active"],
            data["notes"],
        )
        try:
            self.repo.set_template_authorized_personnel(new_id, dlg.get_authorized_person_ids())
        except Exception:
            pass
        self._load_templates()

    def on_clone(self):
        """Duplicate current template and all its fields."""
        tpl_id = self._current_template_id()
        if not tpl_id:
            QtWidgets.QMessageBox.information(
                self, "No selection", "Select a template to clone."
            )
            return
        tpl = self.repo.get_template(tpl_id)
        if not tpl:
            QtWidgets.QMessageBox.warning(
                self, "Clone failed", "Template not found."
            )
            return
        type_id = tpl.get("instrument_type_id")
        if not type_id:
            QtWidgets.QMessageBox.warning(
                self, "Clone failed", "Template has no instrument type."
            )
            return
        try:
            new_name = (tpl.get("name") or "Template") + " (copy)"
            new_id = self.repo.create_template(
                type_id, new_name, 1, False, tpl.get("notes") or "",
                status="Draft",
            )
            fields = self.repo.list_template_fields(tpl_id)
            for i, f in enumerate(fields):
                self.repo.add_template_field(
                    new_id,
                    f.get("name", ""),
                    f.get("label", ""),
                    f.get("data_type", "number"),
                    f.get("unit"),
                    bool(f.get("required")),
                    i,
                    f.get("group_name"),
                    f.get("calc_type"),
                    f.get("calc_ref1_name"),
                    f.get("calc_ref2_name"),
                    f.get("calc_ref3_name"),
                    f.get("calc_ref4_name"),
                    f.get("calc_ref5_name"),
                    f.get("calc_ref6_name"),
                    f.get("calc_ref7_name"),
                    f.get("calc_ref8_name"),
                    f.get("calc_ref9_name"),
                    f.get("calc_ref10_name"),
                    f.get("calc_ref11_name"),
                    f.get("calc_ref12_name"),
                    f.get("tolerance"),
                    bool(f.get("autofill_from_first_group", 0)),
                    f.get("default_value"),
                    f.get("tolerance_type"),
                    f.get("tolerance_equation"),
                    f.get("nominal_value"),
                    f.get("tolerance_lookup_json"),
                    f.get("sig_figs", 3),
                    f.get("stat_value_group"),
                    f.get("plot_x_axis_name"),
                    f.get("plot_y_axis_name"),
                    f.get("plot_title"),
                    f.get("plot_x_min"),
                    f.get("plot_x_max"),
                    f.get("plot_y_min"),
                    f.get("plot_y_max"),
                    bool(f.get("plot_best_fit", 0)),
                )
            self._load_templates()
            QtWidgets.QMessageBox.information(
                self, "Cloned", f"Created '{new_name}' with {len(fields)} field(s). Open Fields... to edit."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Clone failed", f"Could not clone template:\n{e}"
            )

    def on_edit(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        tpl = self.repo.get_template(tpl_id)
        if not tpl:
            return
        dlg = TemplateEditDialog(self.repo, template=tpl, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        self.repo.update_template(
            tpl_id,
            data["name"],
            data["version"],
            data["is_active"],
            data["notes"],
            effective_date=data.get("effective_date"),
            change_reason=data.get("change_reason"),
            status=data.get("status"),
        )
        try:
            self.repo.set_template_authorized_personnel(tpl_id, dlg.get_authorized_person_ids())
        except Exception:
            pass
        self._load_templates()

    def on_delete(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        resp = QtWidgets.QMessageBox.question(
            self, "Delete template",
            "Delete this template?\n\nIt must not have calibration records."
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.repo.delete_template(tpl_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error deleting template", str(e))
        self._load_templates()

    def on_fields(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        dlg = TemplateFieldsDialog(self.repo, tpl_id, parent=self)
        dlg.exec_()


class CalibrationFormDialog(QtWidgets.QDialog):
    """
    Dynamic calibration form based on calibration_templates and fields.
    Supports both New and Edit (if record_id provided).
    read_only=True disables edits (Approved/Archived records).
    """
    def __init__(self, repo: CalibrationRepository, instrument: dict,
                 record_id: int | None = None, parent=None, read_only: bool = False):
        super().__init__(parent)
        self.repo = repo
        self.instrument = instrument
        self.record_id = record_id
        self.read_only = read_only
        self.template = None
        self.fields = []
        self.field_widgets = {}  # field_id -> widget

        inst_tag = instrument.get("tag_number", str(instrument["id"]))
        self.setWindowTitle(f"Calibration - {inst_tag}" + (" (read-only)" if read_only else ""))

        layout = QtWidgets.QVBoxLayout(self)

        # Top: basic info
        info_parts = [f"ID: {inst_tag}"]
        if instrument.get("location"):
            info_parts.append(f"Location: {instrument['location']}")
        layout.addWidget(QtWidgets.QLabel(" | ".join(info_parts)))

        # Stack of group pages
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Group navigation
        nav_layout = QtWidgets.QHBoxLayout()
        self.prev_btn = QtWidgets.QPushButton("Previous group")
        self.next_btn = QtWidgets.QPushButton("Next group")
        self.group_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addStretch(1)
        nav_layout.addWidget(self.group_label)
        layout.addLayout(nav_layout)

        self.prev_btn.clicked.connect(self.on_prev_group)
        self.next_btn.clicked.connect(self.on_next_group)

        self.group_names = []
        self.current_group_index = 0


        # Bottom: general cal metadata
        meta_group = QtWidgets.QGroupBox("Calibration metadata")
        meta_layout = QtWidgets.QFormLayout(meta_group)

        self.date_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.dateChanged.connect(self._sync_date_to_all_date_fields)

        # Performed by: personnel combo (from template authorized list or all) + Other
        self.performed_combo = QtWidgets.QComboBox()
        self.performed_combo.setEditable(False)
        self.performed_other_edit = QtWidgets.QLineEdit()
        self.performed_other_edit.setPlaceholderText("Enter name if not in list")
        self.performed_other_edit.setVisible(False)
        self.performed_combo.currentIndexChanged.connect(self._on_performed_combo_changed)
        meta_layout.addRow("Cal date", self.date_edit)
        meta_layout.addRow("Performed by", self.performed_combo)
        meta_layout.addRow("", self.performed_other_edit)

        # Result is auto-assigned from tolerance/boolean pass-fail when saving (no user selection)

        layout.addWidget(meta_group)
        
        # Template notes (read-only, displayed at bottom of every calibration from this template)
        self.template_notes_label = QtWidgets.QLabel("Template Notes:")
        self.template_notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.template_notes_label)
        
        self.template_notes_display = QtWidgets.QPlainTextEdit()
        self.template_notes_display.setReadOnly(True)
        self.template_notes_display.setMinimumHeight(80)
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.template_notes_display.document().setDefaultTextOption(option)
        layout.addWidget(self.template_notes_display)

        # Buttons
        self.btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        self.btn_box.helpRequested.connect(lambda: self._show_help())
        layout.addWidget(self.btn_box)
        
        # Set initial dialog size
        self.resize(950, 600)

        if self.record_id is None:
            self._init_new()
        else:
            self._init_edit()
        if self.read_only:
            self._set_read_only()
    
    def _sync_date_to_all_date_fields(self, new_date):
        """When Cal date is changed, set all date-type template fields to the same date."""
        if not hasattr(self, "fields") or not hasattr(self, "field_widgets"):
            return
        for f in self.fields:
            if (f.get("data_type") or "").strip().lower() != "date":
                continue
            fid = f.get("id")
            w = self.field_widgets.get(fid)
            if w and isinstance(w, QtWidgets.QDateEdit):
                w.blockSignals(True)
                w.setDate(new_date)
                w.blockSignals(False)

    def _on_performed_combo_changed(self, index):
        is_other = self.performed_combo.currentText() == "Other..."
        self.performed_other_edit.setVisible(is_other)
        if is_other:
            self.performed_other_edit.setFocus()

    def _build_performed_by_combo(self):
        """Populate Performed by combo from template-authorized personnel or all personnel."""
        self.performed_combo.clear()
        try:
            if self.template and self.template.get("id"):
                people = self.repo.list_personnel_authorized_for_template(self.template["id"])
            else:
                people = self.repo.list_personnel(active_only=True)
            for p in people:
                self.performed_combo.addItem(p.get("name", ""), p.get("id"))
            self.performed_combo.addItem("Other...", None)
            # Default: operator_name from settings if it matches a personnel name
            try:
                op = self.repo.get_setting("operator_name", "") or ""
            except Exception:
                op = ""
            if op:
                idx = self.performed_combo.findText(op)
                if idx >= 0:
                    self.performed_combo.setCurrentIndex(idx)
                elif self.performed_combo.count() > 1:
                    self.performed_combo.setCurrentIndex(0)
        except Exception:
            self.performed_combo.addItem("Other...", None)

    def _set_read_only(self):
        """Disable all inputs and hide OK for Approved/Archived records."""
        self.date_edit.setEnabled(False)
        self.performed_combo.setEnabled(False)
        self.performed_other_edit.setEnabled(False)
        for w in self.field_widgets.values():
            w.setEnabled(False)
        ok_btn = self.btn_box.button(QtWidgets.QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setVisible(False)
        cancel_btn = self.btn_box.button(QtWidgets.QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setText("Close")
        # Result combo removed; result is derived from tolerance pass/fail

    def _show_help(self):
        title, content = get_help_content("CalibrationFormDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def reject(self):
        """Confirm before closing (Escape or Cancel) when filling out a calibration."""
        if self.read_only:
            super().reject()
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Discard calibration?",
            "Are you sure you want to close? Unsaved data will be lost.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            super().reject()
    
    def showEvent(self, event):
        """Override showEvent to ensure dialog is properly displayed."""
        super().showEvent(event)
        # Force layout update and ensure stack widget is visible
        self.updateGeometry()
        if self.stack.count() > 0:
            self._update_group_nav()
            
    def _choose_template_for_instrument(self):
        inst_type_id = self.instrument.get("instrument_type_id")
        if not inst_type_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No instrument type",
                "This instrument does not have an instrument type selected, so "
                "no calibration template can be chosen.",
            )
            return None

        templates = self.repo.list_templates_for_type(inst_type_id, active_only=True)
        if not templates:
            QtWidgets.QMessageBox.warning(
                self,
                "No templates",
                "No calibration templates defined for this instrument type.",
            )
            return None

        if len(templates) == 1:
            return templates[0]

        # Let user choose if multiple
        names = [f"{t['name']} (v{t['version']})" for t in templates]
        items = [names[i] for i in range(len(names))]
        item, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Select template",
            "Calibration template:",
            items,
            0,
            False,
        )
        if not ok:
            return None
        idx = items.index(item)
        return templates[idx]

    def _build_dynamic_form(self):
        # Clear old pages
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        self.field_widgets.clear()

        self.fields = self.repo.list_template_fields(self.template["id"])

        # Split into header vs grouped
        header_fields = [f for f in self.fields if not f.get("group_name")]
        grouped = {}
        for f in self.fields:
            g = f.get("group_name")
            if g:
                grouped.setdefault(g, []).append(f)
        
        # Sort group names by min sort_order
        ordered_groups = []
        for gname, flist in grouped.items():
            min_sort = min((f.get("sort_order") or 0) for f in flist)
            ordered_groups.append((gname, min_sort, flist))
        ordered_groups.sort(key=lambda t: t[1])

        # If there are no named groups, treat header as a single page
        if not ordered_groups and header_fields:
            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            for f in sorted(header_fields, key=lambda f: f.get("sort_order") or 0):
                w = self._create_field_widget(f)
                self.field_widgets[f["id"]] = w
                if (f.get("data_type") or "").strip().lower() == "field_header":
                    form.addRow(w)
                else:
                    label_text = f["label"]
                    if f.get("unit"):
                        label_text += f" ({f['unit']})"
                    form.addRow(label_text, w)
            self.stack.addWidget(page)
            self.group_names = [""]
        else:
            # Build one page per group; header fields go on first page
            first_page = True
            for gname, _, flist in ordered_groups:
                page = QtWidgets.QWidget()
                form = QtWidgets.QFormLayout(page)

                if first_page and header_fields:
                    for f in sorted(header_fields, key=lambda f: f.get("sort_order") or 0):
                        w = self._create_field_widget(f)
                        self.field_widgets[f["id"]] = w
                        if (f.get("data_type") or "").strip().lower() == "field_header":
                            form.addRow(w)
                        else:
                            label_text = f["label"]
                            if f.get("unit"):
                                label_text += f" ({f['unit']})"
                            form.addRow(label_text, w)
                    first_page = False

                for f in sorted(flist, key=lambda f: f.get("sort_order") or 0):
                    w = self._create_field_widget(f)
                    self.field_widgets[f["id"]] = w
                    if (f.get("data_type") or "").strip().lower() == "field_header":
                        form.addRow(w)
                    else:
                        label_text = f["label"]
                        if f.get("unit"):
                            label_text += f" ({f['unit']})"
                        form.addRow(label_text, w)

                self.stack.addWidget(page)

            self.group_names = [gname for (gname, _, _) in ordered_groups]

        self.current_group_index = 0
        self._update_group_nav()

        self._connect_convert_updates()
        self._update_convert_fields()

        # Sync Cal date to all date-type fields (so they match when form is first built)
        if hasattr(self, "date_edit"):
            self._sync_date_to_all_date_fields(self.date_edit.date())

        # Load and display template notes
        if self.template:
            template_notes = str(self.template.get("notes", "") or "")
            self.template_notes_display.setPlainText(template_notes)
            # Hide template notes section if there are no notes
            if not template_notes.strip():
                self.template_notes_label.hide()
                self.template_notes_display.hide()
            else:
                self.template_notes_label.show()
                self.template_notes_display.show()
    
    def _create_field_widget(self, f):
        data_type = f["data_type"]
        w = None

        if data_type == "number":
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText("Number")
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
        elif data_type == "bool":
            w = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(w)
            layout.setContentsMargins(0, 0, 0, 0)
            pass_btn = QtWidgets.QRadioButton("Pass")
            pass_btn.setObjectName("pass_btn")
            fail_btn = QtWidgets.QRadioButton("Fail")
            fail_btn.setObjectName("fail_btn")
            btn_group = QtWidgets.QButtonGroup(w)
            btn_group.addButton(pass_btn)
            btn_group.addButton(fail_btn)
            layout.addWidget(pass_btn)
            layout.addWidget(fail_btn)
            fail_btn.setChecked(True)
        elif data_type == "date" or data_type == "non_affected_date":
            w = QtWidgets.QDateEdit(calendarPopup=True)
            w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(QtCore.QDate.currentDate())
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
        elif data_type == "signature":
            w = QtWidgets.QComboBox()
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
            w.addItem("", None)
            from pathlib import Path
            signatures_dir = Path("Signatures")
            if signatures_dir.exists():
                image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
                for file_path in signatures_dir.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                        w.addItem(file_path.stem, file_path.name)
            default_sig = f.get("default_value")
            if default_sig:
                idx = w.findData(default_sig)
                if idx >= 0:
                    w.setCurrentIndex(idx)
        elif data_type == "reference":
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText("Reference value")
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
            ref_val = f.get("default_value") or ""
            if ref_val:
                w.setText(str(ref_val))
        elif data_type == "tolerance":
            w = QtWidgets.QLineEdit()
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
            w.setReadOnly(True)
            w.setPlaceholderText("—")
            w.setText("—")
        elif data_type == "stat":
            w = QtWidgets.QLineEdit()
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
            w.setReadOnly(True)
            w.setPlaceholderText("—")
            w.setText("—")
        elif data_type == "convert":
            w = QtWidgets.QLineEdit()
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)
            w.setReadOnly(True)
            w.setPlaceholderText("—")
            w.setText("—")
        elif data_type == "field_header":
            w = QtWidgets.QLabel(f.get("label") or f.get("name") or "—")
            font = w.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 2)
            w.setFont(font)
        else:  # text / default
            w = QtWidgets.QLineEdit()
            w.setMinimumWidth(STANDARD_FIELD_WIDTH)

        # Computed fields are read-only
        if f.get("calc_type"):
            if isinstance(w, QtWidgets.QLineEdit):
                w.setReadOnly(True)
            elif isinstance(w, QtWidgets.QCheckBox):
                w.setEnabled(False)
            elif isinstance(w, QtWidgets.QWidget) and w.findChild(QtWidgets.QRadioButton, "pass_btn"):
                w.setEnabled(False)
            elif isinstance(w, QtWidgets.QDateEdit):
                w.setReadOnly(True)
        
        # Set up autofill connections for fields with autofill enabled
        return w

    def _get_unit_for_ref(self, ref_name: str) -> str:
        """Return the unit for the template field matching ref_name (by name or label)."""
        if not ref_name:
            return ""
        ref_clean = (ref_name or "").strip().lower()
        for f in self.fields:
            fn = (f.get("name") or "").strip().lower()
            fl = (f.get("label") or "").strip().lower()
            if fn == ref_clean or fl == ref_clean:
                return (f.get("unit") or "").strip()
        return ""

    @staticmethod
    def _parse_numeric_stripping_unit(val_text, unit: str):
        """Parse value as float, stripping trailing unit (e.g. '122.0 °F' with unit '°F' -> 122.0)."""
        if val_text is None or val_text == "":
            return None
        s = str(val_text).strip()
        if not s:
            return None
        u = (unit or "").strip()
        if u:
            if s.endswith(u):
                s = s[:-len(u)].strip()
            elif s.endswith(" " + u):
                s = s[:-len(" " + u)].strip()
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    def _get_current_values_by_name(self) -> dict[str, str]:
        """Current form values by field name (from widgets). Excludes tolerance, convert, stat, and field_header (display-only)."""
        out = {}
        for f in self.fields:
            dt = f.get("data_type") or ""
            if dt in ("tolerance", "convert", "stat", "field_header"):
                continue
            fid = f["id"]
            name = (f.get("name") or f.get("field_name") or "").strip()
            if not name:
                continue
            w = self.field_widgets.get(fid)
            if not w:
                continue
            if dt == "bool":
                pass_btn = w.findChild(QtWidgets.QRadioButton, "pass_btn") if hasattr(w, "findChild") else None
                out[name] = "1" if (pass_btn and pass_btn.isChecked()) else "0"
            elif dt == "date":
                out[name] = w.date().toString("yyyy-MM-dd") if hasattr(w, "date") else ""
            elif dt == "signature" and isinstance(w, QtWidgets.QComboBox):
                out[name] = w.currentData() or w.currentText() or ""
            else:
                out[name] = (w.text() or "").strip() if hasattr(w, "text") else ""
        return out

    def _update_convert_fields(self):
        """Update read-only convert field widgets from current input values and equations."""
        try:
            from tolerance_service import evaluate_tolerance_equation, format_calculation_display
        except ImportError:
            return
        values_by_name = self._get_current_values_by_name()
        for f in self.fields:
            if (f.get("data_type") or "").strip().lower() != "convert":
                continue
            eq = (f.get("tolerance_equation") or "").strip()
            if not eq:
                continue
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w or not hasattr(w, "setText"):
                continue
            vars_map = {"nominal": 0.0, "reading": 0.0}
            for i in range(1, 13):
                ref_name = f.get(f"calc_ref{i}_name")
                if ref_name and ref_name in values_by_name:
                    v = values_by_name.get(ref_name)
                    if v not in (None, ""):
                        unit = self._get_unit_for_ref(ref_name)
                        num = self._parse_numeric_stripping_unit(v, unit)
                        if num is not None:
                            vars_map[f"ref{i}"] = num
                            vars_map[f"val{i}"] = num
            try:
                result = evaluate_tolerance_equation(eq, vars_map)
                decimals = max(0, min(4, int(f.get("sig_figs") or 3)))
                w.setText(format_calculation_display(result, decimal_places=decimals))
            except (ValueError, TypeError):
                w.setText("—")

    def _update_stat_fields(self):
        """Update read-only stat field widgets from current input values and equations."""
        try:
            from tolerance_service import evaluate_tolerance_equation, format_calculation_display
        except ImportError:
            return
        values_by_name = self._get_current_values_by_name()
        for f in self.fields:
            if (f.get("data_type") or "").strip().lower() != "stat":
                continue
            eq = (f.get("tolerance_equation") or "").strip()
            if not eq:
                continue
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w or not hasattr(w, "setText"):
                continue
            vars_map = {"nominal": 0.0, "reading": 0.0}
            for i in range(1, 13):
                ref_name = f.get(f"calc_ref{i}_name")
                if ref_name and ref_name in values_by_name:
                    v = values_by_name.get(ref_name)
                    if v not in (None, ""):
                        unit = self._get_unit_for_ref(ref_name)
                        num = self._parse_numeric_stripping_unit(v, unit)
                        if num is not None:
                            vars_map[f"ref{i}"] = num
                            vars_map[f"val{i}"] = num
            try:
                result = evaluate_tolerance_equation(eq, vars_map)
                decimals = max(0, min(4, int(f.get("sig_figs") or 3)))
                w.setText(format_calculation_display(result, decimal_places=decimals))
            except (ValueError, TypeError):
                w.setText("—")

    def _connect_convert_updates(self):
        """Connect input widgets so convert and stat fields update when user types."""
        def schedule_update():
            QtCore.QTimer.singleShot(0, lambda: (self._update_convert_fields(), self._update_stat_fields()))

        for f in self.fields:
            dt = f.get("data_type") or ""
            if dt in ("tolerance", "convert", "stat"):
                continue
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w:
                continue
            if dt == "bool":
                pass_btn = w.findChild(QtWidgets.QRadioButton, "pass_btn") if hasattr(w, "findChild") else None
                fail_btn = w.findChild(QtWidgets.QRadioButton, "fail_btn") if hasattr(w, "findChild") else None
                if pass_btn:
                    pass_btn.toggled.connect(schedule_update)
                if fail_btn:
                    fail_btn.toggled.connect(schedule_update)
            elif dt == "date" and hasattr(w, "dateChanged"):
                w.dateChanged.connect(schedule_update)
            elif dt == "signature" and isinstance(w, QtWidgets.QComboBox):
                w.currentIndexChanged.connect(schedule_update)
            elif hasattr(w, "textChanged"):
                w.textChanged.connect(schedule_update)
    
    def _apply_autofill_to_current_group(self):
        """Apply autofill values from the previous group to the currently visible group."""
        # Only apply autofill if we're not on the first group (need a previous group to autofill from)
        if self.current_group_index == 0:
            return
        
        # Get all fields in the previous group that have autofill enabled
        if not self.group_names or len(self.group_names) == 0:
            return
        
        # Find fields in the previous group (the one we just came from)
        prev_group_index = self.current_group_index - 1
        if prev_group_index < 0 or prev_group_index >= len(self.group_names):
            return
        
        prev_group_name = self.group_names[prev_group_index]
        prev_group_fields = [f for f in self.fields if (f.get("group_name") or "") == prev_group_name]
        
        # Get current group name
        current_group_name = ""
        if self.group_names and self.current_group_index < len(self.group_names):
            current_group_name = self.group_names[self.current_group_index]
        
        # Find fields in the current group
        current_group_fields = [f for f in self.fields if (f.get("group_name") or "") == current_group_name]
        
        # For each autofill-enabled field in the CURRENT group, get its value from matching fields in PREVIOUS group
        # This is more intuitive: enable autofill on the field you want to auto-fill
        for current_field in current_group_fields:
            # Check autofill flag - handle both int (0/1) and bool (False/True) and string ("0"/"1")
            autofill_flag = current_field.get("autofill_from_first_group")
            
            # Convert to boolean: 1, True, "1" = True; 0, False, "0", None = False
            try:
                is_autofill = bool(int(autofill_flag)) if autofill_flag is not None else False
            except (ValueError, TypeError):
                is_autofill = bool(autofill_flag) if autofill_flag else False
            
            if not is_autofill:
                continue
            
            current_field_id = current_field["id"]
            if current_field_id not in self.field_widgets:
                continue
            
            current_widget = self.field_widgets[current_field_id]
            current_data_type = current_field.get("data_type", "text")
            
            # Find matching field in the previous group by name or label
            # Try to match by label first (more user-friendly), then by base name (without numeric suffix)
            current_field_name_full = current_field.get("name") or ""
            current_field_label = current_field.get("label") or ""
            
            if not current_field_name_full and not current_field_label:
                continue
            
            # Extract base name by removing trailing numbers (e.g., "date_2" -> "date", "digital_sig_1" -> "digital_sig")
            import re
            current_base_name = re.sub(r'_\d+$', '', current_field_name_full) if current_field_name_full else ""
            
            matched = False
            for prev_field in prev_group_fields:
                prev_field_name = prev_field.get("name") or ""
                prev_field_label = prev_field.get("label") or ""
                prev_base_name = re.sub(r'_\d+$', '', prev_field_name) if prev_field_name else ""
                
                # Match by label first (exact match), then by base name (without suffix)
                match_by_label = prev_field_label and current_field_label and prev_field_label.strip().lower() == current_field_label.strip().lower()
                match_by_base_name = prev_base_name and current_base_name and prev_base_name.strip().lower() == current_base_name.strip().lower()
                
                if match_by_label or match_by_base_name:
                    matched = True
                    prev_field_id = prev_field["id"]
                    if prev_field_id not in self.field_widgets:
                        continue
                    
                    # Get the current value from the previous group's widget
                    prev_widget = self.field_widgets[prev_field_id]
                    
                    # Force widget to process any pending events to ensure value is committed
                    QtWidgets.QApplication.processEvents()
                    
                    value = None
                    
                    if isinstance(prev_widget, QtWidgets.QLineEdit):
                        value = prev_widget.text()
                    elif isinstance(prev_widget, QtWidgets.QCheckBox):
                        value = "1" if prev_widget.isChecked() else "0"
                    elif isinstance(prev_widget, QtWidgets.QWidget):
                        p = prev_widget.findChild(QtWidgets.QRadioButton, "pass_btn")
                        if p is not None:
                            value = "1" if p.isChecked() else "0"
                    elif isinstance(prev_widget, QtWidgets.QDateEdit):
                        value = prev_widget.date().toString("yyyy-MM-dd")
                    elif isinstance(prev_widget, QtWidgets.QComboBox):
                        value = prev_widget.currentData() or ""
                        # Also try currentText if currentData is empty
                        if not value:
                            value = prev_widget.currentText()
                    
                    # Skip only if value is None (not if it's empty string, as empty might be valid)
                    if value is None:
                        continue
                    
                    # Apply the value, blocking signals to prevent recursive updates
                    if isinstance(current_widget, QtWidgets.QLineEdit):
                        current_widget.blockSignals(True)
                        current_widget.setText(value)
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QCheckBox):
                        current_widget.blockSignals(True)
                        current_widget.setChecked(value == "1" or (value and value.lower() == "true"))
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QWidget):
                        p = current_widget.findChild(QtWidgets.QRadioButton, "pass_btn")
                        if p is not None:
                            current_widget.blockSignals(True)
                            is_pass = value == "1" or (value and str(value).lower() in ("true", "yes"))
                            p.setChecked(is_pass)
                            f = current_widget.findChild(QtWidgets.QRadioButton, "fail_btn")
                            if f:
                                f.setChecked(not is_pass)
                            current_widget.blockSignals(False)
                            current_widget.update()
                            current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QDateEdit):
                        current_widget.blockSignals(True)
                        try:
                            date = QtCore.QDate.fromString(value, "yyyy-MM-dd")
                            if date.isValid():
                                current_widget.setDate(date)
                        except Exception:
                            pass
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QComboBox):
                        current_widget.blockSignals(True)
                        # For combo boxes, try to match by data first, then by text
                        if current_data_type == "signature":
                            idx = current_widget.findData(value)
                            if idx < 0:
                                idx = current_widget.findText(value)
                            if idx >= 0:
                                current_widget.setCurrentIndex(idx)
                        else:
                            # For other combo boxes, match by text
                            idx = current_widget.findText(value)
                            if idx >= 0:
                                current_widget.setCurrentIndex(idx)
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    break  # Found matching field, move to next current group field
        
        # Force UI update after all autofill operations
        QtWidgets.QApplication.processEvents()
        current_page = self.stack.currentWidget()
        if current_page:
            current_page.update()
            current_page.repaint()

    def _update_group_nav(self):
        count = self.stack.count()
        if count == 0:
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.group_label.setText("No groups")
            return

        if self.current_group_index < 0:
            self.current_group_index = 0
        if self.current_group_index > count - 1:
            self.current_group_index = count - 1

        self.stack.setCurrentIndex(self.current_group_index)
        # Force update and repaint to ensure the new page is visible
        current_widget = self.stack.currentWidget()
        if current_widget:
            current_widget.show()
            current_widget.update()
            current_widget.repaint()
        self.stack.update()
        self.stack.repaint()
        
        # Apply autofill values from previous group to current group
        # Use QTimer to ensure the new page is fully visible before applying autofill
        QtCore.QTimer.singleShot(10, self._apply_autofill_to_current_group)
        
        self.prev_btn.setEnabled(self.current_group_index > 0)
        self.next_btn.setEnabled(self.current_group_index < count - 1)

        name = ""
        if self.group_names and self.current_group_index < len(self.group_names):
            name = self.group_names[self.current_group_index]

        if name:
            text = f"{name} ({self.current_group_index + 1}/{count})"
        else:
            text = f"Group {self.current_group_index + 1} of {count}"
        self.group_label.setText(text)

    def on_prev_group(self):
        if self.current_group_index > 0:
            self.current_group_index -= 1
            self._update_group_nav()

    def on_next_group(self):
        if self.current_group_index < self.stack.count() - 1:
            self.current_group_index += 1
            self._update_group_nav()

    def _init_new(self):
        self.template = self._choose_template_for_instrument()
        if not self.template:
            # close dialog if no template
            QtCore.QTimer.singleShot(0, self.reject)
            return
        self._build_dynamic_form()
        self._build_performed_by_combo()
        # Load and display template notes
        template_notes = str(self.template.get("notes", "") or "")
        self.template_notes_display.setPlainText(template_notes)
        # Hide template notes section if there are no notes
        if not template_notes.strip():
            self.template_notes_label.hide()
            self.template_notes_display.hide()
        else:
            self.template_notes_label.show()
            self.template_notes_display.show()

    def _init_edit(self):
        rec = self.repo.get_calibration_record_with_template(self.record_id)
        if not rec:
            QtWidgets.QMessageBox.warning(
                self,
                "Not found",
                "Calibration record not found.",
            )
            QtCore.QTimer.singleShot(0, self.reject)
            return

        self._record_updated_at = rec.get("updated_at")
        self.template = self.repo.get_template(rec["template_id"])
        self._build_dynamic_form()
        self._build_performed_by_combo()

        # Fill metadata
        try:
            d = datetime.strptime(rec["cal_date"], "%Y-%m-%d").date()
            self.date_edit.setDate(QtCore.QDate(d.year, d.month, d.day))
        except Exception:
            pass

        performed_by = rec.get("performed_by") or ""
        idx = self.performed_combo.findText(performed_by)
        if idx >= 0:
            self.performed_combo.setCurrentIndex(idx)
            self.performed_other_edit.setVisible(False)
        else:
            self.performed_combo.setCurrentIndex(self.performed_combo.count() - 1)  # Other...
            self.performed_other_edit.setText(performed_by)
            self.performed_other_edit.setVisible(True)

        # Result is stored on record but not shown in UI; derived from tolerance pass/fail on save

        # Load and display template notes (not per-instance notes)
        template_notes = str(self.template.get("notes", "") or "")
        self.template_notes_display.setPlainText(template_notes)
        # Hide template notes section if there are no notes
        if not template_notes.strip():
            self.template_notes_label.hide()
            self.template_notes_display.hide()
        else:
            self.template_notes_label.show()
            self.template_notes_display.show()

        # Fill field values
        vals = self.repo.get_calibration_values(self.record_id)
        by_field = {v["field_id"]: v for v in vals}
        values_by_name = {v.get("field_name"): v.get("value_text") for v in vals}
        for f in self.fields:
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w:
                continue
            dt = f["data_type"]
            if dt == "field_header":
                continue
            v = by_field.get(fid)
            if not v:
                continue
            val_text = v.get("value_text")
            if dt == "bool":
                pass_btn = w.findChild(QtWidgets.QRadioButton, "pass_btn") if hasattr(w, "findChild") else None
                fail_btn = w.findChild(QtWidgets.QRadioButton, "fail_btn") if hasattr(w, "findChild") else None
                if pass_btn and fail_btn:
                    is_pass = val_text == "1" or (val_text and str(val_text).lower() in ("true", "yes"))
                    pass_btn.setChecked(is_pass)
                    fail_btn.setChecked(not is_pass)
            elif dt in ("date", "non_affected_date"):
                try:
                    d = datetime.strptime(val_text, "%Y-%m-%d").date()
                    w.setDate(QtCore.QDate(d.year, d.month, d.day))
                except Exception:
                    pass
            elif dt == "signature":
                # For signature combobox, find by data (filename)
                if isinstance(w, QtWidgets.QComboBox):
                    idx = w.findData(val_text)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
            else:
                w.setText(val_text or "")

        # For equation-tolerance fields, show "lhs op rhs, PASS/FAIL" in the template form
        try:
            from tolerance_service import equation_tolerance_display
            for f in self.fields:
                fid = f["id"]
                w = self.field_widgets.get(fid)
                if not w or not hasattr(w, "setText"):
                    continue
                v = by_field.get(fid)
                if not v:
                    continue
                tol_type = (f.get("tolerance_type") or "").lower()
                if tol_type != "equation" or not f.get("tolerance_equation"):
                    continue
                nominal = 0.0
                nominal_str = f.get("nominal_value")
                if nominal_str not in (None, ""):
                    try:
                        nominal = float(str(nominal_str).strip())
                    except (TypeError, ValueError):
                        pass
                reading = 0.0
                val_text = v.get("value_text")
                if val_text not in (None, ""):
                    try:
                        reading = float(str(val_text).strip())
                    except (TypeError, ValueError):
                        pass
                vars_map = {"nominal": nominal, "reading": reading}
                for i in range(1, 6):
                    ref_name = f.get(f"calc_ref{i}_name")
                    if ref_name and ref_name in values_by_name:
                        try:
                            vars_map[f"ref{i}"] = float(values_by_name[ref_name] or 0)
                        except (TypeError, ValueError):
                            vars_map[f"ref{i}"] = 0.0
                parts = equation_tolerance_display(f.get("tolerance_equation"), vars_map)
                if parts is not None:
                    lhs, op_str, rhs, pass_ = parts
                    from tolerance_service import format_calculation_display
                    _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                    w.setText(f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}, {'PASS' if pass_ else 'FAIL'}")
        except ImportError:
            pass
        # One-time display for tolerance-type (data_type) fields from stored values
        self._populate_tolerance_field_displays_from_values(values_by_name)

    def accept(self):
        if not self.template:
            super().reject()
            return

        cal_date = self.date_edit.date().toString("yyyy-MM-dd")
        performed_by = (
            self.performed_other_edit.text().strip()
            if self.performed_combo.currentText() == "Other..."
            else self.performed_combo.currentText().strip()
        )
        notes = ""  # Notes are permanent from template

        field_values = self._collect_field_values()
        if field_values is None:
            return
        values_by_name = {}
        for f in self.fields:
            name = (f.get("name") or f.get("field_name") or "").strip()
            if name:
                values_by_name[name] = field_values.get(f["id"])

        self._apply_computations(field_values, values_by_name)
        # Rebuild values_by_name after computations (computed values now in field_values)
        for f in self.fields:
            name = (f.get("name") or f.get("field_name") or "").strip()
            if name:
                values_by_name[name] = field_values.get(f["id"])
        any_out_of_tol, _ = self._check_tolerance_pass_fail(field_values, values_by_name, "PASS")
        result = "FAIL" if any_out_of_tol else "PASS"

        ok_btn = self.btn_box.button(QtWidgets.QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setEnabled(False)
        try:
            self._save_calibration_record(cal_date, performed_by, result, notes, field_values)
        except StaleDataError as e:
            if ok_btn:
                ok_btn.setEnabled(True)
            logger.warning("Calibration save failed (stale data): record_id=%s instrument_id=%s: %s", self.record_id, getattr(self, "instrument_id", None), e)
            QtWidgets.QMessageBox.warning(
                self,
                "Save failed",
                str(e) + "\n\nClose this dialog, refresh the history, and try again.",
            )
            return
        except Exception as e:
            if ok_btn:
                ok_btn.setEnabled(True)
            logger.warning("Calibration save failed: record_id=%s instrument_id=%s: %s", self.record_id, getattr(self, "instrument_id", None), e, exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Error saving calibration", str(e))
            return

        if ok_btn:
            ok_btn.setText("Saved!")
        QtCore.QTimer.singleShot(400, self._finish_accept)

    def _populate_tolerance_field_displays_from_values(self, values_by_name: dict):
        """One-time: set read-only tolerance/stat field widgets from values_by_name (e.g. from DB when editing)."""
        try:
            from tolerance_service import equation_tolerance_display, list_variables, format_calculation_display, evaluate_tolerance_equation
        except ImportError:
            return
        for f in self.fields:
            dt = (f.get("data_type") or "").strip().lower()
            if dt not in ("tolerance", "stat"):
                continue
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w or not hasattr(w, "setText"):
                continue
            eq = (f.get("tolerance_equation") or "").strip()
            if not eq:
                w.setText("—")
                continue
            nominal = 0.0
            nominal_str = f.get("nominal_value")
            if nominal_str not in (None, ""):
                try:
                    nominal = float(str(nominal_str).strip())
                except (TypeError, ValueError):
                    pass
            vars_map = {"nominal": nominal, "reading": 0.0}
            for i in range(1, 13):
                ref_name = f.get(f"calc_ref{i}_name")
                if ref_name and ref_name in values_by_name and values_by_name.get(ref_name) not in (None, ""):
                    try:
                        vars_map[f"ref{i}"] = float(str(values_by_name[ref_name]).strip())
                    except (TypeError, ValueError):
                        pass
            if "reading" in list_variables(eq):
                ref1 = f.get("calc_ref1_name")
                if ref1 and ref1 in values_by_name and values_by_name.get(ref1) not in (None, ""):
                    try:
                        vars_map["reading"] = float(str(values_by_name[ref1]).strip())
                    except (TypeError, ValueError):
                        pass
            from tolerance_service import _ensure_val_aliases
            vars_map = _ensure_val_aliases(vars_map)
            required_vars = list_variables(eq)
            if any(var not in vars_map for var in required_vars):
                w.setText("—")
                continue
            try:
                if dt == "stat":
                    result = evaluate_tolerance_equation(eq, vars_map)
                    _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                    w.setText(format_calculation_display(result, decimal_places=_dec))
                else:
                    parts = equation_tolerance_display(eq, vars_map)
                    if parts is not None:
                        lhs, op_str, rhs, pass_ = parts
                        _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                        w.setText(f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}, {'PASS' if pass_ else 'FAIL'}")
                    else:
                        w.setText("—")
            except (ValueError, TypeError):
                w.setText("—")

    def _collect_field_values(self) -> dict[int, str] | None:
        """Collect user-entered values from widgets. Returns None if validation fails. Skips tolerance- and convert-type (computed) fields."""
        field_values: dict[int, str] = {}
        for f in self.fields:
            fid = f["id"]
            dt = f["data_type"]
            if dt in ("tolerance", "convert", "stat", "field_header"):
                continue
            w = self.field_widgets.get(fid)
            if w is None:
                continue
            val = None

            if dt == "bool":
                pass_btn = w.findChild(QtWidgets.QRadioButton, "pass_btn") if hasattr(w, "findChild") else None
                val = "1" if (pass_btn and pass_btn.isChecked()) else "0"
            elif dt == "date":
                val = w.date().toString("yyyy-MM-dd")
            elif dt == "signature":
                if isinstance(w, QtWidgets.QComboBox):
                    val = w.currentData() or ""
                else:
                    val = ""
            else:
                val = w.text().strip()

            is_computed = bool(f.get("calc_type"))
            is_required = bool(f.get("required"))

            if is_required and not is_computed:
                if val is None or val == "" or (val == "0" and dt != "bool"):
                    logger.warning("Calibration validation failed: required field '%s' (label '%s') is empty", f.get("name"), f.get("label"))
                    QtWidgets.QMessageBox.warning(
                        self, "Validation", f"Field '{f['label']}' is required.",
                    )
                    return None

            field_values[fid] = val

        return field_values

    def _apply_computations(self, field_values: dict[int, str], values_by_name: dict[str, str]) -> None:
        """Apply computed field values (ABS_DIFF, PCT_ERROR, etc.) in place."""
        for f in self.fields:
            calc_type = f.get("calc_type")
            if not calc_type:
                continue

            fid = f["id"]

            if calc_type == "ABS_DIFF":
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                v1 = values_by_name.get(ref1)
                v2 = values_by_name.get(ref2)
                result_val = ""
                try:
                    if v1 not in (None, "") and v2 not in (None, ""):
                        a = float(v1)
                        b = float(v2)
                        result_val = f"{abs(a - b):.3f}"
                except (TypeError, ValueError):
                    result_val = ""
                field_values[fid] = result_val

            elif calc_type == "PCT_ERROR":
                # Value 1 = measured, Value 2 = reference
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                v1 = values_by_name.get(ref1)
                v2 = values_by_name.get(ref2)
                result_val = ""
                try:
                    if v1 not in (None, "") and v2 not in (None, ""):
                        a = float(v1)
                        b = float(v2)
                        if b != 0:
                            result_val = f"{(abs(a - b) / abs(b) * 100):.3f}"
                        else:
                            result_val = ""
                except (TypeError, ValueError):
                    result_val = ""
                field_values[fid] = result_val

            elif calc_type == "PCT_DIFF":
                # Percent difference: |V1 - V2| / avg(V1,V2) * 100 = 200*|V1-V2|/(V1+V2); order of fields does not matter
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                v1 = values_by_name.get(ref1)
                v2 = values_by_name.get(ref2)
                result_val = ""
                try:
                    if v1 not in (None, "") and v2 not in (None, ""):
                        a = float(v1)
                        b = float(v2)
                        denom = a + b
                        if denom != 0:
                            result_val = f"{(200.0 * abs(a - b) / denom):.3f}"
                        else:
                            result_val = ""
                except (TypeError, ValueError):
                    result_val = ""
                field_values[fid] = result_val

            elif calc_type in ("MIN_OF", "MAX_OF", "RANGE_OF"):
                ref_names = [f.get(f"calc_ref{i}_name") for i in range(1, 13)]
                nums = []
                for r in ref_names:
                    if not r:
                        continue
                    v = values_by_name.get(r)
                    if v not in (None, ""):
                        try:
                            nums.append(float(v))
                        except (TypeError, ValueError):
                            pass
                result_val = ""
                if len(nums) >= 2:
                    if calc_type == "MIN_OF":
                        result_val = f"{min(nums):.3f}"
                    elif calc_type == "MAX_OF":
                        result_val = f"{max(nums):.3f}"
                    else:  # RANGE_OF
                        result_val = f"{(max(nums) - min(nums)):.3f}"
                field_values[fid] = result_val

            elif calc_type == "CUSTOM_EQUATION":
                ref_names = [f.get(f"calc_ref{i}_name") for i in range(1, 13)]
                vars_map = {"nominal": 0.0, "reading": 0.0}
                nominal_str = f.get("nominal_value")
                if nominal_str not in (None, ""):
                    try:
                        vars_map["nominal"] = float(str(nominal_str).strip())
                    except (TypeError, ValueError):
                        pass
                for i, r in enumerate(ref_names, 1):
                    if r and r in values_by_name:
                        v = values_by_name.get(r)
                        unit = self._get_unit_for_ref(r)
                        num = self._parse_numeric_stripping_unit(v, unit)
                        if num is not None:
                            vars_map[f"ref{i}"] = num
                        else:
                            try:
                                vars_map[f"ref{i}"] = float(values_by_name[r] or 0)
                            except (TypeError, ValueError):
                                vars_map[f"ref{i}"] = 0.0
                eq = f.get("tolerance_equation")
                result_val = ""
                if eq:
                    try:
                        from tolerance_service import equation_tolerance_display
                        parts = equation_tolerance_display(eq, vars_map)
                        if parts is not None:
                            lhs, op_str, rhs, pass_ = parts
                            from tolerance_service import format_calculation_display
                            _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                            result_val = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}, {'PASS' if pass_ else 'FAIL'}"
                        else:
                            from tolerance_service import evaluate_tolerance_equation
                            val = evaluate_tolerance_equation(eq, vars_map)
                            result_val = "Pass" if val >= 0.5 else "Fail"
                    except Exception:
                        result_val = "Fail"
                field_values[fid] = result_val

        # Convert-type (data_type "convert") fields: value = equation evaluated from refs
        try:
            from tolerance_service import evaluate_tolerance_equation, format_calculation_display
        except ImportError:
            pass
        else:
            for f in self.fields:
                if (f.get("data_type") or "").strip().lower() != "convert":
                    continue
                eq = (f.get("tolerance_equation") or "").strip()
                if not eq:
                    continue
                fid = f["id"]
                vars_map = {"nominal": 0.0, "reading": 0.0}
                for i in range(1, 13):
                    ref_name = f.get(f"calc_ref{i}_name")
                    if ref_name and ref_name in values_by_name:
                        v = values_by_name.get(ref_name)
                        if v not in (None, ""):
                            unit = self._get_unit_for_ref(ref_name)
                            num = self._parse_numeric_stripping_unit(v, unit)
                            if num is not None:
                                vars_map[f"ref{i}"] = num
                                vars_map[f"val{i}"] = num
                try:
                    result = evaluate_tolerance_equation(eq, vars_map)
                    decimals = max(0, min(4, int(f.get("sig_figs") or 3)))
                    field_values[fid] = format_calculation_display(result, decimal_places=decimals)
                except (ValueError, TypeError):
                    field_values[fid] = ""

        # If you ever add more calc types, handle them here.

    def _check_tolerance_pass_fail(
        self,
        field_values: dict[int, str],
        values_by_name: dict[str, str],
        result: str,
    ) -> tuple[bool, str]:
        """Check tolerance on computed/bool fields. Returns (any_out_of_tol, result)."""
        any_out_of_tol = False
        try:
            from tolerance_service import evaluate_pass_fail
        except ImportError:
            evaluate_pass_fail = None
        for f in self.fields:
            if f.get("calc_type") not in ("ABS_DIFF", "PCT_ERROR", "PCT_DIFF", "MIN_OF", "MAX_OF", "RANGE_OF"):
                continue

            tol_raw = f.get("tolerance")
            tol_fixed = None
            if tol_raw not in (None, ""):
                try:
                    tol_fixed = float(str(tol_raw))
                except (TypeError, ValueError):
                    pass
            if tol_fixed is None and not f.get("tolerance_equation"):
                continue

            fid = f["id"]
            val_txt = field_values.get(fid)
            if not val_txt:
                continue

            try:
                diff = abs(float(str(val_txt)))
            except (TypeError, ValueError):
                continue

            if evaluate_pass_fail:
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                ref3 = f.get("calc_ref3_name")
                ref4 = f.get("calc_ref4_name")
                ref5 = f.get("calc_ref5_name")
                vars_map = {"nominal": 0.0, "reading": diff}
                for i, r in enumerate((ref1, ref2, ref3, ref4, ref5), 1):
                    if r and r in values_by_name:
                        v = values_by_name.get(r)
                        unit = self._get_unit_for_ref(r)
                        num = self._parse_numeric_stripping_unit(v, unit)
                        if num is not None:
                            vars_map[f"ref{i}"] = num
                        else:
                            try:
                                vars_map[f"ref{i}"] = float(values_by_name[r] or 0)
                            except (TypeError, ValueError):
                                vars_map[f"ref{i}"] = 0.0
                pass_, _, _ = evaluate_pass_fail(
                    f.get("tolerance_type"),
                    tol_fixed,
                    f.get("tolerance_equation"),
                    nominal=0.0,
                    reading=diff,
                    vars_map=vars_map,
                    tolerance_lookup_json=f.get("tolerance_lookup_json"),
                )
                if not pass_:
                    any_out_of_tol = True
                    break
            else:
                if tol_fixed is not None and diff > tol_fixed:
                    any_out_of_tol = True
                    break

        # Third-b: Custom equation (pass/fail from formula)
        if not any_out_of_tol and evaluate_pass_fail:
            for f in self.fields:
                if f.get("calc_type") != "CUSTOM_EQUATION":
                    continue
                eq = f.get("tolerance_equation")
                if not eq:
                    continue
                ref_names = [
                    f.get("calc_ref1_name"),
                    f.get("calc_ref2_name"),
                    f.get("calc_ref3_name"),
                    f.get("calc_ref4_name"),
                    f.get("calc_ref5_name"),
                ]
                vars_map = {"nominal": 0.0, "reading": 0.0}
                nominal_str = f.get("nominal_value")
                if nominal_str not in (None, ""):
                    try:
                        vars_map["nominal"] = float(str(nominal_str).strip())
                    except (TypeError, ValueError):
                        pass
                for i, r in enumerate(ref_names, 1):
                    if r and r in values_by_name:
                        try:
                            vars_map[f"ref{i}"] = float(values_by_name[r] or 0)
                        except (TypeError, ValueError):
                            vars_map[f"ref{i}"] = 0.0
                try:
                    from tolerance_service import evaluate_tolerance_equation
                    val = evaluate_tolerance_equation(eq, vars_map)
                    if val < 0.5:
                        any_out_of_tol = True
                        break
                except Exception:
                    any_out_of_tol = True
                    break

        # Fourth pass: bool tolerance — auto-FAIL if bool field value doesn't match configured pass (true/false)
        if not any_out_of_tol and evaluate_pass_fail:
            for f in self.fields:
                if f.get("data_type") != "bool" or f.get("tolerance_type") != "bool":
                    continue
                pass_when = (f.get("tolerance_equation") or "true").strip().lower()
                if pass_when not in ("true", "false"):
                    continue
                fid = f["id"]
                val_txt = field_values.get(fid)
                if val_txt is None:
                    continue
                reading_bool = val_txt in ("1", "true", "yes", "on")
                reading_float = 1.0 if reading_bool else 0.0
                pass_, _, _ = evaluate_pass_fail(
                    "bool",
                    None,
                    pass_when,
                    nominal=0.0,
                    reading=reading_float,
                    vars_map={},
                    tolerance_lookup_json=None,
                )
                if not pass_:
                    any_out_of_tol = True
                    break

        # Fifth pass: other fields with tolerance (number, reference, etc. — equation, fixed, percent, lookup)
        # Skip convert: they are computed display values, not tolerance checks.
        if not any_out_of_tol and evaluate_pass_fail:
            for f in self.fields:
                if f.get("calc_type") or (f.get("data_type") or "") == "bool" or (f.get("data_type") or "") == "tolerance" or (f.get("data_type") or "") == "convert" or (f.get("data_type") or "") == "stat":
                    continue
                tol_type = (f.get("tolerance_type") or "fixed").lower()
                if not f.get("tolerance_equation") and f.get("tolerance") is None and tol_type not in ("equation", "percent", "lookup"):
                    continue
                fid = f["id"]
                val_txt = field_values.get(fid)
                if val_txt is None or val_txt == "":
                    continue
                unit_f = (f.get("unit") or "").strip()
                reading = self._parse_numeric_stripping_unit(val_txt, unit_f)
                if reading is None:
                    try:
                        reading = float(str(val_txt).strip())
                    except (TypeError, ValueError):
                        continue
                nominal = 0.0
                nominal_str = f.get("nominal_value")
                if nominal_str not in (None, ""):
                    try:
                        nominal = float(str(nominal_str).strip())
                    except (TypeError, ValueError):
                        pass
                vars_map = {"nominal": nominal, "reading": reading}
                for i in range(1, 13):
                    r = f.get(f"calc_ref{i}_name")
                    if r and r in values_by_name:
                        v = values_by_name.get(r)
                        unit = self._get_unit_for_ref(r)
                        num = self._parse_numeric_stripping_unit(v, unit)
                        if num is not None:
                            vars_map[f"ref{i}"] = num
                        else:
                            try:
                                vars_map[f"ref{i}"] = float(str(v or 0).strip())
                            except (TypeError, ValueError):
                                pass
                tol_fixed = None
                tol_raw = f.get("tolerance")
                if tol_raw not in (None, ""):
                    try:
                        tol_fixed = float(str(tol_raw))
                    except (TypeError, ValueError):
                        pass
                try:
                    pass_, _, _ = evaluate_pass_fail(
                        tol_type,
                        tol_fixed,
                        f.get("tolerance_equation"),
                        nominal,
                        reading,
                        vars_map=vars_map,
                        tolerance_lookup_json=f.get("tolerance_lookup_json"),
                    )
                    if not pass_:
                        any_out_of_tol = True
                        break
                except Exception:
                    any_out_of_tol = True
                    break

        # Sixth pass: tolerance-type (data_type "tolerance") fields — not in field_values; evaluate from values_by_name
        if not any_out_of_tol and evaluate_pass_fail:
            for f in self.fields:
                if (f.get("data_type") or "").strip().lower() != "tolerance":
                    continue
                eq = (f.get("tolerance_equation") or "").strip()
                if not eq:
                    continue
                nominal = 0.0
                nominal_str = f.get("nominal_value")
                if nominal_str not in (None, ""):
                    try:
                        nominal = float(str(nominal_str).strip())
                    except (TypeError, ValueError):
                        pass
                vars_map = {"nominal": nominal, "reading": 0.0}
                for i in range(1, 13):
                    ref_name = f.get(f"calc_ref{i}_name")
                    if ref_name and ref_name in values_by_name:
                        v = values_by_name.get(ref_name)
                        if v not in (None, ""):
                            unit = self._get_unit_for_ref(ref_name)
                            num = self._parse_numeric_stripping_unit(v, unit)
                            if num is not None:
                                vars_map[f"ref{i}"] = num
                                vars_map[f"val{i}"] = num
                            else:
                                try:
                                    n = float(str(v).strip())
                                    vars_map[f"ref{i}"] = n
                                    vars_map[f"val{i}"] = n
                                except (TypeError, ValueError):
                                    pass
                try:
                    from tolerance_service import list_variables
                    if "reading" in list_variables(eq):
                        ref1 = f.get("calc_ref1_name")
                        if ref1 and ref1 in values_by_name:
                            v = values_by_name.get(ref1)
                            if v not in (None, ""):
                                unit1 = self._get_unit_for_ref(ref1)
                                num1 = self._parse_numeric_stripping_unit(v, unit1)
                                if num1 is not None:
                                    vars_map["reading"] = num1
                                else:
                                    try:
                                        vars_map["reading"] = float(str(v).strip())
                                    except (TypeError, ValueError):
                                        pass
                except ImportError:
                    pass
                for i in range(1, 13):
                    rk, vk = f"ref{i}", f"val{i}"
                    if rk in vars_map and vk not in vars_map:
                        vars_map[vk] = vars_map[rk]
                try:
                    from tolerance_service import list_variables, equation_tolerance_display
                    required = list_variables(eq)
                    if any(var not in vars_map for var in required):
                        continue
                    parts = equation_tolerance_display(eq, vars_map)
                    if parts is not None:
                        _, _, _, pass_ = parts
                        if not pass_:
                            any_out_of_tol = True
                            break
                    else:
                        reading = vars_map.get("reading", 0.0)
                        pass_, _, _ = evaluate_pass_fail(
                            "equation", None, eq, nominal, reading,
                            vars_map=vars_map, tolerance_lookup_json=None,
                        )
                        if not pass_:
                            any_out_of_tol = True
                            break
                except Exception:
                    continue

        derived_result = "FAIL" if any_out_of_tol else "PASS"
        return (any_out_of_tol, derived_result)

    def _save_calibration_record(
        self,
        cal_date: str,
        performed_by: str,
        result: str,
        notes: str,
        field_values: dict[int, str],
    ) -> None:
        """Persist calibration record. Raises on error."""
        if self.record_id is None:
            calibration_service.create_calibration_record(
                self.repo,
                self.instrument["id"],
                self.template["id"],
                cal_date,
                performed_by,
                result,
                notes,
                field_values,
                template_version=self.template.get("version"),
            )
        else:
            calibration_service.update_calibration_record(
                self.repo,
                self.record_id,
                cal_date,
                performed_by,
                result,
                notes,
                field_values,
                expected_updated_at=getattr(self, "_record_updated_at", None),
            )

    def _finish_accept(self):
        """Called after brief 'Saved!' feedback."""
        super(CalibrationFormDialog, self).accept()
