# migrations.py
# Schema versioning and migrations for Calibration Tracker.
# Run after core schema creation; migrations are applied in order.

import sqlite3
import logging

logger = logging.getLogger(__name__)

SCHEMA_VERSION_TABLE = "schema_version"


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return current schema version (0 if table or row missing)."""
    cur = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (SCHEMA_VERSION_TABLE,),
    )
    if cur.fetchone() is None:
        return 0
    cur = conn.execute(f"SELECT MAX(version) AS v FROM {SCHEMA_VERSION_TABLE}")
    row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set schema version (replaces any existing row)."""
    conn.execute(f"DELETE FROM {SCHEMA_VERSION_TABLE}")
    conn.execute(f"INSERT INTO {SCHEMA_VERSION_TABLE} (version) VALUES (?)", (version,))
    conn.commit()


def migrate_1_instruments_status_and_audit_reason(conn: sqlite3.Connection) -> None:
    """
    Migration 1: Allow OUT_FOR_CAL in instruments.status (UI uses it; DB had only INACTIVE).
    Add reason column to audit_log for change justification.
    """
    cur = conn.cursor()
    # Add audit_log.reason if missing
    cur.execute("PRAGMA table_info(audit_log)")
    audit_cols = [r[1] for r in cur.fetchall()]
    if "reason" not in audit_cols:
        cur.execute("ALTER TABLE audit_log ADD COLUMN reason TEXT")
        conn.commit()

    # Recreate instruments table with CHECK including OUT_FOR_CAL (SQLite cannot ALTER CHECK)
    cur.execute("PRAGMA table_info(instruments)")
    inst_cols = [r[1] for r in cur.fetchall()]
    if "deleted_at" in inst_cols:
        # Already has later migrations' columns; only ensure we don't double-run
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cur.execute(
            """
            CREATE TABLE instruments_new (
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
        cur.execute(
            "INSERT INTO instruments_new SELECT * FROM instruments"
        )
        cur.execute("DROP TABLE instruments")
        cur.execute("ALTER TABLE instruments_new RENAME TO instruments")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_tag_number ON instruments(tag_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_status ON instruments(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_next_due_date ON instruments(next_due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_instrument_type_id ON instruments(instrument_type_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_destination_id ON instruments(destination_id)")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Migration 1 applied: instruments.status OUT_FOR_CAL, audit_log.reason")


def migrate_2_soft_delete(conn: sqlite3.Connection) -> None:
    """Add deleted_at, deleted_by to instruments and calibration_records for soft delete/archive."""
    cur = conn.cursor()
    for table in ("instruments", "calibration_records"):
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if "deleted_at" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")
        if "deleted_by" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN deleted_by TEXT")
    conn.commit()
    logger.info("Migration 2 applied: soft delete columns")


def migrate_3_record_state(conn: sqlite3.Connection) -> None:
    """Add record_state and review/approval fields to calibration_records."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calibration_records)")
    cols = [r[1] for r in cur.fetchall()]
    if "record_state" not in cols:
        cur.execute(
            "ALTER TABLE calibration_records ADD COLUMN record_state TEXT DEFAULT 'Draft' "
            "CHECK (record_state IN ('Draft','Reviewed','Approved','Archived'))"
        )
    if "reviewed_by" not in cols:
        cur.execute("ALTER TABLE calibration_records ADD COLUMN reviewed_by TEXT")
    if "reviewed_at" not in cols:
        cur.execute("ALTER TABLE calibration_records ADD COLUMN reviewed_at TEXT")
    if "approved_by" not in cols:
        cur.execute("ALTER TABLE calibration_records ADD COLUMN approved_by TEXT")
    if "approved_at" not in cols:
        cur.execute("ALTER TABLE calibration_records ADD COLUMN approved_at TEXT")
    cur.execute("UPDATE calibration_records SET record_state = 'Draft' WHERE record_state IS NULL")
    conn.commit()
    logger.info("Migration 3 applied: record state and review/approval fields")


