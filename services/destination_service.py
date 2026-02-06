# services/destination_service.py - Destination persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (audit, conflict handling) without changing UI.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def add_destination(
    repo: "CalibrationRepository",
    name: str,
    contact: str = "",
    email: str = "",
    phone: str = "",
    address: str = "",
) -> None:
    """Validate and add destination. Raises ValueError on invalid input."""
    if not (name or "").strip():
        raise ValueError("Name is required")
    repo.add_destination(
        name=name.strip(),
        contact=(contact or "").strip(),
        email=(email or "").strip(),
        phone=(phone or "").strip(),
        address=(address or "").strip(),
    )


def update_destination(repo: "CalibrationRepository", dest_id: int, data: dict) -> None:
    """Validate and update destination. Raises ValueError on invalid input."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")
    repo.update_destination(dest_id, data)


def delete_destination(repo: "CalibrationRepository", dest_id: int) -> None:
    """Delete destination by ID."""
    repo.delete_destination(dest_id)
