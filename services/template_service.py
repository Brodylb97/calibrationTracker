# services/template_service.py - Template persistence orchestration
#
# Thin layer: validates input, delegates to repository.
# Enables future hooks (audit, conflict handling) without changing UI.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database import CalibrationRepository


def create_template(
    repo: "CalibrationRepository",
    instrument_type_id: int,
    name: str,
    version: int = 1,
    is_active: bool = True,
    notes: str = "",
    effective_date: str | None = None,
    change_reason: str | None = None,
    status: str | None = None,
) -> int:
    """Validate and create template. Returns new template ID. Raises ValueError on invalid input."""
    if not (name or "").strip():
        raise ValueError("Template name is required")
    return repo.create_template(
        instrument_type_id=instrument_type_id,
        name=name.strip(),
        version=version,
        is_active=is_active,
        notes=notes or "",
        effective_date=effective_date,
        change_reason=change_reason,
        status=status,
    )


def update_template(
    repo: "CalibrationRepository",
    template_id: int,
    name: str,
    version: int,
    is_active: bool,
    notes: str,
    effective_date: str | None = None,
    change_reason: str | None = None,
    status: str | None = None,
) -> None:
    """Validate and update template. Raises ValueError on invalid input."""
    if not (name or "").strip():
        raise ValueError("Template name is required")
    repo.update_template(
        template_id,
        name=name.strip(),
        version=version,
        is_active=is_active,
        notes=notes or "",
        effective_date=effective_date,
        change_reason=change_reason,
        status=status,
    )


def delete_template(repo: "CalibrationRepository", template_id: int) -> None:
    """Delete template by ID. Raises ValueError if template has calibration records."""
    repo.delete_template(template_id)


def add_template_field(repo: "CalibrationRepository", **kwargs: Any) -> int:
    """Add template field. Delegates to repository. Returns new field ID."""
    name = (kwargs.get("name") or "").strip()
    if not name:
        raise ValueError("Field name is required")
    return repo.add_template_field(**kwargs)


def update_template_field(repo: "CalibrationRepository", field_id: int, data: dict) -> None:
    """Update template field. Delegates to repository."""
    repo.update_template_field(field_id, data)


def delete_template_field(repo: "CalibrationRepository", field_id: int) -> None:
    """Delete template field by ID."""
    repo.delete_template_field(field_id)


def set_template_authorized_personnel(
    repo: "CalibrationRepository", template_id: int, person_ids: list[int]
) -> None:
    """Set which personnel are authorized to perform this template."""
    repo.set_template_authorized_personnel(template_id, person_ids)
