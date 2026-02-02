# database.py

import os
import sqlite3
from datetime import date, timedelta, datetime
import json
import hashlib


class CalibrationRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------
    # Schema
    # ------------------------
    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")

        # Instrument types
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instrument_types (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )

        # Destinations (labs / vendors)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS destinations (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL UNIQUE,
                contact TEXT,
                email   TEXT,
                phone   TEXT,
                address TEXT
            )
            """
        )

        # Instruments
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_number        TEXT NOT NULL UNIQUE,
                serial_number     TEXT,
                description       TEXT,
                location          TEXT,
                calibration_type  TEXT NOT NULL DEFAULT 'SEND_OUT'
                                   CHECK (calibration_type IN ('SEND_OUT','PULL_IN')),
                instrument_type_id INTEGER REFERENCES instrument_types(id),
                destination_id    INTEGER REFERENCES destinations(id),
                last_cal_date     TEXT,   -- 'YYYY-MM-DD'
                next_due_date     TEXT,   -- 'YYYY-MM-DD'
                frequency_months  INTEGER NOT NULL DEFAULT 12,
                status            TEXT NOT NULL DEFAULT 'ACTIVE',
                notes             TEXT
            )
            """
        )

        # Instrument-level attachments (BLOB storage)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instrument_attachments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                filename      TEXT NOT NULL,
                file_data     BLOB NOT NULL,
                uploaded_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # Calibration templates
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calibration_templates (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_type_id INTEGER NOT NULL REFERENCES instrument_types(id) ON DELETE CASCADE,
                name              TEXT NOT NULL,
                version           INTEGER NOT NULL DEFAULT 1,
                is_active         INTEGER NOT NULL DEFAULT 1,
                notes             TEXT
            )
            """
        )

        # Template fields
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calibration_template_fields (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL REFERENCES calibration_templates(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                label           TEXT NOT NULL,
                data_type       TEXT NOT NULL DEFAULT 'text',  -- 'text','number','bool','date'
                unit            TEXT,
                required        INTEGER NOT NULL DEFAULT 0,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                group_name      TEXT,
                calc_type       TEXT CHECK (calc_type IN ('ABS_DIFF','PERCENT_ERROR')),
                calc_ref1_name  TEXT,
                calc_ref2_name  TEXT,
                tolerance       REAL
            )
            """
        )

        # Calibration records (template-based or external)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calibration_records (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id      INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                template_id        INTEGER REFERENCES calibration_templates(id),
                cal_date           TEXT NOT NULL, -- 'YYYY-MM-DD'
                performed_by       TEXT,
                result             TEXT,
                notes              TEXT,
                is_external        INTEGER NOT NULL DEFAULT 0,
                external_filename  TEXT,
                external_file_data BLOB
            )
            """
        )

        # Calibration values for template-based records
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calibration_values (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL REFERENCES calibration_records(id) ON DELETE CASCADE,
                field_id  INTEGER NOT NULL REFERENCES calibration_template_fields(id) ON DELETE CASCADE,
                value_text TEXT
            )
            """
        )

        # Simple key-value settings
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # ------------------------
        # LIMS / security tables
        # ------------------------

        # Roles
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )

        # Users
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                full_name     TEXT,
                password_hash TEXT NOT NULL,
                role_id       INTEGER REFERENCES roles(id),
                active        INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        # Audit log
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                user_id     INTEGER REFERENCES users(id),
                action      TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id   INTEGER,
                description TEXT,
                old_values  TEXT,
                new_values  TEXT
            )
            """
        )

        # Clients
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL UNIQUE,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                notes        TEXT
            )
            """
        )

        # Projects
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id    INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                year         INTEGER NOT NULL,
                code         TEXT NOT NULL,
                description  TEXT,
                facility_name TEXT,
                status       TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN / HOLD / CLOSED
                opened_date  TEXT,
                due_date     TEXT,
                closed_date  TEXT,
                notes        TEXT,
                UNIQUE (client_id, code)
            )
            """
        )

        # Basic indexes
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_instruments_next_due ON instruments(next_due_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_cal_records_instrument ON calibration_records(instrument_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_cal_records_date ON calibration_records(cal_date)"
        )

        # Make sure we have at least one admin user
        self._ensure_default_admin()

        self.conn.commit()

    # ------------------------
    # Helpers
    # ------------------------
    @staticmethod
    def _row_to_dict(row):
        return dict(row) if row is not None else None

    @staticmethod
    def _rows_to_list(rows):
        return [dict(r) for r in rows]

    # ------------------------
    # User / auth helpers
    # ------------------------
    def _hash_password(self, password: str) -> str:
        """Simple SHA-256 hash for local auth."""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _ensure_default_admin(self):
        """If no users exist, create admin/admin."""
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM users")
        row = cur.fetchone()
        if row is not None and row["c"] > 0:
            return

        # Ensure Admin role exists
        self.conn.execute(
            "INSERT OR IGNORE INTO roles (name) VALUES (?)",
            ("Admin",),
        )
        role_row = self.conn.execute(
            "SELECT id FROM roles WHERE name = ?",
            ("Admin",),
        ).fetchone()
        role_id = role_row["id"] if role_row else None

        pw_hash = self._hash_password("admin")
        self.conn.execute(
            """
            INSERT INTO users (username, full_name, password_hash, role_id, active)
            VALUES (?,?,?,?,1)
            """,
            ("admin", "Default Admin", pw_hash, role_id),
        )
        self.conn.commit()

    def validate_login(self, username: str, password: str):
        """
        Return user dict if credentials are valid, else None.
        Not wired into UI yet, but ready.
        """
        cur = self.conn.execute(
            """
            SELECT u.*, r.name AS role_name
            FROM users u
            LEFT JOIN roles r ON r.id = u.role_id
            WHERE u.username = ? AND u.active = 1
            """,
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return None
        if row["password_hash"] != self._hash_password(password):
            return None
        return dict(row)

    # ------------------------
    # Audit log
    # ------------------------
    def add_audit_entry(
        self,
        user_id,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        description: str = "",
        old_values=None,
        new_values=None,
    ):
        """
        Generic audit entry helper.
        old_values/new_values can be dicts; they are stored as JSON.
        """
        ts = datetime.utcnow().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO audit_log
            (timestamp, user_id, action, entity_type, entity_id,
             description, old_values, new_values)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                ts,
                user_id,
                action,
                entity_type,
                entity_id,
                description,
                json.dumps(old_values) if old_values is not None else None,
                json.dumps(new_values) if new_values is not None else None,
            ),
        )
        self.conn.commit()

    # ------------------------
    # Settings
    # ------------------------
    def get_setting(self, key: str, default=None):
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ------------------------
    # Instrument types
    # ------------------------
    def list_instrument_types(self):
        cur = self.conn.execute("SELECT id, name FROM instrument_types ORDER BY name")
        return self._rows_to_list(cur.fetchall())

    def get_instrument_type(self, type_id: int):
        cur = self.conn.execute(
            "SELECT id, name FROM instrument_types WHERE id = ?", (type_id,)
        )
        return self._row_to_dict(cur.fetchone())

    # ------------------------
    # Destinations
    # ------------------------
    def list_destinations(self):
        cur = self.conn.execute("SELECT id, name FROM destinations ORDER BY name")
        return self._rows_to_list(cur.fetchall())

    def list_destinations_full(self):
        cur = self.conn.execute(
            "SELECT id, name, contact, email, phone, address "
            "FROM destinations ORDER BY name"
        )
        return self._rows_to_list(cur.fetchall())

    def add_destination(self, name, contact, email, phone, address):
        self.conn.execute(
            """
            INSERT INTO destinations(name, contact, email, phone, address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, contact, email, phone, address),
        )
        self.conn.commit()

    def update_destination(self, dest_id: int, data: dict):
        self.conn.execute(
            """
            UPDATE destinations
            SET name = ?, contact = ?, email = ?, phone = ?, address = ?
            WHERE id = ?
            """,
            (
                data.get("name"),
                data.get("contact"),
                data.get("email"),
                data.get("phone"),
                data.get("address"),
                dest_id,
            ),
        )
        self.conn.commit()

    def delete_destination(self, dest_id: int):
        self.conn.execute("DELETE FROM destinations WHERE id = ?", (dest_id,))
        self.conn.commit()

    def get_destination_name(self, dest_id: int | None):
        if not dest_id:
            return None
        cur = self.conn.execute(
            "SELECT name FROM destinations WHERE id = ?", (dest_id,)
        )
        row = cur.fetchone()
        return row["name"] if row else None

    # ------------------------
    # Instruments
    # ------------------------
    def list_instruments(self):
        cur = self.conn.execute(
            """
            SELECT i.*,
                   it.name AS instrument_type_name,
                   d.name  AS destination_name
            FROM instruments i
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            LEFT JOIN destinations d     ON i.destination_id = d.id
            ORDER BY i.tag_number
            """
        )
        return self._rows_to_list(cur.fetchall())

    def get_instrument(self, inst_id: int):
        cur = self.conn.execute(
            """
            SELECT i.*,
                   it.name AS instrument_type_name,
                   d.name  AS destination_name
            FROM instruments i
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            LEFT JOIN destinations d     ON i.destination_id = d.id
            WHERE i.id = ?
            """,
            (inst_id,),
        )
        return self._row_to_dict(cur.fetchone())

    def add_instrument(self, data: dict):
        self.conn.execute(
            """
            INSERT INTO instruments(
                tag_number, serial_number, description,
                location, calibration_type, instrument_type_id,
                destination_id, last_cal_date, next_due_date,
                frequency_months, status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("tag_number"),
                data.get("serial_number") or "",
                data.get("description") or "",
                data.get("location"),
                data.get("calibration_type", "SEND_OUT"),
                data.get("instrument_type_id"),
                data.get("destination_id"),
                data.get("last_cal_date"),
                data.get("next_due_date"),
                data.get("frequency_months", 12),
                data.get("status", "ACTIVE"),
                data.get("notes"),
            ),
        )
        self.conn.commit()

    def update_instrument(self, inst_id: int, data: dict):
        self.conn.execute(
            """
            UPDATE instruments SET
                tag_number        = ?,
                serial_number     = ?,
                description       = ?,
                location          = ?,
                calibration_type  = ?,
                instrument_type_id = ?,
                destination_id    = ?,
                last_cal_date     = ?,
                next_due_date     = ?,
                frequency_months  = ?,
                status            = ?,
                notes             = ?
            WHERE id = ?
            """,
            (
                data.get("tag_number"),
                data.get("serial_number") or "",
                data.get("description") or "",
                data.get("location"),
                data.get("calibration_type", "SEND_OUT"),
                data.get("instrument_type_id"),
                data.get("destination_id"),
                data.get("last_cal_date"),
                data.get("next_due_date"),
                data.get("frequency_months", 12),
                data.get("status", "ACTIVE"),
                data.get("notes"),
                inst_id,
            ),
        )
        self.conn.commit()

    def delete_instrument(self, inst_id: int):
        self.conn.execute("DELETE FROM instruments WHERE id = ?", (inst_id,))
        self.conn.commit()

    def mark_calibrated_on(self, inst_id: int, cal_date: date):
        """
        Set last_cal_date to cal_date, next_due_date to +12 months (approx).
        """
        last_str = cal_date.isoformat()
        # Simple "add 12 months" by year+1
        try:
            next_date = cal_date.replace(year=cal_date.year + 1)
        except ValueError:
            # 2/29 etc -> clamp to 2/28 next year
            next_date = cal_date + timedelta(days=365)
        next_str = next_date.isoformat()

        self.conn.execute(
            """
            UPDATE instruments
            SET last_cal_date = ?, next_due_date = ?
            WHERE id = ?
            """,
            (last_str, next_str, inst_id),
        )
        self.conn.commit()

    def list_instruments_due_within(self, days: int):
        """
        Helper for LAN reminders: return instruments whose next_due_date
        is between today and today+days (inclusive).
        """
        today = date.today()
        end = today + timedelta(days=days)
        cur = self.conn.execute(
            """
            SELECT i.*,
                   it.name AS instrument_type_name,
                   d.name  AS destination_name
            FROM instruments i
            LEFT JOIN instrument_types it ON i.instrument_type_id = it.id
            LEFT JOIN destinations d     ON i.destination_id = d.id
            WHERE next_due_date IS NOT NULL
              AND next_due_date >= ?
              AND next_due_date <= ?
            ORDER BY next_due_date, tag_number
            """,
            (today.isoformat(), end.isoformat()),
        )
        return self._rows_to_list(cur.fetchall())

    # ------------------------
    # Instrument attachments (BLOB)
    # ------------------------
    def list_attachments(self, instrument_id: int):
        cur = self.conn.execute(
            """
            SELECT id, filename, uploaded_at
            FROM instrument_attachments
            WHERE instrument_id = ?
            ORDER BY uploaded_at DESC, id DESC
            """,
            (instrument_id,),
        )
        return self._rows_to_list(cur.fetchall())

    def add_attachment(self, instrument_id: int, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        with open(path, "rb") as f:
            data = f.read()
        filename = os.path.basename(path)
        self.conn.execute(
            """
            INSERT INTO instrument_attachments (instrument_id, filename, file_data)
            VALUES (?, ?, ?)
            """,
            (instrument_id, filename, sqlite3.Binary(data)),
        )
        self.conn.commit()

    def get_attachment_file(self, attachment_id: int):
        cur = self.conn.execute(
            """
            SELECT filename, file_data
            FROM instrument_attachments
            WHERE id = ?
            """,
            (attachment_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"filename": row["filename"], "data": row["file_data"]}

    # ------------------------
    # Templates
    # ------------------------
    def list_templates_for_type(self, instrument_type_id: int, active_only: bool = False):
        sql = """
            SELECT id, instrument_type_id, name, version, is_active, notes
            FROM calibration_templates
            WHERE instrument_type_id = ?
        """
        params = [instrument_type_id]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY name, version"
        cur = self.conn.execute(sql, params)
        return self._rows_to_list(cur.fetchall())

    def create_template(self, instrument_type_id: int, name: str,
                        version: int, is_active: bool, notes: str | None):
        self.conn.execute(
            """
            INSERT INTO calibration_templates(
                instrument_type_id, name, version, is_active, notes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (instrument_type_id, name, version, 1 if is_active else 0, notes),
        )
        self.conn.commit()

    def get_template(self, template_id: int):
        cur = self.conn.execute(
            """
            SELECT id, instrument_type_id, name, version, is_active, notes
            FROM calibration_templates
            WHERE id = ?
            """,
            (template_id,),
        )
        return self._row_to_dict(cur.fetchone())

    def update_template(self, template_id: int, name: str,
                        version: int, is_active: bool, notes: str | None):
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
        # Will fail if FK constraints are violated (existing records)
        self.conn.execute(
            "DELETE FROM calibration_templates WHERE id = ?", (template_id,)
        )
        self.conn.commit()

    # ------------------------
    # Template fields
    # ------------------------
    def list_template_fields(self, template_id: int):
        cur = self.conn.execute(
            """
            SELECT *
            FROM calibration_template_fields
            WHERE template_id = ?
            ORDER BY sort_order, id
            """,
            (template_id,),
        )
        return self._rows_to_list(cur.fetchall())

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
        calc_type: str | None,
        calc_ref1_name: str | None,
        calc_ref2_name: str | None,
        tolerance: float | None,
    ):
        self.conn.execute(
            """
            INSERT INTO calibration_template_fields(
                template_id, name, label, data_type, unit,
                required, sort_order, group_name,
                calc_type, calc_ref1_name, calc_ref2_name, tolerance
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self.conn.commit()

    def update_template_field(self, field_id: int, data: dict):
        self.conn.execute(
            """
            UPDATE calibration_template_fields
            SET name = ?, label = ?, data_type = ?, unit = ?,
                required = ?, sort_order = ?, group_name = ?,
                calc_type = ?, calc_ref1_name = ?, calc_ref2_name = ?, tolerance = ?
            WHERE id = ?
            """,
            (
                data.get("name"),
                data.get("label"),
                data.get("data_type"),
                data.get("unit"),
                1 if data.get("required") else 0,
                data.get("sort_order", 0),
                data.get("group_name"),
                data.get("calc_type"),
                data.get("calc_ref1_name"),
                data.get("calc_ref2_name"),
                data.get("tolerance"),
                field_id,
            ),
        )
        self.conn.commit()

    def delete_template_field(self, field_id: int):
        self.conn.execute(
            "DELETE FROM calibration_template_fields WHERE id = ?",
            (field_id,),
        )
        self.conn.commit()

    # ------------------------
    # Calibration records
    # ------------------------
    def list_calibration_records_for_instrument(self, instrument_id: int):
        cur = self.conn.execute(
            """
            SELECT
                cr.id,
                cr.instrument_id,
                cr.template_id,
                cr.cal_date,
                cr.performed_by,
                cr.result,
                cr.notes,
                cr.is_external,
                cr.external_filename,
                ct.name AS template_name
            FROM calibration_records cr
            LEFT JOIN calibration_templates ct ON cr.template_id = ct.id
            WHERE cr.instrument_id = ?
            ORDER BY cr.cal_date DESC, cr.id DESC
            """,
            (instrument_id,),
        )
        rows = self._rows_to_list(cur.fetchall())
        # Normalize template_name for external records
        for r in rows:
            if r.get("is_external"):
                fname = r.get("external_filename") or ""
                if fname:
                    r["template_name"] = f"[External] {fname}"
                else:
                    r["template_name"] = "[External]"
        return rows

    def get_calibration_record_with_template(self, record_id: int):
        cur = self.conn.execute(
            """
            SELECT
                cr.*,
                ct.name    AS template_name,
                ct.version AS template_version
            FROM calibration_records cr
            LEFT JOIN calibration_templates ct ON cr.template_id = ct.id
            WHERE cr.id = ?
            """,
            (record_id,),
        )
        return self._row_to_dict(cur.fetchone())

    def create_calibration_record(
        self,
        instrument_id: int,
        template_id: int,
        cal_date: str,
        performed_by: str | None,
        result: str | None,
        notes: str | None,
        field_values: dict[int, str],
    ):
        """
        Template-based record.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO calibration_records(
                instrument_id, template_id, cal_date,
                performed_by, result, notes, is_external
            )
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (instrument_id, template_id, cal_date, performed_by, result, notes),
        )
        record_id = cur.lastrowid

        # Insert values
        for field_id, value in field_values.items():
            cur.execute(
                """
                INSERT INTO calibration_values(record_id, field_id, value_text)
                VALUES (?, ?, ?)
                """,
                (record_id, field_id, value),
            )

        self.conn.commit()
        return record_id

    def update_calibration_record(
        self,
        record_id: int,
        cal_date: str,
        performed_by: str | None,
        result: str | None,
        notes: str | None,
        field_values: dict[int, str],
    ):
        """
        Update template-based record & its values.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE calibration_records
            SET cal_date = ?, performed_by = ?, result = ?, notes = ?
            WHERE id = ? AND is_external = 0
            """,
            (cal_date, performed_by, result, notes, record_id),
        )

        # Replace values
        cur.execute("DELETE FROM calibration_values WHERE record_id = ?", (record_id,))
        for field_id, value in field_values.items():
            cur.execute(
                """
                INSERT INTO calibration_values(record_id, field_id, value_text)
                VALUES (?, ?, ?)
                """,
                (record_id, field_id, value),
            )

        self.conn.commit()

    def delete_calibration_record(self, record_id: int):
        self.conn.execute("DELETE FROM calibration_records WHERE id = ?", (record_id,))
        self.conn.commit()

    def get_calibration_values(self, record_id: int):
        """
        Return values joined with field metadata for display & calcs.
        """
        cur = self.conn.execute(
            """
            SELECT
                cv.id,
                cv.record_id,
                cv.field_id,
                cv.value_text,
                f.name        AS field_name,
                f.label       AS label,
                f.data_type   AS data_type,
                f.unit        AS unit,
                f.group_name  AS group_name,
                f.calc_type   AS calc_type,
                f.calc_ref1_name AS calc_ref1_name,
                f.calc_ref2_name AS calc_ref2_name,
                f.tolerance   AS tolerance
            FROM calibration_values cv
            JOIN calibration_template_fields f ON cv.field_id = f.id
            WHERE cv.record_id = ?
            ORDER BY f.sort_order, f.id
            """,
            (record_id,),
        )
        return self._rows_to_list(cur.fetchall())

    # ------------------------
    # External calibration records (file-based)
    # ------------------------
    def create_external_calibration_record(
        self,
        instrument_id: int,
        cal_date: str,
        performed_by: str | None,
        result: str | None,
        notes: str | None,
        filename: str,
        file_data: bytes,
    ):
        self.conn.execute(
            """
            INSERT INTO calibration_records(
                instrument_id, template_id, cal_date,
                performed_by, result, notes,
                is_external, external_filename, external_file_data
            )
            VALUES (?, NULL, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                instrument_id,
                cal_date,
                performed_by,
                result,
                notes,
                filename,
                sqlite3.Binary(file_data),
            ),
        )
        self.conn.commit()

    def get_calibration_file(self, record_id: int):
        cur = self.conn.execute(
            """
            SELECT external_filename, external_file_data, is_external
            FROM calibration_records
            WHERE id = ?
            """,
            (record_id,),
        )
        row = cur.fetchone()
        if not row or not row["is_external"]:
            return None
        if row["external_file_data"] is None:
            return None
        return {
            "filename": row["external_filename"],
            "data": row["external_file_data"],
        }

    # ------------------------
    # Clients & Projects
    # ------------------------
    def list_clients(self):
        cur = self.conn.execute(
            """
            SELECT *
            FROM clients
            ORDER BY name COLLATE NOCASE
            """
        )
        return self._rows_to_list(cur.fetchall())

    def get_client(self, client_id: int):
        cur = self.conn.execute(
            "SELECT * FROM clients WHERE id = ?",
            (client_id,),
        )
        return self._row_to_dict(cur.fetchone())

    def add_client(self, data: dict) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO clients
                (name, contact_name, contact_email, contact_phone, notes)
            VALUES (?,?,?,?,?)
            """,
            (
                data["name"],
                data.get("contact_name"),
                data.get("contact_email"),
                data.get("contact_phone"),
                data.get("notes"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_client(self, client_id: int, data: dict):
        self.conn.execute(
            """
            UPDATE clients
            SET
                name = ?,
                contact_name = ?,
                contact_email = ?,
                contact_phone = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data.get("contact_name"),
                data.get("contact_email"),
                data.get("contact_phone"),
                data.get("notes"),
                client_id,
            ),
        )
        self.conn.commit()

    def delete_client(self, client_id: int):
        self.conn.execute(
            "DELETE FROM clients WHERE id = ?",
            (client_id,),
        )
        self.conn.commit()

    def list_projects_for_client(self, client_id: int):
        cur = self.conn.execute(
            """
            SELECT *
            FROM projects
            WHERE client_id = ?
            ORDER BY year DESC, code COLLATE NOCASE
            """,
            (client_id,),
        )
        return self._rows_to_list(cur.fetchall())

    def get_project(self, project_id: int):
        cur = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        )
        return self._row_to_dict(cur.fetchone())

    def add_project(self, data: dict) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO projects
                (client_id, year, code, description, facility_name,
                 status, opened_date, due_date, closed_date, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["client_id"],
                data["year"],
                data["code"],
                data.get("description"),
                data.get("facility_name"),
                data.get("status", "OPEN"),
                data.get("opened_date"),
                data.get("due_date"),
                data.get("closed_date"),
                data.get("notes"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_project(self, project_id: int, data: dict):
        self.conn.execute(
            """
            UPDATE projects
            SET
                year = ?,
                code = ?,
                description = ?,
                facility_name = ?,
                status = ?,
                opened_date = ?,
                due_date = ?,
                closed_date = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                data["year"],
                data["code"],
                data.get("description"),
                data.get("facility_name"),
                data.get("status", "OPEN"),
                data.get("opened_date"),
                data.get("due_date"),
                data.get("closed_date"),
                data.get("notes"),
                project_id,
            ),
        )
        self.conn.commit()

    def delete_project(self, project_id: int):
        self.conn.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,),
        )
        self.conn.commit()

    # ------------------------
    # Close
    # ------------------------
    def close(self):
        self.conn.close()
