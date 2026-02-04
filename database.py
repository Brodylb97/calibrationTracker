# database.py

import json
import os
import sys
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.models import Instrument
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import shutil

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

def _last_db_file() -> Path:
    """Path to the file storing the last-used DB path (for --db override / restart)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
        if not base:
            base = Path.home() / "AppData" / "Roaming"
        else:
            base = Path(base)
    else:
        base = Path.home() / ".config"
    return base / "CalibrationTracker" / "last_db.txt"


def get_persisted_last_db_path() -> Path | None:
    """Read last-used DB path from %APPDATA%\\CalibrationTracker\\last_db.txt (or ~/.config on non-Windows). Returns None if missing or invalid."""
    p = _last_db_file()
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return Path(raw)
    except Exception:
        return None


def persist_last_db_path(path: Path) -> None:
    """Write the given DB path so the next launch can use it as default (e.g. after an update)."""
    import logging
    from file_utils import atomic_write_text
    p = _last_db_file()
    try:
        atomic_write_text(p, str(path.resolve()))
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to persist last DB path to %s: %s", p, e
        )

# Default DB path when no config is set (shared network location)
_DEFAULT_SERVER_DB_PATH = Path(
    r"Z:\Shared\Laboratory\Particulate Matter and Other Results\Brody's Project Junk\Cal Tracker Current\calibration.db"
)

# Environment variable to override config file location
CONFIG_PATH_ENV = "CALIBRATION_TRACKER_CONFIG"
# Environment variable to override database path directly (overrides config file)
DB_PATH_ENV = "CALIBRATION_TRACKER_DB_PATH"


def _app_base_dir() -> Path:
    """Directory containing the app (install dir when frozen, script dir when run from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _is_local_directory_path(path: Path) -> bool:
    """
    True if path is under the application directory or current working directory.
    Such paths are treated as local copies; only the server database path is allowed.
    """
    try:
        path = path.resolve()
    except OSError:
        return True  # Unresolvable: treat as invalid/local
    base = _app_base_dir().resolve()
    cwd = Path.cwd().resolve()
    try:
        path.relative_to(base)
        return True
    except ValueError:
        pass
    try:
        path.relative_to(cwd)
        return True
    except ValueError:
        pass
    return False


def _load_configured_db_path() -> Path:
    """
    Load database path from configuration.
    Order: DB_PATH_ENV > config.json > update_config.json > _DEFAULT_SERVER_DB_PATH.
    Paths under the app directory or current directory are rejected; only the server path is used.
    """
    import logging
    _log = logging.getLogger(__name__)

    def _reject_local_and_return(path: Path) -> Path:
        if _is_local_directory_path(path):
            _log.warning(
                "Database path is in application or current directory (local copy). "
                "Using server path only: %s",
                _DEFAULT_SERVER_DB_PATH,
            )
            return _DEFAULT_SERVER_DB_PATH
        return path

    base = _app_base_dir()
    # 1. Environment variable (highest priority)
    env_path = os.environ.get(DB_PATH_ENV)
    if env_path and env_path.strip():
        return _reject_local_and_return(Path(env_path.strip()).resolve())

    # 2. config.json
    for config_name in ("config.json", "update_config.json"):
        config_path = base / config_name
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw = data.get("db_path")
                if raw and isinstance(raw, str) and raw.strip():
                    p = Path(raw.strip())
                    if not p.is_absolute():
                        p = (config_path.parent / p).resolve()
                    return _reject_local_and_return(p)
            except (json.JSONDecodeError, OSError):
                pass

    return _DEFAULT_SERVER_DB_PATH


# Resolved default path (from config or constant)
SERVER_DB_PATH = _load_configured_db_path()


def _path_equal(a: Path | None, b: Path | None) -> bool:
    """True if both paths refer to the same location (normalized for slashes and case)."""
    if a is None or b is None:
        return a == b
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def is_server_db_path(path: Path | None) -> bool:
    """True if path is the server database path (so we only use server, never Program Files or other local paths)."""
    return path is not None and _path_equal(path, SERVER_DB_PATH)


def get_base_dir() -> Path:
    """Base dir for the app (install dir when frozen, script dir when run from source)."""
    return _app_base_dir()


BASE_DIR = get_base_dir()

# App connects only to the server database (DB_PATH or explicit --db to same server).
DB_PATH = SERVER_DB_PATH
ATTACHMENTS_DIR = DB_PATH.parent / "attachments"

# Future: "server" | "local". When server-backed work begins, this gates connection and sync behavior.
DATA_MODE = "local"

_effective_db_path: Path | None = None


def get_effective_db_path() -> Path:
    """Path of the DB in use (always the server path we connected to)."""
    return _effective_db_path if _effective_db_path is not None else DB_PATH


def get_attachments_dir() -> Path:
    """Attachments dir next to the server DB."""
    return get_effective_db_path().parent / "attachments"

# -----------------------------------------------------------------------------
# Connection helpers
# -----------------------------------------------------------------------------

def get_connection(db_path: Path | None = None, timeout: float = 30.0, retries: int = 3):
    """
    Connect to the server database only. No local copies; only the server path is allowed.
    Raises ValueError if db_path is not the server path. Raises on open failure or read-only.
    timeout: seconds to wait for locks (use a shorter value for UI-triggered reconnect).
    retries: number of retries on SQLITE_BUSY / database is locked (with exponential backoff).
    """
    import time
    global _effective_db_path
    if db_path is None:
        db_path = DB_PATH
    if not is_server_db_path(db_path):
        raise ValueError(
            f"Only the server database is allowed. Path '{db_path}' is not the server path. "
            "Local copies are not used."
        )
    _effective_db_path = db_path
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    last_err = None
    for attempt in range(max(1, retries)):
        try:
            conn = sqlite3.connect(str(db_path), timeout=timeout)
            break
        except sqlite3.OperationalError as e:
            last_err = e
            err_lower = str(e).lower()
            if "unable to open database file" in err_lower:
                raise sqlite3.OperationalError(
                    f"Could not open database at:\n{db_path}\n\n"
                    "Check that:\n"
                    "• The drive (e.g. Z:) is connected and the path is accessible\n"
                    "• The folder exists (or that the app can create it)\n"
                    "• You have read and write permission for that location"
                ) from e
            if ("database is locked" in err_lower or "sqlite_busy" in err_lower) and attempt < retries - 1:
                time.sleep(0.1 * (2 ** attempt))
                continue
            raise
    else:
        if last_err:
            raise last_err
        raise RuntimeError("Failed to connect to database")

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# -----------------------------------------------------------------------------
# Default instrument types
# -----------------------------------------------------------------------------

DEFAULT_INSTRUMENT_TYPES = [
    "3D Flow Consoles",
    "3D Probes",
    "Analytical Balances",
    "Calipers",
    "Class A Glassware",
    "Digital Barometer",
    "Digital Manometers",
    "Digital Micrometer",
    "Digital Thermometer with Probe",
    "Dilutors",
    "Dionex Ion Chromatograph",
    "Dispenser and Titrette",
    "Field Balance Weights",
    "Fume Hood",
    "Gage Blocks",
    "Hotwire Anemometer",
    "Infrared Thermometer",
    "Laboratory Calibration Weights",
    "Low Flow Consoles",
    "Mercury Analyzer",
    "Mercury Console",
    "Nozzles",
    "Orifice Sets",
    "OVA",
    "Oven",
    "pH Meters",
    "Pipettes",
    "Pitot Block Verifications",
    "Pitot Tubes",
    "PM-10 Head Nozzles",
    "PM-Equipment",
    "Portable Analyzers",
    "Refridgerator Thermometer",  # your spelling preserved
    "Setting Rings",
    "Spectrophotometer",
    "Thermocouple Source",
    "Thermocouple Thermometers",
    "Weather Stations",
]

def seed_default_instrument_types(conn: sqlite3.Connection):
    """
    Insert default instrument types if they don't already exist.
    Safe to call every startup; uses INSERT OR IGNORE.
    """
    cur = conn.cursor()
    for name in DEFAULT_INSTRUMENT_TYPES:
        cur.execute(
            """
            INSERT OR IGNORE INTO instrument_types (name, description)
            VALUES (?, '')
            """,
            (name,),
        )
    conn.commit()

# -----------------------------------------------------------------------------
# Schema initialization
# -----------------------------------------------------------------------------

def run_integrity_check(conn: sqlite3.Connection) -> str | None:
    """
    Run PRAGMA integrity_check. Returns None if OK, or an error message string if failed.
    """
    cur = conn.execute("PRAGMA integrity_check")
    row = cur.fetchone()
    if row is None:
        return None
    result = row[0] if hasattr(row, "__getitem__") else str(row)
    if result == "ok":
        return None
    return result


def initialize_db(conn: sqlite3.Connection, db_path: Path | None = None) -> sqlite3.Connection:
    """
    Initialize database schema and seed defaults. No fallback; app uses server DB only.
    On read-only error, raises with a clear message so the user can fix server/share permissions.
    Runs integrity check after init; on failure logs a warning (does not block startup).
    """
    try:
        _initialize_db_core(conn, db_path)
        err = run_integrity_check(conn)
        if err:
            import logging
            logging.getLogger(__name__).warning("Database integrity check failed: %s", err)
        return conn
    except sqlite3.OperationalError as e:
        err = str(e).lower()
        if "readonly" in err or "attempt to write" in err:
            path = db_path if db_path is not None else get_effective_db_path()
            raise sqlite3.OperationalError(
                f"The database at {path} is read-only. "
                "Ensure the folder and file have write permission for your user "
                "(check the network share or server permissions), then try again."
            ) from e
        raise


def _initialize_db_core(conn: sqlite3.Connection, db_path: Path | None = None) -> None:
    """Internal: run schema creation and seeding. Raises on readonly."""
    cur = conn.cursor()

    # Enable foreign keys and optimize SQLite settings
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
    cur.execute("PRAGMA synchronous = NORMAL")  # Balance between safety and speed
    cur.execute("PRAGMA cache_size = -64000")  # 64MB cache
    cur.execute("PRAGMA temp_store = MEMORY")  # Store temp tables in memory

    # Core tables
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            email TEXT,
            phone TEXT,
            address TEXT
        )
        """
    )
    # Index for destination lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_destinations_name ON destinations(name)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS instruments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_number TEXT NOT NULL,
            serial_number TEXT,
            description TEXT,
            location TEXT,
            calibration_type TEXT CHECK (calibration_type IN ('SEND_OUT','PULL_IN')),
            destination_id INTEGER,
            last_cal_date TEXT,
            next_due_date TEXT NOT NULL,
            frequency_months INTEGER,
            status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'RETIRED', 'INACTIVE', 'OUT_FOR_CAL')),
            notes TEXT,
            instrument_type_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(destination_id) REFERENCES destinations(id) ON DELETE SET NULL,
            FOREIGN KEY(instrument_type_id) REFERENCES instrument_types(id) ON DELETE SET NULL
        )
        """
    )
    # Indexes for frequently queried columns (instrument_type_id index created after column may be added below)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_tag_number ON instruments(tag_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_status ON instruments(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_next_due_date ON instruments(next_due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_destination_id ON instruments(destination_id)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id INTEGER NOT NULL,
            filename     TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            uploaded_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            record_id    INTEGER,
            FOREIGN KEY(instrument_id) REFERENCES instruments(id) ON DELETE CASCADE,
            FOREIGN KEY(record_id) REFERENCES calibration_records(id) ON DELETE CASCADE
        )
        """
    )
    # Add record_id if missing (migration)
    cur.execute("PRAGMA table_info(attachments)")
    cols = [r[1] for r in cur.fetchall()]
    if "record_id" not in cols:
        cur.execute(
            "ALTER TABLE attachments "
            "ADD COLUMN record_id INTEGER REFERENCES calibration_records(id) ON DELETE CASCADE"
        )
    # Remove unused file_data column if it exists (cleanup)
    if "file_data" in cols:
        # SQLite doesn't support DROP COLUMN, so we'll leave it but document it's unused
        pass
    # Indexes for attachments
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_instrument_id ON attachments(instrument_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_record_id ON attachments(record_id)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id INTEGER NOT NULL,
            reminder_date TEXT NOT NULL,
            FOREIGN KEY(instrument_id) REFERENCES instruments(id)
        )
        """
    )

    # Instrument types
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_types (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            description     TEXT
        )
        """
    )
    # Index for instrument types (name is already unique, but explicit index helps)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instrument_types_name ON instrument_types(name)")

    # Add instrument_type_id to instruments if missing (existing DBs may not have it)
    cur.execute("PRAGMA table_info(instruments)")
    cols = [r[1] for r in cur.fetchall()]
    if "instrument_type_id" not in cols:
        cur.execute(
            "ALTER TABLE instruments ADD COLUMN instrument_type_id INTEGER REFERENCES instrument_types(id) ON DELETE SET NULL"
        )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_instrument_type_id ON instruments(instrument_type_id)")

    # Calibration templates (per instrument_type)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_templates (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_type_id  INTEGER NOT NULL REFERENCES instrument_types(id) ON DELETE CASCADE,
            name                TEXT NOT NULL,
            version             INTEGER NOT NULL DEFAULT 1,
            is_active           INTEGER NOT NULL DEFAULT 1,
            notes               TEXT
        )
        """
    )
    # Indexes for templates
    cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_instrument_type_id ON calibration_templates(instrument_type_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_is_active ON calibration_templates(is_active)")

    # Fields in each template
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_template_fields (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id     INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            label           TEXT NOT NULL,
            data_type       TEXT NOT NULL CHECK (data_type IN ('text', 'number', 'bool', 'date', 'signature')),
            unit            TEXT,
            required        INTEGER NOT NULL DEFAULT 0,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            group_name      TEXT,
            calc_type       TEXT,
            calc_ref1_name  TEXT,
            calc_ref2_name  TEXT,
            tolerance       REAL,
            autofill_from_first_group INTEGER NOT NULL DEFAULT 0,
            default_value   TEXT
        )
        """
    )
    # Indexes for template fields
    cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_template_id ON calibration_template_fields(template_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_sort_order ON calibration_template_fields(template_id, sort_order)")
    # Add computed-field columns if they don't exist yet (schema migration)
    cur.execute("PRAGMA table_info(calibration_template_fields)")
    cols = [r[1] for r in cur.fetchall()]
    if "calc_type" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN calc_type TEXT")
    if "calc_ref1_name" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN calc_ref1_name TEXT")
    if "calc_ref2_name" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN calc_ref2_name TEXT")
    for ref_col in ("calc_ref3_name", "calc_ref4_name", "calc_ref5_name", "calc_ref6_name", "calc_ref7_name", "calc_ref8_name", "calc_ref9_name", "calc_ref10_name"):
        if ref_col not in cols:
            cur.execute(f"ALTER TABLE calibration_template_fields ADD COLUMN {ref_col} TEXT")
    if "tolerance" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN tolerance REAL")
    if "autofill_from_first_group" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN autofill_from_first_group INTEGER NOT NULL DEFAULT 0")
    if "default_value" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN default_value TEXT")
    if "sig_figs" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN sig_figs INTEGER DEFAULT 3")
    if "stat_value_group" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN stat_value_group TEXT")

    # Calibration records per instrument
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
            template_id     INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE RESTRICT,
            cal_date        TEXT NOT NULL,      -- YYYY-MM-DD
            performed_by    TEXT,
            result          TEXT,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    # Indexes for calibration records
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_records_instrument_id ON calibration_records(instrument_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_records_template_id ON calibration_records(template_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_records_cal_date ON calibration_records(cal_date)")

    # Values for each field in each record
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_values (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id       INTEGER NOT NULL REFERENCES calibration_records(id) ON DELETE CASCADE,
            field_id        INTEGER NOT NULL REFERENCES calibration_template_fields(id) ON DELETE RESTRICT,
            value_text      TEXT
        )
        """
    )
    # Indexes for calibration values
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_values_record_id ON calibration_values(record_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_values_field_id ON calibration_values(field_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cal_values_record_field ON calibration_values(record_id, field_id)")

    # Audit log: instruments & calibrations (must exist before migrations)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK (entity_type IN ('instrument', 'calibration')),
            entity_id   INTEGER NOT NULL,
            action      TEXT NOT NULL,
            field       TEXT,
            old_value   TEXT,
            new_value   TEXT,
            actor       TEXT,
            ts          TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    # Indexes for audit log (important for querying history)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts DESC)")
    # Ensure reason column exists (migration 1 adds it; this handles pre-migration or version skip)
    cur.execute("PRAGMA table_info(audit_log)")
    audit_cols = [r[1] for r in cur.fetchall()]
    if "reason" not in audit_cols:
        cur.execute("ALTER TABLE audit_log ADD COLUMN reason TEXT")
    conn.commit()

    # Schema version and migrations (run after core tables including audit_log)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
    )
    conn.commit()
    try:
        from migrations import run_migrations
        run_migrations(conn, db_path)
    except ImportError:
        pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Schema migration failed: %s", e, exc_info=True)
        raise RuntimeError(
            f"Database schema migration failed. Your database may be incompatible with this version.\n\n"
            f"Error: {e}\n\n"
            "Check the log file or try restoring from a backup."
        ) from e

    conn.commit()
    get_attachments_dir().mkdir(parents=True, exist_ok=True)
    seed_default_instrument_types(conn)
    
    # Perform daily backup if needed (import here to avoid circular dependency)
    try:
        from database_backup import perform_daily_backup_if_needed
        perform_daily_backup_if_needed(get_effective_db_path(), max_backups=30)
    except ImportError:
        # database_backup module not available, skip backup
        pass
    except Exception as e:
        # Don't fail initialization if backup fails
        import logging
        logging.getLogger(__name__).warning(f"Daily backup check failed: {e}")
    
    conn.commit()


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------

class StaleDataError(Exception):
    """Raised when optimistic lock fails (record was modified by another process/user)."""


# -----------------------------------------------------------------------------
# Repository
# -----------------------------------------------------------------------------

class CalibrationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    # ---------- Audit log ----------

    def _get_actor(self):
        try:
            return self.get_setting("operator_name", None)
        except Exception:
            return None

    def log_audit(self, entity_type: str, entity_id: int, action: str,
                  field: str | None = None,
                  old_value: str | None = None,
                  new_value: str | None = None,
                  reason: str | None = None,
                  _commit: bool = True):
        actor = self._get_actor()
        self.conn.execute(
            """
            INSERT INTO audit_log
                (entity_type, entity_id, action, field, old_value, new_value, actor, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, action, field, old_value, new_value, actor, reason),
        )
        if _commit:
            self.conn.commit()

    def get_audit_for_instrument(self, instrument_id: int):
        cur = self.conn.execute(
            """
            SELECT *
            FROM audit_log
            WHERE entity_type = 'instrument'
              AND entity_id = ?
            ORDER BY ts DESC, id DESC
            """,
            (instrument_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_audit_for_calibration(self, record_id: int):
        cur = self.conn.execute(
            """
            SELECT *
            FROM audit_log
            WHERE entity_type = 'calibration'
              AND entity_id = ?
            ORDER BY ts DESC, id DESC
            """,
            (record_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    
    # ---------- Delete attachment ----------
    def delete_attachment(self, attachment_id: int):
        """
        Delete a single attachment, removing both the DB row and the stored file
        on disk (if it still exists).
        """
        att = self.get_attachment(attachment_id)
        if att:
            file_path = att.get("file_path")
            if file_path:
                try:
                    p = Path(file_path)
                    if p.exists():
                        p.unlink()
                except Exception:
                    # Don't blow up if the file is already gone
                    pass

        self.conn.execute(
            "DELETE FROM attachments WHERE id = ?",
            (attachment_id,),
        )
        self.conn.commit()
    
    
    def delete_calibration_record(self, record_id: int, reason: str | None = None):
        rec = self.get_calibration_record(record_id)
        if not rec:
            return
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                "DELETE FROM calibration_values WHERE record_id = ?",
                (record_id,),
            )
            cur.execute(
                "DELETE FROM calibration_records WHERE id = ?",
                (record_id,),
            )
            self.log_audit(
                "calibration",
                record_id,
                "delete",
                field=None,
                old_value=str(rec),
                new_value=None,
                reason=reason,
                _commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- Delete instrument ----------

    def delete_instrument(self, instrument_id: int, reason: str | None = None):
        """Hard-delete an instrument (and its attachments). For soft delete use archive_instrument."""
        cur = self.conn.cursor()
        old = self.get_instrument(instrument_id)
        try:
            cur.execute("BEGIN")
            cur.execute(
                "DELETE FROM attachments WHERE instrument_id = ?",
                (instrument_id,),
            )
            cur.execute(
                "DELETE FROM instruments WHERE id = ?",
                (instrument_id,),
            )
            if old:
                self.log_audit(
                    "instrument",
                    instrument_id,
                    "delete",
                    field=None,
                    old_value=str(old),
                    new_value=None,
                    reason=reason,
                    _commit=False,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def batch_update_instruments(self, instrument_ids: list[int], updates: dict,
                                  reason: str | None = None) -> int:
        """
        Apply the same field updates to multiple instruments in one transaction.
        updates: dict with only keys to change, e.g. {"status": "ACTIVE"} or {"next_due_date": "2025-12-31"}.
        Returns number of instruments updated.
        """
        if not instrument_ids or not updates:
            return 0
        allowed = {"status", "next_due_date", "last_cal_date", "notes", "instrument_type_id"}
        updates = {k: v for k, v in updates.items() if k in allowed}
        if not updates:
            return 0
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            old_by_id = {iid: self.get_instrument(iid) for iid in instrument_ids}
            set_parts = ["updated_at = CURRENT_TIMESTAMP"]
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            placeholders = ",".join("?" * len(instrument_ids))
            sql = f"UPDATE instruments SET {', '.join(set_parts)} WHERE id IN ({placeholders})"
            cur.execute(sql, params + instrument_ids)
            for iid in instrument_ids:
                old = old_by_id.get(iid)
                if old:
                    for fld in updates:
                        if str(old.get(fld)) != str(updates.get(fld)):
                            self.log_audit(
                                "instrument",
                                iid,
                                "batch_update",
                                field=fld,
                                old_value=str(old.get(fld)) if old.get(fld) is not None else None,
                                new_value=str(updates.get(fld)) if updates.get(fld) is not None else None,
                                reason=reason,
                                _commit=False,
                            )
            self.conn.commit()
            return len(instrument_ids)
        except Exception:
            self.conn.rollback()
            raise

    def archive_instrument(self, instrument_id: int, deleted_by: str | None = None,
                          reason: str | None = None) -> None:
        """Soft-delete (archive) an instrument. List methods exclude archived by default."""
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" not in cols:
            raise RuntimeError("Schema migration 2 required for archive (deleted_at column)")
        actor = deleted_by or self._get_actor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                "UPDATE instruments SET deleted_at = datetime('now'), deleted_by = ? WHERE id = ?",
                (actor, instrument_id),
            )
            self.log_audit(
                "instrument",
                instrument_id,
                "archive",
                field="deleted_at",
                old_value=None,
                new_value="archived",
                reason=reason,
                _commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def archive_calibration_record(self, record_id: int, deleted_by: str | None = None,
                                   reason: str | None = None) -> None:
        """Soft-delete (archive) a calibration record. List methods exclude archived by default."""
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_records)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" not in cols:
            raise RuntimeError("Schema migration 2 required for archive (deleted_at column)")
        actor = deleted_by or self._get_actor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                "UPDATE calibration_records SET deleted_at = datetime('now'), deleted_by = ? WHERE id = ?",
                (actor, record_id),
            )
            self.log_audit(
                "calibration",
                record_id,
                "archive",
                field="deleted_at",
                old_value=None,
                new_value="archived",
                reason=reason,
                _commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------------- Instrument types ----------------

    def list_instrument_types(self):
        cur = self.conn.execute(
            "SELECT id, name, description FROM instrument_types ORDER BY name ASC"
        )
        return [dict(r) for r in cur.fetchall()]

    def add_instrument_type(self, name: str, description: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO instrument_types (name, description) VALUES (?, ?)",
            (name, description),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_instrument_type(self, type_id: int):
        cur = self.conn.execute(
            "SELECT id, name, description FROM instrument_types WHERE id = ?",
            (type_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    # ---------------- Personnel (M7) ----------------

    def _personnel_table_exists(self) -> bool:
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='personnel'"
        )
        return cur.fetchone() is not None

    def list_personnel(self, active_only: bool = True):
        if not self._personnel_table_exists():
            return []
        sql = "SELECT id, name, role, qualifications, review_expiry, active FROM personnel ORDER BY name ASC"
        if active_only:
            sql = "SELECT id, name, role, qualifications, review_expiry, active FROM personnel WHERE active = 1 ORDER BY name ASC"
        cur = self.conn.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    def get_personnel(self, person_id: int):
        if not self._personnel_table_exists():
            return None
        cur = self.conn.execute("SELECT * FROM personnel WHERE id = ?", (person_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def add_personnel(self, name: str, role: str = "", qualifications: str = "",
                      review_expiry: str | None = None, active: bool = True) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO personnel (name, role, qualifications, review_expiry, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip(), role.strip(), qualifications.strip(), review_expiry, 1 if active else 0),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_personnel(self, person_id: int, name: str, role: str = "", qualifications: str = "",
                         review_expiry: str | None = None, active: bool = True):
        self.conn.execute(
            """
            UPDATE personnel
            SET name = ?, role = ?, qualifications = ?, review_expiry = ?, active = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (name.strip(), role.strip(), qualifications.strip(), review_expiry, 1 if active else 0, person_id),
        )
        self.conn.commit()

    def delete_personnel(self, person_id: int):
        self.conn.execute("DELETE FROM calibration_template_personnel WHERE person_id = ?", (person_id,))
        self.conn.execute("DELETE FROM personnel WHERE id = ?", (person_id,))
        self.conn.commit()

    def list_personnel_authorized_for_template(self, template_id: int):
        """Personnel authorized to perform this template (for Performed by dropdown)."""
        if not self._personnel_table_exists():
            return []
        cur = self.conn.execute(
            """
            SELECT p.id, p.name, p.role
            FROM personnel p
            JOIN calibration_template_personnel ctp ON ctp.person_id = p.id
            WHERE ctp.template_id = ? AND p.active = 1
            ORDER BY p.name ASC
            """,
            (template_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def set_template_authorized_personnel(self, template_id: int, person_ids: list[int]):
        """Set which personnel are authorized to perform this template."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM calibration_template_personnel WHERE template_id = ?", (template_id,))
        for pid in person_ids or []:
            cur.execute(
                "INSERT INTO calibration_template_personnel (template_id, person_id) VALUES (?, ?)",
                (template_id, pid),
            )
        self.conn.commit()

    def get_template_authorized_person_ids(self, template_id: int) -> list[int]:
        if not self._personnel_table_exists():
            return []
        cur = self.conn.execute(
            "SELECT person_id FROM calibration_template_personnel WHERE template_id = ?",
            (template_id,),
        )
        return [r[0] for r in cur.fetchall()]

    # ---------------- Calibration templates ----------------

    def list_templates_for_type(self, instrument_type_id: int, active_only: bool = True):
        sql = """
            SELECT t.*
            FROM calibration_templates t
            WHERE t.instrument_type_id = ?
        """
        params = [instrument_type_id]
        if active_only:
            sql += " AND t.is_active = 1"
        sql += " ORDER BY t.name, t.version"
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def get_template(self, template_id: int):
        cur = self.conn.execute(
            "SELECT * FROM calibration_templates WHERE id = ?",
            (template_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_template_fields(self, template_id: int):
        cur = self.conn.execute(
            """
            SELECT *
            FROM calibration_template_fields
            WHERE template_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (template_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    
    def create_template(self, instrument_type_id: int, name: str,
                        version: int = 1, is_active: bool = True,
                        notes: str = "",
                        effective_date: str | None = None,
                        change_reason: str | None = None,
                        status: str | None = None) -> int:
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_templates)")
        cols = [r[1] for r in cur.fetchall()]
        if "effective_date" in cols and "change_reason" in cols and "status" in cols:
            cur.execute(
                """
                INSERT INTO calibration_templates
                    (instrument_type_id, name, version, is_active, notes,
                     effective_date, change_reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (instrument_type_id, name, version, 1 if is_active else 0, notes,
                 effective_date, change_reason, status or "Draft"),
            )
        else:
            cur.execute(
                """
                INSERT INTO calibration_templates
                    (instrument_type_id, name, version, is_active, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (instrument_type_id, name, version, 1 if is_active else 0, notes),
            )
        self.conn.commit()
        return cur.lastrowid

    def update_template(self, template_id: int, name: str,
                        version: int, is_active: bool, notes: str,
                        effective_date: str | None = None,
                        change_reason: str | None = None,
                        status: str | None = None):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_templates)")
        cols = [r[1] for r in cur.fetchall()]
        if "effective_date" in cols and "change_reason" in cols and "status" in cols:
            cur.execute(
                """
                UPDATE calibration_templates
                SET name = ?, version = ?, is_active = ?, notes = ?,
                    effective_date = ?, change_reason = ?, status = ?
                WHERE id = ?
                """,
                (name, version, 1 if is_active else 0, notes,
                 effective_date, change_reason, status, template_id),
            )
        else:
            cur.execute(
                """
                UPDATE calibration_templates
                SET name = ?, version = ?, is_active = ?, notes = ?
                WHERE id = ?
                """,
                (name, version, 1 if is_active else 0, notes, template_id),
            )
        self.conn.commit()

    def delete_template(self, template_id: int):
        # optional safety: refuse delete if records exist
        cur = self.conn.execute(
            "SELECT COUNT(*) AS c FROM calibration_records WHERE template_id = ?",
            (template_id,),
        )
        c = cur.fetchone()["c"]
        if c > 0:
            raise ValueError(
                f"Cannot delete template; {c} calibration record(s) are using it."
            )

        # delete fields first
        self.conn.execute(
            "DELETE FROM calibration_template_fields WHERE template_id = ?",
            (template_id,),
        )
        self.conn.execute(
            "DELETE FROM calibration_templates WHERE id = ?",
            (template_id,),
        )
        self.conn.commit()

    def add_template_field(
        self,
        template_id: int,
        name: str,
        label: str,
        data_type: str,
        unit: str | None,
        required: bool,
        sort_order: int,
        group_name: str | None,
        calc_type: str | None = None,
        calc_ref1_name: str | None = None,
        calc_ref2_name: str | None = None,
        calc_ref3_name: str | None = None,
        calc_ref4_name: str | None = None,
        calc_ref5_name: str | None = None,
        calc_ref6_name: str | None = None,
        calc_ref7_name: str | None = None,
        calc_ref8_name: str | None = None,
        calc_ref9_name: str | None = None,
        calc_ref10_name: str | None = None,
        calc_ref11_name: str | None = None,
        calc_ref12_name: str | None = None,
        tolerance: float | None = None,
        autofill_from_first_group: bool = False,
        default_value: str | None = None,
        tolerance_type: str | None = None,
        tolerance_equation: str | None = None,
        nominal_value: str | None = None,
        tolerance_lookup_json: str | None = None,
        sig_figs: int | None = 3,
        stat_value_group: str | None = None,
        plot_x_axis_name: str | None = None,
        plot_y_axis_name: str | None = None,
        plot_title: str | None = None,
        plot_x_min: float | None = None,
        plot_x_max: float | None = None,
        plot_y_min: float | None = None,
        plot_y_max: float | None = None,
        plot_best_fit: bool = False,
    ) -> int:
        """
        Insert a new template field. Safe for both normal and computed fields.
        tolerance_type: 'fixed' | 'percent' | 'equation' | 'lookup' | None (legacy fixed).
        stat_value_group: for stat type, which group's fields to use for val1..val12 (value selection).
        plot_*: for plot type, axis names, title, ranges, and best-fit option.
        """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_template_fields)")
        cols = [r[1] for r in cur.fetchall()]
        has_plot = "plot_x_axis_name" in cols
        plot_sql = ", plot_x_axis_name, plot_y_axis_name, plot_title, plot_x_min, plot_x_max, plot_y_min, plot_y_max, plot_best_fit" if has_plot else ""
        plot_ph = ", ?, ?, ?, ?, ?, ?, ?, ?" if has_plot else ""
        plot_vals = (plot_x_axis_name, plot_y_axis_name, plot_title, plot_x_min, plot_x_max, plot_y_min, plot_y_max, 1 if plot_best_fit else 0) if has_plot else ()
        has_ref3 = "calc_ref3_name" in cols
        ref3_sql = ", calc_ref3_name, calc_ref4_name, calc_ref5_name" if has_ref3 else ""
        ref3_ph = ", ?, ?, ?" if has_ref3 else ""
        ref3_vals = (calc_ref3_name, calc_ref4_name, calc_ref5_name) if has_ref3 else ()
        has_ref6 = "calc_ref6_name" in cols
        ref6_sql = ", calc_ref6_name, calc_ref7_name, calc_ref8_name, calc_ref9_name, calc_ref10_name" if has_ref6 else ""
        ref6_ph = ", ?, ?, ?, ?, ?" if has_ref6 else ""
        ref6_vals = (calc_ref6_name, calc_ref7_name, calc_ref8_name, calc_ref9_name, calc_ref10_name) if has_ref6 else ()
        has_ref11 = "calc_ref11_name" in cols
        ref11_sql = ", calc_ref11_name, calc_ref12_name" if has_ref11 else ""
        ref11_ph = ", ?, ?" if has_ref11 else ""
        ref11_vals = (calc_ref11_name, calc_ref12_name) if has_ref11 else ()
        sig_figs_val = 3 if sig_figs is None else max(0, min(4, int(sig_figs)))  # decimal places for display
        has_sig_figs = "sig_figs" in cols
        sig_figs_sql = ", sig_figs" if has_sig_figs else ""
        sig_figs_ph = ", ?" if has_sig_figs else ""
        sig_figs_vals = (sig_figs_val,) if has_sig_figs else ()
        has_stat_value_group = "stat_value_group" in cols
        stat_value_group_sql = ", stat_value_group" if has_stat_value_group else ""
        stat_value_group_ph = ", ?" if has_stat_value_group else ""
        stat_value_group_vals = (stat_value_group,) if has_stat_value_group else ()
        if "tolerance_type" in cols:
            if "tolerance_lookup_json" in cols:
                cur.execute(
                    """
                    INSERT INTO calibration_template_fields
                        (template_id, name, label, data_type, unit,
                         required, sort_order, group_name,
                         calc_type, calc_ref1_name, calc_ref2_name""" + ref3_sql + ref6_sql + ref11_sql + """,
                         tolerance, autofill_from_first_group, default_value,
                         tolerance_type, tolerance_equation, nominal_value, tolerance_lookup_json""" + sig_figs_sql + stat_value_group_sql + plot_sql + """)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""" + ref3_ph + ref6_ph + ref11_ph + """, ?, ?, ?, ?, ?, ?, ?""" + sig_figs_ph + stat_value_group_ph + plot_ph + """)
                    """,
                    (
                        template_id,
                        name,
                        label,
                        data_type,
                        unit,
                        1 if required else 0,
                        sort_order,
                        group_name,
                        calc_type,
                        calc_ref1_name,
                        calc_ref2_name,
                        *ref3_vals,
                        *ref6_vals,
                        *ref11_vals,
                        tolerance,
                        1 if autofill_from_first_group else 0,
                        default_value,
                        tolerance_type,
                        tolerance_equation,
                        nominal_value,
                        tolerance_lookup_json,
                        *sig_figs_vals,
                        *stat_value_group_vals,
                        *plot_vals,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO calibration_template_fields
                        (template_id, name, label, data_type, unit,
                         required, sort_order, group_name,
                         calc_type, calc_ref1_name, calc_ref2_name""" + ref3_sql + ref6_sql + ref11_sql + """,
                         tolerance, autofill_from_first_group, default_value,
                         tolerance_type, tolerance_equation, nominal_value""" + sig_figs_sql + stat_value_group_sql + plot_sql + """)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""" + ref3_ph + ref6_ph + ref11_ph + """, ?, ?, ?, ?, ?, ?, ?""" + sig_figs_ph + stat_value_group_ph + plot_ph + """)
                    """,
                    (
                        template_id,
                        name,
                        label,
                        data_type,
                        unit,
                        1 if required else 0,
                        sort_order,
                        group_name,
                        calc_type,
                        calc_ref1_name,
                        calc_ref2_name,
                        *ref3_vals,
                        *ref6_vals,
                        *ref11_vals,
                        tolerance,
                        1 if autofill_from_first_group else 0,
                        default_value,
                        tolerance_type,
                        tolerance_equation,
                        nominal_value,
                        *sig_figs_vals,
                        *stat_value_group_vals,
                        *plot_vals,
                    ),
                )
        else:
            cur.execute(
                """
                INSERT INTO calibration_template_fields
                    (template_id, name, label, data_type, unit,
                     required, sort_order, group_name,
                     calc_type, calc_ref1_name, calc_ref2_name""" + ref3_sql + ref6_sql + ref11_sql + """,
                     tolerance, autofill_from_first_group, default_value""" + sig_figs_sql + stat_value_group_sql + plot_sql + """)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""" + ref3_ph + ref6_ph + ref11_ph + """, ?, ?, ?""" + sig_figs_ph + stat_value_group_ph + plot_ph + """)
                """,
                (
                    template_id,
                    name,
                    label,
                    data_type,
                    unit,
                    1 if required else 0,
                    sort_order,
                    group_name,
                    calc_type,
                    calc_ref1_name,
                    calc_ref2_name,
                    *ref3_vals,
                    *ref6_vals,
                    *ref11_vals,
                    tolerance,
                    1 if autofill_from_first_group else 0,
                    default_value,
                    *sig_figs_vals,
                    *stat_value_group_vals,
                    *plot_vals,
                ),
            )
        self.conn.commit()
        return cur.lastrowid

    def update_template_field(self, field_id: int, data: dict):
        """
        Update an existing template field. `data` should match get_data() from FieldEditDialog.
        """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_template_fields)")
        cols = [r[1] for r in cur.fetchall()]
        set_clause = """
            name = :name,
            label = :label,
            data_type = :data_type,
            unit = :unit,
            required = :required,
            sort_order = :sort_order,
            group_name = :group_name,
            calc_type = :calc_type,
            calc_ref1_name = :calc_ref1_name,
            calc_ref2_name = :calc_ref2_name,
            tolerance = :tolerance,
            autofill_from_first_group = :autofill_from_first_group,
            default_value = :default_value
        """
        params = {
            "id": field_id,
            "name": data["name"],
            "label": data["label"],
            "data_type": data["data_type"],
            "unit": data.get("unit"),
            "required": 1 if data.get("required") else 0,
            "sort_order": data.get("sort_order", 0),
            "group_name": data.get("group_name"),
            "calc_type": data.get("calc_type"),
            "calc_ref1_name": data.get("calc_ref1_name"),
            "calc_ref2_name": data.get("calc_ref2_name"),
            "tolerance": data.get("tolerance"),
            "autofill_from_first_group": 1 if data.get("autofill_from_first_group") else 0,
            "default_value": data.get("default_value"),
        }
        if "tolerance_type" in cols:
            set_clause += ", tolerance_type = :tolerance_type, tolerance_equation = :tolerance_equation, nominal_value = :nominal_value"
            params["tolerance_type"] = data.get("tolerance_type")
            params["tolerance_equation"] = data.get("tolerance_equation")
            params["nominal_value"] = data.get("nominal_value")
        if "calc_ref3_name" in cols:
            set_clause += ", calc_ref3_name = :calc_ref3_name, calc_ref4_name = :calc_ref4_name, calc_ref5_name = :calc_ref5_name"
            params["calc_ref3_name"] = data.get("calc_ref3_name")
            params["calc_ref4_name"] = data.get("calc_ref4_name")
            params["calc_ref5_name"] = data.get("calc_ref5_name")
        if "calc_ref6_name" in cols:
            set_clause += ", calc_ref6_name = :calc_ref6_name, calc_ref7_name = :calc_ref7_name, calc_ref8_name = :calc_ref8_name, calc_ref9_name = :calc_ref9_name, calc_ref10_name = :calc_ref10_name"
            params["calc_ref6_name"] = data.get("calc_ref6_name")
            params["calc_ref7_name"] = data.get("calc_ref7_name")
            params["calc_ref8_name"] = data.get("calc_ref8_name")
            params["calc_ref9_name"] = data.get("calc_ref9_name")
            params["calc_ref10_name"] = data.get("calc_ref10_name")
        if "calc_ref11_name" in cols:
            set_clause += ", calc_ref11_name = :calc_ref11_name, calc_ref12_name = :calc_ref12_name"
            params["calc_ref11_name"] = data.get("calc_ref11_name")
            params["calc_ref12_name"] = data.get("calc_ref12_name")
        if "tolerance_lookup_json" in cols:
            set_clause += ", tolerance_lookup_json = :tolerance_lookup_json"
            params["tolerance_lookup_json"] = data.get("tolerance_lookup_json")
        if "sig_figs" in cols:
            set_clause += ", sig_figs = :sig_figs"
            params["sig_figs"] = data.get("sig_figs", 3)
        if "stat_value_group" in cols:
            set_clause += ", stat_value_group = :stat_value_group"
            params["stat_value_group"] = data.get("stat_value_group")
        if "plot_x_axis_name" in cols:
            set_clause += ", plot_x_axis_name = :plot_x_axis_name, plot_y_axis_name = :plot_y_axis_name, plot_title = :plot_title, plot_x_min = :plot_x_min, plot_x_max = :plot_x_max, plot_y_min = :plot_y_min, plot_y_max = :plot_y_max, plot_best_fit = :plot_best_fit"
            params["plot_x_axis_name"] = data.get("plot_x_axis_name")
            params["plot_y_axis_name"] = data.get("plot_y_axis_name")
            params["plot_title"] = data.get("plot_title")
            params["plot_x_min"] = data.get("plot_x_min")
            params["plot_x_max"] = data.get("plot_x_max")
            params["plot_y_min"] = data.get("plot_y_min")
            params["plot_y_max"] = data.get("plot_y_max")
            params["plot_best_fit"] = 1 if data.get("plot_best_fit") else 0
        cur.execute(
            f"UPDATE calibration_template_fields SET {set_clause} WHERE id = :id",
            params,
        )
        self.conn.commit()

    def delete_template_field(self, field_id: int):
        # Remove calibration values that reference this field (FK is ON DELETE RESTRICT)
        self.conn.execute(
            "DELETE FROM calibration_values WHERE field_id = ?",
            (field_id,),
        )
        self.conn.execute(
            "DELETE FROM calibration_template_fields WHERE id = ?",
            (field_id,),
        )
        self.conn.commit()


    # ---------------- Calibration records ----------------

    def list_calibration_records_for_instrument(self, instrument_id: int,
                                                 include_archived: bool = False):
        sql = """
            SELECT r.*,
                   t.name AS template_name
            FROM calibration_records r
            JOIN calibration_templates t ON r.template_id = t.id
            WHERE r.instrument_id = ?
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_records)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            sql += " AND (r.deleted_at IS NULL OR r.deleted_at = '')"
        sql += " ORDER BY r.cal_date DESC, r.id DESC"
        cur = self.conn.execute(sql, (instrument_id,))
        return [dict(r) for r in cur.fetchall()]
    
    def list_all_calibration_records(self, include_archived: bool = False):
        """
        Get all calibration records with instrument and instrument type information.
        Returns list of dicts with record, instrument, and instrument_type data.
        Excludes archived records unless include_archived=True.
        """
        sql = """
            SELECT r.*,
                   i.tag_number,
                   i.serial_number,
                   i.description AS instrument_description,
                   i.location,
                   it.name AS instrument_type_name,
                   it.id AS instrument_type_id
            FROM calibration_records r
            JOIN instruments i ON r.instrument_id = i.id
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_records)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            sql += " WHERE (r.deleted_at IS NULL OR r.deleted_at = '')"
        sql += " ORDER BY it.name ASC, i.tag_number ASC, r.cal_date DESC"
        cur = self.conn.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    def get_calibration_record(self, record_id: int):
        cur = self.conn.execute(
            "SELECT * FROM calibration_records WHERE id = ?",
            (record_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_calibration_record_with_template(self, record_id: int):
        cur = self.conn.execute(
            """
            SELECT r.*,
                   t.name AS template_name,
                   t.notes AS template_notes,
                   it.name AS instrument_type_name
            FROM calibration_records r
            JOIN calibration_templates t ON r.template_id = t.id
            JOIN instruments i ON r.instrument_id = i.id
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            WHERE r.id = ?
            """,
            (record_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_calibration_values(self, record_id: int):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_template_fields)")
        field_cols = {r[1] for r in cur.fetchall()}
        extra = []
        for col in ("tolerance_type", "tolerance_equation", "nominal_value", "tolerance_lookup_json",
                    "calc_ref3_name", "calc_ref4_name", "calc_ref5_name", "calc_ref6_name", "calc_ref7_name", "calc_ref8_name", "calc_ref9_name", "calc_ref10_name", "calc_ref11_name", "calc_ref12_name", "sig_figs", "stat_value_group",
                    "plot_x_axis_name", "plot_y_axis_name", "plot_title", "plot_x_min", "plot_x_max", "plot_y_min", "plot_y_max", "plot_best_fit"):
            if col in field_cols:
                extra.append(f"f.{col}")
        extra_sql = ", " + ", ".join(extra) if extra else ""
        cur.execute(
            """
            SELECT v.*,
                f.name AS field_name,
                f.label,
                f.data_type,
                f.unit,
                f.group_name,
                f.calc_type,
                f.calc_ref1_name,
                f.calc_ref2_name,
                f.tolerance
                """ + extra_sql + """
            FROM calibration_values v
            JOIN calibration_template_fields f ON v.field_id = f.id
            WHERE v.record_id = ?
            ORDER BY f.sort_order ASC, f.id ASC
            """,
            (record_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def create_calibration_record(self, instrument_id: int, template_id: int,
                                  cal_date: str, performed_by: str,
                                  result: str, notes: str,
                                  field_values: dict[int, str],
                                  template_version: int | None = None) -> int:
        """
        field_values: dict[field_id] = value_text
        template_version: version of template at time of calibration (H4 audit trail).
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute("PRAGMA table_info(calibration_records)")
            cols = [r[1] for r in cur.fetchall()]
            if "template_version" in cols:
                cur.execute(
                    """
                    INSERT INTO calibration_records
                        (instrument_id, template_id, cal_date, performed_by, result, notes, template_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (instrument_id, template_id, cal_date, performed_by, result, notes, template_version),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO calibration_records
                        (instrument_id, template_id, cal_date, performed_by, result, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (instrument_id, template_id, cal_date, performed_by, result, notes),
                )
            rec_id = cur.lastrowid

            for field_id, val in field_values.items():
                cur.execute(
                    """
                    INSERT INTO calibration_values (record_id, field_id, value_text)
                    VALUES (?, ?, ?)
                    """,
                    (rec_id, field_id, str(val) if val is not None else None),
                )

            self.log_audit(
                "calibration",
                rec_id,
                "create",
                field=None,
                old_value=None,
                new_value=f"instrument_id={instrument_id}, template_id={template_id}",
                _commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return rec_id

    def update_calibration_record(self, record_id: int, cal_date: str,
                                  performed_by: str, result: str, notes: str,
                                  field_values: dict[int, str],
                                  expected_updated_at: str | None = None):
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            if expected_updated_at is not None:
                cur.execute(
                    """
                    UPDATE calibration_records
                    SET cal_date = ?, performed_by = ?, result = ?, notes = ?,
                        updated_at = datetime('now')
                    WHERE id = ? AND updated_at = ?
                    """,
                    (cal_date, performed_by, result, notes, record_id, expected_updated_at),
                )
                if cur.rowcount == 0:
                    self.conn.rollback()
                    raise StaleDataError("Calibration record was modified elsewhere. Refresh and try again.")
            else:
                cur.execute(
                    """
                    UPDATE calibration_records
                    SET cal_date = ?, performed_by = ?, result = ?, notes = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (cal_date, performed_by, result, notes, record_id),
                )

            cur.execute(
                "DELETE FROM calibration_values WHERE record_id = ?",
                (record_id,),
            )

            for field_id, val in field_values.items():
                cur.execute(
                    """
                    INSERT INTO calibration_values (record_id, field_id, value_text)
                    VALUES (?, ?, ?)
                    """,
                    (record_id, field_id, str(val) if val is not None else None),
                )

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def set_record_state(self, record_id: int, state: str,
                         reviewed_by: str | None = None,
                         approved_by: str | None = None,
                         reason: str | None = None) -> None:
        """
        Set calibration record state: Draft, Reviewed, Approved, Archived.
        For Reviewed set reviewed_by and reviewed_at; for Approved set approved_by and approved_at.
        """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(calibration_records)")
        cols = [r[1] for r in cur.fetchall()]
        if "record_state" not in cols:
            raise RuntimeError("Schema migration 3 required for record_state")
        actor = self._get_actor()
        try:
            cur.execute("BEGIN")
            if state == "Reviewed":
                cur.execute(
                    """UPDATE calibration_records
                       SET record_state = ?, reviewed_by = ?, reviewed_at = datetime('now')
                       WHERE id = ?""",
                    (state, reviewed_by or actor, record_id),
                )
            elif state == "Approved":
                cur.execute(
                    """UPDATE calibration_records
                       SET record_state = ?, approved_by = ?, approved_at = datetime('now')
                       WHERE id = ?
                    """,
                    (state, approved_by or actor, record_id),
                )
            elif state in ("Draft", "Archived"):
                cur.execute(
                    "UPDATE calibration_records SET record_state = ? WHERE id = ?",
                    (state, record_id),
                )
            else:
                self.conn.rollback()
                raise ValueError(f"Invalid record_state: {state}")
            self.log_audit(
                "calibration",
                record_id,
                "set_state",
                field="record_state",
                old_value=None,
                new_value=state,
                reason=reason,
                _commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- Settings ----------

    def get_setting(self, key: str, default=None):
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ---------- Recipients ----------

    def list_recipients(self):
        cur = self.conn.execute(
            "SELECT id, name, email, active FROM recipients ORDER BY email"
        )
        return [dict(row) for row in cur.fetchall()]

    def add_recipient(self, name: str, email: str, active: bool = True):
        self.conn.execute(
            "INSERT INTO recipients (name, email, active) VALUES (?, ?, ?)",
            (name, email, 1 if active else 0),
        )
        self.conn.commit()

    def delete_recipient(self, recipient_id: int):
        self.conn.execute("DELETE FROM recipients WHERE id = ?", (recipient_id,))
        self.conn.commit()

    def get_active_recipient_emails(self):
        cur = self.conn.execute(
            "SELECT email FROM recipients WHERE active = 1 ORDER BY email"
        )
        return [row["email"] for row in cur.fetchall()]

    # ---------- Destinations ----------

    def list_destinations(self):
        cur = self.conn.execute(
            "SELECT id, name FROM destinations ORDER BY name"
        )
        return [dict(row) for row in cur.fetchall()]

    def list_destinations_full(self):
        cur = self.conn.execute(
            "SELECT id, name, contact, email, phone, address "
            "FROM destinations ORDER BY name"
        )
        return [dict(row) for row in cur.fetchall()]

    def get_destination_name(self, dest_id: int):
        if dest_id is None:
            return ""
        cur = self.conn.execute(
            "SELECT name FROM destinations WHERE id = ?", (dest_id,)
        )
        row = cur.fetchone()
        return row["name"] if row else ""

    def add_destination(self, name: str, contact: str = "", email: str = "",
                        phone: str = "", address: str = ""):
        self.conn.execute(
            "INSERT INTO destinations (name, contact, email, phone, address) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, contact, email, phone, address),
        )
        self.conn.commit()

    def update_destination(self, dest_id: int, data: dict):
        data["id"] = dest_id
        self.conn.execute(
            """
            UPDATE destinations
            SET name = :name,
                contact = :contact,
                email = :email,
                phone = :phone,
                address = :address
            WHERE id = :id
            """,
            data,
        )
        self.conn.commit()

    def delete_destination(self, dest_id: int):
        self.conn.execute("DELETE FROM destinations WHERE id = ?", (dest_id,))
        self.conn.commit()

    # ---------- Instruments ----------

    def list_instruments(self, include_archived: bool = False):
        query = """
        SELECT i.id,
               i.tag_number,
               i.serial_number,
               i.description,
               i.location,
               i.calibration_type,
               i.destination_id,
               i.last_cal_date,
               i.next_due_date,
               i.frequency_months,
               i.status,
               i.notes,
               i.instrument_type_id,
               i.updated_at,
               d.name  AS destination_name,
               it.name AS instrument_type_name
        FROM instruments i
        LEFT JOIN destinations d
               ON i.destination_id = d.id
        LEFT JOIN instrument_types it
               ON i.instrument_type_id = it.id
        """
        # Exclude archived unless requested (requires migration 2 columns)
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            query += " WHERE (i.deleted_at IS NULL OR i.deleted_at = '')"

        # Overall result (Pass/Fail) of the single most recent calibration record per instrument only
        cur.execute("PRAGMA table_info(calibration_records)")
        rec_cols = [r[1] for r in cur.fetchall()]
        cal_deleted_filter = " AND (r.deleted_at IS NULL OR r.deleted_at = '')" if "deleted_at" in rec_cols and not include_archived else ""
        subq = (
            "(SELECT r.result FROM calibration_records r "
            "WHERE r.instrument_id = i.id" + cal_deleted_filter + " "
            "ORDER BY r.cal_date DESC, r.id DESC LIMIT 1) AS last_cal_result"
        )
        query = query.replace(
            " it.name AS instrument_type_name\n        FROM instruments i",
            " it.name AS instrument_type_name,\n               " + subq + "\n        FROM instruments i",
        )

        query += " ORDER BY date(i.next_due_date) ASC, i.tag_number"
        cur = self.conn.execute(query)
        return [dict(r) for r in cur.fetchall()]

    def get_overdue_instruments(self, include_archived: bool = False):
        """Instruments with next_due_date < today, ACTIVE, not archived."""
        today = date.today().isoformat()
        sql = """
            SELECT i.id, i.tag_number, i.next_due_date, i.status, i.updated_at,
                   d.name AS destination_name, it.name AS instrument_type_name
            FROM instruments i
            LEFT JOIN destinations d ON i.destination_id = d.id
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            WHERE i.status = 'ACTIVE'
              AND i.next_due_date IS NOT NULL
              AND date(i.next_due_date) < date(?)
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            sql += " AND (i.deleted_at IS NULL OR i.deleted_at = '')"
        sql += " ORDER BY i.next_due_date ASC, i.tag_number"
        cur = self.conn.execute(sql, (today,))
        return [dict(r) for r in cur.fetchall()]

    def get_due_soon_instruments(self, days: int, include_archived: bool = False):
        """Instruments due within [today, today + days], ACTIVE."""
        today = date.today()
        upper = (today + timedelta(days=days)).isoformat()
        today_str = today.isoformat()
        sql = """
            SELECT i.id, i.tag_number, i.next_due_date, i.status, i.updated_at,
                   d.name AS destination_name, it.name AS instrument_type_name
            FROM instruments i
            LEFT JOIN destinations d ON i.destination_id = d.id
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            WHERE i.status = 'ACTIVE'
              AND i.next_due_date IS NOT NULL
              AND date(i.next_due_date) >= date(?)
              AND date(i.next_due_date) <= date(?)
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            sql += " AND (i.deleted_at IS NULL OR i.deleted_at = '')"
        sql += " ORDER BY i.next_due_date ASC, i.tag_number"
        cur = self.conn.execute(sql, (today_str, upper))
        return [dict(r) for r in cur.fetchall()]

    def get_recently_modified_instruments(self, days: int = 7, include_archived: bool = False):
        """Instruments with updated_at in the last days (for Needs Attention)."""
        sql = """
            SELECT i.id, i.tag_number, i.next_due_date, i.updated_at,
                   d.name AS destination_name, it.name AS instrument_type_name
            FROM instruments i
            LEFT JOIN destinations d ON i.destination_id = d.id
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            WHERE datetime(i.updated_at) >= datetime('now', ?)
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols and not include_archived:
            sql += " AND (i.deleted_at IS NULL OR i.deleted_at = '')"
        sql += " ORDER BY i.updated_at DESC, i.tag_number"
        cur = self.conn.execute(sql, (f"-{days} days",))
        return [dict(r) for r in cur.fetchall()]

    def get_instrument(self, instrument_id: int) -> "Instrument | None":
        """Return Instrument model or None if not found."""
        from domain.models import Instrument

        cur = self.conn.execute(
            "SELECT * FROM instruments WHERE id = ?", (instrument_id,)
        )
        row = cur.fetchone()
        return Instrument.from_row(row) if row else None

    def add_instrument(self, data: dict) -> int:
        # make sure key exists even if None
        data.setdefault("instrument_type_id", None)

        self.conn.execute(
            """
            INSERT INTO instruments (
                tag_number, serial_number, description, location,
                calibration_type, destination_id, last_cal_date,
                next_due_date, frequency_months, status, notes,
                instrument_type_id,
                created_at, updated_at
            ) VALUES (
                :tag_number, :serial_number, :description, :location,
                :calibration_type, :destination_id, :last_cal_date,
                :next_due_date, :frequency_months, :status, :notes,
                :instrument_type_id,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            data,
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    
    def update_instrument(self, instrument_id: int, data: dict):
        # ensure key exists even if None
        data.setdefault("instrument_type_id", None)

        # fetch old for audit
        old = self.get_instrument(instrument_id) or {}

        data["id"] = instrument_id
        expected_updated_at = data.get("updated_at")
        cur = self.conn.cursor()
        if expected_updated_at is not None:
            params = {**data, "expected_updated_at": expected_updated_at}
            cur.execute(
                """
                UPDATE instruments
                SET tag_number         = :tag_number,
                    serial_number      = :serial_number,
                    description        = :description,
                    location           = :location,
                    calibration_type   = :calibration_type,
                    destination_id     = :destination_id,
                    last_cal_date      = :last_cal_date,
                    next_due_date      = :next_due_date,
                    frequency_months   = :frequency_months,
                    status             = :status,
                    notes              = :notes,
                    instrument_type_id = :instrument_type_id,
                    updated_at         = CURRENT_TIMESTAMP
                WHERE id = :id AND updated_at = :expected_updated_at
                """,
                params,
            )
            if cur.rowcount == 0:
                raise StaleDataError("Instrument was modified by another user. Refresh and try again.")
        else:
            cur.execute(
                """
                UPDATE instruments
                SET tag_number         = :tag_number,
                    serial_number      = :serial_number,
                    description        = :description,
                    location           = :location,
                    calibration_type   = :calibration_type,
                    destination_id     = :destination_id,
                    last_cal_date      = :last_cal_date,
                    next_due_date      = :next_due_date,
                    frequency_months   = :frequency_months,
                    status             = :status,
                    notes              = :notes,
                    instrument_type_id = :instrument_type_id,
                    updated_at         = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                data,
            )
        self.conn.commit()

        # simple field-by-field audit
        watched_fields = [
            "tag_number",
            "location",
            "calibration_type",
            "destination_id",
            "last_cal_date",
            "next_due_date",
            "frequency_months",
            "status",
            "notes",
            "instrument_type_id",
        ]
        for fld in watched_fields:
            old_val = old.get(fld)
            new_val = data.get(fld)
            if str(old_val) != str(new_val):
                self.log_audit(
                    "instrument",
                    instrument_id,
                    "update",
                    field=fld,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(new_val) if new_val is not None else None,
                )

    def mark_calibrated_on(self, instrument_id: int, last_cal: date):
        """Set last_cal_date to given date and next_due_date to +1 year."""
        next_due = last_cal + timedelta(days=365)
        last_str = last_cal.isoformat()
        next_str = next_due.isoformat()

        self.conn.execute(
            """
            UPDATE instruments
            SET last_cal_date = ?, next_due_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (last_str, next_str, instrument_id),
        )
        self.conn.commit()

        self.log_audit(
            "instrument",
            instrument_id,
            "mark_calibrated",
            field="last_cal_date",
            old_value=None,
            new_value=last_str,
        )
        self.log_audit(
            "instrument",
            instrument_id,
            "mark_calibrated",
            field="next_due_date",
            old_value=None,
            new_value=next_str,
        )

    def mark_calibrated_today(self, instrument_id: int):
        """Convenience wrapper: uses today's date."""
        self.mark_calibrated_on(instrument_id, date.today())

    # ---------- Attachments ----------

    def list_attachments(self, instrument_id: int):
        cur = self.conn.execute(
            "SELECT id, filename, file_path, uploaded_at "
            "FROM attachments WHERE instrument_id = ? ORDER BY uploaded_at DESC",
            (instrument_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def add_attachment(self, instrument_id: int, src_path: str, record_id: int | None = None):
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(src_path)

        dest_dir = get_attachments_dir() / str(instrument_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{src.stem}_{uuid.uuid4().hex[:8]}{src.suffix}"
        dest_path = dest_dir / unique_name

        shutil.copy2(str(src), str(dest_path))

        self.conn.execute(
            "INSERT INTO attachments (instrument_id, filename, file_path, record_id) "
            "VALUES (?, ?, ?, ?)",
            (instrument_id, src.name, str(dest_path), record_id),  # filename = display name
        )
        self.conn.commit()

    def get_attachment(self, attachment_id: int):
        cur = self.conn.execute(
            "SELECT * FROM attachments WHERE id = ?",
            (attachment_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_attachment(self, attachment_id: int):
        """
        Delete a single attachment, removing both the DB row and the stored file.
        """
        att = self.get_attachment(attachment_id)
        if att:
            file_path = att.get("file_path")
            if file_path:
                try:
                    p = Path(file_path)
                    if p.exists():
                        p.unlink()
                except Exception:
                    # If it's already gone, whatever
                    pass

        self.conn.execute(
            "DELETE FROM attachments WHERE id = ?",
            (attachment_id,),
        )
        self.conn.commit()
        
    def list_attachments_for_record(self, record_id: int):
        cur = self.conn.execute(
            "SELECT id, filename, file_path, uploaded_at "
            "FROM attachments WHERE record_id = ? "
            "ORDER BY uploaded_at DESC",
            (record_id,),
        )
        return [dict(r) for r in cur.fetchall()]


    # ---------- Reminder / notification logic ----------

    def get_due_instruments(self, reminder_days: int):
        """
        Return instruments due within [today, today + reminder_days].

        This version does NOT care whether a reminder has been sent before.
        If the date is in range, it will be included every time you run it.
        """
        today = date.today()
        upper = today + timedelta(days=reminder_days)

        sql = """
            SELECT i.*,
                   d.name AS destination_name
            FROM instruments i
            LEFT JOIN destinations d ON i.destination_id = d.id
            WHERE i.status = 'ACTIVE'
              AND i.next_due_date IS NOT NULL
              AND i.next_due_date >= ?
              AND i.next_due_date <= ?
            """
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(instruments)")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" in cols:
            sql += " AND (i.deleted_at IS NULL OR i.deleted_at = '')"
        sql += " ORDER BY i.next_due_date ASC, i.tag_number ASC"
        cur = self.conn.execute(sql, (today.isoformat(), upper.isoformat()))
        rows = cur.fetchall()
        return [dict(row) for row in rows]
