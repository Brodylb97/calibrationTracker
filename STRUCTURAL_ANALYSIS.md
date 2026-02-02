# Calibration Tracker — Structural Analysis & Streamlining Plan

*Generated for incremental migration. No rewrites; preserve existing behavior.*

**Status:** Migration completed 2025-01-30. Phases A–D implemented.

---

## 1. Current Structure Summary

### File Tree (Python and Key Assets)

```
CT/
├── main.py                 # Entry point, crash recovery, arg parsing
├── ui_main.py              # Thin shim: from ui.run import run_gui
├── database.py             # Repository, schema init, path/config (≈1800 lines)
├── database_backup.py      # Daily backup, integrity check
├── migrations.py           # Schema versioning
├── tolerance_service.py    # Equation parsing, pass/fail evaluation
├── pdf_export.py           # PDF generation
├── crash_log.py            # Global excepthook, logging
├── lan_notify.py           # LAN reminder broadcast
├── lan_listener.py         # (standalone, not imported)
├── email_utils.py          # (standalone, not imported)
├── debug_types.py          # Dev script: list instrument types (not imported)
├── update_checker.py       # Version check, update UI integration
├── update_app.py           # Download/extract update
├── build_update_package.py # Release packaging
├── release.py              # Release automation
├── domain/
│   ├── __init__.py
│   └── models.py           # Instrument dataclass
├── ui/
│   ├── __init__.py
│   ├── run.py              # run_gui()
│   ├── main_window.py      # MainWindow (≈1177 lines)
│   ├── models.py           # InstrumentTableModel, HighlightDelegate, FilterProxy
│   ├── help_content.py     # Help dialog, markdown content
│   ├── theme.py            # Themes, apply_global_style, validation
│   ├── theme_storage.py    # Custom theme persistence
│   ├── theme_utils.py      # Color picker, hex validation
│   ├── theme_preview.py    # Theme preview widget
│   ├── theme_models.py     # ThemeInfo dataclass (unused)
│   └── dialogs/
│       ├── __init__.py     # Re-exports
│       ├── all_dialogs.py  # 19 dialog classes (≈4060 lines)
│       └── theme_editor_dialog.py
├── restart_helper/         # C helper for post-update restart
├── Signatures/
├── .cursor/
└── [config, docs, tests: *.md, *.json, *.bat, ...]
```

### Module Responsibility Matrix

| Module | Responsibility | Imports (internal) | Imported By |
|--------|----------------|--------------------|-------------|
| **main.py** | Entry, crash recovery, DB init | database, ui_main, crash_log, lan_notify | — |
| **ui_main.py** | Shim for run_gui | ui.run | main.py |
| **database.py** | Repository, schema, paths, config | domain.models (TYPE_CHECKING), migrations, database_backup | main, ui.run, ui.main_window, ui.dialogs.*, pdf_export, lan_notify, email_utils, debug_types |
| **database_backup.py** | Backup, integrity | — | database |
| **migrations.py** | Schema migrations | — | database |
| **tolerance_service.py** | Equation eval | — | ui.dialogs.all_dialogs, pdf_export |
| **pdf_export.py** | PDF generation | database, tolerance_service | ui.main_window, ui.dialogs.all_dialogs |
| **crash_log.py** | Excepthook, logging | — | main |
| **lan_notify.py** | LAN reminders | database (type hint) | main, ui.main_window |
| **update_checker.py** | Version check | — | ui.main_window, ui.run |
| **update_app.py** | Update download | — | (standalone CLI) |
| **domain/models.py** | Instrument dataclass | — | database |
| **ui/run.py** | run_gui | database, ui.main_window, ui.theme, update_checker | ui_main |
| **ui/main_window.py** | MainWindow | database, lan_notify, ui.*, dialogs, update_checker, pdf_export | ui.run |
| **ui/models.py** | Table models, delegate | — | ui.main_window |
| **ui/help_content.py** | Help dialog | — | ui.main_window, ui.dialogs.all_dialogs |
| **ui/theme.py** | Themes, styling | ui.theme_storage (lazy) | ui.run, ui.main_window, ui.dialogs.theme_editor, theme_* |
| **ui/theme_storage.py** | Custom theme persistence | ui.theme | ui.theme, ui.dialogs.theme_editor |
| **ui/theme_utils.py** | Color picker, hex validation | ui.theme | ui.dialogs.theme_editor |
| **ui/theme_preview.py** | Preview widget | ui.theme | ui.dialogs.theme_editor |
| **ui/theme_models.py** | ThemeInfo (unused) | ui.theme | — |
| **ui/dialogs/all_dialogs.py** | 19 dialogs | database, ui.help_content, tolerance_service, pdf_export | ui.main_window, ui.dialogs.__init__ |
| **ui/dialogs/theme_editor_dialog.py** | Theme editor | ui.theme*, theme_storage, theme_utils, theme_preview | ui.main_window, ui.dialogs.__init__ |

