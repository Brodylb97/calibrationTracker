# Calibration Tracker — ISO/IEC 17025:2017 Improvement Plan

**Purpose:** Incremental, low-risk improvements for usability, robustness, and accreditation readiness.  
**Stack (as implemented):** Python, **PyQt5** (not Tkinter), SQLite, ReportLab PDF, LAN UDP, PyInstaller.  
**Design goals:** Audit defensibility, operator speed, long-term maintainability.

---

## Executive Summary

The application already has: instruments, calibration records with templates, audit log (instrument + calibration), daily backups, LAN reminders, PDF export, update checker, and search/filter on the main table. Gaps relative to ISO 17025 and your objectives are addressed below with **High / Medium / Later** priorities and concrete file- and schema-level steps.

**Immediate fix:** Database `instruments.status` CHECK allows `ACTIVE`, `RETIRED`, `INACTIVE` but the UI uses `OUT_FOR_CAL`. Align schema and UI (see § Database schema changes).

---

## 1. Prioritized Improvement List

### High (audit-critical, data integrity, quick wins)

| # | Area | Improvement | Relevant clause |
|---|------|-------------|----------------|
| H1 | Data integrity | Wrap all multi-step DB operations in explicit transactions; add startup integrity check (e.g. PRAGMA integrity_check) | 7.11, 8.5 |
| H2 | Record control | Add record state (Draft → Reviewed → Approved → Archived); lock Approved/Archived as read-only | 7.5, 7.11 |
| H3 | Change management | Extend audit_log with mandatory “reason” field for changes; log who/what/when/why on instrument and calibration updates | 7.11, 8.4 |
| H4 | Delete behavior | Replace hard deletes with soft-delete/archive (e.g. `deleted_at`, `deleted_by`) for instruments and calibration records | 7.11, 8.6 |
| H5 | Backup | Add backup verification (e.g. open backup DB and run integrity_check); optional “recover from backup” prompt on crash detection | 8.5, 8.6 |
| H6 | Status alignment | Fix instruments.status: allow `OUT_FOR_CAL` in schema (migration) and keep UI as-is, or map UI to INACTIVE; document choice | 6.4 |

### Medium (workflow, traceability, reporting)

| # | Area | Improvement | Relevant clause |
|---|------|-------------|----------------|
| M1 | UX – Needs Attention | “Needs Attention” dashboard/section: overdue, due soon, recently modified, records blocked by compliance (e.g. no method) | 7.1, 7.5, 7.11 |
| M2 | UX – Bulk actions | Multi-select instruments; batch update (e.g. next_due_date, status); batch closeout where applicable | 7.1, 7.5 |
| M3 | UX – Modals | Replace non-critical modal dialogs with inline warnings/banners where possible (e.g. validation messages) | 7.1 |
| M4 | Search | Fuzzy search across instruments, serial numbers, procedures (templates), owners, due dates (e.g. rapidfuzz or simple scoring) | 7.5 |
| M5 | Traceability | Data model: reference standards, parent–child links; certificate (ID, lab, accreditation body, expiry); uncertainty + method ref; env conditions per calibration | 6.5, 6.6, 7.6 |
| M6 | Method control | Controlled procedures: procedure_id, revision, effective_date, status (Validated/Verified/Under development); evidence attachments; block approval without authorized method | 7.2, 7.7 |
| M7 | Personnel | Lightweight personnel: name, role, qualifications, authorized procedures, review/expiry; link calibrations to performed_by/reviewed_by/approved_by | 6.2 |
| M8 | Equipment status | Instrument/standard status: In service, Out of service, Under investigation, Retired; enforce use restrictions (e.g. no use of expired standards) | 6.4, 6.5, 7.6 |
| M9 | Reporting | Export presets (internal review, external audit, customer); batch PDF; CSV/Excel; ISO-style certificate (method, uncertainty, traceability); scope warning | 7.8, 8.9 |
| M10 | Notifications | Configurable reminder lead times by equipment type; escalation (Reminder → Warning → Overdue); LAN retry + failure log; optional quiet hours | 7.7, 8.5 |

