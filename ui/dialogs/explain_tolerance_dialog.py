# ui/dialogs/explain_tolerance_dialog.py - Read-only explanation of tolerance calculation

from PyQt5 import QtWidgets


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
