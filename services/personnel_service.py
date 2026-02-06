# services/personnel_service.py - Personnel persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (audit, conflict handling) without changing UI.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import CalibrationRepository


def add_personnel(
    repo: "CalibrationRepository",
    name: str,
    role: str = "",
    qualifications: str = "",
    review_expiry: str | None = None,
    active: bool = True,
) -> int:
    """Validate and add personnel. Returns new person ID. Raises ValueError on invalid input."""
    if not (name or "").strip():
        raise ValueError("Name is required")
    return repo.add_personnel(
        name=name.strip(),
        role=(role or "").strip(),
        qualifications=(qualifications or "").strip(),
        review_expiry=review_expiry,
        active=active,
    )


def update_personnel(
    repo: "CalibrationRepository",
    person_id: int,
    name: str,
    role: str = "",
    qualifications: str = "",
    review_expiry: str | None = None,
    active: bool = True,
) -> None:
    """Validate and update personnel. Raises ValueError on invalid input."""
    if not (name or "").strip():
        raise ValueError("Name is required")
    repo.update_personnel(
        person_id,
        name=name.strip(),
        role=(role or "").strip(),
        qualifications=(qualifications or "").strip(),
        review_expiry=review_expiry,
        active=active,
    )


def delete_personnel(repo: "CalibrationRepository", person_id: int) -> None:
    """Delete personnel by ID."""
    repo.delete_personnel(person_id)
