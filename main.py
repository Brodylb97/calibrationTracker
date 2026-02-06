# main.py

import argparse
import os
import sys
import sqlite3
from pathlib import Path

from database import (
    get_connection,
    initialize_db,
    run_integrity_check,
    DB_PATH,
    CalibrationRepository,
    get_effective_db_path,
    get_persisted_last_db_path,
    persist_last_db_path,
    is_server_db_path,
)
from ui_main import run_gui
from crash_log import install_global_excepthook, logger, log_current_exception
from lan_notify import send_due_reminders_via_lan


def _crash_flag_path() -> Path:
    """Path to crash flag file (previous run may have ended unexpectedly)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "CalibrationTracker" / "crash_flag.txt"


def _crash_flag_exists() -> bool:
    p = _crash_flag_path()
    return p.is_file()


def _crash_flag_write() -> None:
    from file_utils import atomic_write_text
    p = _crash_flag_path()
    try:
        atomic_write_text(p, "1")
    except Exception as e:
        logger.warning("Failed to write crash flag to %s: %s", p, e)


def _crash_flag_remove() -> None:
    p = _crash_flag_path()
    try:
        if p.is_file():
            p.unlink()
    except Exception as e:
        logger.warning("Failed to remove crash flag %s: %s", p, e)


def _show_crash_recovery_dialog(db_path: Path) -> None:
    """Offer to run integrity check or open backup folder after possible crash."""
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    box = QMessageBox()
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Previous run may have ended unexpectedly")
    box.setText(
        "The application did not close normally last time. "
        "You may want to run an integrity check on the database or restore from a backup."
    )
    box.setInformativeText(f"Database: {db_path}\nBackups: {db_path.parent / 'backups'}")
    box.addButton("OK", QMessageBox.AcceptRole)
    box.exec_()


def _is_readonly_db_error(exc: BaseException) -> bool:
    err = str(exc).lower()
    return "readonly" in err or "attempt to write" in err


def _show_readonly_dialog(message: str) -> bool:
    """Show dialog for read-only database. Returns True to try again, False to close."""
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    box = QMessageBox()
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Database read-only")
    box.setText("The application cannot connect to the database on the server because it is read-only.")
    box.setInformativeText(
        message + "\n\nFix the server or share permissions, then click Try Again."
    )
    try_again = box.addButton("Try Again", QMessageBox.AcceptRole)
    close_btn = box.addButton("Close", QMessageBox.RejectRole)
    box.exec_()
    return box.clickedButton() == try_again


def main():
    # Install global hook so any uncaught exception is logged
    install_global_excepthook()

    parser = argparse.ArgumentParser(
        description="Calibration Tracker (GUI + LAN reminder mode)"
    )
    parser.add_argument(
        "--send-reminders",
        action="store_true",
        help="Run in headless mode and send LAN reminders, then exit.",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to server SQLite database (only the server path is accepted; no local copies)",
    )
    args = parser.parse_args()
    # Only the server database is allowed; no local copies.
    persisted = get_persisted_last_db_path()
    db_path = None
    if args.db:
        p = Path(args.db)
        if is_server_db_path(p):
            db_path = p
        else:
            logger.warning("Ignoring --db (not server path): %s. Using server database only.", args.db)
    if db_path is None:
        db_path = (persisted if is_server_db_path(persisted) else None) or DB_PATH

    # Log startup info
    logger.info("Program start. args=%s db=%s", sys.argv, db_path)

    try:
        while True:
            try:
                conn = get_connection(db_path)
                conn = initialize_db(conn, db_path)
                # Integrity check: fail fast if database is corrupt
                integrity_err = run_integrity_check(conn)
                if integrity_err:
                    logger.error("Database integrity check failed: %s", integrity_err)
                    try:
                        from PyQt5.QtWidgets import QApplication, QMessageBox
                        app = QApplication.instance()
                        if app is None:
                            app = QApplication(sys.argv)
                        QMessageBox.critical(
                            None,
                            "Database integrity check failed",
                            f"The database integrity check failed:\n\n{integrity_err}\n\n"
                            f"Restore from backup or contact support.\n\n"
                            f"Database: {db_path}\nBackups: {db_path.parent / 'backups'}",
                        )
                    except Exception:
                        print(f"Database integrity check failed: {integrity_err}", file=sys.stderr)
                    sys.exit(1)
                break
            except sqlite3.OperationalError as e:
                err_lower = str(e).lower()
                if "unable to open database file" in err_lower:
                    logger.error("Database file not openable: %s", e)
                    try:
                        from PyQt5.QtWidgets import QApplication, QMessageBox
                        app = QApplication.instance()
                        if app is None:
                            app = QApplication(sys.argv)
                        QMessageBox.critical(
                            None,
                            "Cannot open database",
                            str(e) + "\n\nExiting.",
                        )
                    except Exception:
                        print(str(e), file=sys.stderr)
                    sys.exit(1)
                if not _is_readonly_db_error(e):
                    raise
                logger.warning("Database read-only: %s", e)
                if not _show_readonly_dialog(str(e)):
                    sys.exit(0)
                # User chose Try Again; loop continues

        # Only persist when using the server path, so we never write Program Files or other local paths.
        if is_server_db_path(get_effective_db_path()):
            persist_last_db_path(get_effective_db_path())
        repo = CalibrationRepository(conn)

        # Crash detection: if flag exists, previous run may have ended unexpectedly
        if _crash_flag_exists():
            _show_crash_recovery_dialog(get_effective_db_path())
        _crash_flag_write()

        if args.send_reminders:
            logger.info("Running in headless mode: send LAN reminders")
            count = send_due_reminders_via_lan(repo)
            msg = (
                f"LAN reminders broadcast for {count} instrument(s)."
                if count
                else "No reminders."
            )
            print(msg)
            logger.info(msg)
            try:
                conn.close()
            except Exception:
                pass
            _crash_flag_remove()
        else:
            logger.info("Starting GUI mode")
            run_gui(repo)
            try:
                conn.close()
            except Exception:
                pass
            _crash_flag_remove()

        logger.info("Program exit normally")

    except RuntimeError as e:
        err_msg = str(e).lower()
        if "migration" in err_msg or "schema" in err_msg:
            log_current_exception("Migration/schema error in main()")
            try:
                from PyQt5.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance()
                if app is None:
                    app = QApplication(sys.argv)
                QMessageBox.critical(
                    None,
                    "Database schema error",
                    str(e) + "\n\nExiting.",
                )
            except Exception:
                print(str(e), file=sys.stderr)
            sys.exit(1)
        raise
    except Exception:
        # This catches top-level failures during startup / shutdown
        log_current_exception("Fatal error in main()")
        # Let global excepthook also handle it (prints to stderr and logs again)
        raise


if __name__ == "__main__":
    main()
