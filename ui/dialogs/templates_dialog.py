# ui/dialogs/templates_dialog.py - Manage calibration templates

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository
from services import template_service
from ui.dialogs.template_edit_dialog import TemplateEditDialog
from ui.dialogs.template_fields_dialog import TemplateFieldsDialog

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
        new_id = template_service.create_template(
            self.repo,
            type_id,
            data["name"],
            version=data["version"],
            is_active=data["is_active"],
            notes=data["notes"],
        )
        try:
            template_service.set_template_authorized_personnel(self.repo, new_id, dlg.get_authorized_person_ids())
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
            new_id = template_service.create_template(
                self.repo,
                type_id,
                new_name,
                version=1,
                is_active=False,
                notes=tpl.get("notes") or "",
                status="Draft",
            )
            fields = self.repo.list_template_fields(tpl_id)
            for i, f in enumerate(fields):
                template_service.add_template_field(
                    self.repo,
                    template_id=new_id,
                    name=f.get("name", ""),
                    label=f.get("label", ""),
                    data_type=f.get("data_type", "number"),
                    unit=f.get("unit"),
                    required=bool(f.get("required")),
                    sort_order=i,
                    group_name=f.get("group_name"),
                    calc_type=f.get("calc_type"),
                    calc_ref1_name=f.get("calc_ref1_name"),
                    calc_ref2_name=f.get("calc_ref2_name"),
                    calc_ref3_name=f.get("calc_ref3_name"),
                    calc_ref4_name=f.get("calc_ref4_name"),
                    calc_ref5_name=f.get("calc_ref5_name"),
                    calc_ref6_name=f.get("calc_ref6_name"),
                    calc_ref7_name=f.get("calc_ref7_name"),
                    calc_ref8_name=f.get("calc_ref8_name"),
                    calc_ref9_name=f.get("calc_ref9_name"),
                    calc_ref10_name=f.get("calc_ref10_name"),
                    calc_ref11_name=f.get("calc_ref11_name"),
                    calc_ref12_name=f.get("calc_ref12_name"),
                    tolerance=f.get("tolerance"),
                    autofill_from_first_group=bool(f.get("autofill_from_first_group", 0)),
                    default_value=f.get("default_value"),
                    tolerance_type=f.get("tolerance_type"),
                    tolerance_equation=f.get("tolerance_equation"),
                    nominal_value=f.get("nominal_value"),
                    tolerance_lookup_json=f.get("tolerance_lookup_json"),
                    sig_figs=f.get("sig_figs", 3),
                    stat_value_group=f.get("stat_value_group"),
                    plot_x_axis_name=f.get("plot_x_axis_name"),
                    plot_y_axis_name=f.get("plot_y_axis_name"),
                    plot_title=f.get("plot_title"),
                    plot_x_min=f.get("plot_x_min"),
                    plot_x_max=f.get("plot_x_max"),
                    plot_y_min=f.get("plot_y_min"),
                    plot_y_max=f.get("plot_y_max"),
                    plot_best_fit=bool(f.get("plot_best_fit", 0)),
                    appear_in_calibrations_table=bool(f.get("appear_in_calibrations_table", 0)),
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
        template_service.update_template(
            self.repo,
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
            template_service.set_template_authorized_personnel(self.repo, tpl_id, dlg.get_authorized_person_ids())
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
            template_service.delete_template(self.repo, tpl_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error deleting template", str(e))
        self._load_templates()

    def on_fields(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        dlg = TemplateFieldsDialog(self.repo, tpl_id, parent=self)
        dlg.exec_()


