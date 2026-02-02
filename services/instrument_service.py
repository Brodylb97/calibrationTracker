# services/instrument_service.py - Instrument persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (conflict detection, audit enrichment) without changing UI.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def add_instrument(repo: "CalibrationRepository", data: dict) -> int:
    """Validate and add instrument. Returns new instrument ID. Raises ValueError on invalid input."""
    tag = (data.get("tag_number") or "").strip()
    if not tag:
        raise ValueError("ID is required")
    return repo.add_instrument(data)


def update_instrument(repo: "CalibrationRepository", instrument_id: int, data: dict) -> None:
    """
    Validate and update instrument.
    Raises ValueError on invalid input, StaleDataError if record was modified elsewhere.
    """
    tag = (data.get("tag_number") or "").strip()
    if not tag:
        raise ValueError("ID is required")
    repo.update_instrument(instrument_id, data)
