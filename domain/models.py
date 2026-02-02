# domain/models.py - Domain entities (dataclasses)
#
# Typed models for cross-layer data. Conversion from sqlite3.Row/dict
# happens at the repository boundary only.

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Instrument:
    """
    Domain model for an instrument (calibration-tracked equipment).
    Replaces raw dict from get_instrument().
    """

    id: int
    tag_number: str
    serial_number: Optional[str]
    description: Optional[str]
    location: Optional[str]
    calibration_type: str
    destination_id: Optional[int]
    last_cal_date: Optional[str]
    next_due_date: str
    frequency_months: Optional[int]
    status: str
    notes: Optional[str]
    instrument_type_id: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "Instrument":
        """Build Instrument from sqlite3.Row or dict."""
        d = dict(row)
        return cls(
            id=d["id"],
            tag_number=d.get("tag_number") or "",
            serial_number=d.get("serial_number"),
            description=d.get("description"),
            location=d.get("location"),
            calibration_type=d.get("calibration_type") or "SEND_OUT",
            destination_id=d.get("destination_id"),
            last_cal_date=d.get("last_cal_date"),
            next_due_date=d.get("next_due_date") or "",
            frequency_months=d.get("frequency_months"),
            status=d.get("status") or "ACTIVE",
            notes=d.get("notes"),
            instrument_type_id=d.get("instrument_type_id"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            deleted_at=d.get("deleted_at"),
            deleted_by=d.get("deleted_by"),
        )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Dict-like access for gradual migration. Prefer attribute access
        (e.g. inst.tag_number) in new code.
        """
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Dict-like access for compatibility (e.g. inst["id"])."""
        return getattr(self, key)

    def __str__(self) -> str:
        """String representation for audit logs."""
        return f"id={self.id}, tag={self.tag_number}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for repository write operations (add/update)."""
        return {
            "id": self.id,
            "tag_number": self.tag_number,
            "serial_number": self.serial_number,
            "description": self.description,
            "location": self.location,
            "calibration_type": self.calibration_type,
            "destination_id": self.destination_id,
            "last_cal_date": self.last_cal_date,
            "next_due_date": self.next_due_date,
            "frequency_months": self.frequency_months,
            "status": self.status,
            "notes": self.notes,
            "instrument_type_id": self.instrument_type_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