def migrate_4_personnel(conn: sqlite3.Connection) -> None:
    """Add personnel table and template–personnel link for authorized performers."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS personnel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT,
            qualifications TEXT,
            review_expiry TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_template_personnel (
            template_id INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE CASCADE,
            person_id INTEGER NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
            PRIMARY KEY (template_id, person_id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_template_personnel_template ON calibration_template_personnel(template_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_template_personnel_person ON calibration_template_personnel(person_id)")
    conn.commit()
    logger.info("Migration 4 applied: personnel and calibration_template_personnel")


def _has_column(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def migrate_5_template_tolerance_and_versioning(conn: sqlite3.Connection) -> None:
    """
    H2/H4: Add tolerance_type, tolerance_equation, nominal_value to fields;
    effective_date, change_reason, status to templates; template_version to calibration_records.
    """
    cur = conn.cursor()
    # calibration_templates
    for col, typ, default in [
        ("effective_date", "TEXT", None),
        ("change_reason", "TEXT", None),
        ("status", "TEXT", "Draft"),
    ]:
        if not _has_column(cur, "calibration_templates", col):
            if default:
                conn.execute(
                    f"ALTER TABLE calibration_templates ADD COLUMN {col} {typ} DEFAULT '{default}'"
                )
            else:
                conn.execute(f"ALTER TABLE calibration_templates ADD COLUMN {col} {typ}")
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
    conn.execute(
        """
        UPDATE calibration_template_fields
        SET tolerance_type = 'fixed'
        WHERE tolerance IS NOT NULL AND (tolerance_type IS NULL OR tolerance_type = '')
        """
    )
    conn.commit()
    logger.info("Migration 5 applied: template tolerance types, versioning, template_version on records")


def migrate_6_add_reference_type(conn: sqlite3.Connection) -> None:
    """Add 'reference' to calibration_template_fields.data_type CHECK."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calibration_template_fields)")
    old_cols = [r[1] for r in cur.fetchall()]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cur.execute(
            """
            CREATE TABLE calibration_template_fields_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                label           TEXT NOT NULL,
                data_type       TEXT NOT NULL CHECK (data_type IN ('text', 'number', 'bool', 'date', 'signature', 'reference')),
                unit            TEXT,
                required        INTEGER NOT NULL DEFAULT 0,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                group_name      TEXT,
                calc_type       TEXT,
                calc_ref1_name  TEXT,
                calc_ref2_name  TEXT,
                calc_ref3_name  TEXT,
                calc_ref4_name  TEXT,
                calc_ref5_name  TEXT,
                tolerance       REAL,
                autofill_from_first_group INTEGER NOT NULL DEFAULT 0,
                default_value   TEXT,
                tolerance_type  TEXT,
                tolerance_equation TEXT,
                nominal_value   TEXT,
                tolerance_lookup_json TEXT
            )
            """
        )
        sel_cols = [c for c in old_cols if c in (
            "id", "template_id", "name", "label", "data_type", "unit", "required", "sort_order",
            "group_name", "calc_type", "calc_ref1_name", "calc_ref2_name", "calc_ref3_name",
            "calc_ref4_name", "calc_ref5_name", "tolerance", "autofill_from_first_group",
            "default_value", "tolerance_type", "tolerance_equation", "nominal_value", "tolerance_lookup_json"
        )]
        ins_cols = sel_cols
        sel_list = ", ".join(sel_cols)
        ins_list = ", ".join(ins_cols)
        cur.execute(
            f"INSERT INTO calibration_template_fields_new ({ins_list}) SELECT {sel_list} FROM calibration_template_fields"
        )
        cur.execute("DROP TABLE calibration_template_fields")
        cur.execute("ALTER TABLE calibration_template_fields_new RENAME TO calibration_template_fields")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_template_id ON calibration_template_fields(template_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_sort_order ON calibration_template_fields(template_id, sort_order)")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Migration 6 applied: added 'reference' to calibration_template_fields.data_type")


