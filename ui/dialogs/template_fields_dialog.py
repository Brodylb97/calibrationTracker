# ui/dialogs/template_fields_dialog.py - Manage template fields

import sqlite3

from PyQt5 import QtWidgets, QtCore

from database import CalibrationRepository
from services import template_service
from ui.help_content import get_help_content, HelpDialog
from ui.dialogs.field_edit_dialog import FieldEditDialog
from ui.dialogs.explain_tolerance_dialog import ExplainToleranceDialog

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
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Label", "Type", "Unit", "Required", "Sort", "Group", "Tolerance"]
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
        self.btn_explain.setToolTip("Show how tolerance is calculated (plain language + technical)")
        self.btn_batch = QtWidgets.QPushButton("Batch")
        self.btn_batch.setToolTip("Apply batch operations to selected fields")
        batch_menu = QtWidgets.QMenu(self)
        act_eq = batch_menu.addAction("Change tolerance equation")
        act_eq.setToolTip("Set tolerance equation for selected fields (equation type)")
        act_unit = batch_menu.addAction("Apply unit")
        act_unit.setToolTip("Set unit for selected fields (e.g. °F, °C)")
        act_decimal = batch_menu.addAction("Set decimal places")
        act_decimal.setToolTip("Set numbers after decimal (0-4) for selected fields")
        act_group = batch_menu.addAction("Set group")
        act_group.setToolTip("Set group name for selected fields")
        act_type = batch_menu.addAction("Set type")
        act_type.setToolTip("Set field type for selected fields")
        batch_menu.addSeparator()
        act_appear = batch_menu.addAction("Check 'Appear in calibrations table'")
        act_appear.setToolTip("Enable 'Appear in calibrations table' for selected number and convert fields (shows value in tolerance table)")
        self.btn_batch.setMenu(batch_menu)
        act_eq.triggered.connect(self.on_batch_change_equation)
        act_unit.triggered.connect(self.on_batch_apply_unit)
        act_decimal.triggered.connect(self.on_batch_set_decimal)
        act_group.triggered.connect(self.on_batch_set_group)
        act_type.triggered.connect(self.on_batch_set_type)
        act_appear.triggered.connect(self.on_batch_appear_in_calibrations_table)
        for i, btn in enumerate([self.btn_add, self.btn_edit, self.btn_delete, self.btn_dup_group,
                                 self.btn_explain, self.btn_batch]):
            btn.setMinimumWidth(100)
            btn_layout.addWidget(btn, i // 4, i % 4)
        layout.addLayout(btn_layout)

        # Connect button signals BEFORE adding to layout
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_dup_group.clicked.connect(self.on_dup_group)
        self.btn_explain.clicked.connect(self.on_explain_tolerance)

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
                self.table.setItem(row, 7, mk(tol_txt))
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
            template_service.add_template_field(
                self.repo,
                template_id=self.template_id,
                name=data["name"],
                label=data["label"],
                data_type=data["data_type"],
                unit=data["unit"],
                required=data["required"],
                sort_order=data["sort_order"],
                group_name=data["group_name"],
                calc_type=data["calc_type"],
                calc_ref1_name=data["calc_ref1_name"],
                calc_ref2_name=data["calc_ref2_name"],
                calc_ref3_name=data.get("calc_ref3_name"),
                calc_ref4_name=data.get("calc_ref4_name"),
                calc_ref5_name=data.get("calc_ref5_name"),
                calc_ref6_name=data.get("calc_ref6_name"),
                calc_ref7_name=data.get("calc_ref7_name"),
                calc_ref8_name=data.get("calc_ref8_name"),
                calc_ref9_name=data.get("calc_ref9_name"),
                calc_ref10_name=data.get("calc_ref10_name"),
                calc_ref11_name=data.get("calc_ref11_name"),
                calc_ref12_name=data.get("calc_ref12_name"),
                tolerance=data["tolerance"],
                autofill_from_first_group=data.get("autofill_from_first_group", False),
                default_value=data.get("default_value"),
                tolerance_type=data.get("tolerance_type"),
                tolerance_equation=data.get("tolerance_equation"),
                nominal_value=data.get("nominal_value"),
                tolerance_lookup_json=data.get("tolerance_lookup_json"),
                sig_figs=data.get("sig_figs", 3),
                stat_value_group=data.get("stat_value_group"),
                plot_x_axis_name=data.get("plot_x_axis_name"),
                plot_y_axis_name=data.get("plot_y_axis_name"),
                plot_title=data.get("plot_title"),
                plot_x_min=data.get("plot_x_min"),
                plot_x_max=data.get("plot_x_max"),
                plot_y_min=data.get("plot_y_min"),
                plot_y_max=data.get("plot_y_max"),
                plot_best_fit=data.get("plot_best_fit", False),
                appear_in_calibrations_table=data.get("appear_in_calibrations_table", False),
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
        template_service.update_template_field(self.repo, field_id, data)
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
                template_service.delete_template_field(self.repo, field_id)
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

    def _field_data_for_update(self, f: dict) -> dict:
        """Build a complete data dict for update_template_field from a field row (current schema)."""
        data = dict(f)
        # Ensure boolean-like fields are explicit for update (handles 0/1 from DB)
        for key in ("required", "autofill_from_first_group", "appear_in_calibrations_table", "plot_best_fit"):
            if key in data and data[key] is not None:
                data[key] = bool(data[key])
        return data

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
            "Equation (Excel-like, e.g. reading <= 0.02 * nominal or LINEST([val1,val2],[ref1,ref2])). Applied to selected fields that support equations (number, reference, tolerance, stat, or computed diff):",
            QtWidgets.QLineEdit.Normal,
            "reading <= 0.02 * nominal",
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
                dt = (f.get("data_type") or "").strip().lower()
                calc_type = f.get("calc_type")
                # Apply to: computed diff fields, number/reference with equation tolerance, tolerance (data_type), or stat
                is_computed = calc_type in ("ABS_DIFF", "PCT_ERROR", "PCT_DIFF", "MIN_OF", "MAX_OF", "RANGE_OF")
                is_number_or_ref = dt in ("number", "reference")
                is_tolerance_type = dt == "tolerance"
                is_stat = dt == "stat"
                if not (is_computed or is_number_or_ref or is_tolerance_type or is_stat):
                    continue
                data = self._field_data_for_update(f)
                data["tolerance_type"] = "equation"
                data["tolerance_equation"] = tol_eq
                template_service.update_template_field(self.repo, fid, data)
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
                data = self._field_data_for_update(f)
                data["unit"] = unit
                template_service.update_template_field(self.repo, fid, data)
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
                data = self._field_data_for_update(f)
                data["sig_figs"] = decimals
                template_service.update_template_field(self.repo, fid, data)
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
                data = self._field_data_for_update(f)
                data["group_name"] = group_name
                template_service.update_template_field(self.repo, fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied group to {applied} field(s)."
        )

    def on_batch_set_type(self):
        """Set field type for selected fields."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Select one or more field rows to set the type for.",
            )
            return
        type_options = [
            "text", "number", "bool", "date", "signature", "reference",
            "reference_cal_date", "tolerance", "convert", "stat", "plot",
            "non_affected_date", "field_header",
        ]
        display_names = [
            "text", "number", "bool", "date", "signature", "reference",
            "Reference cal date", "tolerance", "convert", "stat", "plot",
            "Non-affected Date", "Field Header",
        ]
        chosen, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Batch set type",
            "Field type to apply to selected fields:",
            display_names,
            0,
            False,
        )
        if not ok or not chosen:
            return
        idx = display_names.index(chosen)
        new_type = type_options[idx]
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                data = self._field_data_for_update(f)
                data["data_type"] = new_type
                template_service.update_template_field(self.repo, fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done", f"Applied type '{chosen}' to {applied} field(s)."
        )

    def on_batch_appear_in_calibrations_table(self):
        """Check 'Appear in calibrations table' for selected number and convert fields."""
        ids = self._selected_field_ids()
        if not ids:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Select one or more number or convert field rows to enable 'Appear in calibrations table'.",
            )
            return
        try:
            fields = self.repo.list_template_fields(self.template_id)
            field_by_id = {f["id"]: f for f in fields}
            applied = 0
            for fid in ids:
                f = field_by_id.get(fid)
                if not f:
                    continue
                if (f.get("data_type") or "").strip().lower() not in ("number", "convert"):
                    continue
                data = self._field_data_for_update(f)
                data["appear_in_calibrations_table"] = True
                template_service.update_template_field(self.repo, fid, data)
                applied += 1
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return
        self._load_fields()
        QtWidgets.QMessageBox.information(
            self, "Done",
            f"Enabled 'Appear in calibrations table' for {applied} field(s)."
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

                template_service.add_template_field(
                    self.repo,
                    template_id=self.template_id,
                    name=name,
                    label=label,
                    data_type=f["data_type"],
                    unit=f.get("unit"),
                    required=bool(f.get("required")),
                    sort_order=new_sort,
                    group_name=new_group,
                    calc_type=calc_type,
                    calc_ref1_name=ref1,
                    calc_ref2_name=ref2,
                    calc_ref3_name=ref3,
                    calc_ref4_name=ref4,
                    calc_ref5_name=ref5,
                    calc_ref6_name=ref6,
                    calc_ref7_name=ref7,
                    calc_ref8_name=ref8,
                    calc_ref9_name=ref9,
                    calc_ref10_name=ref10,
                    calc_ref11_name=ref11,
                    calc_ref12_name=ref12,
                    tolerance=tol,
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
        except sqlite3.OperationalError as e:
            self._db_error(e)
            return

        self._load_fields()


