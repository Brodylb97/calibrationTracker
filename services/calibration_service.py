# services/calibration_service.py - Calibration record persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (conflict detection, revisioning) without changing UI.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def create_calibration_record(
    repo: "CalibrationRepository",
    instrument_id: int,
    template_id: int,
    cal_date: str,
    performed_by: str,
    result: str,
    notes: str,
    field_values: dict[int, str],
    template_version: int | None = None,
) -> int:
    """Validate and create calibration record. Returns new record ID. Raises ValueError on invalid input."""
    if not (cal_date or "").strip():
        raise ValueError("Cal date is required")
    return repo.create_calibration_record(
        instrument_id, template_id, cal_date, performed_by, result, notes,
        field_values, template_version=template_version,
    )


def update_calibration_record(
    repo: "CalibrationRepository",
    record_id: int,
    cal_date: str,
    performed_by: str,
    result: str,
    notes: str,
    field_values: dict[int, str],
    expected_updated_at: str | None = None,
) -> None:
    """
    Validate and update calibration record.
    Raises ValueError on invalid input, StaleDataError if record was modified elsewhere.
    """
    if not (cal_date or "").strip():
        raise ValueError("Cal date is required")
    repo.update_calibration_record(
        record_id, cal_date, performed_by, result, notes, field_values,
        expected_updated_at=expected_updated_at,
    )
