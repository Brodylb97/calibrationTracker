# ui/dialogs/field_edit_dialog.py - Add/edit template field

from PyQt5 import QtWidgets, QtCore

from ui.dialogs.common import STANDARD_FIELD_WIDTH, parse_float_optional
from ui.help_content import get_help_content, HelpDialog

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
        self.type_combo.addItem("Reference cal date", "reference_cal_date")
        self.type_combo.addItem("Non-affected Date", "non_affected_date")
        self.type_combo.addItem("Field Header", "field_header")
        dt = self.field.get("data_type") or "text"
        idx = self.type_combo.findData(dt) if dt in ("non_affected_date", "field_header", "reference_cal_date") else self.type_combo.findText(dt)
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
        self.appear_in_cal_check = QtWidgets.QCheckBox("Appear in calibrations table?")
        self.appear_in_cal_check.setToolTip("When checked, this field's value is shown in the Variables column alongside reference values for each calibration point. Applies to number and convert fields.")
        self.appear_in_cal_check.setChecked(bool(self.field.get("appear_in_calibrations_table", 0)))
        form.addRow("", self.appear_in_cal_check)
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
        if hasattr(self, "appear_in_cal_check"):
            self.appear_in_cal_check.setVisible((dt or "").strip().lower() in ("number", "convert"))
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
        data_type = (self.type_combo.currentData() or self.type_combo.currentText() or "").strip().lower().replace(" ", "_")
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
        dt = (data_type or "").strip().lower().replace(" ", "_")
        is_number = (dt == "number")
        is_reference = (dt == "reference")
        is_reference_cal_date = (dt == "reference_cal_date")
        is_tolerance = (dt == "tolerance")
        is_convert = (dt == "convert")
        is_stat = (dt == "stat")
        is_plot = (dt == "plot")
        is_field_header = (dt in ("field_header",))
        is_bool = (dt == "bool")
        show_unit = is_number or is_convert or is_tolerance or is_reference or is_stat
        if hasattr(self, "unit_edit") and hasattr(self, "unit_label"):
            self.unit_edit.setVisible(show_unit)
            self.unit_label.setVisible(show_unit)
        if hasattr(self, "appear_in_cal_check"):
            self.appear_in_cal_check.setVisible(is_number or is_convert)
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
            self.tol_type_combo.setVisible(not is_convert and not is_stat and not is_plot and not is_field_header and not is_reference_cal_date)
        if is_tolerance and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_convert and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_stat and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_plot and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        if is_reference_cal_date and hasattr(self, "test_group"):
            self.test_group.setVisible(False)
        # Reference cal date: label is displayed; Instrument reference points to field containing instrument ID
        if is_reference_cal_date:
            self._refresh_value_combos()
            if hasattr(self, "val1_label"):
                self.val1_label.setText("Instrument reference")
                self.val1_label.setToolTip("Field that contains the instrument ID or tag number. Use when the label does not contain the ID.")
                self.val1_label.setVisible(True)
            if hasattr(self, "ref1_combo"):
                self.ref1_combo.setVisible(True)
                self.ref1_combo.setToolTip("Select the field that holds the reference instrument's ID or tag number.")
            for i in range(2, 13):
                lbl = getattr(self, f"val{i}_label", None)
                cb = getattr(self, f"ref{i}_combo", None)
                if lbl:
                    lbl.setVisible(False)
                if cb:
                    cb.setVisible(False)
            if hasattr(self, "tol_equation_edit"):
                self.tol_equation_edit.setVisible(False)
            if hasattr(self, "tol_equation_label"):
                self.tol_equation_label.setVisible(False)
            if hasattr(self, "tol_validation_label"):
                self.tol_validation_label.setVisible(False)
            if hasattr(self, "var_btn_widget"):
                self.var_btn_widget.setVisible(False)
            if hasattr(self, "tol_bool_pass_combo"):
                self.tol_bool_pass_combo.setVisible(False)
            if hasattr(self, "tol_bool_pass_label"):
                self.tol_bool_pass_label.setVisible(False)
        # Tolerance-type, convert, stat, and plot fields: show equation + refs (val1-val5 always; val6-val12 only when used)
        elif is_convert or is_stat or is_plot:
            if hasattr(self, "val1_label"):
                self.val1_label.setText("val1 field")
                self.val1_label.setToolTip("")
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
            self.required_check.setVisible(not is_tolerance and not is_convert and not is_stat and not is_plot and not is_reference_cal_date)
            if is_tolerance or is_convert or is_stat or is_plot or is_reference_cal_date:
                self.required_check.setChecked(False)

    def _on_tolerance_type_changed(self, index: int):
        """Show equation edit and val1-val5 when Equation; val6-val12 only when used in equation or ref set. Bool pass combo for Boolean."""
        data_type = (self.type_combo.currentData() or self.type_combo.currentText() or "").strip().lower().replace(" ", "_")
        is_convert = (data_type == "convert")
        is_stat = (data_type == "stat")
        is_plot = (data_type == "plot")
        is_reference_cal_date = (data_type == "reference_cal_date")
        tol_type = self.tol_type_combo.currentData() if hasattr(self, "tol_type_combo") else None
        is_equation = (tol_type == "equation") or is_convert or is_stat or is_plot
        is_bool = (tol_type == "bool") and not is_convert
        if hasattr(self, "tol_equation_edit"):
            self.tol_equation_edit.setVisible(is_equation)
            self.tol_equation_label.setVisible(is_equation)
        if hasattr(self, "tol_bool_pass_combo"):
            self.tol_bool_pass_combo.setVisible(is_bool)
            self.tol_bool_pass_label.setVisible(is_bool)
        # reference_cal_date: show only val1/ref1 (Instrument reference)
        if is_reference_cal_date:
            if hasattr(self, "val1_label"):
                self.val1_label.setVisible(True)
            if hasattr(self, "ref1_combo"):
                self.ref1_combo.setVisible(True)
            for i in range(2, 13):
                lbl = getattr(self, f"val{i}_label", None)
                cb = getattr(self, f"ref{i}_combo", None)
                if lbl:
                    lbl.setVisible(False)
                if cb:
                    cb.setVisible(False)
        else:
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
        # Reference cal date: ref1 = field containing instrument ID (tag or numeric)
        elif data_type == "reference_cal_date":
            ref1_name = self.ref1_combo.currentData()
            if not ref1_name:
                QtWidgets.QMessageBox.warning(
                    self, "Validation",
                    "Instrument reference is required. Select the field that contains the reference instrument's ID or tag number.",
                )
                return None
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
            "plot_x_min": parse_float_optional(self.plot_x_min_edit.text()) if data_type == "plot" else None,
            "plot_x_max": parse_float_optional(self.plot_x_max_edit.text()) if data_type == "plot" else None,
            "plot_y_min": parse_float_optional(self.plot_y_min_edit.text()) if data_type == "plot" else None,
            "plot_y_max": parse_float_optional(self.plot_y_max_edit.text()) if data_type == "plot" else None,
            "plot_best_fit": self.plot_best_fit_check.isChecked() if data_type == "plot" else False,
            "appear_in_calibrations_table": self.appear_in_cal_check.isChecked() if data_type in ("number", "convert") else False,
        }

