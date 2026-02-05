# Stability and UX Improvements — Summary

*Quick reference. Full detail: `STABILITY_AND_UX_IMPROVEMENTS_PROPOSAL.md`.*

**Status: Implemented**

---

## Stability (safe, incremental)

- **PDF export:** Guard `_vars_map_for_plot` when `record_values_by_name` or template data is missing. In `_render_plot_to_png`, handle non-finite values in `xs`/`ys` before calling numpy. Skip group loop cleanly when there are no template fields.
- **Logging:** Log when a plot is skipped in PDF (reason). Log calibration save failures with context (which dialog/field) at WARNING.
- **Database / instruments:** If the `last_cal_result` subquery in `list_instruments` fails, catch, log, and run the query without that column so the list still loads. In the table model, normalize `last_cal_result` (e.g. `str(...).strip()`) so the flag/filter work with odd data.
- **Tolerance / plot equations:** Document that plot equation callers should catch both `ValueError` and `SyntaxError`. In `evaluate_plot_equation`, handle `vars_map is None` (e.g. treat as `{}` or raise a clear error).

## UX (low risk)

- **PDF “no plot” message:** Keep the existing message clear and user-facing; optionally add a short plot-equation/ref hint in the field editor tooltip.
- **Instrument Flag:** Add a tooltip on the Flag column: e.g. “Shows ⚠ Fail when the most recent calibration failed. Use ‘Last cal failed’ in Needs Attention to filter.”
- **Calibration History:** Add a short tooltip on “Tolerance values (pass/fail)”: e.g. “Pass/fail per point; ref labels and values shown.”

## Deferred

- Large UI refactors (e.g. full inline validation).
- Schema changes for flagging (current subquery approach is sufficient).
- New features (e.g. Excel calibration export).

## Priority order

1. Defensive checks in PDF export.
2. `list_instruments` subquery fallback when `last_cal_result` fails.
3. Logging in PDF export and calibration save.
4. Tooltips for Flag column and Calibration History “Tolerance values”.
5. Document plot equation exceptions; optional `vars_map` guard in `evaluate_plot_equation`.
