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


def delete_instrument(repo: "CalibrationRepository", instrument_id: int, reason: str | None = None) -> None:
    """Hard-delete instrument. For soft delete use archive_instrument."""
    repo.delete_instrument(instrument_id, reason=reason)


def archive_instrument(
    repo: "CalibrationRepository",
    instrument_id: int,
    deleted_by: str | None = None,
    reason: str | None = None,
) -> None:
    """Soft-delete (archive) instrument."""
    repo.archive_instrument(instrument_id, deleted_by=deleted_by, reason=reason)


def batch_update_instruments(
    repo: "CalibrationRepository",
    instrument_ids: list[int],
    updates: dict,
    reason: str | None = None,
) -> int:
    """Apply the same field updates to multiple instruments. Returns number updated."""
    return repo.batch_update_instruments(instrument_ids, updates, reason=reason)


def mark_calibrated_on(repo: "CalibrationRepository", instrument_id: int, cal_date: str) -> None:
    """Update instrument's last_cal_date and next_due_date based on calibration."""
    repo.mark_calibrated_on(instrument_id, cal_date)
