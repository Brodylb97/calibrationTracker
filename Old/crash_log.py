# crash_log.py

import logging
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "calibration_crash.log"

logger = logging.getLogger("calibration_tracker")
logger.setLevel(logging.INFO)

# Avoid duplicate handlers if this gets imported more than once
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def log_exception(exc_type, exc_value, exc_tb):
    """
    Global exception hook: log uncaught exceptions to file and stderr.
    """
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        logger.error("Uncaught exception:\n%s", tb_str)
    except Exception:
        # Logging should never crash the crash logger
        pass

    # Also echo to real stderr so you see it if running from console
    try:
        sys.__stderr__.write(tb_str)
        sys.__stderr__.flush()
    except Exception:
        pass


def log_current_exception(context: str = ""):
    """
    Helper to log inside a try/except block if you manually catch something fatal.
    """
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None:
        return
    prefix = f"[{context}] " if context else ""
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        logger.error("%sCaught exception:\n%s", prefix, tb_str)
    except Exception:
        pass


def install_global_excepthook():
    """
    Install the global excepthook so any uncaught exception is logged.
    """
    sys.excepthook = log_exception
