# ui/dialogs/settings_dialog.py - Settings dialog

import os
from pathlib import Path

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository
from services import settings_service
from ui.help_content import get_help_content, HelpDialog


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog: reminders, operator name, quiet hours, manual backup."""

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

        self.btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        layout.addWidget(self.btn_box)

        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        self.btn_box.helpRequested.connect(lambda: self._show_help())

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
            settings_service.set_setting(
                self.repo, "reminder_days", str(self.reminder_days_spin.value())
            )
            settings_service.set_setting(
                self.repo, "operator_name", self.operator_edit.text().strip()
            )
            qstart = self.quiet_start_edit.time().toString("HH:mm")
            qend = self.quiet_end_edit.time().toString("HH:mm")
            settings_service.set_setting(self.repo, "quiet_start", qstart)
            settings_service.set_setting(self.repo, "quiet_end", qend)
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
