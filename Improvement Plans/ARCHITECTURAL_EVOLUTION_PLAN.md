# Calibration Tracker — Architectural Evolution Plan

*Disciplined architectural maturation. No rewrites. Incremental, low-risk changes.*

---

## 1. Ideal Target Architecture

### 1.1 Text Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              main.py (entry)                                 │
│  Bootstrap: config → connection → repo → run_gui(repo)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           UI LAYER (ui/)                                     │
│  main_window.py, dialogs/*, table_models.py, theme/, help_content.py         │
│  Responsibility: Presentation, user input, display. No persistence calls.   │
│  Depends on: services (orchestration), domain (read-only models)             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SERVICES LAYER (services/)                             │
│  instrument_service, calibration_service, template_service, ...              │
│  Responsibility: Orchestration, validation, audit, conflict handling.        │
│  Depends on: persistence (repository), domain (models)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOMAIN LAYER (domain/)                             │
│  models.py: Instrument, CalibrationRecord, Template, Field, ...              │
│  Responsibility: Typed data shapes, business rules (pure).                   │
│  Depends on: nothing (pure)                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PERSISTENCE LAYER (persistence/)                         │
│  repository.py: CalibrationRepository (CRUD, queries)                        │
│  connection.py: get_connection, config loading                               │
│  migrations.py: schema versioning (unchanged)                                │
│  Responsibility: Storage, schema, connection. No business logic.             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONFIGURATION (config/)                               │
│  config.py: load_db_path(), load_app_config()                                │
│  Sources: env, config.json, update_config.json, defaults                    │
│  Responsibility: Single place for runtime config. No business logic.        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
User action → UI → Service (validate, orchestrate) → Repository (persist) → DB
                → Repository (read) → Service (optional transform) → UI
```

- **Reads:** UI may call repository directly for simple reads (e.g. list instruments) when no orchestration is needed. Services own writes and complex orchestration.
- **Writes:** UI → Service → Repository. Service validates, logs audit, handles conflicts.

### 1.3 Ownership Model

| Entity | Write Authority | Read Authority |
|--------|-----------------|----------------|
| Instrument | instrument_service | UI, repo |
| Calibration record | calibration_service | UI, repo |
| Template | template_service (future) | UI, repo |
| Config | config module | All modules |

### 1.4 Future Server-Backed Mode (Not Implemented)

- **Today:** Single SQLite file on network share. One writer at a time.
- **Future:** Server is authoritative. Clients sync via API or polling. Local cache for offline.
- **Design:** Repository interface stays; implementation can swap `SqliteRepository` → `ApiRepository` behind a facade. No change to UI or services if interface is stable.

### 1.5 User Identity and Audit (Future)

- **Today:** `audit_log.actor` is often empty or "system".
- **Future:** `config.current_user_id` or login session; services pass `actor` to `log_audit()`.
- **Design:** Services already accept `actor`/`reason`; add config/session layer when multi-user is needed.

---

## 2. Architectural Principles Being Enforced

1. **Single responsibility per module** — One module does one thing.
2. **Dependency direction** — UI → Services → Domain; Persistence → Domain; Config → all. No cycles.
3. **Write boundary** — All writes go through services. No UI → Repository direct writes.
4. **Repository at boundary** — Conversion from sqlite3.Row/dict to domain models happens only in repository.
5. **Config centralization** — All runtime config (db_path, paths, feature flags) comes from one config module.
6. **No framework creep** — PyQt5, SQLite, stdlib. No new frameworks.
7. **Local-first preserved** — Architecture supports server-backed mode without breaking local-only.

---

## 3. Current → Target Mapping Analysis

### 3.1 Mapping Table

| Current | Target | Status |
|---------|--------|--------|
| `main.py` | Entry, bootstrap | ✅ Aligned |
| `ui_main.py` | Thin shim for `run_gui` | ✅ Aligned |
| `ui/run.py` | run_gui, wires repo | ✅ Aligned |
| `ui/main_window.py` | MainWindow | ⚠️ Partial: passes repo to dialogs; some direct repo calls |
| `ui/dialogs/all_dialogs.py` | 14+ dialogs | ❌ Monolithic; ~5000 lines; direct repo calls |
| `ui/dialogs/*.py` (audit_log, batch, instrument_info) | Small dialogs | ✅ Aligned |
| `ui/table_models.py` | UI models | ✅ Aligned |
| `ui/theme/core.py` | Theme | ✅ Aligned |
| `ui/help_content.py` | Help | ✅ Aligned |
| `services/instrument_service.py` | Instrument orchestration | ✅ Aligned |
| `services/calibration_service.py` | Calibration orchestration | ✅ Aligned |
| `domain/models.py` | Instrument dataclass | ⚠️ Partial: CalibrationRecord, Template not yet |
| `database.py` | Repository + config + connection + schema | ❌ Mixed; should split |
| `migrations.py` | Schema migrations | ✅ Aligned |
| `database_backup.py` | Backup | ✅ Aligned |
| `tolerance_service.py` | Domain logic (pure) | ✅ Aligned |
| `pdf_export.py` | Export (reads repo) | ⚠️ Partial: acceptable; could use service for consistency |
| `config.json`, `update_config.json` | Config sources | ⚠️ Loaded in database.py; should be config module |

### 3.2 Files Requiring No Change

- `main.py` — Entry, crash recovery, DB init
- `ui_main.py` — Shim
- `ui/run.py` — run_gui
- `ui/table_models.py` — Table models
- `ui/theme/core.py`, `ui/theme/storage.py` — Theme
- `ui/help_content.py` — Help
- `migrations.py` — Schema migrations
- `database_backup.py` — Backup
- `tolerance_service.py` — Domain logic
- `crash_log.py` — Excepthook
- `file_utils.py` — Utilities

### 3.3 Files Requiring Movement

| File | Action |
|------|--------|
| Config loading from `database.py` | Extract to `config/` or `config.py` |
| `CalibrationRepository` | Keep in `database.py` for now; optional rename to `persistence/repository.py` later |

### 3.4 Files Requiring Boundary Tightening

| File | Issue | Fix |
|------|-------|-----|
| `ui/dialogs/all_dialogs.py` | 14 classes, 92+ repo calls | Split into one file per dialog; route writes through services |
| `ui/main_window.py` | 19 direct repo calls | Route writes through instrument_service; reads can stay |
| `database.py` | Config + connection + repository + schema | Extract config; keep rest together initially |

---

## 4. Structural Misalignment Summary

### 4.1 Critical Violations

1. **UI → Repository direct writes** — ~100+ calls in UI. Services exist for instrument add/update and calibration create/update; most other operations (template, destination, personnel, batch) bypass services.
2. **Monolithic all_dialogs.py** — 14 dialog classes, ~5000 lines. Single file churn risk; hard to test.
3. **Config in database.py** — `_load_configured_db_path()` lives in persistence module. Config belongs in a separate module.

### 4.2 Moderate Violations

4. **Domain models incomplete** — Only `Instrument` is a dataclass. CalibrationRecord, Template, Field, etc. remain dicts.
5. **Repository returns mixed types** — Some methods return `Instrument`, others return dict. Inconsistent boundary.

### 4.3 Minor Violations

6. **Global mutable state** — `database._effective_db_path` mutated by `get_connection()`. Acceptable for single-user; document for future.
7. **Root-level sprawl** — Many modules at root. Acceptable; no urgent need to nest.

---

## 5. Staged Migration Roadmap

### Stage 1: Extract Config (Low Risk)

**Objective:** Move DB path and app config loading out of `database.py` into a dedicated config module.

**Files affected:** New `config.py`, `database.py`

**Steps:**
1. Create `config.py` with `load_db_path()`, `get_app_config()`.
2. `database.py` imports `config.load_db_path()` instead of defining `_load_configured_db_path()`.
3. Remove config logic from `database.py`; keep `get_connection()`, `DB_PATH` as re-exports.

**Risk:** Low. Config is read at startup; no behavior change.

**Verification:** Run app; connect to DB; verify config.json and env still work.

**Rollback:** Revert config.py; restore `_load_configured_db_path()` in database.py.

---

### Stage 2: Route Remaining UI Writes Through Services (Medium Risk)

**Objective:** Add template_service, destination_service, personnel_service; route all UI writes through services.

**Files affected:** New `services/template_service.py`, `services/destination_service.py`, `services/personnel_service.py`; `ui/dialogs/all_dialogs.py`, `ui/main_window.py`

**Steps:**
1. Create thin services that validate and delegate to repo (same pattern as instrument_service).
2. One dialog at a time: replace `repo.update_template(...)` with `template_service.update_template(repo, ...)`.
3. No UI logic changes; only call path.

**Risk:** Medium. Many call sites; careful search and replace.

**Verification:** Run app; add/edit/delete template, destination, personnel; verify audit log entries.

**Rollback:** Revert service additions; restore direct repo calls.

---

### Stage 3: Split all_dialogs.py (Medium Risk)

**Objective:** Move each dialog class into its own file under `ui/dialogs/`.

**Files affected:** `ui/dialogs/all_dialogs.py` → split into `instrument_dialog.py`, `settings_dialog.py`, `calibration_form_dialog.py`, etc.; `ui/dialogs/__init__.py`; `ui/main_window.py` (imports)

**Steps:**
1. Create `ui/dialogs/instrument_dialog.py`; move `InstrumentDialog`; update imports.
2. Repeat for each dialog. One at a time.
3. Keep `all_dialogs.py` as re-export module for backward compatibility: `from ui.dialogs.instrument_dialog import InstrumentDialog`, etc.
4. Eventually remove `all_dialogs.py` or keep as thin `__init__.py` re-exports.

**Risk:** Medium. Many imports; ensure no circular dependencies.

**Verification:** Run app; open each dialog; verify no import errors.

**Rollback:** Revert split; restore monolithic file.

---

### Stage 4: Add CalibrationRecord, Template Domain Models (Low Risk)

**Objective:** Introduce dataclasses for CalibrationRecord and Template (and Field) where they cross layer boundaries.

**Files affected:** `domain/models.py`, `database.py`, `ui/dialogs/all_dialogs.py` (or split dialogs)

**Steps:**
1. Add `CalibrationRecord` dataclass with `from_row`, `to_dict`, `get`, `__getitem__` for compatibility.
2. `database.get_calibration_record()` returns `CalibrationRecord | None`.
3. Migrate callers incrementally; use `.get()` where needed.
4. Repeat for Template, Field when touching those areas.

**Risk:** Low. Same pattern as Instrument; backward-compatible accessors.

**Verification:** Run app; view calibration history; edit calibration.

**Rollback:** Revert model changes; restore dict return.

---

### Stage 5: Extract Connection from database.py (Low Risk, Optional)

**Objective:** Move `get_connection`, `get_effective_db_path`, path helpers into `persistence/connection.py` or `connection.py`.

**Files affected:** New `connection.py` or `persistence/connection.py`; `database.py`; `main.py`

**Steps:**
1. Create `connection.py` with `get_connection`, `get_effective_db_path`, path helpers.
2. `database.py` imports from `connection`; `CalibrationRepository` takes `conn` as today.
3. `main.py` imports `get_connection` from `connection` if desired.

**Risk:** Low. Pure extraction.

**Verification:** Run app; connect; run migrations.

**Rollback:** Revert; restore in database.py.

---

## 6. Coupling Reduction Plan

### 6.1 UI → Repository Direct Calls

**Coupling:** UI dialogs call `repo.add_instrument`, `repo.update_template`, etc. directly. Changes to persistence logic require touching UI.

**Risk:** UI and persistence evolve together; harder to add server-backed mode later.

**Smallest change:** Route writes through services. Services become the single place for validation, audit, and orchestration. UI imports services, not repo for writes.

**Improves stability today:** Yes. Centralizes validation and audit; easier to add conflict handling.

---

### 6.2 database.py → config.json, update_config.json

**Coupling:** `database.py` reads config files directly. Config format changes require touching persistence.

**Risk:** Low. Config is stable.

**Smallest change:** Extract `_load_configured_db_path()` to `config.py`. `database.py` imports `config.load_db_path()`.

**Improves stability today:** Yes. Single config module; clearer ownership.

---

### 6.3 all_dialogs.py → 14 Dialog Classes

**Coupling:** All dialogs in one file; any change risks merge conflicts and broad edits.

**Risk:** High. Single file churn.

**Smallest change:** Split one dialog at a time into `ui/dialogs/<name>_dialog.py`. Re-export from `__init__.py`.

**Improves stability today:** Yes. Smaller files; easier to reason about.

---

### 6.4 pdf_export, lan_notify → database

**Coupling:** `pdf_export` and `lan_notify` import `CalibrationRepository` and call repo methods directly. They are read-only.

**Risk:** Low. Reads are acceptable; no orchestration needed.

**Smallest change:** None required for now. If services later expose "get instruments for export" with filtering, they could use that. Not a priority.

---

## 7. Complexity Guardrails

### 7.1 What We Are Intentionally NOT Building

- **Microservices** — Single process, single DB. No service mesh.
- **Event sourcing** — Audit log is append-only history; no event replay.
- **CQRS** — Read and write paths can share the same repository.
- **Real-time sync** — Sync-later is acceptable. No WebSockets, no live conflict resolution.
- **Multi-tenant** — Single tenant per deployment. No tenant isolation.
- **API-first** — Desktop app first. No REST API for external consumers.
- **ORM** — SQLite + raw SQL. No SQLAlchemy, no Django ORM.

### 7.2 Scale Assumptions Locked In

- **Max 10 users** — Shared server DB; no connection pooling complexity.
- **Single SQLite file** — No sharding, no replication.
- **Sync-later** — Conflict resolution can be batch or manual.
- **Local-first** — Offline capability via local cache; server is authoritative when connected.

---

## 8. If We Evolve Nothing Else Architecturally, Evolve These Three Areas

### 1. Route All Writes Through Services

**Why:** Today, instrument and calibration writes go through services; template, destination, personnel, batch do not. Centralizing all writes in services gives:

- Single place for validation
- Single place for audit
- Single place for future conflict handling (e.g. `expected_updated_at`)

**Effort:** Small. Add 3–4 thin services; replace ~50 repo calls in UI with service calls. No UI behavior change.

**Impact:** High. Enables future multi-user and server-backed mode without refactoring UI again.

---

### 2. Split all_dialogs.py Into One File Per Dialog

**Why:** 5000+ lines, 14 classes. Single file is a cognitive and merge bottleneck.

**Effort:** Medium. One dialog per PR; move class, fix imports, update `__init__.py`. No logic change.

**Impact:** High. Easier navigation, testing, and parallel work. Reduces risk of accidental breakage.

---

### 3. Extract Config to a Dedicated Module

**Why:** Config loading lives in `database.py`. Config is a cross-cutting concern; it should not be owned by persistence.

**Effort:** Small. Add `config.py`; move `_load_configured_db_path()` and related config logic; update `database.py` to import.

**Impact:** Medium. Clearer ownership; easier to add new config (e.g. `current_user_id` when multi-user) without touching persistence.

---

*End of plan.*
