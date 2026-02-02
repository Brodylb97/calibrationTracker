# pdf_export.py
"""
Export calibration records to PDF using reportlab.
Portrait, black and white. Logo, calibration details, one table per field group
(black headers, header row can word-wrap; tables do not wrap/split). Signatures
displayed as embedded images from Signatures/. Notes at bottom.
"""

from pathlib import Path
import re
from collections import OrderedDict

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Table,
    TableStyle,
    Image,
    Spacer,
    KeepTogether,
)

from database import get_base_dir

# Black and white only
BLACK = colors.HexColor("#000000")
WHITE = colors.HexColor("#ffffff")


def _safe_filename(s: str) -> str:
    """Return a string safe for use in filenames."""
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    return s.strip() or "unknown"


def _logo_path() -> Path:
    """Path to AHI_logo.png (centered at top)."""
    return get_base_dir() / "AHI_logo.png"


def _signatures_dir() -> Path:
    """Path to Signatures subdirectory."""
    return get_base_dir() / "Signatures"


def _group_values_by_group(values: list) -> OrderedDict:
    """Partition values by group_name, preserving template order."""
    groups = OrderedDict()
    for v in values:
        gname = v.get("group_name") or ""
        if gname not in groups:
            groups[gname] = []
        groups[gname].append(v)
    return groups


def _signature_image_path(filename: str | None) -> Path | None:
    """Return path to signature image in Signatures/ if file exists."""
    if not (filename or "").strip():
        return None
    p = _signatures_dir() / filename.strip()
    return p if p.is_file() else None


def _find_signature_image(values: list, performed_by: str) -> Path | None:
    """
    Find signature image path: first value with data_type 'signature' and filename,
    else Signatures/{performed_by}.png if it exists.
    """
    sig_dir = _signatures_dir()
    if not sig_dir.is_dir():
        return None
    for v in values:
        if (v.get("data_type") or "").lower() == "signature":
            filename = (v.get("value_text") or "").strip()
            if filename:
                p = sig_dir / filename
                if p.is_file():
                    return p
    if performed_by:
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
            p = sig_dir / f"{performed_by}{ext}"
            if p.is_file():
                return p
    return None


def _make_signature_flowable(filename: str | None, max_h: float = 0.35 * inch, max_w: float = 1.0 * inch):
    """Return an Image flowable for Signatures/filename, or None if not found."""
    p = _signature_image_path(filename)
    if not p:
        return None
    img = Image(str(p))
    # Preserve aspect ratio while fitting within max_w/max_h.
    ow = float(getattr(img, "imageWidth", img.drawWidth) or img.drawWidth)
    oh = float(getattr(img, "imageHeight", img.drawHeight) or img.drawHeight)
    if ow > 0 and oh > 0:
        scale = min(max_w / ow, max_h / oh, 1.0)
        img.drawWidth = ow * scale
        img.drawHeight = oh * scale
    return img


def _format_value_for_pdf(v: dict) -> str:
    """
    Return display text for a field value in PDF. For bool fields, show Pass/Fail
    when bool tolerance is used; otherwise Yes/No. Other types return value_text as-is.
    """
    data_type = (v.get("data_type") or "").lower()
    val_text = (v.get("value_text") or "").strip()

    if data_type != "bool":
        return val_text or "—"

    # Bool: display Pass/Fail or Yes/No instead of 1/0
    reading_bool = val_text in ("1", "true", "yes", "on")
    tol_type = (v.get("tolerance_type") or "").lower()
    if tol_type == "bool":
        pass_when = (v.get("tolerance_equation") or "true").strip().lower()
        if pass_when not in ("true", "false"):
            return "Yes" if reading_bool else "No"
        try:
            from tolerance_service import evaluate_pass_fail
            reading_float = 1.0 if reading_bool else 0.0
            pass_, _, _ = evaluate_pass_fail(
                "bool", None, pass_when, 0.0, reading_float,
                vars_map={}, tolerance_lookup_json=None,
            )
            return "Pass" if pass_ else "Fail"
        except Exception:
            return "Yes" if reading_bool else "No"
    return "Yes" if reading_bool else "No"


