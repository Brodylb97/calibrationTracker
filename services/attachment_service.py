# services/attachment_service.py - Attachment persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (audit, size limits) without changing UI.

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def add_attachment(
    repo: "CalibrationRepository",
    instrument_id: int,
    src_path: str,
    record_id: int | None = None,
) -> None:
    """Validate and add attachment. Raises FileNotFoundError if path does not exist."""
    path = Path(src_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {src_path}")
    repo.add_attachment(instrument_id, src_path, record_id=record_id)


def delete_attachment(repo: "CalibrationRepository", attachment_id: int) -> None:
    """Delete attachment by ID."""
    repo.delete_attachment(attachment_id)
