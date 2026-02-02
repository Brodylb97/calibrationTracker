# Calibration Tracker: Architecture & Improvement Proposal

*Generated: 2025-01-30*

---

## Section 1: High-Level Assessment

### What's Working Well

- **Single source of truth for tolerance logic** (`tolerance_service.py`) — clean, AST-based equation parsing, no `eval()`, well-tested.
- **Schema migrations** (`migrations.py`) — versioned, ordered migrations; schema version table.
- **Audit logging** — `log_audit()` called for instrument and calibration changes; `audit_log` with entity_type, action, field, old/new values, actor, reason.
- **Crash handling** — global excepthook, crash flag, recovery dialog.
- **Database backup** — daily backup via `database_backup.py` with SQLite backup API and integrity verification.
- **Cursor rules, patterns, anti-patterns** — explicit guidance for maintainability, data integrity, and threading.
- **Server-only database policy** — `is_server_db_path()` enforces no local copies; read-only retry loop in `main.py`.
- **Template system** — flexible fields, tolerance types (fixed, percent, equation, lookup, bool), computed fields, versioning.

### What's Risky

| Risk | Location | Description |
|------|----------|-------------|
| **Monolithic UI** | `ui_main.py` (~7000 lines) | All dialogs, MainWindow, models, themes, help content in one file. 114+ direct `repo.*` calls in callbacks. Hard to navigate and test. |
| **In-place calibration edits** | `database.update_calibration_record()` | Deletes `calibration_values` and re-inserts. Violates Cursor Pattern 2 (revisioning, superseded records). No audit of field-level changes. |
| **Raw dicts everywhere** | `database.py`, `ui_main.py` | Rules require dataclasses/Pydantic. Dict access via string keys is brittle and undocumented. |
| **Blocking UI thread** | `ui_main.on_export_all_calibrations`, `send_due_reminders_via_lan` | Long operations run synchronously. Progress dialog is shown but `export_all_calibrations_to_directory()` blocks. |
| **Global mutable state** | `database._effective_db_path` | Module-level `_effective_db_path` mutated by `get_connection()`. |
| **Silent failures** | `persist_last_db_path()`, `_crash_flag_write()` | `except Exception: pass` — user never knows if last-DB path persistence failed. |
| **Hard-coded server path** | `database.SERVER_DB_PATH` | `Z:\Shared\Laboratory\...` is embedded. Deployment to different environments requires code change. |
| **Mixed concerns in dialogs** | `CalibrationFormDialog`, `TemplatesDialog` | Dialogs contain validation, persistence calls, and rendering. Anti-pattern per rules. |

---

## Section 2: Top 5 Structural Improvements (Ranked by Impact)

### 1. Extract UI into modules (ui/, dialogs/, models/)

**Impact: High** — Enables incremental refactoring and clearer boundaries.

**Current:** Single ~7000-line `ui_main.py`.

**Proposed steps:**
1. Create `ui/` with `main_window.py`, `dialogs/` (instrument, calibration, template, settings, etc.), `models/` (InstrumentTableModel, FilterProxy).
2. Move one dialog at a time (e.g. `InstrumentDialog` → `ui/dialogs/instrument_dialog.py`).
3. Keep `ui_main.py` as thin `run_gui()` entry point that imports and wires.

**Files affected:** `ui_main.py` → split into 10–15 modules. `main.py` import path unchanged.

---

### 2. Introduce domain models (dataclasses) for cross-layer data ✅ *Done*

**Impact: High** — Reduces bugs, documents intent, aligns with Cursor rules.

**Current:** `get_instrument()` returns `dict`; UI and persistence pass dicts.

**Implemented:** `domain/models.py` with `Instrument` dataclass; `get_instrument()` returns `Instrument | None`. Compatible `.get()` and `__getitem__` for gradual migration. MainWindow and pdf_export updated to use attributes. Remaining: `CalibrationRecord`, `CalibrationValue` (deferred).

