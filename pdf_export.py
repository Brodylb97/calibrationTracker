# pdf_export.py
"""
Export calibration records to PDF using reportlab.
Single-record export and batch export to a directory (organized by instrument type).
"""

from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer, PageBreak

from database import get_base_dir


def _safe_filename(s: str) -> str:
    """Return a string safe for use in filenames."""
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    return s.strip() or "unknown"


def _logo_path() -> Path:
    """Path to AHI_logo.png (centered at top of in-house PDF exports)."""
    return get_base_dir() / "AHI_logo.png"


def export_calibration_to_pdf(repo, rec_id: int, output_path: str | Path) -> None:
    """
    Export a single calibration record to a PDF file.
    repo: CalibrationRepository instance.
    rec_id: calibration record id.
    output_path: path to the output PDF file.
    """
    output_path = Path(output_path)
    rec = repo.get_calibration_record_with_template(rec_id)
    if not rec:
        raise ValueError(f"Calibration record {rec_id} not found.")
    instrument = repo.get_instrument(rec["instrument_id"]) or {}
    values = repo.get_calibration_values(rec_id)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Logo at top (centered)
    logo_path = _logo_path()
    if logo_path.is_file():
        img = Image(str(logo_path))
        img.drawHeight = min(1.0 * inch, img.drawHeight)
        img.drawWidth = min(2.5 * inch, img.drawWidth)
        logo_table = Table([[img]], colWidths=[6 * inch])
        logo_table.setStyle(
            TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])
        )
        story.append(logo_table)
        story.append(Spacer(1, 0.2 * inch))

    # Title
    tag = instrument.get("tag_number") or "—"
    cal_date = rec.get("cal_date") or "—"
    template_name = rec.get("template_name") or "Calibration"
    story.append(Paragraph(f"<b>Calibration Record: {_safe_filename(tag)}</b>", styles["Heading1"]))
    story.append(Spacer(1, 0.15 * inch))

    # Instrument / record info
    info_data = [
        ["Tag number", str(tag)],
        ["Serial number", str(instrument.get("serial_number") or "—")],
        ["Description", str(instrument.get("description") or "—")],
        ["Location", str(instrument.get("location") or "—")],
        ["Template", str(template_name)],
        ["Calibration date", str(cal_date)],
        ["Performed by", str(rec.get("performed_by") or "—")],
        ["Result", str(rec.get("result") or "—")],
    ]
    notes = rec.get("notes")
    if notes:
        info_data.append(["Notes", str(notes)])
    info_table = Table(info_data, colWidths=[1.5 * inch, 4.5 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0e0e0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 0.25 * inch))

    # Calibration values (template fields)
    if values:
        story.append(Paragraph("<b>Calibration values</b>", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))
        val_data = [["Field", "Value", "Unit"]]
        for v in values:
            label = v.get("label") or v.get("field_name") or "—"
            val_text = (v.get("value_text") or "—").replace("\n", " ")
            unit = (v.get("unit") or "—").strip() or "—"
            val_data.append([label, val_text, unit])
        val_table = Table(val_data, colWidths=[2.0 * inch, 3.0 * inch, 1.0 * inch])
        val_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c0c0c0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(val_table)

    doc.build(story)


def export_all_calibrations_to_directory(repo, base_dir: str | Path) -> dict:
    """
    Export all calibration records to PDF files in the given directory.
    Organizes files by instrument type: base_dir / instrument_type_name / tag_caldate.pdf
    Returns dict with: success_count, attachment_count, error_count, errors (list of strings).
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    records = repo.list_all_calibration_records()
    success_count = 0
    error_count = 0
    errors = []

    for rec in records:
        rec_id = rec["id"]
        instrument_type_name = rec.get("instrument_type_name") or "Unknown"
        tag = rec.get("tag_number") or "unknown"
        cal_date = rec.get("cal_date") or ""
        safe_type = _safe_filename(instrument_type_name)
        safe_tag = _safe_filename(tag)
        safe_date = _safe_filename(cal_date) if cal_date else "nodate"
        subdir = base_dir / safe_type
        subdir.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_tag}_{safe_date}.pdf"
        out_path = subdir / filename
        try:
            export_calibration_to_pdf(repo, rec_id, out_path)
            success_count += 1
        except Exception as e:
            error_count += 1
            errors.append(f"Record {rec_id} ({tag} {cal_date}): {e}")

    return {
        "success_count": success_count,
        "attachment_count": 0,
        "error_count": error_count,
        "errors": errors,
    }