### Later (defer without blocking accreditation)

| # | Area | Improvement | Relevant clause |
|---|------|-------------|----------------|
| L1 | Nonconformance | Nonconformance records, link to calibrations/equipment, root cause, corrective actions, effectiveness, trends | 7.10, 8.7 |
| L2 | Retention | Configurable retention periods; archive instead of delete; retention report | 7.5, 7.11 |
| L3 | Audit package | One-click audit package export (date range, records, logs, traceability, summaries) | 8.9 |
| L4 | Risk automation | Drift trend warnings, early review suggestions | 8.5 |
| L5 | Codebase | Extract validation/business rules from UI; centralize logging/errors; type hints; smaller modules | 8.2, 8.4 |

---

## 2. Module- and File-Level Recommendations

### 2.1 `database.py`

- **Transactions:** For every multi-step operation (e.g. `create_calibration_record`, `update_calibration_record`, `delete_instrument`, `delete_calibration_record`), use:
  - `conn.execute("BEGIN")` at start,
  - `conn.commit()` on success,
  - `conn.rollback()` in except, then re-raise.
- **Integrity:** In `initialize_db` (or a new `check_integrity()`), run `PRAGMA integrity_check` and surface failure at startup (e.g. log + optional dialog).
- **Audit “reason”:** Extend `log_audit(..., reason: str | None = None)`. Add column `reason TEXT` to `audit_log` via migration. All update/delete paths that call `log_audit` should require (or strongly encourage) a reason from the UI.
- **Soft delete:** Add `deleted_at TEXT`, `deleted_by TEXT` to `instruments` and `calibration_records`; in repository, replace DELETE with UPDATE setting these; add filters in list methods to exclude deleted by default; add “Show archived” toggle and an “Archive” action instead of Delete.
- **Status:** Migration to allow `OUT_FOR_CAL` in `instruments.status` CHECK (see § Database schema changes).

### 2.2 `ui_main.py`

- **Size:** File is very large (~4.8k lines). Prefer extracting dialogs into separate modules (e.g. `ui_dialogs_instrument.py`, `ui_dialogs_calibration.py`, `ui_dialogs_settings.py`) over time; start with one or two dialogs to establish the pattern.
- **Validation:** Centralize repeated validation patterns (e.g. required fields, date order) in a small `validation.py` or in repository helpers; call from dialogs to avoid duplication.
- **Record state:** When record states exist, show state (Draft/Reviewed/Approved/Archived) in calibration history and instrument detail; disable edit/delete for Approved/Archived and show inline banner instead of modal where possible.
- **Needs Attention:** Add a dedicated widget or top panel: query overdue, due-soon, recently modified (e.g. `updated_at` last 7 days), and (later) “blocked” (e.g. no method). Link each to the main table selection/filter.
- **Bulk actions:** Switch main table to `SelectRows` + `ExtendedSelection` or `MultiSelection`; add toolbar/menu “Batch update…” (e.g. status, next_due_date) and “Batch closeout” that iterate selected IDs and call repository within a single transaction.
- **Keyboard shortcuts:** Keep F1 (shortcuts), Ctrl+F (search). Add e.g. Ctrl+N (new instrument), Ctrl+E (edit), Enter (open), Delete (delete with confirmation) if not already present.
- **Modals:** For non-fatal validation (e.g. “ID is required”), consider inline label or tooltip next to field instead of QMessageBox; reserve modals for destructive or irreversible actions.

### 2.3 `database_backup.py`

- **Verification:** After `backup_conn.backup()` (or fallback copy), open the backup file, run `PRAGMA integrity_check`, and log failure; optionally return a boolean “verified.”
- **Crash recovery:** In `main.py` or startup, if a “crash” flag file exists (e.g. written on startup, removed on normal exit), show a short “Recover from backup?” prompt and optionally open latest backup or run integrity check on main DB.