**Original proposed steps:**
1. Add `domain/models.py` with `Instrument`, `CalibrationRecord`, `CalibrationValue` (dataclasses).
2. Repository methods return models; callers receive typed objects.
3. Conversion from `sqlite3.Row`/dict happens at repository boundary only.

**Example (before/after in Section 6).**

---

### 3. Add a thin service layer between UI and persistence

**Impact: Medium–High** — Separates orchestration from storage; enables validation and audit at one place.

**Current:** UI calls `repo.add_instrument()`, `repo.update_calibration_record()` directly.

**Proposed steps:**
1. Create `services/instrument_service.py`, `services/calibration_service.py`.
2. Services: validate input, call repo, log audit, return success/failure.
3. UI calls services only; no direct repo in dialogs.

**Benefit:** Central place for "add instrument" / "edit calibration" rules; easier to add pre/post hooks.

---

### 4. Move long-running operations off the UI thread

**Impact: Medium** — Prevents perceived freezing during export, LAN reminders, bulk operations.

**Current:** `export_all_calibrations_to_directory()` and `send_due_reminders_via_lan()` run on main thread.

**Proposed steps:**
1. Add `QThread` (or `QRunnable` + `QThreadPool`) wrapper for export.
2. Emit progress (e.g. `signals.progress(int, int)`) and final result.
3. MainWindow connects signals; disables export button during run; re-enables on done/error.
4. Apply same pattern to "Send reminders" if it can block (e.g. slow network).

---

### 5. Make database path configurable ✅ *Done*

**Impact: Medium** — Supports different environments (dev, staging, other sites).

**Current:** `SERVER_DB_PATH` hard-coded in `database.py`.

**Implemented:** Config loading in `database.py` — `config.json`, `update_config.json`, or `CALIBRATION_TRACKER_DB_PATH` env var. `config.example.json` and docs in README, USER_GUIDE, Troubleshooting.

**Original proposed steps:**
1. Read from `update_config.json` or new `config.json` (e.g. `db_path` key).
2. Fall back to `SERVER_DB_PATH` if not set.
3. Validate with `is_server_db_path()` or relax that check if multi-site is desired.
4. Document in README and USER_GUIDE.

---

## Section 3: Top 5 UX Improvements (Ranked by User Value)

### 1. Add confirmation for destructive actions with undo hint

**Current:** Delete instrument asks "Are you sure?" and for reason. No mention of archive option.

**Improvement:** For delete: "This permanently removes the instrument and all calibration history. Consider archiving instead (Status → Retired) to preserve history. Proceed with permanent delete?"

**Location:** `MainWindow.on_delete()` in `ui_main.py`.

---

### 2. Improve progress feedback for bulk export

**Current:** Indeterminate progress bar ("Exporting calibrations..."); no cancel; UI blocked.

**Improvement:**
- Show determinate progress (e.g. "Exporting 15/120...") when run in background thread.
- Add Cancel that stops export gracefully and reports partial success.
- Optionally disable menu/buttons during export.

**Location:** `on_export_all_calibrations`, `on_export_calibrations_to_folder`.

---

### 3. Surface validation errors in-context

**Current:** Many dialogs use `QMessageBox.warning(self, "Validation", "ID is required.")` — generic, modal.

**Improvement:**
- For required fields: show red outline or inline label next to the field.
- Keep modal only for critical/blocking errors.
- Summarize multiple validation errors in one dialog when submitting.

**Location:** `InstrumentDialog`, `CalibrationFormDialog`, `FieldEditDialog`, etc.

---

### 4. Clear success feedback after save

**Current:** Status bar shows "Instrument updated successfully" for 3 seconds. Easy to miss.

**Improvement:**
- Brief, non-intrusive toast or highlighted status message.
- For calibration form: explicit "Saved" checkmark or flash on Save button.
- Ensure status bar message is visible (some themes may hide it).

---

### 5. Warn before overwriting existing export file

**Current:** CSV/Excel export uses `QFileDialog.getSaveFileName`; overwrite behavior depends on OS. PDF single export may overwrite.

