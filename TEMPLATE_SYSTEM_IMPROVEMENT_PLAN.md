# Template System Improvement Plan

**Calibration Tracker — ISO/IEC 17025–aligned template authoring and tolerance handling**

This document provides a prioritized improvement list, schema changes, UI integration points, safe equation evaluation patterns, and risk mitigation for the template system. Design goals: **powerful, safe, audit-ready, and easy to use** without architectural rewrites.

---

## Current State Summary

| Area | Current | Gap |
|------|---------|-----|
| **Templates** | `calibration_templates`: id, instrument_type_id, name, version, is_active, notes | No effective_date; no change reason; no lock on approved |
| **Fields** | `calibration_template_fields`: name, label, data_type, unit, required, sort_order, group_name, calc_type, calc_ref1/2, **tolerance (REAL)**, autofill, default_value | Single numeric tolerance only; no nominal; no tolerance_type or equation |
| **Tolerance** | One real number per field; used only with ABS_DIFF / PCT_ERROR / PCT_DIFF | No fixed/percent/equation/lookup choice; no equation editor or test panel |
| **Pass/fail** | Evaluated in `CalibrationFormDialog` and history details; logic in UI | Not in a central service; no “explain tolerance” or plain-language view |
| **Records** | `calibration_records` store template_id only | No template_revision stored; cannot reproduce exact procedure at audit time |
| **Field editor** | Modal FieldEditDialog; table list in TemplateFieldsDialog | No wizard; no inline edit; no bulk apply; no drag-drop; no summary row |
| **Help** | Some tooltips and Help dialog content | No contextual “What does this mean?”; no example templates; no ISO clause links |

---

## 1. Prioritized Improvement List

### High priority (safety, audit, single source of truth)

| ID | Item | Rationale |
|----|------|-----------|
| H1 | **Central tolerance evaluation service** | Move pass/fail and tolerance logic out of UI into a single module; single source of truth for units, variables, and evaluation. Required for equation-based tolerances and audit defensibility. |
| H2 | **Tolerance type + equation storage (schema)** | Add `tolerance_type` (fixed \| percent \| equation \| lookup), `tolerance_equation` (text), optional `nominal_value`; keep backward compatibility with existing `tolerance` REAL. |
| H3 | **Safe equation evaluation (sandbox)** | Restrict to a minimal DSL or safe subset (e.g. `ast` + whitelist of operators/functions). No `eval(unsafe_input)`. Validation API: parse, list variables, evaluate with sample inputs, unit check. |
| H4 | **Template version + revision on records** | Store `template_version` (and optionally template snapshot id) on `calibration_records`; add `effective_date` and `change_reason` to templates. Link every calibration to template ID + revision. |
| H5 | **Validation and guardrails before save** | In template/field save: validate equation syntax, undefined variables, unit compatibility; warn on very tight tolerance or discontinuous-looking expressions; block approval if validation fails. |
| H6 | **“Explain tolerance” (preview)** | Read-only preview: show nominal, tolerance (expanded from equation), unit; “Explain” shows calculation in words and substituted values (technical + plain-language toggle). |

### Medium priority (UX, productivity, learning)

| ID | Item | Rationale |
|----|------|-----------|
| M1 | **Tolerance type selector in field editor** | UI: Fixed / Percentage / Equation / Lookup table. Each option: short plain-language description + inline example. |
| M2 | **Equation editor + variable picker** | For equation-based tolerance: syntax-highlighted (or plain) editor; variable picker (nominal, reading, ref1, ref2, etc.); insert-variable buttons; inline validation (syntax, undefined vars). |
| M3 | **Test equation panel** | Sample inputs for nominal/reading/environment; live tolerance result; pass/fail for sample reading; no guessing. |
| M4 | **Template creation wizard (optional)** | Steps: instrument & unit → measurement points → tolerance definition → review. Skip for advanced users. Persist drafts. |
| M5 | **Measurement point UX** | Inline editing in field table where possible; bulk: “Apply tolerance to selected”, “Shift nominals by offset”; drag-drop reorder; summary row (point count, tightest/widest tolerance, optional risk indicator). |
| M6 | **Template clone + “Copy from similar”** | Clone template; “Copy from similar” by instrument type; highlight differences from source. |
| M7 | **Smart defaults** | Remember last-used tolerance type; suggest common tolerance formats by instrument type; optional “frequently used equations” list. |
| M8 | **Version diff + change reason** | When creating new revision: mandatory change reason; diff view (fields/tolerance equation changes); lock approved revision read-only. |

### Later (polish, scale, optional)