### 2.4 `pdf_export.py`

- **Certificate content:** When traceability/uncertainty tables exist, add sections for method reference, measurement uncertainty, traceability statement; add a simple “Accreditation scope” warning if calibration type or scope is outside a configured scope.
- **Export presets:** Add a thin layer (or config) that defines “Internal review,” “External audit,” “Customer” with different PDF options (e.g. include/exclude attachments, summary page); batch PDF already exists; extend to CSV/Excel export.

### 2.5 `lan_notify.py` / `lan_listener.py`

- **Retry:** In `send_lan_broadcast`, retry N times with short delay on failure; log failures.
- **Quiet hours:** In settings, store optional “quiet start”/“quiet end” times; in listener, do not show popup if current time in range (still log).
- **Lead time:** Store reminder lead time per instrument type (or global); `get_due_instruments(reminder_days)` could take type-specific windows from settings/database.

### 2.6 `crash_log.py`

- **Levels:** Use `logger.debug()` for developer-only details and `logger.info()`/`error()` for operations; avoid logging sensitive data.
- **User-facing errors:** Where the app shows a message to the user (e.g. “Database read-only”), use a single helper (e.g. `user_message.warning(title, text)`) so that user-facing text is consistent and can be separated from technical logs.

### 2.7 New modules (suggested)

- **`migrations.py`:** Run-once schema migrations (add columns, add tables, change CHECKs) with a simple `schema_version` table and version number; call from `initialize_db` after core schema.
- **`validation.py`:** Shared rules (required fields, date ranges, tolerance checks) used by UI and optionally by repository.
- **`traceability.py`** (later): Models and DB helpers for standards, certificates, uncertainty, env conditions.

---

## 3. Database Schema Changes & Migration Strategy

### 3.1 Strategy

- Use a **schema_version** table: `CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);` and set `version = N` after each migration.
- In `initialize_db`, after `_initialize_db_core`, run a **migration runner** that checks `schema_version` and applies pending migrations in order (e.g. `migrate_1()`, `migrate_2()`, …).
- Each migration is a function that takes `conn` and performs one logical change; it updates `schema_version` at the end. No dropping of columns that might contain data; only ADD COLUMN, CREATE TABLE, and careful CHECK changes.

### 3.2 Immediate migration (version 1)

- **Instruments status:** SQLite does not allow altering CHECK. Options:
  - **A:** Create new table `instruments_new` with CHECK including `OUT_FOR_CAL`, copy data (map existing `INACTIVE` to `INACTIVE` or `OUT_FOR_CAL` per policy), drop old table, rename new. Or add a trigger to enforce allowed values and leave CHECK as-is if you prefer to keep `INACTIVE` and map “Out for cal” in UI to `INACTIVE` with a label.
  - **B (simplest):** Add a migration that creates a new table with `CHECK (status IN ('ACTIVE', 'RETIRED', 'INACTIVE', 'OUT_FOR_CAL'))`, copy data, drop `instruments`, rename. Recreate indexes and foreign keys.
- **audit_log reason:** `ALTER TABLE audit_log ADD COLUMN reason TEXT;`
- **schema_version:** `INSERT INTO schema_version (version) VALUES (1);`

### 3.3 Soft delete (version 2)

- **instruments:** `ALTER TABLE instruments ADD COLUMN deleted_at TEXT;` `ALTER TABLE instruments ADD COLUMN deleted_by TEXT;`
- **calibration_records:** Same.
- **Repository:** In `list_instruments` and `list_calibration_records_*`, add `WHERE deleted_at IS NULL` unless “show archived” is requested. New methods: `archive_instrument(id, by, reason)`, `archive_calibration_record(id, by, reason)` (set deleted_at, deleted_by, and log_audit with reason).

