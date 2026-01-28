# main.py

import argparse
import sys
import sqlite3
from pathlib import Path

from database import (
    get_connection,
    initialize_db,
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
        help="Path to server SQLite database (default: last used, or server path)",
    )

    args = parser.parse_args()
    # Only use server database: ignore persisted path unless it is the server path (avoids Program Files from old fallback).
    persisted = get_persisted_last_db_path()
    db_path = Path(args.db) if args.db else (persisted if is_server_db_path(persisted) else None) or DB_PATH

    # Log startup info
    logger.info("Program start. args=%s db=%s", sys.argv, db_path)

    try:
        while True:
            try:
                conn = get_connection(db_path)
                conn = initialize_db(conn, db_path)
                break
            except sqlite3.OperationalError as e:
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
        else:
            logger.info("Starting GUI mode")
            run_gui(repo)

        logger.info("Program exit normally")

    except Exception:
        # This catches top-level failures during startup / shutdown
        log_current_exception("Fatal error in main()")
        # Let global excepthook also handle it (prints to stderr and logs again)
        raise


if __name__ == "__main__":
    main()