def export_calibration_to_pdf(repo, rec_id: int, output_path: str | Path) -> None:
    """
    Export a single calibration record to a PDF file.
    Layout: logo, details (each on own line), one table per group (delineated
    headers, signatures in table cells), notes at bottom. Fit to one sheet.
    """
    output_path = Path(output_path)
    rec = repo.get_calibration_record_with_template(rec_id)
    if not rec:
        raise ValueError(f"Calibration record {rec_id} not found.")
    instrument = repo.get_instrument(rec["instrument_id"])
    values = repo.get_calibration_values(rec_id)

    # Portrait, black and white
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )
    styles = getSampleStyleSheet()
    small_style = ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=8 * 1.5,
        textColor=BLACK,
    )
    title_style = ParagraphStyle(
        name="PDFTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=12 * 1.5,
        alignment=1,
        textColor=BLACK,
    )
    # Header: clearly delineated (bold, black text, borders); body: centered
    table_header_style = ParagraphStyle(
        name="TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        textColor=WHITE,
        alignment=1,
    )
    table_cell_style = ParagraphStyle(
        name="TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=8,
        textColor=BLACK,
        alignment=1,
    )
    story = []

    # Logo at top center
    logo_path = _logo_path()
    if logo_path.is_file():
        img = Image(str(logo_path))
        # Preserve aspect ratio while sizing (avoid stretching/smooshing).
        max_h = 0.65 * inch
        max_w = 1.9 * inch
        ow = float(getattr(img, "imageWidth", img.drawWidth) or img.drawWidth)
        oh = float(getattr(img, "imageHeight", img.drawHeight) or img.drawHeight)
        if ow > 0 and oh > 0:
            scale = min(max_w / ow, max_h / oh, 1.0)
            img.drawWidth = ow * scale
            img.drawHeight = oh * scale
        logo_table = Table([[img]], colWidths=[7.5 * inch])
        logo_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(logo_table)
        story.append(Spacer(1, 0.08 * inch))

    tag = (instrument.tag_number if instrument else None) or "—"
    cal_date = rec.get("cal_date") or "—"
    template_name = rec.get("template_name") or "Calibration"
    location = (instrument.location if instrument else None) or "—"
    performed_by = rec.get("performed_by") or "—"
    result = rec.get("result") or "—"

    # Title: Calibration Record - TAG (centered)
    story.append(Paragraph(f"Calibration Record - {_safe_filename(tag)}", title_style))
    story.append(Spacer(1, 0.1 * inch))

    # Calibration details (each on own line, left)
    details_lines = [
        f"<b>Location:</b> {_safe_filename(str(location))}",
        f"<b>Calibration Date:</b> {cal_date}",
        f"<b>Performed By:</b> {performed_by}",
        f"<b>Result:</b> {result}",
        f"<b>Template:</b> {template_name}",
    ]
    story.append(Paragraph("<br/>".join(details_lines), small_style))
    story.append(Spacer(1, 0.12 * inch))

    # One table per group: clearly delineated column headers (bold, bordered), all cells centered
    groups = _group_values_by_group(values)
    pad = 3

    for group_name, group_values in groups.items():
        if not group_values:
            continue
        header_cells = []
        data_cells = []
        for v in group_values:
            label = v.get("label") or v.get("field_name") or "—"
            unit = (v.get("unit") or "").strip()
            tol_raw = v.get("tolerance")
            tol_f = None
            if tol_raw is not None and str(tol_raw).strip() != "":
                try:
                    tol_f = float(tol_raw)
                except (ValueError, TypeError):
                    pass
            # Delta/difference columns: show tolerance in parentheses for pass/fail, e.g. "∆ Temp (±1.500 °F)"
            if tol_f is not None:
                tol_str = f"{tol_f:.3f}".rstrip("0").rstrip(".") if tol_f != int(tol_f) else str(int(tol_f))
                if unit:
                    header_text = f"{label} (±{tol_str} {unit})"
                else:
                    header_text = f"{label} (±{tol_str})"
            elif unit:
                header_text = f"{label} ({unit})"
            else:
                header_text = label
            header_cells.append(Paragraph(header_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_header_style))

            is_signature = (v.get("data_type") or "").lower() == "signature"
            if is_signature:
                sig_flowable = _make_signature_flowable(v.get("value_text"))
                data_cells.append(sig_flowable if sig_flowable else Paragraph("—", table_cell_style))
            else:
                val_text = _format_value_for_pdf(v)
                if not val_text:
                    val_text = "—"
                val_text = val_text.replace("\n", " ")
                data_cells.append(Paragraph(val_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_cell_style))

        num_cols = len(header_cells)
        if num_cols == 0:
            continue
        col_width = min(1.2 * inch, (7.5 * inch) / num_cols)
        table_data = [header_cells, data_cells]
        tbl = Table(table_data, colWidths=[col_width] * num_cols)
        tbl.setStyle(
            TableStyle(
                [
                    # Header: black with white text, with white grid lines for clear column delineation.
                    ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("GRID", (0, 0), (-1, 0), 0.5, WHITE),
                    # Body: black text, black grid lines.
                    ("TEXTCOLOR", (0, 1), (-1, -1), BLACK),
                    ("GRID", (0, 1), (-1, -1), 0.5, BLACK),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), pad),
                    ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                    ("TOPPADDING", (0, 0), (-1, -1), pad),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                ]
            )
        )
        story.append(KeepTogether([tbl]))
        story.append(Spacer(1, 0.15 * inch))

    # Notes at bottom
    notes = rec.get("notes")
    if notes:
        story.append(Paragraph(f"<b>Notes:</b><br/>{notes}", small_style))

    doc.build(story)


def export_all_calibrations_to_directory(
    repo, base_dir: str | Path, *,
    progress_callback=None,
    cancelled_check=None,
) -> dict:
    """
    Export all calibration records to PDF files in the given directory.
    Organizes files by instrument type: base_dir / instrument_type_name / tag_caldate.pdf
    Returns dict with: success_count, attachment_count, error_count, errors (list of strings),
    cancelled (bool).

    Optional: progress_callback(current, total) called after each record.
    Optional: cancelled_check() - if returns True, export stops and returns partial result.
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    records = repo.list_all_calibration_records()
    total = len(records)
    success_count = 0
    error_count = 0
    errors = []
    cancelled = False

    for i, rec in enumerate(records):
        if cancelled_check and cancelled_check():
            cancelled = True
            break
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
        if progress_callback:
            progress_callback(i + 1, total)

    return {
        "success_count": success_count,
        "attachment_count": 0,
        "error_count": error_count,
        "errors": errors,
        "cancelled": cancelled,
    }
