# services/settings_service.py - Settings persistence orchestration
#
# Thin layer: delegates to repository.
# Enables future hooks (validation, audit) without changing UI.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def set_setting(repo: "CalibrationRepository", key: str, value: str) -> None:
    """Set a key-value setting. Delegates to repository."""
    repo.set_setting(key, value)
