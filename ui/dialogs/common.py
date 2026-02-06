# ui/dialogs/common.py - Shared constants and helpers for dialogs

STANDARD_FIELD_WIDTH = 280


def parse_float_optional(s: str):
    """Return float(s) or None if s is blank or invalid."""
    if not (s or "").strip():
        return None
    try:
        return float(str(s).strip())
    except ValueError:
        return None