def migrate_7_add_tolerance_type(conn: sqlite3.Connection) -> None:
    """Add 'tolerance' to calibration_template_fields.data_type CHECK (read-only display field)."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calibration_template_fields)")
    old_cols = [r[1] for r in cur.fetchall()]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cur.execute(
            """
            CREATE TABLE calibration_template_fields_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                label           TEXT NOT NULL,
                data_type       TEXT NOT NULL CHECK (data_type IN ('text', 'number', 'bool', 'date', 'signature', 'reference', 'tolerance')),
                unit            TEXT,
                required        INTEGER NOT NULL DEFAULT 0,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                group_name      TEXT,
                calc_type       TEXT,
                calc_ref1_name  TEXT,
                calc_ref2_name  TEXT,
                calc_ref3_name  TEXT,
                calc_ref4_name  TEXT,
                calc_ref5_name  TEXT,
                tolerance       REAL,
                autofill_from_first_group INTEGER NOT NULL DEFAULT 0,
                default_value   TEXT,
                tolerance_type  TEXT,
                tolerance_equation TEXT,
                nominal_value   TEXT,
                tolerance_lookup_json TEXT
            )
            """
        )
        sel_cols = [c for c in old_cols if c in (
            "id", "template_id", "name", "label", "data_type", "unit", "required", "sort_order",
            "group_name", "calc_type", "calc_ref1_name", "calc_ref2_name", "calc_ref3_name",
            "calc_ref4_name", "calc_ref5_name", "tolerance", "autofill_from_first_group",
            "default_value", "tolerance_type", "tolerance_equation", "nominal_value", "tolerance_lookup_json"
        )]
        sel_list = ", ".join(sel_cols)
        ins_list = ", ".join(sel_cols)
        cur.execute(
            f"INSERT INTO calibration_template_fields_new ({ins_list}) SELECT {sel_list} FROM calibration_template_fields"
        )
        cur.execute("DROP TABLE calibration_template_fields")
        cur.execute("ALTER TABLE calibration_template_fields_new RENAME TO calibration_template_fields")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_template_id ON calibration_template_fields(template_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_sort_order ON calibration_template_fields(template_id, sort_order)")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Migration 7 applied: added 'tolerance' to calibration_template_fields.data_type")


def _migration_lock_path(db_path) -> "Path | None":
    """Path to advisory lock file next to the database."""
    if db_path is None:
        return None
    from pathlib import Path
    return Path(db_path).parent / ".migrating"


def run_migrations(conn: sqlite3.Connection, db_path=None) -> None:
    """Run all pending migrations in order. Uses advisory lock file to prevent concurrent migration."""
    import time
    lock_path = _migration_lock_path(db_path)
    if lock_path:
        # Wait briefly if another process is migrating
        for _ in range(30):
            if not lock_path.exists():
                break
            time.sleep(0.2)
        if lock_path.exists():
            raise RuntimeError(
                "Another process appears to be running migrations. "
                "Wait for it to finish or remove the .migrating file if it crashed."
            )
        try:
            lock_path.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass

    try:
        _run_migrations_impl(conn)
    finally:
        if lock_path and lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass


def _run_migrations_impl(conn: sqlite3.Connection) -> None:
    """Internal: run migrations without lock."""
    version = get_schema_version(conn)
    if version < 1:
        migrate_1_instruments_status_and_audit_reason(conn)
        set_schema_version(conn, 1)
        version = 1
    if version < 2:
        migrate_2_soft_delete(conn)
        set_schema_version(conn, 2)
        version = 2
    if version < 3:
        migrate_3_record_state(conn)
        set_schema_version(conn, 3)
        version = 3
    if version < 4:
        migrate_4_personnel(conn)
        set_schema_version(conn, 4)
        version = 4
    if version < 5:
        migrate_5_template_tolerance_and_versioning(conn)
        set_schema_version(conn, 5)
        version = 5
    if version < 6:
        migrate_6_add_reference_type(conn)
        set_schema_version(conn, 6)
        version = 6
    if version < 7:
        migrate_7_add_tolerance_type(conn)
        set_schema_version(conn, 7)