### 3.4 Record state (version 3)

- **calibration_records:**  
  `ALTER TABLE calibration_records ADD COLUMN record_state TEXT DEFAULT 'Draft' CHECK (record_state IN ('Draft','Reviewed','Approved','Archived'));`  
  `ALTER TABLE calibration_records ADD COLUMN reviewed_by TEXT;`  
  `ALTER TABLE calibration_records ADD COLUMN reviewed_at TEXT;`  
  `ALTER TABLE calibration_records ADD COLUMN approved_by TEXT;`  
  `ALTER TABLE calibration_records ADD COLUMN approved_at TEXT;`
- **UI:** Show state; prevent edit/delete when state is Approved or Archived; allow “Review” / “Approve” actions with audit log and optional reason.

### 3.5 Traceability & certificates (later versions)

- New tables (conceptual): **reference_standards** (id, instrument_id or link to equipment, parent_standard_id, certificate_id, …), **certificates** (id, certificate_id, issuing_lab, accreditation_body, expiry_date, …), **calibration_uncertainty** (record_id, value, method_or_ref, …), **calibration_env_conditions** (record_id, temperature, humidity, pressure, …). Link to `calibration_records` and instruments via FKs. Migrations add these and any new columns on existing tables.

### 3.6 Procedures & personnel (later)

- **procedures:** procedure_id, revision, effective_date, status (Validated/Verified/Under development), link to template or instrument type; **personnel:** name, role, qualifications, authorized_procedures, review_expiry; **calibration_records:** performed_by_id, reviewed_by_id, approved_by_id (FK to personnel if you add a personnel table).

---

## 4. UX Adjustments to Reduce Operator Error

- **Smart defaults:** Pre-fill next_due_date from last_cal_date + frequency; default “Performed by” from settings operator_name; default template from instrument type’s active template.
- **Inline validation:** Required-field and format checks on blur or on Save, with inline message (e.g. red label or tooltip) instead of blocking modal where appropriate.
- **Bulk actions:** Multi-select + “Update due date” / “Mark calibrated” / “Change status” to reduce repetitive one-by-one edits.
- **Needs Attention:** Single place to see what’s overdue, due soon, or recently changed so operators don’t miss items.
- **Record state visible:** Always show Draft/Reviewed/Approved/Archived so operators know what can be edited and what is locked.
- **Approval gate:** “Approve” only when method is authorized and (if you add it) traceability/uncertainty are present; show clear reason when approval is blocked.
- **Keyboard shortcuts:** Consistent shortcuts (e.g. Ctrl+N, Ctrl+E, Enter, F1, Ctrl+F) reduce reliance on mouse and speed up frequent actions.

---

## 5. Design Principles

- **Audit defensibility:** Every change to controlled data is logged (who, what, when, why); approved records are immutable; corrections are versioned; backups are verified.
- **Operator speed:** Fewer clicks (bulk actions, smart defaults), less interruption (inline warnings, banners), quick access (shortcuts, Needs Attention).
- **Long-term maintainability:** Small, focused modules; shared validation and logging; schema versioning and non-destructive migrations; no full rewrites.

---

## 6. Implementation Order Suggestion

1. **Week 1:** Schema version + migration 1 (status fix, audit reason); transactions in `database.py`; startup integrity check.
2. **Week 2:** Soft delete (migration 2 + repository + UI “Archive” and “Show archived”).
3. **Week 3:** Record state (migration 3 + UI state display + lock Approved/Archived).
4. **Week 4:** Needs Attention panel; optional bulk multi-select + one batch action.
5. **Ongoing:** Traceability/model changes, method control, personnel, reporting enhancements, LAN/notification improvements, then nonconformance and audit package.

This plan keeps the current architecture and stack, avoids rewrites, and aligns improvements with ISO/IEC 17025:2017 clauses while improving day-to-day usability and audit readiness.