| ID | Item | Rationale |
|----|------|-----------|
| L1 | **Lookup-table tolerance** | Table: range (e.g. nominal range) → tolerance value. UI: add/edit rows; evaluation service resolves range → value. |
| L2 | **Example template library** | Ship or link Voltage, Temperature, Pressure, Dimensional examples; contextual “Load example”. |
| L3 | **Embedded help** | “What does this mean?” for uncertainty, tolerance equation; tooltips with examples; optional ISO clause references. |
| L4 | **Accessibility polish** | Keyboard navigation, tab order, focus indicators, readable errors; avoid color-only pass/fail (e.g. icon + text). |
| L5 | **Test coverage** | Unit tests for equation parsing, edge cases (divide by zero, missing vars), regression for existing ABS_DIFF/PCT_* behavior. |

---

## 2. Database Schema Changes and Migration Strategy

### 2.1 New columns (add via migrations, preserve existing data)

**`calibration_templates`**

| Column | Type | Purpose |
|--------|------|---------|
| `effective_date` | TEXT (YYYY-MM-DD) NULL | When this revision became effective |
| `change_reason` | TEXT NULL | Mandatory when creating new revision (stored on the *new* row) |
| `status` | TEXT DEFAULT 'Draft' | Draft \| Approved \| Archived; Approved can be locked read-only |

**`calibration_template_fields`**

| Column | Type | Purpose |
|--------|------|---------|
| `tolerance_type` | TEXT NULL | 'fixed' \| 'percent' \| 'equation' \| 'lookup' (NULL = legacy fixed) |
| `tolerance_equation` | TEXT NULL | For tolerance_type = 'equation'; e.g. "0.02 * abs(nominal)" |
| `nominal_value` | TEXT NULL | Default nominal for this point (display + equation vars) |
| `tolerance_lookup_json` | TEXT NULL | For tolerance_type = 'lookup'; JSON array of {range_low, range_high, tolerance} |

**`calibration_records`**

| Column | Type | Purpose |
|--------|------|---------|
| `template_version` | INTEGER NULL | Version of template at time of calibration (audit trail) |

Existing rows: `template_version` = NULL meaning “use current template version at read time”; new records set it from `calibration_templates.version` when creating.

### 2.2 Migration strategy

- **Schema version**: Bump (e.g. migration 5) after adding columns.
- **Add columns** with `ALTER TABLE ... ADD COLUMN`; all new columns nullable or with defaults.
- **Backfill**: Set `tolerance_type = 'fixed'` where `tolerance IS NOT NULL` and `tolerance_type IS NULL`; set `status = 'Draft'` for existing templates if status column added.
- **No drop**: Do not remove existing `tolerance` REAL; keep it as the resolved value for fixed tolerance or as cache for equation result.
- **Application code**: Prefer `tolerance_type` + `tolerance_equation` when present; fall back to `tolerance` for legacy fixed.

### 2.3 Example migration (pseudocode)

```python
# migrations.py — add migration_5_template_tolerance_and_versioning

def migrate_5_template_tolerance_and_versioning(conn):
    cur = conn.cursor()
    # calibration_templates
    for col, typ, default in [
        ("effective_date", "TEXT", None),
        ("change_reason", "TEXT", None),
        ("status", "TEXT", "'Draft'"),
    ]:
        if not _has_column(cur, "calibration_templates", col):
            conn.execute(f"ALTER TABLE calibration_templates ADD COLUMN {col} {typ}" + (f" DEFAULT {default}" if default else ""))
    # calibration_template_fields
    for col, typ in [
        ("tolerance_type", "TEXT"),
        ("tolerance_equation", "TEXT"),
        ("nominal_value", "TEXT"),
        ("tolerance_lookup_json", "TEXT"),
    ]:
        if not _has_column(cur, "calibration_template_fields", col):
            conn.execute(f"ALTER TABLE calibration_template_fields ADD COLUMN {col} {typ}")
    # calibration_records
    if not _has_column(cur, "calibration_records", "template_version"):
        conn.execute("ALTER TABLE calibration_records ADD COLUMN template_version INTEGER")
    # Backfill: existing numeric tolerance => fixed
    conn.execute("""
        UPDATE calibration_template_fields
        SET tolerance_type = 'fixed'
        WHERE tolerance IS NOT NULL AND (tolerance_type IS NULL OR tolerance_type = '')
    """)
    conn.commit()
```

---

## 3. UI Integration Points

