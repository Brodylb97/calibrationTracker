"""
Integration tests for database migrations.
Run with: python test_migrations.py
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

# Import migrations after we have a clean conn
from migrations import (
    get_schema_version,
    set_schema_version,
    migrate_6_add_reference_type,
)


class TestMigration6(unittest.TestCase):
    """Test that migrate_6_add_reference_type adds 'reference' to data_type CHECK."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def _create_old_schema(self, conn):
        """Create calibration_template_fields with old CHECK (no 'reference')."""
        conn.execute("""
            CREATE TABLE calibration_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_type_id INTEGER,
                name TEXT,
                version INTEGER,
                is_active INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO calibration_templates (instrument_type_id, name, version, is_active)
            VALUES (1, 'Test', 1, 1)
        """)
        conn.execute("""
            CREATE TABLE calibration_template_fields (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL,
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
                calc_ref3_name  TEXT,
                calc_ref4_name  TEXT,
                calc_ref5_name  TEXT,
                tolerance       REAL,
                autofill_from_first_group INTEGER NOT NULL DEFAULT 0,
                default_value   TEXT,
                tolerance_type  TEXT,
                tolerance_equation TEXT,
                nominal_value   TEXT,
                tolerance_lookup_json TEXT,
                FOREIGN KEY (template_id) REFERENCES calibration_templates(id)
            )
        """)
        conn.execute("""
            CREATE INDEX idx_template_fields_template_id ON calibration_template_fields(template_id)
        """)
        conn.execute("""
            CREATE INDEX idx_template_fields_sort_order ON calibration_template_fields(template_id, sort_order)
        """)
        conn.execute(
            "INSERT INTO calibration_template_fields (template_id, name, label, data_type, required, sort_order) VALUES (1, 'f1', 'Field 1', 'number', 1, 0)"
        )
        conn.commit()

    def test_migrate_6_preserves_data_and_adds_reference_type(self):
        conn = sqlite3.connect(str(self.path))
        try:
            self._create_old_schema(conn)
            set_schema_version(conn, 5)

            cur = conn.execute("SELECT id, name, data_type FROM calibration_template_fields")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][2], "number")

            # Old schema rejects 'reference'
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO calibration_template_fields (template_id, name, label, data_type, required, sort_order) VALUES (1, 'ref', 'Ref', 'reference', 0, 1)"
                )
                conn.commit()

            migrate_6_add_reference_type(conn)

            # Original row preserved
            cur = conn.execute("SELECT id, name, data_type FROM calibration_template_fields")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][2], "number")

            # Can insert 'reference' type
            conn.execute(
                "INSERT INTO calibration_template_fields (template_id, name, label, data_type, required, sort_order) VALUES (1, 'ref', 'Ref', 'reference', 0, 1)"
            )
            conn.commit()

            cur = conn.execute("SELECT data_type FROM calibration_template_fields WHERE name = 'ref'")
            row = cur.fetchone()
            self.assertEqual(row[0], "reference")
        finally:
            conn.close()
