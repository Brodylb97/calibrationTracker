# config.py - Runtime configuration (DB path, app base dir)
#
# Single place for loading configuration. Persistence (database.py) imports
# from here instead of defining config logic itself.

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Environment variable to override database path directly (highest priority)
DB_PATH_ENV = "CALIBRATION_TRACKER_DB_PATH"

# Default DB path when no config is set (shared network location)
DEFAULT_SERVER_DB_PATH = Path(
    r"Z:\Shared\Laboratory\Particulate Matter and Other Results\Brody's Project Junk\Cal Tracker Current\calibration.db"
)


def get_app_base_dir() -> Path:
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
        return True
    base = get_app_base_dir().resolve()
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


def load_db_path() -> Path:
    """
    Load database path from configuration.
    Order: DB_PATH_ENV > config.json > update_config.json > DEFAULT_SERVER_DB_PATH.
    Paths under the app directory or current directory are rejected; only the server path is used.
    """
    def _reject_local_and_return(path: Path) -> Path:
        if _is_local_directory_path(path):
            logger.warning(
                "Database path is in application or current directory (local copy). "
                "Using server path only: %s",
                DEFAULT_SERVER_DB_PATH,
            )
            return DEFAULT_SERVER_DB_PATH
        return path

    base = get_app_base_dir()
    # 1. Environment variable (highest priority)
    env_path = os.environ.get(DB_PATH_ENV)
    if env_path and env_path.strip():
        return _reject_local_and_return(Path(env_path.strip()).resolve())

    # 2. config.json then update_config.json
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

    return DEFAULT_SERVER_DB_PATH