| Location | Change |
|----------|--------|
| **FieldEditDialog** | Add tolerance type combo (Fixed / Percent / Equation / Lookup). Show/hide: fixed → tolerance spinbox; percent → % + reference (e.g. nominal); equation → equation editor + variable picker + “Test”; lookup → table editor. Plain-language description + example per type. |
| **TemplateFieldsDialog** | Inline edit for name/label/unit/nominal where feasible; “Apply tolerance to selected”; “Shift nominals”; drag-drop reorder; summary row (count, min/max tolerance). Optional “Bulk set tolerance type”. |
| **TemplateEditDialog** | On “New revision”: prompt for change_reason, set effective_date (default today), clone fields; show diff from previous version (optional in M8). Status dropdown (Draft/Approved/Archived); Approved → lock edits. |
| **CalibrationFormDialog** | No change to pass/fail *logic* (moved to service); call `ToleranceService.evaluate(field, values_by_name)` for each computed/difference field; use result for auto-FAIL and for “Explain” in preview. |
| **New: Template Preview / Explain** | Read-only view: list points with nominal, tolerance (numeric, or “from equation”), unit. “Explain tolerance” button → modal/side panel: formula, substituted values, result; toggle Technical / Plain language. |
| **New: Template Creation Wizard** | Optional entry from “New template” or “Add template”. Steps: 1) Instrument type & unit 2) Add measurement points (name, nominal, unit) 3) Set tolerance per point or bulk 4) Review & save (as draft). Skip wizard link for advanced. |
| **Calibration history / record view** | Display template name + version (from record.template_version or template.version); link to “View template at this version” (read-only) if versioning snapshot exists. |

---

## 4. Central Tolerance Evaluation Service

Single module (e.g. `tolerance_service.py`) used by UI and any batch/export code.

### 4.1 Responsibilities

- **Parse** tolerance equation (syntax only).
- **List variables** required by an equation.
- **Evaluate** tolerance (fixed, percent, or equation) given a variable map.
- **Evaluate pass/fail** for a reading vs nominal and tolerance (with unit awareness if needed).
- **Explain** in plain language (e.g. “Tolerance = 0.02 × |nominal| = 0.04 for nominal 2.0”).

### 4.2 Safe equation evaluation (Python example)

Do **not** use `eval(user_input)`. Use AST + whitelist:

```python
# tolerance_service.py — safe equation evaluation

import ast
import operator
from typing import Any

# Allowed node types and binary ops
ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}
ALLOWED_FUNCS = {"abs": abs, "min": min, "max": max}  # extend as needed


def _eval_node(node: ast.AST, vars_map: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value) if isinstance(node.value, (int, float)) else 0.0
    if isinstance(node, ast.Name):
        return float(vars_map.get(node.id, 0.0))
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, vars_map)
        right = _eval_node(node.right, vars_map)
        op = ALLOWED_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed operator: {node.op}")
        return op(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, vars_map)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCS:
            args = [_eval_node(a, vars_map) for a in node.args]
            return float(ALLOWED_FUNCS[node.func.id](*args))
        raise ValueError("Disallowed function")
    raise ValueError("Unsupported expression")


def parse_equation(equation: str) -> ast.Expression:
    """Parse equation string; raise ValueError on syntax error or disallowed construct."""
    tree = ast.parse(equation, mode="eval")
    # Optional: walk tree and reject ast.Call to unknown functions, ast.Attribute, etc.
    return tree.body


def list_variables(equation: str) -> list[str]:
    """Return list of variable names used in the equation."""
    tree = ast.parse(equation, mode="eval")
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
    return list(dict.fromkeys(names))


def evaluate_tolerance_equation(equation: str, vars_map: dict[str, float]) -> float:
    """Evaluate equation with given variables. Raises on error."""
    body = parse_equation(equation)
    return _eval_node(body, vars_map)
```

- **Validation**: Before save, call `parse_equation`; if it fails, show error and block save. Call `list_variables` and check against allowed names (nominal, reading, ref1, ref2, etc.); warn on undefined.
- **Unit checks**: If you introduce units in the equation (e.g. “nominal_V”), validate that equation result is dimensionless or matches expected unit; optional in v1.

### 4.3 Pass/fail and “Explain” (pseudocode)