**Improvement:** Before writing, check if file exists. If so: "File already exists. Overwrite?" with Yes/No/Cancel. Align with Cursor Pattern 4 (File Export).

**Location:** `on_export_csv`, `on_export_excel`, single-record PDF export path.

---

## Section 4: Quick Wins (Low Effort, High Payoff) ✅ *Done*

| Task | Effort | Impact | Where |
|------|--------|--------|-------|
| Log `persist_last_db_path` failures | ~5 min | Visibility into config write issues | `database.py` |
| Add overwrite confirmation for CSV/Excel export | ~15 min | Prevents accidental overwrite | `ui/main_window.py` `on_export_csv`, `on_export_excel` |
| Disable "Send reminders" button while sending | ~10 min | Avoids double-send; shows busy state | `MainWindow.on_send_reminders` |
| Add `archive_instrument` option to delete flow | ~30 min | Preserves history; matches soft-delete pattern | `on_delete`, "Archive instead" button |
| Surface schema migration errors to user | ~20 min | User knows if DB is incompatible | `database.initialize_db`, `main.py` |

---

## Section 5: Deferred Improvements (Good Ideas, Not Urgent)

- **Import flow (CSV/Excel → instruments):** Not present; add when needed. Follow Pattern 3 (validate → parse → persist atomically).
- **Dataclass migration:** Do incrementally when touching a given entity (instruments first, then templates, then calibration records).
- **Full ui/ split:** Can be done in phases; start with dialogs that change least.
- **Connection pooling / reconnect UI:** Current single-connection model is fine for single-user; revisit if multi-user or long-lived sessions become a requirement.
- **Pydantic for validation:** Stronger than dataclasses but adds dependency; consider only if validation complexity grows.
- **Automated tests for UI flows:** Would require test framework (pytest-qt or similar); lower priority than unit tests for `tolerance_service` and repository.

---

## Section 6: Example Refactor — Before/After

### Scenario: Replace raw dict with Instrument dataclass at repository boundary ✅ *Implemented*

**See:** `domain/models.py`, `database.get_instrument`, `ui/main_window.py`, `pdf_export.py`

**Before (original):**

```python
# database.py
def get_instrument(self, instrument_id: int):
    cur = self.conn.execute(...)
    row = cur.fetchone()
    return dict(row) if row else None

# Caller
inst = self.repo.get_instrument(inst_id)
tag = inst.get("tag_number", str(inst_id))  # KeyError if typo; None handling scattered
```

**After (current):**

```python
# domain/models.py
@dataclass
class Instrument:
    id: int
    tag_number: str
    # ... all fields
    def get(self, key: str, default=None): ...   # backward compatibility
    def __getitem__(self, key: str): ...
    @classmethod
    def from_row(cls, row) -> "Instrument": ...

# database.py
def get_instrument(self, instrument_id: int) -> Instrument | None:
    ...
    return Instrument.from_row(row) if row else None

# Caller (e.g. ui/main_window.py)
inst = self.repo.get_instrument(inst_id)
if inst:
    tag = inst.tag_number  # Typed; IDE autocomplete
```

**Why this helps:**
- `Instrument` documents the shape of the data.
- Typo `tag_numer` fails at attribute access instead of returning `None`.
- UI code is simpler: `inst.tag_number` instead of `inst.get("tag_number", "")`.
- `.get()` and `__getitem__` allow gradual migration of existing callers.

---

## Summary Table

| Priority | Improvement | Effort | Impact |
|----------|-------------|--------|--------|
| P0 | Log persist_last_db_path failures ✅ | S | M |
| P0 | Overwrite confirmation for exports ✅ | S | M |
| P1 | Extract UI into modules | L | H |
| P1 | Domain models (dataclasses) | M | H |
| P1 | Service layer | M | M–H |
| P2 | Move export to background thread | M | M |
| P2 | Configurable DB path | S | M |
| P2 | Destructive action confirmations | S | M |
| P3 | In-context validation | M | M |
| P3 | Revisioning for calibration edits | L | H (data integrity) |

---

*End of proposal.*
