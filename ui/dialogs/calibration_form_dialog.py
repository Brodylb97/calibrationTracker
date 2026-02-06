# ui/dialogs/calibration_form_dialog.py - Calibration data entry form

from datetime import datetime, date
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository, StaleDataError
from services import calibration_service, template_service
from ui.dialogs.common import STANDARD_FIELD_WIDTH
from ui.help_content import get_help_content, HelpDialog

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
        self._update_stat_fields()
        self._update_reference_cal_date_fields()

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
        elif data_type == "reference_cal_date":
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
        """Current form values by field name (from widgets). Excludes tolerance, convert, stat, reference_cal_date, and field_header (display-only)."""
        out = {}
        for f in self.fields:
            dt = f.get("data_type") or ""
            if dt in ("tolerance", "convert", "stat", "reference_cal_date", "field_header"):
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

    def _update_reference_cal_date_fields(self):
        """Update reference_cal_date widgets: look up instrument by ref1 value, display last_cal_date."""
        values_by_name = self._get_current_values_by_name()
        for f in self.fields:
            if (f.get("data_type") or "").strip().lower() != "reference_cal_date":
                continue
            ref1_name = f.get("calc_ref1_name")
            if not ref1_name or ref1_name not in values_by_name:
                continue
            id_or_tag = (values_by_name.get(ref1_name) or "").strip()
            if not id_or_tag:
                continue
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w or not hasattr(w, "setText"):
                continue
            try:
                inst = self.repo.get_instrument_by_id_or_tag(id_or_tag)
                if inst and inst.last_cal_date:
                    w.setText(inst.last_cal_date)
                else:
                    w.setText("—")
            except Exception:
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
        """Connect input widgets so convert, stat, and reference_cal_date fields update when user types."""
        def schedule_update():
            QtCore.QTimer.singleShot(0, lambda: (
                self._update_convert_fields(),
                self._update_stat_fields(),
                self._update_reference_cal_date_fields(),
            ))

        for f in self.fields:
            dt = f.get("data_type") or ""
            if dt in ("tolerance", "convert", "stat", "reference_cal_date"):
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
        """Collect user-entered values from widgets. Returns None if validation fails. Skips tolerance-, convert-, and reference_cal_date-type (computed) fields."""
        field_values: dict[int, str] = {}
        for f in self.fields:
            fid = f["id"]
            dt = f["data_type"]
            if dt in ("tolerance", "convert", "stat", "reference_cal_date", "field_header"):
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

        # Reference cal date: value = last_cal_date of instrument matching ref1 (ID or tag)
        for f in self.fields:
            if (f.get("data_type") or "").strip().lower() != "reference_cal_date":
                continue
            ref1_name = f.get("calc_ref1_name")
            if not ref1_name or ref1_name not in values_by_name:
                continue
            id_or_tag = (values_by_name.get(ref1_name) or "").strip()
            if not id_or_tag:
                continue
            fid = f["id"]
            try:
                inst = self.repo.get_instrument_by_id_or_tag(id_or_tag)
                if inst and inst.last_cal_date:
                    field_values[fid] = inst.last_cal_date
                else:
                    field_values[fid] = ""
            except Exception:
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
                if f.get("calc_type") or (f.get("data_type") or "") == "bool" or (f.get("data_type") or "") == "tolerance" or (f.get("data_type") or "") == "convert" or (f.get("data_type") or "") == "stat" or (f.get("data_type") or "") == "reference_cal_date":
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
