# ui/theme/storage.py - Persistence for custom themes

import json
import logging
import os
from pathlib import Path

from file_utils import atomic_write_text
from ui.theme.core import BUILT_IN_THEME_NAMES, validate_theme_colors


def _themes_config_path() -> Path:
    """Path to themes.json in user config (APPDATA/CalibrationTracker or ~/.config/CalibrationTracker)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", "")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    else:
        base = str(Path.home() / ".config")
    return Path(base) / "CalibrationTracker" / "themes.json"


def load_custom_themes() -> dict[str, dict]:
    """
    Load custom themes from themes.json.
    Returns dict name -> colors (only validated themes; invalid ones are skipped with a log).
    """
    path = _themes_config_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        logging.getLogger(__name__).warning("Failed to load themes from %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    themes_container = data.get("themes")
    if not isinstance(themes_container, dict):
        return {}
    result = {}
    for name, entry in themes_container.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if name in BUILT_IN_THEME_NAMES:
            continue
        colors = _extract_colors(entry)
        if colors is None:
            continue
        valid, err = validate_theme_colors(colors)
        if not valid:
            logging.getLogger(__name__).warning("Skipping invalid theme %r: %s", name, err)
            continue
        result[name.strip()] = colors
    return result


def _extract_colors(entry: object) -> dict | None:
    """Extract colors dict from a theme entry (either {colors: {...}} or plain {...})."""
    if isinstance(entry, dict):
        if "colors" in entry and isinstance(entry["colors"], dict):
            return dict(entry["colors"])
        if all(k in entry for k in ("WINDOW_COLOR", "TEXT_COLOR", "HIGHLIGHT")):
            return dict(entry)
    return None


def save_custom_themes(themes: dict[str, dict]) -> bool:
    """
    Persist custom themes to themes.json.
    Only saves themes not in BUILT_IN_THEME_NAMES.
    Returns True on success.
    """
    path = _themes_config_path()
    filtered = {
        name: {"colors": colors}
        for name, colors in themes.items()
        if name not in BUILT_IN_THEME_NAMES
        and isinstance(name, str)
        and name.strip()
        and isinstance(colors, dict)
    }
    data = {"version": 1, "themes": filtered}
    try:
        atomic_write_text(path, json.dumps(data, indent=2))
        return True
    except OSError as e:
        logging.getLogger(__name__).error("Failed to save themes to %s: %s", path, e)
        return False


def add_custom_theme(name: str, colors: dict) -> bool:
    """Add or update a custom theme. Returns True on success."""
    valid, _ = validate_theme_colors(colors)
    if not valid:
        return False
    if name in BUILT_IN_THEME_NAMES:
        return False
    current = load_custom_themes()
    current[name.strip()] = colors
    return save_custom_themes(current)


def update_custom_theme(name: str, colors: dict) -> bool:
    """Update an existing custom theme. Returns True on success."""
    return add_custom_theme(name, colors)


def delete_custom_theme(name: str) -> bool:
    """Remove a custom theme. Returns True if deleted (or did not exist)."""
    if name in BUILT_IN_THEME_NAMES:
        return False
    current = load_custom_themes()
    if name not in current:
        return True
    del current[name]
    return save_custom_themes(current)