---

## 2. Key Problems (Ranked by Impact)

### P1 — Monolithic all_dialogs.py (~4060 lines, 19 classes)

**Impact: High** — Navigation, merges, and testing are difficult; single-file churn risk.

- 19 dialog classes in one file
- Mixed concerns: UI, validation, direct repo calls, tolerance_service, pdf_export
- “Temporary consolidation” comment implies intended split

### P2 — database.py Overload (~1800 lines)

**Impact: High** — Path/config, schema init, repository, and migrations all in one module.

- `database.py` does: paths, config, connection, schema init, migrations hook, CalibrationRepository, backup trigger
- Repository alone is large; paths/config are separate concerns

### P3 — Unused or Orphan Modules

**Impact: Medium** — Dead code, confusion, misleading surface area.

| Module | Status |
|--------|--------|
| **ui/theme_models.py** | ThemeInfo defined but never imported |
| **email_utils.py** | Not imported anywhere |
| **lan_listener.py** | Not imported anywhere |
| **debug_types.py** | Dev utility, never imported |

### P4 — Theme Module Fragmentation

**Impact: Medium** — Five theme-related modules; some overlap.

- `theme.py`, `theme_storage.py`, `theme_utils.py`, `theme_preview.py`, `theme_models.py`
- `theme_utils` is thin (~28 lines); could live in `theme.py` or `theme_editor_dialog`
- `theme_models` is dead

### P5 — Naming and Placement Inconsistencies

**Impact: Medium** — Ambiguity and rule drift.

- `ui/models.py` = Qt table models, not domain models
- Rules prefer `services/`, `persistence/` — not present
- `ui_main.py` vs `ui/run.py`: two entry layers

### P6 — Root-Level Sprawl

**Impact: Low–Medium** — Many top-level modules; docs and scripts mixed with app code.

- App: main, database, pdf_export, tolerance_service, crash_log, lan_*, update_*, email_utils, debug_types
- Build: build_*.bat, build_update_package.py, release.py
- Docs: multiple *.md plans

---

## 3. Proposed Target Structure

```
CT/
├── main.py
├── ui_main.py                    # Keep for backward compatibility
│
├── database.py                   # Keep as-is for now (see migration)
├── database_backup.py
├── migrations.py
│
├── services/                     # NEW — orchestration layer (future)
│   └── __init__.py
│
├── domain/
│   ├── __init__.py
│   └── models.py
│
├── ui/
│   ├── __init__.py
│   ├── run.py
│   ├── main_window.py
│   ├── table_models.py           # RENAME from models.py (disambiguate)
│   ├── help_content.py
│   │
│   ├── theme/
│   │   ├── __init__.py           # Re-export theme API
│   │   ├── core.py               # theme.py content
│   │   ├── storage.py            # theme_storage.py
│   │   ├── preview.py            # theme_preview.py
│   │   └── editor.py             # theme_editor_dialog (moved from dialogs)
│   │
│   └── dialogs/
│       ├── __init__.py
│       ├── instrument.py         # InstrumentDialog
│       ├── settings.py           # SettingsDialog
│       ├── attachments.py        # AttachmentsDialog
│       ├── destinations.py       # DestinationEdit, Destinations
│       ├── personnel.py          # PersonnelEdit, Personnel
│       ├── templates.py          # TemplateEdit, FieldEdit, TemplateFields, Templates
│       ├── calibration.py        # CalibrationForm, CalibrationHistory, CalDate
│       ├── batch.py              # BatchUpdate, BatchAssignInstrumentType
│       ├── explain_tolerance.py  # ExplainToleranceDialog
│       ├── instrument_info.py    # InstrumentInfoDialog
│       ├── audit_log.py          # AuditLogDialog
│       └── _all.py               # Optional: backward-compat re-exports
│
├── tolerance_service.py          # Keep
├── pdf_export.py                 # Keep
├── crash_log.py
├── lan_notify.py
├── update_checker.py
├── update_app.py
│
├── scripts/                      # NEW — dev/build helpers
│   ├── __init__.py
│   ├── debug_types.py
│   ├── build_update_package.py
│   └── release.py
│
├── restart_helper/
├── Signatures/
├── .cursor/
└── [config, docs, tests]
```

### Deferred / Deprecated (Not Moved Yet)

| Item | Action |
|------|--------|
| **email_utils.py** | Deprecate or move to `scripts/` if needed later |
| **lan_listener.py** | Deprecate or move to `scripts/` if needed |
| **ui/theme_models.py** | Merge into theme/core or delete |
| **theme_utils.py** | Merge into theme/core (small) |

---

## 4. File-by-File Recommendations

### High Priority

