# ui/dialogs/calibration_history_dialog.py - View/edit calibration history for an instrument

from PyQt5 import QtWidgets, QtCore, QtGui

from database import CalibrationRepository
from services import calibration_service, template_service
from ui.help_content import get_help_content, HelpDialog
from ui.dialogs.calibration_form_dialog import CalibrationFormDialog

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
        self.details_label.setToolTip("Pass/fail per tolerance point. Variables (refs + checked number fields), Tolerance (field label + value), Result. Groups highlighted green (pass) or red (fail).")
        layout.addWidget(self.details_label)
        self.details_table = QtWidgets.QTableWidget()
        self.details_table.setColumnCount(3)
        self.details_table.setHorizontalHeaderLabels(["Variables", "Tolerance", "Result"])
        header = self.details_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)   # Variables
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
                calibration_service.delete_calibration_record(self.repo, rec_id, reason=(reason or "").strip() or None)
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
                    calibration_service.archive_calibration_record(self.repo, rec_id, reason="Archived from history dialog")
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
                    calibration_service.delete_calibration_record(self.repo, rec_id, reason=(reason or "").strip() or None)
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

        tpl_id = template_service.create_template(
            self.repo,
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
            # Reference cal date: lookup instrument by ref1 value, add last_cal_date to values_by_name
            for tf in template_fields_by_id.values():
                if (tf.get("group_name") or "") != group_name:
                    continue
                if (tf.get("data_type") or "").strip().lower() != "reference_cal_date":
                    continue
                ref1_name = tf.get("calc_ref1_name")
                if not ref1_name:
                    continue
                id_or_tag = (_get_value(ref1_name) or "").strip()
                if not id_or_tag:
                    continue
                try:
                    inst = self.repo.get_instrument_by_id_or_tag(id_or_tag)
                    formatted = inst.last_cal_date if (inst and inst.last_cal_date) else "—"
                except Exception:
                    formatted = "—"
                tname = (tf.get("name") or "").strip()
                tlabel = (tf.get("label") or "").strip()
                if tname:
                    _add_key(values_by_name, tname, formatted)
                if tlabel:
                    _add_key(values_by_name, tlabel, formatted)

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

            def _ref_points_to_checked_number(ref_name):
                """True if ref_name matches a number or convert field with appear_in_calibrations_table."""
                if not (ref_name or "").strip():
                    return False
                rl = (ref_name or "").strip().lower()
                for nf in fields_in_group:
                    if (nf.get("data_type") or "").strip().lower() not in ("number", "convert"):
                        continue
                    if not nf.get("appear_in_calibrations_table"):
                        continue
                    n = (nf.get("name") or "").strip().lower()
                    l = (nf.get("label") or "").strip().lower()
                    if n == rl or l == rl:
                        return True
                return False

            def _variables_string(ref1_name, ref2_name, include_checked_numbers=True):
                """Build Variables column: refs (excluding those that are checked numbers) and number/convert fields with appear_in_calibrations_table."""
                parts = []
                for rn in ((ref1_name or "").strip(), (ref2_name or "").strip()):
                    if not rn:
                        continue
                    if _ref_points_to_checked_number(rn):
                        continue  # skip; will be shown in checked numbers
                    lbl = _find_label(rn)
                    val = _get_value(rn)
                    val_str = str(val).strip() if val not in (None, "") else "—"
                    parts.append(f"{lbl or rn}: {val_str}")
                if include_checked_numbers:
                    for nf in fields_in_group:
                        if (nf.get("data_type") or "").strip().lower() not in ("number", "convert"):
                            continue
                        if not (nf.get("appear_in_calibrations_table") or nf.get("id") == fid):
                            continue
                        nf_label = (nf.get("label") or nf.get("name") or "").strip()
                        if not nf_label:
                            continue
                        nf_val = by_field_id.get(nf.get("id"), {})
                        nf_val_txt = nf_val.get("value_text")
                        if nf_val_txt is None:
                            nf_val_txt = _get_value((nf.get("name") or "").strip())
                        nf_val_str = str(nf_val_txt).strip() if nf_val_txt not in (None, "") else "—"
                        parts.append(f"{nf_label}: {nf_val_str}")
                return ", ".join(parts) if parts else ""

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
                            "calc_ref1_name", "calc_ref2_name", "calc_ref3_name", "calc_ref4_name", "calc_ref5_name",
                            "appear_in_calibrations_table"):
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

                    variables_str = _variables_string(ref1_name, ref2_name)
                    if display_parts is not None:
                        lhs, op_str, rhs, pass_ = display_parts
                        from tolerance_service import format_calculation_display
                        _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                        tol_val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                        _add_row(group_name, variables_str, f"{label}: {tol_val_str}", "", "PASS" if pass_ else "FAIL")
                    else:
                        try:
                            num_val = float(str(val_txt).strip())
                            from tolerance_service import format_calculation_display
                            _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                            val_display = format_calculation_display(num_val, decimal_places=_dec)
                        except (TypeError, ValueError):
                            val_display = val_txt
                        res = ("\u2713 PASS" if "PASS" in (status or "") else "\u2717 FAIL") if status else ""
                        tol_display = f"{val_display}{unit_str}"
                        if tol_used:
                            tol_display += tol_used
                        _add_row(group_name, variables_str, f"{label}: {tol_display}", "", res)
                    continue

                # 2) Convert-type fields: do not display in tolerance (pass/fail) section
                if (f.get("data_type") or "").strip().lower() == "convert":
                    continue

                # 3) Bool fields with bool tolerance — display single "Pass" or "Fail" (not "True ✓ PASS" / "Pass, Pass")
                if data_type == "bool" and tol_type == "bool":
                    pass_when = (v.get("tolerance_equation") or "true").strip().lower()
                    reading_bool = val_txt in ("1", "true", "yes", "on")
                    variables_str = _variables_string(None, None)  # bool has no refs; may have checked numbers
                    if pass_when not in ("true", "false"):
                        _add_row(group_name, variables_str, f"{label}: {'Pass' if reading_bool else 'Fail'}", "", "")
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
                    _add_row(group_name, variables_str, f"{label}: {result}", "", result)
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
                            variables_str = _variables_string(ref1, ref2)
                            if any(var not in vars_map for var in required):
                                missing = [var for var in required if var not in vars_map]
                                _add_row(group_name, variables_str, f"{label}: — (need: {', '.join(missing)})", "", "")
                            else:
                                parts = equation_tolerance_display(eq, vars_map)
                                if parts is not None:
                                    lhs, op_str, rhs, pass_ = parts
                                    _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                                    val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                                    _add_row(group_name, variables_str, f"{label}: {val_str}", "", "PASS" if pass_ else "FAIL")
                                elif evaluate_pass_fail:
                                    try:
                                        reading = vars_map.get("reading", 0.0)
                                        pass_, _, _ = evaluate_pass_fail(
                                            "equation", None, eq, nominal, reading,
                                            vars_map=vars_map, tolerance_lookup_json=None,
                                        )
                                        _add_row(group_name, variables_str, f"{label}: PASS" if pass_ else f"{label}: FAIL", "", "PASS" if pass_ else "FAIL")
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
                            variables_str = _variables_string(ref1, ref2)
                            if any(var not in vars_map for var in required):
                                missing = [var for var in required if var not in vars_map]
                                _add_row(group_name, variables_str, f"{label}: — (need: {', '.join(missing)})", "", "")
                            else:
                                result = evaluate_tolerance_equation(eq, vars_map)
                                _dec = max(0, min(4, int(f.get("sig_figs") or 3)))
                                _add_row(group_name, variables_str, f"{label}: {format_calculation_display(result, decimal_places=_dec)}", "", "")
                        except (ImportError, ValueError, TypeError):
                            variables_str = _variables_string(f.get("calc_ref1_name"), f.get("calc_ref2_name"))
                            _add_row(group_name, variables_str, f"{label}: —", "", "")
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
                    variables_str = _variables_string(ref1, ref2)
                    if display_parts is not None:
                        lhs, op_str, rhs, pass_ = display_parts
                        from tolerance_service import format_calculation_display
                        _dec = max(0, min(4, int(v.get("sig_figs") or f.get("sig_figs") or 3)))
                        val_str = f"{format_calculation_display(lhs, decimal_places=_dec)} {op_str} {format_calculation_display(rhs, decimal_places=_dec)}"
                        _add_row(group_name, variables_str, f"{label}: {val_str}", "", "PASS" if pass_ else "FAIL")
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
                        _add_row(group_name, variables_str, f"{label}: {val_display}{unit_str}", "", res)
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
            tpl_id = template_service.create_template(
                self.repo,
                inst_type_id,
                "External calibration file",
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
            attachment_service.add_attachment(self.repo, self.instrument_id, path, record_id=rec_id)
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
       
