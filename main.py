# main.py

import argparse
import sys
from pathlib import Path

from database import (
    get_connection,
    initialize_db,
    DB_PATH,
    CalibrationRepository,
    get_effective_db_path,
    get_persisted_last_db_path,
    persist_last_db_path,
)
from ui_main import run_gui
from crash_log import install_global_excepthook, logger, log_current_exception
from lan_notify import send_due_reminders_via_lan


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
        help="Path to SQLite database (default: last used, or server path)",
    )

    args = parser.parse_args()
    db_path = Path(args.db) if args.db else (get_persisted_last_db_path() or DB_PATH)

    # Log startup info
    logger.info("Program start. args=%s db=%s", sys.argv, db_path)

    try:
        conn = get_connection(db_path)
        persist_last_db_path(get_effective_db_path())  # so manual start after update uses same DB
        conn = initialize_db(conn, db_path)  # may fall back to local if network DB is read-only
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
