# ui/dialogs/destination_edit_dialog.py - Add/edit destination dialog

from PyQt5 import QtWidgets, QtGui

from ui.help_content import get_help_content, HelpDialog


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
