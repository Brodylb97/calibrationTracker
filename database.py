# database.py

import sqlite3
from datetime import date, timedelta
from pathlib import Path
import sys
import shutil

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

# Default DB path: shared network location
SERVER_DB_PATH = Path(
    r"Z:\Shared\Laboratory\Particulate Matter and Other Results\Brody's Project Junk\Cal Tracker\calibration.db"
)

def get_base_dir() -> Path:
    """
    Base dir for the app (install dir when frozen, script dir when run from source).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()

# Default is the server DB; if it can't be opened, get_connection() falls back to local
DB_PATH = SERVER_DB_PATH
ATTACHMENTS_DIR = DB_PATH.parent / "attachments"

# When default (network) is unavailable, we use local; this is set by get_connection()
_effective_db_path: Path | None = None

def get_effective_db_path() -> Path:
    """Path of the DB actually in use (local fallback path when network is unavailable)."""
    return _effective_db_path if _effective_db_path is not None else DB_PATH

def get_attachments_dir() -> Path:
    """Attachments dir for the DB in use (matches get_effective_db_path())."""
    return (BASE_DIR / "attachments") if _effective_db_path is not None else (DB_PATH.parent / "attachments")

# -----------------------------------------------------------------------------
# Connection helpers
# -----------------------------------------------------------------------------

def get_connection(db_path: Path | None = None):
    """
    Get a database connection with optimized settings.
    When db_path is None (default), tries DB_PATH (network) first; if that fails
    with "unable to open database file", falls back to local calibration.db so
    the app still runs when the network is unavailable.
    """
    global _effective_db_path
    if db_path is None:
        db_path = DB_PATH
    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)  # 30 second timeout for locked database
    except sqlite3.OperationalError as e:
        if "unable to open database file" in str(e) and db_path == DB_PATH:
            fallback = BASE_DIR / "calibration.db"
            _effective_db_path = fallback
            conn = sqlite3.connect(str(fallback), timeout=30.0)
        else:
            raise
    else:
        if db_path == DB_PATH:
            _effective_db_path = None  # using default (network) successfully
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

def initialize_db(conn: sqlite3.Connection):
    """
    Initialize database schema with optimized indexes and constraints.
    Also performs daily backup if needed.
    """
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
            status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'RETIRED', 'INACTIVE')),
            notes TEXT,
            instrument_type_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(destination_id) REFERENCES destinations(id) ON DELETE SET NULL,
            FOREIGN KEY(instrument_type_id) REFERENCES instrument_types(id) ON DELETE SET NULL
        )
        """
    )
    # Indexes for frequently queried columns
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_tag_number ON instruments(tag_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_status ON instruments(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_next_due_date ON instruments(next_due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_instrument_type_id ON instruments(instrument_type_id)")
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

    # Add instrument_type_id to instruments if missing
    cur.execute("PRAGMA table_info(instruments)")
    cols = [r[1] for r in cur.fetchall()]
    if "instrument_type_id" not in cols:
        cur.execute(
            "ALTER TABLE instruments ADD COLUMN instrument_type_id INTEGER REFERENCES instrument_types(id) ON DELETE SET NULL"
        )

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
    if "tolerance" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN tolerance REAL")
    if "autofill_from_first_group" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN autofill_from_first_group INTEGER NOT NULL DEFAULT 0")
    if "default_value" not in cols:
        cur.execute("ALTER TABLE calibration_template_fields ADD COLUMN default_value TEXT")


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
    
    # Audit log: instruments & calibrations
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
                  new_value: str | None = None):
        actor = self._get_actor()
        self.conn.execute(
            """
            INSERT INTO audit_log
                (entity_type, entity_id, action, field, old_value, new_value, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, action, field, old_value, new_value, actor),
        )
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
    
    
    def delete_calibration_record(self, record_id: int):
        rec = self.get_calibration_record(record_id)
        if not rec:
            return
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM calibration_values WHERE record_id = ?",
            (record_id,),
        )
        cur.execute(
            "DELETE FROM calibration_records WHERE id = ?",
            (record_id,),
        )
        self.conn.commit()

        self.log_audit(
            "calibration",
            record_id,
            "delete",
            field=None,
            old_value=str(rec),
            new_value=None,
        )

    # ---------- Delete instrument ----------

    def delete_instrument(self, instrument_id: int):
        """Delete an instrument (and its attachments)."""
        cur = self.conn.cursor()
        try:
            cur.execute(
                "DELETE FROM attachments WHERE instrument_id = ?",
                (instrument_id,),
            )
        except Exception:
            pass

        cur.execute(
            "DELETE FROM instruments WHERE id = ?",
            (instrument_id,),
        )
        self.conn.commit()

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
                        notes: str = "") -> int:
        cur = self.conn.execute(
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
                        version: int, is_active: bool, notes: str):
        self.conn.execute(
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
        tolerance: float | None = None,
        autofill_from_first_group: bool = False,
    ) -> int:
        """
        Insert a new template field. Safe for both normal and computed fields.
        """
        cur = self.conn.execute(
            """
            INSERT INTO calibration_template_fields
                (template_id, name, label, data_type, unit,
                 required, sort_order, group_name,
                 calc_type, calc_ref1_name, calc_ref2_name,
                 tolerance, autofill_from_first_group, default_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                tolerance,
                1 if autofill_from_first_group else 0,
                None,  # default_value will be set via update if needed
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_template_field(self, field_id: int, data: dict):
        """
        Update an existing template field. `data` should match get_data() from FieldEditDialog.
        """
        self.conn.execute(
            """
            UPDATE calibration_template_fields
            SET name           = :name,
                label          = :label,
                data_type      = :data_type,
                unit           = :unit,
                required       = :required,
                sort_order     = :sort_order,
                group_name     = :group_name,
                calc_type      = :calc_type,
                calc_ref1_name = :calc_ref1_name,
                calc_ref2_name = :calc_ref2_name,
                tolerance      = :tolerance,
                autofill_from_first_group = :autofill_from_first_group,
                default_value  = :default_value
            WHERE id = :id
            """,
            {
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
            },
        )
        self.conn.commit()

    def delete_template_field(self, field_id: int):
        self.conn.execute(
            "DELETE FROM calibration_template_fields WHERE id = ?",
            (field_id,),
        )
        self.conn.commit()


    # ---------------- Calibration records ----------------

    def list_calibration_records_for_instrument(self, instrument_id: int):
        cur = self.conn.execute(
            """
            SELECT r.*,
                   t.name AS template_name
            FROM calibration_records r
            JOIN calibration_templates t ON r.template_id = t.id
            WHERE r.instrument_id = ?
            ORDER BY r.cal_date DESC, r.id DESC
            """,
            (instrument_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    
    def list_all_calibration_records(self):
        """
        Get all calibration records with instrument and instrument type information.
        Returns list of dicts with record, instrument, and instrument_type data.
        """
        cur = self.conn.execute(
            """
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
            ORDER BY it.name ASC, i.tag_number ASC, r.cal_date DESC
            """,
        )
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
        cur = self.conn.execute(
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
                                  field_values: dict[int, str]) -> int:
        """
        field_values: dict[field_id] = value_text
        """
        cur = self.conn.cursor()
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

        self.conn.commit()
        
        # audit
        self.log_audit(
            "calibration",
            rec_id,
            "create",
            field=None,
            old_value=None,
            new_value=f"instrument_id={instrument_id}, template_id={template_id}",
        )

        return rec_id

    def update_calibration_record(self, record_id: int, cal_date: str,
                                  performed_by: str, result: str, notes: str,
                                  field_values: dict[int, str]):
        cur = self.conn.cursor()
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

    def list_instruments(self):
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
               d.name  AS destination_name,
               it.name AS instrument_type_name
        FROM instruments i
        LEFT JOIN destinations d
               ON i.destination_id = d.id
        LEFT JOIN instrument_types it
               ON i.instrument_type_id = it.id
        ORDER BY date(i.next_due_date) ASC, i.tag_number
        """
        cur = self.conn.execute(query)
        return [dict(r) for r in cur.fetchall()]

    def get_instrument(self, instrument_id: int):
        cur = self.conn.execute(
            "SELECT * FROM instruments WHERE id = ?", (instrument_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

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
        self.conn.execute(
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
        dest_path = dest_dir / src.name

        shutil.copy2(str(src), str(dest_path))

        self.conn.execute(
            "INSERT INTO attachments (instrument_id, filename, file_path, record_id) "
            "VALUES (?, ?, ?, ?)",
            (instrument_id, src.name, str(dest_path), record_id),
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

        cur = self.conn.execute(
            """
            SELECT i.*,
                   d.name AS destination_name
            FROM instruments i
            LEFT JOIN destinations d ON i.destination_id = d.id
            WHERE i.status = 'ACTIVE'
              AND i.next_due_date IS NOT NULL
              AND i.next_due_date >= ?
              AND i.next_due_date <= ?
            ORDER BY i.next_due_date ASC, i.tag_number ASC
            """,
            (today.isoformat(), upper.isoformat()),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