| File | Recommendation |
|------|----------------|
| **ui/dialogs/all_dialogs.py** | Split into one file per logical group (see target structure). Start with smallest dialogs. |
| **ui/models.py** | Rename to `ui/table_models.py` to avoid confusion with `domain/models`. |
| **ui/theme_models.py** | Delete or merge `ThemeInfo` into `theme/core.py` if ever used. |

### Medium Priority

| File | Recommendation |
|------|----------------|
| **theme_utils.py** | Merge `open_color_picker`, `validate_hex_input` into `theme/core.py` or `theme/editor.py`. |
| **ui/theme.py + theme_*.py** | Group under `ui/theme/` package; keep imports backward-compatible via `ui/theme/__init__.py`. |
| **database.py** | Defer split; document internal sections. Future: extract `paths.py`, `config.py` if it grows. |

### Low Priority / Deprecate

| File | Recommendation |
|------|----------------|
| **email_utils.py** | Add deprecation comment; move to `scripts/` if a feature ever uses it. |
| **lan_listener.py** | Same as email_utils. |
| **debug_types.py** | Move to `scripts/debug_types.py`; document as dev-only. |

---

## 5. Migration Steps

### Phase A — Non-Breaking Cleanup (Do First)

1. **Rename ui/models.py → ui/table_models.py**
   - Update import in `ui/main_window.py`
   - No other references expected

2. **Merge theme_utils into theme**
   - Move `open_color_picker`, `validate_hex_input` into `ui/theme.py`
   - Update `theme_editor_dialog` imports
   - Delete `ui/theme_utils.py`

3. **Remove or merge theme_models**
   - If ThemeInfo is unused: delete `ui/theme_models.py`
   - If kept: move ThemeInfo into `ui/theme.py`

4. **Add deprecation notices**
   - In `email_utils.py` and `lan_listener.py`: add top-of-file note that they are unused/deprecated

### Phase B — Theme Package (Backward-Compatible)

5. **Create ui/theme/ package**
   - `ui/theme/__init__.py`: re-export everything from current theme.py, theme_storage, theme_preview
   - Move `theme.py` → `theme/core.py`
   - Move `theme_storage.py` → `theme/storage.py`
   - Move `theme_preview.py` → `theme/preview.py`
   - Move `theme_editor_dialog.py` → `theme/editor.py` (or leave in dialogs and import from theme)
   - Keep `from ui.theme import ...` working via `__init__.py`

6. **Update imports**
   - `ui/run.py`, `ui/main_window.py`, `ui/dialogs/__init__.py`: change to `from ui.theme import ...` (no change if re-exports are correct)

### Phase C — Split all_dialogs.py (Incremental)

7. **Extract one dialog at a time** (smallest first):
   - `AuditLogDialog` → `dialogs/audit_log.py`
   - `InstrumentInfoDialog` → `dialogs/instrument_info.py`
   - `CalDateDialog` → `dialogs/calibration.py` (with CalibrationHistory, CalibrationForm)
   - Continue until all 19 are split

8. **Maintain dialogs/__init__.py**
   - Import from new modules, re-export same symbols
   - `from ui.dialogs.all_dialogs import X` → `from ui.dialogs.audit_log import AuditLogDialog` etc.
   - Optional: keep `all_dialogs.py` as `_all.py` that re-exports from splits for a transition period

### Phase D — Scripts Directory (Optional)

9. **Create scripts/**
   - Move `debug_types.py`, `build_update_package.py`, `release.py`
   - Update build scripts to call `python scripts/release.py` etc.
   - Add `scripts/README.md` explaining purpose

### Order of Operations to Avoid Breakage

1. Renames and merges (Phase A) — low risk
2. Theme package (Phase B) — use re-exports to keep imports stable
3. Dialog split (Phase C) — one dialog per PR; update `dialogs/__init__.py` each time
4. Scripts (Phase D) — update only build/docs, not app imports

---

## 6. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **Import breaks after renames** | Grep for old paths; add temporary compatibility aliases in `__init__.py` |
| **PyInstaller hidden imports** | Update `.spec` or `build_executable.bat` if new packages (e.g. `ui.theme`) need `--hidden-import` |
| **Circular imports in theme** | theme → theme_storage is already lazy; preserve that in theme package |
| **Dialog split breaks wiring** | Each new dialog module must be imported in `dialogs/__init__.py`; run tests after each extract |
| **database_backup hidden import** | Build already has `--hidden-import=database_backup`; no change if database.py layout unchanged |

---

## 7. Summary

- **Immediate wins:** Rename `models.py` → `table_models.py`; merge `theme_utils`; remove or merge `theme_models`; deprecate unused modules.
- **Medium-term:** Introduce `ui/theme/` package; split `all_dialogs.py` incrementally.
- **Defer:** database.py split; services/ layer; moving update/build scripts.

*End of structural analysis.*