```python
def evaluate_pass_fail(
    tolerance_type: str,
    tolerance_fixed: float | None,
    tolerance_equation: str | None,
    nominal: float,
    reading: float,
    vars_map: dict[str, float],
) -> tuple[bool, float, str]:
    """
    Returns (pass: bool, tolerance_used: float, explanation: str).
    """
    if tolerance_type == "percent":
        # e.g. tolerance_equation or fixed stored as "2.0" meaning 2%
        tol_pct = tolerance_fixed or 0.0
        tol_value = abs(nominal) * (tol_pct / 100.0) if nominal else 0.0
        diff = abs(reading - nominal)
        pass_ = diff <= tol_value
        explanation = f"Tolerance = {tol_pct}% of |nominal| = {tol_value}; |reading − nominal| = {diff} → {'PASS' if pass_ else 'FAIL'}"
        return pass_, tol_value, explanation
    if tolerance_type == "equation":
        tol_value = evaluate_tolerance_equation(tolerance_equation, vars_map)
        diff = abs(reading - nominal)
        pass_ = diff <= tol_value
        explanation = f"Tolerance (from equation) = {tol_value}; |reading − nominal| = {diff} → {'PASS' if pass_ else 'FAIL'}"
        return pass_, tol_value, explanation
    # fixed (or legacy)
    tol_value = tolerance_fixed or 0.0
    diff = abs(reading - nominal)
    pass_ = diff <= tol_value
    return pass_, tol_value, f"Tolerance = {tol_value}; diff = {diff} → {'PASS' if pass_ else 'FAIL'}"
```

---

## 5. Validation Logic (Guardrails)

- **On field save (equation type)**  
  - Parse equation; on syntax error → block save, show message.  
  - List variables; if any variable not in allowed set → warn (or block if strict).  
  - Optional: “Test with sample values” and show result.

- **On template approve**  
  - All equation-type tolerances parse and have only allowed variables.  
  - No required field missing.  
  - Optional: unit consistency check.

- **Warnings (do not block save)**  
  - Tolerance very small (e.g. &lt; 1e-9) or very large.  
  - Equation contains division by expression that could be zero (e.g. `nominal` in denominator).  
  - New revision with no change reason.

- **Block**  
  - Equation syntax error.  
  - Required variable missing when evaluating (at run time, fail that point and optionally overall FAIL).

---

## 6. Risk Analysis and Mitigation

| Risk | Mitigation |
|------|-------------|
| **Code injection via equation** | No `eval()`; AST + whitelist of operators and functions only; no `__import__`, `open`, etc. |
| **Division by zero / overflow** | In `_eval_node`, check denominator; cap or return error for extreme values; in UI show “Invalid” and do not mark PASS. |
| **Audit: “Which procedure was used?”** | Store template_version (and effective_date in template) on every calibration record; optional snapshot of template at approval. |
| **Operator confusion** | “Explain tolerance” in plain language; examples in UI; optional wizard; tooltips. |
| **Regression of existing pass/fail** | Central service implements current ABS_DIFF/PCT_* behavior first; unit tests for existing templates; feature flag or tolerance_type=legacy path. |
| **Complexity creep** | Phase equation and lookup-table support; keep fixed and percent in same UI first; add equation in next phase. |

---

## 7. Design Philosophy Checklist

- **Hard to mess up**: Wizard optional; defaults; validation before save; “Test equation” panel.  
- **Easy to review**: Preview mode; “Explain tolerance”; diff view between revisions; summary row on points.  
- **Age well under audits**: Template ID + version + effective_date on records; change reason; lock approved revisions.  
- **Minimal tribal knowledge**: Plain-language explanations; contextual help; examples; no PDF manuals required.

---

## 8. Suggested Implementation Order

1. **Phase 1 (High)**  
   - Add migration for new columns (templates, fields, records).  
   - Implement `tolerance_service.py` with fixed + percent + equation (AST whitelist); integrate current ABS_DIFF/PCT_* logic into service; call from CalibrationFormDialog.  
   - Add tolerance_type (and equation) to FieldEditDialog; validation on save.  
   - Store template_version when creating calibration record; show in history.

2. **Phase 2 (Medium)**  
   - Template preview + “Explain tolerance” (technical + plain).  
   - Variable picker and “Test equation” in field editor.  
   - Template wizard (optional), draft persistence.  
   - Measurement point UX: inline edit, bulk apply, reorder, summary row.

3. **Phase 3 (Later)**  
   - Lookup-table tolerance; example library; embedded help; accessibility polish; test coverage.

---

## 9. Test Coverage (Targets)

- **Equation parsing**: Valid expressions, invalid syntax, disallowed ops/funcs.  
- **Variable listing**: Correct set of names.  
- **Evaluation**: Sample vars → correct tolerance and pass/fail.  
- **Edge cases**: Division by zero, very large/small numbers, missing variable.  
- **Regression**: Existing templates with ABS_DIFF/PCT_ERROR/PCT_DIFF produce same result via service as current UI logic.

This plan keeps the application incremental and maintainable while moving toward full equation-based tolerances, clear auditability, and a better authoring experience.
