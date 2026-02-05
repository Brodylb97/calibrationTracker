# Stability and UX Improvements — Proposal (Current Scope)

*Safe, incremental improvements that build on recent fixes (PDF plot export, calibration history tolerance display, instrument failed-flag). No large refactors.*

**Status: Implemented** (all items from the suggested order of work have been completed)

---

## Context

Recent work addressed:

- **PDF plot export**: Plot rendering when groups have no table columns; vars_map from `record_values_by_name`; page break after plot when a non-Signature group follows; matplotlib/numpy-only rendering.
- **Calibration History**: Tolerance values show ref labels and values instead of group name; plot equation validation catches `SyntaxError`.
- **Instrument list**: Flagging for instruments whose most recent calibration failed (column + filter + row styling).

The codebase already has: global excepthook and `crash_log`, database integrity check on startup, PDF export in a worker thread with progress and cancel, and solid filter/sort in the instrument table.

---

## 1. Stability Improvements (Safe, High Value)

### 1.1 Defensive checks in PDF export

**Risk:** Low. **Effort:** Low.

- **`_vars_map_for_plot`**: If `record_values_by_name` or `template_fields` is missing/empty, return an empty dict and avoid `TypeError` in callers.
- **`_render_plot_to_png`**: Guard against non-finite floats in `xs`/`ys` (e.g. `float('nan')`) before calling numpy; replace or skip and return `b""` with a log line.
- **Group iteration**: When building `template_group_order`, if `template_fields_sorted` is empty, skip the group loop cleanly instead of relying on downstream code.

**Why:** Prevents rare crashes when data is incomplete or malformed (e.g. bad template, partial record).

---

### 1.2 Logging in critical paths

**Risk:** Low. **Effort:** Low.

- **PDF export**: When a plot is skipped (missing equation, missing vars, render error), log once at INFO with a short reason (e.g. `logger.info("Plot skipped for record %s: %s", rec_id, reason)`). Helps diagnose “no plot” without touching UI.
- **Calibration save**: On success, log at DEBUG (record id, instrument id). On validation or DB error, log at WARNING with context (e.g. which dialog, which field failed). Use existing `crash_log.logger` or a named logger.

**Why:** Supports support and debugging without changing user-facing behavior.

---

### 1.3 Database / list_instruments robustness

**Risk:** Low. **Effort:** Low.

- **`list_instruments` subquery**: If `PRAGMA table_info(calibration_records)` fails or returns an unexpected structure, catch the exception, log it, and run the query *without* the `last_cal_result` column so the list still loads (flag column will be blank).
- **Instrument table model**: When reading `inst.get("last_cal_result")`, treat non-string values (e.g. from an old code path) with `str(...).strip().upper()` so the flag and filter still behave.

**Why:** Ensures the main window and instrument list remain usable even if the new subquery hits an edge case.

---

### 1.4 Tolerance service / equation validation

**Risk:** Low. **Effort:** Low.

- **`parse_plot_equation`**: Already raises `ValueError` and can raise `SyntaxError` from `ast.parse`. UI now catches both. In `tolerance_service`, document that callers should catch `SyntaxError` as well as `ValueError` for incomplete input.
- **`evaluate_plot_equation`**: If `vars_map` is None, treat as empty dict (or raise a clear `ValueError`) so callers get a consistent error message.

**Why:** Clear contract and fewer surprises when equations are incomplete or vars are missing.

---

## 2. UX Improvements (Safe, High Impact)

### 2.1 Clearer feedback when no plot appears in PDF

**Risk:** Low. **Effort:** Low.

- The PDF already appends a message when no plot could be generated (with `_plot_last_error`). Ensure that message is always user-facing and concise (e.g. “No plot could be generated. Ensure the plot equation uses PLOT([val1, val3, …], [val2, val4, …]) and that val1–val12 are assigned to fields with numeric data.”).
- Optionally add a one-line hint in the field editor (e.g. in the plot equation tooltip): “Charts appear in PDF export; ensure refs point to fields that have values for this record.”

**Why:** Reduces confusion when a user expects a chart but the record or refs are missing data.

---

### 2.2 Instrument Flag column tooltip

**Risk:** None. **Effort:** Trivial.

- Set a tooltip on the “Flag” column header (or on the first cell of that column) explaining: “Shows ⚠ Fail when the most recent calibration for this instrument failed. Use ‘Last cal failed’ in Needs Attention to filter.”

**Why:** Makes the new column and filter discoverable.

---

### 2.3 Calibration History — “Tolerance values” label

**Risk:** None. **Effort:** Trivial.

- The details area label is “Tolerance values (pass/fail)”. Optionally add a short tooltip: “Pass/fail per tolerance point. Ref labels and values shown for each point.”

**Why:** Aligns expectations with the new display (ref labels + values instead of group name).

---

### 2.4 Export progress and cancel (already in place)

- Export already runs in a worker thread with a progress dialog (“Exporting current/total…”) and a working Cancel that sets `cancelled_check`. No change needed here; only ensure any new export paths (e.g. single-record export) also use the same pattern if they can be long-running.

---

## 3. What to Defer (Stay Safe)

- **Large UI refactors** (e.g. inline validation everywhere, new layout system): Higher risk; better as a separate plan.
- **Schema changes** for flagging: Current design (subquery in `list_instruments`) is sufficient and avoids migrations.
- **New features** (e.g. Excel export of calibrations): Out of scope for this stability/UX pass.

---

## 4. Suggested Order of Work

| Priority | Item | Area |
|----------|------|------|
| 1 | Defensive checks in PDF export (`_vars_map_for_plot`, `_render_plot_to_png`, group iteration) | Stability |
| 2 | `list_instruments` subquery fallback when last_cal_result fails | Stability |
| 3 | Logging in PDF export (plot skipped) and calibration save (failure context) | Stability |
| 4 | Tooltip for Flag column; tooltip/label for Calibration History “Tolerance values” | UX |
| 5 | Document `SyntaxError` + `ValueError` for plot equation; optional `vars_map` guard in `evaluate_plot_equation` | Stability |

---

## 5. Summary

- **Stability**: Add defensive checks and fallbacks in PDF export and instrument list, plus targeted logging, so that bad or incomplete data does not crash the app and issues are easier to diagnose.
- **UX**: Small, copy/tooltip-level improvements so plot-in-PDF expectations, the failed-cal flag, and the new tolerance display are clear.

All items are backward-compatible and avoid schema or behavioral breaking changes.
