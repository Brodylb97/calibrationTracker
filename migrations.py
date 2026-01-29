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


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending migrations in order."""
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
