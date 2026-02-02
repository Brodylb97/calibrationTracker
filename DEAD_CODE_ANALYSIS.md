# Dead Code Analysis — Calibration Tracker

*Conservative, evidence-based assessment. No code deleted; cleanup recommendations only.*

---

## 1. Summary of Overall Dead Code Health

**Assessment:** The codebase has a modest amount of dead or dormant code. Most is concentrated in a few modules. No critical persistence, migration, or configuration logic is affected.

| Category | Count | Risk |
|----------|-------|------|
| **Definitely Dead** | 3 items | Low — safe to remove after confirmation |
| **Likely Dead** | 2 items | Low — deprecate or consolidate |
| **Dormant but Valid** | 4 items | None — keep; may be used or are entry points |
| **Unused Variables** | 1 item | Trivial — one-line fix |

**Overall:** Healthy. No urgent cleanup; recommended actions are staged and low-risk.

---

## 2. Table of Suspected Dead Code

| Item | Location | Type | Classification | Evidence |
|------|----------|------|----------------|----------|
| **email_utils.py** (entire module) | Root | Module | **Definitely Dead** | No `import email_utils` or `from email_utils` anywhere. Has deprecation notice. |
| **get_backup_info()** | database_backup.py:167 | Function | **Definitely Dead** | Defined but never called. Returns backup stats (count, size, oldest, newest). |
| **DIST** variable | scripts/build_update_package.py:17 | Variable | **Definitely Dead** | Assigned `ROOT / "dist"` but never used; code uses `ROOT / "dist" / "..."` inline. |
| **lan_listener.py** (entire module) | Root | Module | **Dormant but Valid** | Not imported; run as `python lan_listener.py`. Standalone LAN reminder listener. Has deprecation notice but is a valid entry point. |
| **Instrument.to_dict()** | domain/models.py:74 | Method | **Dormant but Valid** | No callers. Intended for future use when persisting from domain models. Part of design. |
| **get_theme_colors()** | ui/theme/core.py | Function | **Likely Dead** | Exported from theme __init__ but no external caller. Used internally only via theme editor/storage. Could be used by future UI. |
| **update_custom_theme()** | ui/theme/storage.py | Function | **Likely Dead** | Wrapper for add_custom_theme; no direct caller. Theme editor uses add_custom_theme. Redundant wrapper. |
| **Theme exports (THEME_SETTINGS_KEY, FONT_SIZE_POINTS, etc.)** | ui/theme/__init__.py | Re-exports | **False Positive** | Part of public API; some may have no external consumers but support extension and scripting. Keep. |
| **test_update_url.py** | Root | Script | **Dormant but Valid** | One-off diagnostic script. Run manually to test GitHub API/raw URL fetch. Not part of test suite. |
| **update_app.py** (as module) | Root | Module | **False Positive** | Not imported; invoked as subprocess by update_checker. Used at runtime. |

---

## 3. Recommended Actions per Item

### 3.1 Definitely Dead

| Item | Action | Rationale |
|------|--------|-----------|
| **email_utils.py** | **Deprecation + safe deletion** | 1) Add `warnings.warn(DeprecationWarning, ...)` if any import is attempted. 2) After one release cycle with deprecation, delete. 3) If email reminders are planned, move to `scripts/` or feature branch instead. |
| **get_backup_info()** | **Deprecation or keep for future** | Could support a "Backup status" UI (e.g. Settings). Options: (a) Add deprecation docstring + `# TODO: Used by Settings backup tab when implemented`, or (b) Remove if no such feature is planned. **Recommend (a)** — low cost to keep. |
| **DIST** variable | **Safe deletion** | Remove line 17 in `scripts/build_update_package.py`. Use `ROOT / "dist"` inline where needed, or keep `DIST` and use it in the two existence checks (lines 36, 39) for consistency. **Recommend:** Use DIST in those checks and remove redundant `ROOT / "dist"` construction. |

### 3.2 Likely Dead

| Item | Action | Rationale |
|------|--------|-----------|
| **get_theme_colors()** | **Keep** | Small; useful for validation/extension. No maintenance cost. |
| **update_custom_theme()** | **Consolidation** | Either (a) deprecate and have callers use add_custom_theme, or (b) keep as semantic alias. **Recommend (b)** — clear naming for "update existing" vs "add or update." |

### 3.3 Dormant but Valid — No Action

| Item | Action |
|------|--------|
| **lan_listener.py** | Keep. Remove "DEPRECATED" from comment; clarify it is a standalone script. Run via `python lan_listener.py` for sites that want a listener. |
| **Instrument.to_dict()** | Keep. Part of domain model design for future persistence. |
| **test_update_url.py** | Keep. Document as dev/diagnostic script in README or scripts/README. |

---

## 4. Cleanup Order and Rationale

**Stage 1 — Zero-risk (do first)**  
1. **DIST variable**: Use it in `build_update_package.py` or remove it. One-line change.

**Stage 2 — Low-risk, high confidence**  
2. **get_backup_info()**: Add a docstring/comment that it is reserved for future backup-status UI. No code change beyond documentation.

**Stage 3 — Requires product decision**  
3. **email_utils.py**: Decide whether email reminders are planned.  
   - If **yes**: Move to `scripts/` or `features/email_reminders/` and document.  
   - If **no**: Add deprecation warning, then delete after one release.

**Stage 4 — Optional**  
4. **lan_listener.py** comment: Replace "DEPRECATED" with "Standalone script — run via `python lan_listener.py`" to avoid confusion.

---

## 5. Risks and Mitigation Strategies

| Risk | Mitigation |
|------|------------|
| **Deleting email_utils breaks future feature** | Move to scripts/ or archive branch instead of delete, if email reminders might be implemented. |
| **get_backup_info() used by undocumented script/tool** | Grep for `get_backup_info` before removal; add integration test if a backup-status UI is added. |
| **Qt auto-connections or dynamic references** | No Qt .ui files; no `connect()` by string name found. Static analysis is reliable for this codebase. |
| **Configuration keys read indirectly** | QSettings keys (theme, font_size) are read via get_saved_theme, get_saved_font_size. No orphaned keys identified. |

---

## 6. Items Explicitly NOT Recommended for Removal

- **Persistence, migrations, audit:** All used; do not touch.
- **database_backup.py** (except get_backup_info): backup_database, verify_backup, cleanup_old_backups, perform_daily_backup_if_needed — all used.
- **tolerance_service.py:** All functions used by dialogs and pdf_export.
- **update_checker.py, update_app.py:** Used at runtime for in-app updates.
- **crash_log.py:** Used by main.py.
- **Theme package:** Re-exports support API stability; pruning not recommended.
- **domain.models.Instrument:** Core model; to_dict is part of the design even if unused today.

---

## 7. Verification Commands

Before any deletion, run:

```bash
# Confirm no references to email_utils
rg "email_utils" --type py

# Confirm no references to get_backup_info
rg "get_backup_info" --type py

# Run existing tests
python -m pytest test_tolerance_service.py -v
python test_tolerance_service.py
```

---

*End of dead code analysis.*
