# pdf_export.py
"""
Export calibration records to PDF using reportlab.
Portrait, black and white. Logo, calibration details, one table per field group
(black headers, header row can word-wrap; tables do not wrap/split). Signatures
displayed as embedded images from Signatures/. Plot-type fields rendered as
matplotlib scatter charts (with optional line of best fit via numpy)
embedded in the PDF. Notes at bottom.
"""

from pathlib import Path
import io
import re
from collections import OrderedDict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
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
    PageBreak,
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


def _parse_numeric_stripping_unit(val_text, unit: str):
    """Parse value as float, stripping trailing unit (e.g. '122.0 °F' with unit '°F' -> 122.0). Returns float or None."""
    if val_text is None or val_text == "":
        return None
    s = str(val_text).strip()
    if not s:
        return None
    u = (unit or "").strip()
    if u:
        if s.endswith(u):
            s = s[:-len(u)].strip()
        elif s.endswith(" " + u):
            s = s[:-len(" " + u)].strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _lookup_value_for_plot(record_values_by_name: dict, ref_name: str):
    """Try multiple key variants to resolve ref_name to a value. Returns value or None."""
    if not ref_name:
        return None
    keys_to_try = [
        ref_name,
        ref_name.lower(),
        ref_name.replace(" ", "_"),
        ref_name.replace("_", " "),
        ref_name.replace(" ", "_").lower(),
        ref_name.replace("_", " ").lower(),
    ]
    for k in keys_to_try:
        v = record_values_by_name.get(k)
        if v is not None and v != "":
            return v
    return None


def _vars_map_for_plot(
    tf: dict,
    values: list,
    template_fields: list,
    template_fields_by_id: dict,
    record_values_by_name: dict,
    stat_computed: dict | None = None,
) -> dict[str, float]:
    """
    Build ref1..ref12 / val1..val12 for a plot field.
    Uses record_values_by_name (same source as stat/convert) with multiple key variants.
    """
    vars_map = {}
    for i in range(1, 13):
        ref_name = (tf.get(f"calc_ref{i}_name") or "").strip()
        if not ref_name:
            continue
        rv = _lookup_value_for_plot(record_values_by_name, ref_name)
        if rv is not None and rv != "":
            try:
                num = float(str(rv).strip())
                vars_map[f"ref{i}"] = num
                vars_map[f"val{i}"] = num
            except (TypeError, ValueError):
                pass
    # Ensure val/ref aliases for evaluate_plot_equation (tolerance_service._ensure_val_aliases)
    for i in range(1, 13):
        rk, vk = f"ref{i}", f"val{i}"
        if rk in vars_map and vk not in vars_map:
            vars_map[vk] = vars_map[rk]
        elif vk in vars_map and rk not in vars_map:
            vars_map[rk] = vars_map[vk]
    return vars_map


def _render_plot_to_png(
    xs: list[float],
    ys: list[float],
    title: str | None,
    x_axis_name: str | None,
    y_axis_name: str | None,
    x_min: float | None,
    x_max: float | None,
    y_min: float | None,
    y_max: float | None,
    show_best_fit: bool,
) -> bytes:
    """
    Render a scatter plot (and optional line of best fit) with matplotlib.
    Returns PNG bytes for embedding in the PDF. Uses numpy for linear fit (no pandas/sklearn required).
    """
    import matplotlib  # type: ignore[import-untyped]
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]

    if not xs or not ys or len(xs) != len(ys):
        return b""
    x_arr = np.array(xs, dtype=float)
    y_arr = np.array(ys, dtype=float)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(x_arr, y_arr, color="black", s=24, zorder=2)
    if show_best_fit and len(x_arr) >= 2:
        try:
            coeffs = np.polyfit(x_arr, y_arr, 1)
            x_line = np.linspace(float(np.min(x_arr)), float(np.max(x_arr)), 100)
            y_line = np.polyval(coeffs, x_line)
            ax.plot(x_line, y_line, color="black", linestyle="--", linewidth=1, zorder=1)
        except Exception:
            pass
    if title:
        ax.set_title(title, fontsize=9)
    if x_axis_name:
        ax.set_xlabel(x_axis_name, fontsize=8)
    if y_axis_name:
        ax.set_ylabel(y_axis_name, fontsize=8)
    if x_min is not None or x_max is not None:
        ax.set_xlim(left=x_min, right=x_max)
    if y_min is not None or y_max is not None:
        ax.set_ylim(bottom=y_min, top=y_max)
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", alpha=0.7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _format_value_for_pdf(v: dict, values_by_name: dict | None = None) -> str:
    """
    Return display text for a field value in PDF.
    For equation tolerance (single comparison): "lhs op rhs, Pass" or ", Fail".
    For bool fields: Pass/Fail when bool tolerance; otherwise Yes/No.
    Other types: value_text as-is.
    """
    data_type = (v.get("data_type") or "").lower()
    val_text = (v.get("value_text") or "").strip()
    tol_type = (v.get("tolerance_type") or "").lower()
    values_by_name = values_by_name or {}

    # Equation tolerance (comparison): show "calculated op compared, Pass/Fail"
    if tol_type == "equation" and v.get("tolerance_equation"):
        try:
            from tolerance_service import equation_tolerance_display
            nominal = 0.0
            nominal_str = v.get("nominal_value")
            if nominal_str not in (None, ""):
                try:
                    nominal = float(str(nominal_str).strip())
                except (TypeError, ValueError):
                    pass
            unit_v = (v.get("unit") or "").strip()
            reading = _parse_numeric_stripping_unit(val_text, unit_v)
            if reading is None and val_text:
                try:
                    reading = float(str(val_text).strip())
                except (TypeError, ValueError):
                    reading = 0.0
            reading = reading if reading is not None else 0.0
            vars_map = {"nominal": nominal, "reading": reading}
            for i in range(1, 13):
                ref_name = v.get(f"calc_ref{i}_name")
                if ref_name:
                    rv = values_by_name.get(ref_name) or values_by_name.get((ref_name or "").strip().lower())
                    if rv not in (None, ""):
                        try:
                            vars_map[f"ref{i}"] = float(str(rv).strip())
                        except (TypeError, ValueError):
                            vars_map[f"ref{i}"] = 0.0
            parts = equation_tolerance_display(v.get("tolerance_equation"), vars_map)
            if parts is not None:
                from tolerance_service import format_calculation_display
                lhs, op_str, rhs, pass_ = parts
                dec = max(0, min(4, int(v.get("sig_figs") or 3)))
                return f"{format_calculation_display(lhs, decimal_places=dec)} {op_str} {format_calculation_display(rhs, decimal_places=dec)}, {'Pass' if pass_ else 'Fail'}"
        except Exception:
            pass

    # Stat-type: evaluate equation (e.g. LINEST) and return formatted value
    if data_type == "stat" and v.get("tolerance_equation"):
        try:
            from tolerance_service import evaluate_tolerance_equation, list_variables, format_calculation_display
            nominal = 0.0
            nominal_str = v.get("nominal_value")
            if nominal_str not in (None, ""):
                try:
                    nominal = float(str(nominal_str).strip())
                except (TypeError, ValueError):
                    pass
            vars_map = {"nominal": nominal, "reading": 0.0}
            for i in range(1, 13):
                ref_name = v.get(f"calc_ref{i}_name")
                if ref_name:
                    rv = values_by_name.get(ref_name) or values_by_name.get((ref_name or "").strip().lower())
                    if rv not in (None, ""):
                        try:
                            vars_map[f"ref{i}"] = float(str(rv).strip())
                        except (TypeError, ValueError):
                            vars_map[f"ref{i}"] = 0.0
            for i in range(1, 13):
                rk, vk = f"ref{i}", f"val{i}"
                if rk in vars_map and vk not in vars_map:
                    vars_map[vk] = vars_map[rk]
                elif vk in vars_map and rk not in vars_map:
                    vars_map[rk] = vars_map[vk]
            required = list_variables(v.get("tolerance_equation"))
            if not any(var not in vars_map for var in required):
                result = evaluate_tolerance_equation(v.get("tolerance_equation"), vars_map)
                dec = max(0, min(4, int(v.get("sig_figs") or 3)))
                return format_calculation_display(result, decimal_places=dec)
        except Exception:
            pass

    # Number or reference: format with decimal places if numeric
    if data_type in ("number", "reference") and val_text:
        try:
            num = float(str(val_text).strip())
            dec = max(0, min(4, int(v.get("sig_figs") or 3)))
            from tolerance_service import format_calculation_display
            return format_calculation_display(num, decimal_places=dec)
        except (TypeError, ValueError):
            pass

    if data_type != "bool":
        return val_text or "—"

    # Bool: display Pass/Fail or Yes/No instead of 1/0
    reading_bool = val_text in ("1", "true", "yes", "on")
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
    template_id = rec.get("template_id")
    template_fields = repo.list_template_fields(template_id) if template_id else []
    template_fields_by_id = {tf["id"]: tf for tf in template_fields}
    pad = 3

    # Build record-wide values_by_name and precompute stat field results (stat can use ref1..ref12 from any group)
    def _add_key(m, key, val):
        if not key:
            return
        m[key] = val
        kl = key.lower()
        if kl != key:
            m[kl] = val
        # Add underscore/space variants for plot ref lookup (field names may use cert_weight_1_low or "cert weight 1 low")
        for variant in [key.replace(" ", "_"), key.replace("_", " ")]:
            if variant and variant != key:
                m[variant] = val
                if variant.lower() != variant:
                    m[variant.lower()] = val
    record_values_by_name = {}
    for v in values:
        val_text = v.get("value_text")
        fn = (v.get("field_name") or "").strip()
        lbl = (v.get("label") or "").strip()
        tf = template_fields_by_id.get(v.get("field_id"))
        unit = (tf.get("unit") or "").strip() if tf else ""
        num = _parse_numeric_stripping_unit(val_text, unit)
        num_str = str(num) if num is not None else (val_text or "")
        _add_key(record_values_by_name, fn, num_str)
        if lbl and lbl != fn:
            _add_key(record_values_by_name, lbl, num_str)
        if tf:
            tname = (tf.get("name") or "").strip()
            tlabel = (tf.get("label") or "").strip()
            if tname:
                _add_key(record_values_by_name, tname, num_str)
            if tlabel and tlabel != tname:
                _add_key(record_values_by_name, tlabel, num_str)
    # Compute convert record-wide so refs can come from any group
    try:
        from tolerance_service import evaluate_tolerance_equation, format_calculation_display
        for tf in template_fields_by_id.values():
            if (tf.get("data_type") or "").strip().lower() != "convert":
                continue
            eq = (tf.get("tolerance_equation") or "").strip()
            if not eq:
                continue
            vars_map = {"nominal": 0.0, "reading": 0.0}
            for i in range(1, 13):
                ref_name = tf.get(f"calc_ref{i}_name")
                if ref_name:
                    rv = record_values_by_name.get(ref_name) or record_values_by_name.get((ref_name or "").strip().lower())
                    if rv not in (None, ""):
                        try:
                            vars_map[f"ref{i}"] = float(str(rv).strip())
                            vars_map[f"val{i}"] = vars_map[f"ref{i}"]
                        except (TypeError, ValueError):
                            pass
            try:
                result = evaluate_tolerance_equation(eq, vars_map)
                decimals = max(0, min(4, int(tf.get("sig_figs") or 3)))
                formatted = format_calculation_display(result, decimal_places=decimals)
                tname = (tf.get("name") or "").strip()
                tlabel = (tf.get("label") or "").strip()
                if tname:
                    _add_key(record_values_by_name, tname, formatted)
                if tlabel:
                    _add_key(record_values_by_name, tlabel, formatted)
            except (ValueError, TypeError):
                pass
    except ImportError:
        pass
    # Precompute stat field results (ref1..ref12 from record-wide)
    stat_computed = {}
    try:
        from tolerance_service import evaluate_tolerance_equation, format_calculation_display
        for tf in template_fields_by_id.values():
            if (tf.get("data_type") or "").strip().lower() != "stat":
                continue
            eq = (tf.get("tolerance_equation") or "").strip()
            if not eq:
                continue
            vars_map = {"nominal": 0.0, "reading": 0.0}
            for i in range(1, 13):
                ref_name = tf.get(f"calc_ref{i}_name")
                if ref_name:
                    rv = record_values_by_name.get(ref_name) or record_values_by_name.get((ref_name or "").strip().lower())
                    if rv not in (None, ""):
                        try:
                            vars_map[f"ref{i}"] = float(str(rv).strip())
                            vars_map[f"val{i}"] = vars_map[f"ref{i}"]
                        except (TypeError, ValueError):
                            pass
            for i in range(1, 13):
                rk, vk = f"ref{i}", f"val{i}"
                if rk in vars_map and vk not in vars_map:
                    vars_map[vk] = vars_map[rk]
                elif vk in vars_map and rk not in vars_map:
                    vars_map[rk] = vars_map[vk]
            try:
                result = evaluate_tolerance_equation(eq, vars_map)
                decimals = max(0, min(4, int(tf.get("sig_figs") or 3)))
                formatted = format_calculation_display(result, decimal_places=decimals)
                stat_computed[tf["id"]] = formatted
                tname = (tf.get("name") or "").strip()
                tlabel = (tf.get("label") or "").strip()
                if tname:
                    _add_key(record_values_by_name, tname, formatted)
                if tlabel and tlabel != tname:
                    _add_key(record_values_by_name, tlabel, formatted)
            except (ValueError, TypeError):
                stat_computed[tf["id"]] = "—"
    except ImportError:
        pass

    # Iterate groups in template order so stat-only (and convert-only) groups are included even when they have no stored value rows
    template_fields_sorted = sorted(template_fields, key=lambda x: (x.get("sort_order") or 0, x.get("id") or 0))
    template_group_order = []
    seen_groups = set()
    for tf in template_fields_sorted:
        g = (tf.get("group_name") or "").strip()
        if g not in seen_groups:
            seen_groups.add(g)
            template_group_order.append(g)

    # Plot rendering (matplotlib): resolve once so we can render plots inline per group
    try:
        import matplotlib  # type: ignore[import-untyped]
        matplotlib.use("Agg")
        _plot_deps_available = True
    except ImportError:
        _plot_deps_available = False
    try:
        from tolerance_service import evaluate_plot_equation
    except ImportError:
        evaluate_plot_equation = None
    plot_fields = [tf for tf in template_fields_sorted if (tf.get("data_type") or "").strip().lower() == "plot"]
    plots_added_total = 0
    _plot_deps_message_shown = False
    _plot_last_error = None

    for group_name in template_group_order:
        group_values = groups.get(group_name, [])
        fields_in_group = [tf for tf in template_fields if (tf.get("group_name") or "").strip() == group_name]
        fields_in_group.sort(key=lambda x: (x.get("sort_order") or 0, x.get("id") or 0))
        if not fields_in_group:
            continue
        # Build values_by_name from this group only (may be empty for stat/convert-only groups)
        def _add_key(m, key, val):
            if not key:
                return
            m[key] = val
            kl = key.lower()
            if kl != key:
                m[kl] = val
        values_by_name = {}
        for v in group_values:
            val_text = v.get("value_text")
            fn = (v.get("field_name") or "").strip()
            lbl = (v.get("label") or "").strip()
            tf = template_fields_by_id.get(v.get("field_id"))
            unit = (tf.get("unit") or "").strip() if tf else ""
            num = _parse_numeric_stripping_unit(val_text, unit)
            num_str = str(num) if num is not None else (val_text or "")
            _add_key(values_by_name, fn, num_str)
            if lbl and lbl != fn:
                _add_key(values_by_name, lbl, num_str)
            if tf:
                tname = (tf.get("name") or "").strip()
                tlabel = (tf.get("label") or "").strip()
                if tname:
                    _add_key(values_by_name, tname, num_str)
                if tlabel and tlabel != tname:
                    _add_key(values_by_name, tlabel, num_str)
        # Compute convert-type fields for this group
        try:
            from tolerance_service import evaluate_tolerance_equation, format_calculation_display
            for tf in template_fields_by_id.values():
                if (tf.get("group_name") or "") != group_name:
                    continue
                if (tf.get("data_type") or "").strip().lower() != "convert":
                    continue
                eq = (tf.get("tolerance_equation") or "").strip()
                if not eq:
                    continue
                vars_map = {"nominal": 0.0, "reading": 0.0}
                for i in range(1, 6):
                    ref_name = tf.get(f"calc_ref{i}_name")
                    if ref_name:
                        rv = values_by_name.get(ref_name) or values_by_name.get((ref_name or "").strip().lower())
                        if rv not in (None, ""):
                            try:
                                vars_map[f"ref{i}"] = float(str(rv).strip())
                                vars_map[f"val{i}"] = vars_map[f"ref{i}"]
                            except (TypeError, ValueError):
                                pass
                try:
                    result = evaluate_tolerance_equation(eq, vars_map)
                    decimals = max(0, min(4, int(tf.get("sig_figs") or 3)))
                    formatted = format_calculation_display(result, decimal_places=decimals)
                    tname = (tf.get("name") or "").strip()
                    tlabel = (tf.get("label") or "").strip()
                    if tname:
                        _add_key(values_by_name, tname, formatted)
                    if tlabel:
                        _add_key(values_by_name, tlabel, formatted)
                except (ValueError, TypeError):
                    pass
        except ImportError:
            pass

        # Optional group header from first field_header in this group (centered, black border)
        header_fields_in_group = [tf for tf in fields_in_group if (tf.get("data_type") or "").strip().lower() == "field_header"]
        if header_fields_in_group:
            first_header = header_fields_in_group[0]
            header_label = (first_header.get("label") or first_header.get("name") or "").strip()
            if header_label:
                header_para = Paragraph(
                    header_label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                    ParagraphStyle(
                        name="GroupHeader",
                        parent=small_style,
                        fontName="Helvetica-Bold",
                        fontSize=11,
                        alignment=TA_CENTER,
                    ),
                )
                header_tbl = Table([[header_para]], colWidths=[7.5 * inch])
                header_tbl.setStyle(
                    TableStyle([
                        ("BOX", (0, 0), (-1, -1), 0.5, BLACK),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0.15 * inch),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0.15 * inch),
                        ("TOPPADDING", (0, 0), (-1, -1), 0.08 * inch),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.08 * inch),
                    ])
                )
                story.append(header_tbl)
                story.append(Spacer(1, 0.08 * inch))

        header_cells = []
        data_cells = []
        by_field_id = {v.get("field_id"): v for v in group_values}

        for tf in fields_in_group:
            fid = tf.get("id")
            data_type = (tf.get("data_type") or "").strip().lower()
            label = tf.get("label") or tf.get("name") or "—"
            unit = (tf.get("unit") or "").strip()
            # Field header and plot: no column in table (header shown above group; plot rendered inline after table)
            if data_type == "field_header" or data_type == "plot":
                continue
            tol_raw = tf.get("tolerance")
            tol_f = None
            if tol_raw is not None and str(tol_raw).strip() != "":
                try:
                    tol_f = float(tol_raw)
                except (ValueError, TypeError):
                    pass
            if tol_f is not None:
                tol_str = f"{tol_f:.3f}".rstrip("0").rstrip(".") if tol_f != int(tol_f) else str(int(tol_f))
                header_text = f"{label} (±{tol_str} {unit})" if unit else f"{label} (±{tol_str})"
            elif unit:
                header_text = f"{label} ({unit})"
            else:
                header_text = label
            header_cells.append(Paragraph(header_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_header_style))

            # Convert: value from record-wide map (refs can be from any group)
            if data_type == "convert":
                tname = (tf.get("name") or "").strip()
                tlabel = (tf.get("label") or "").strip()
                val_text = record_values_by_name.get(tname) or record_values_by_name.get(tlabel) or record_values_by_name.get((tname or "").lower()) or record_values_by_name.get((tlabel or "").lower())
                if not val_text:
                    val_text = "—"
                val_text = str(val_text).replace("\n", " ")
                data_cells.append(Paragraph(val_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_cell_style))
                continue

            # Stat-type: use precomputed value (record-wide ref1..ref12)
            if data_type == "stat":
                val_text = stat_computed.get(fid, "—")
                val_text = str(val_text).replace("\n", " ")
                data_cells.append(Paragraph(val_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_cell_style))
                continue

            # Tolerance-type: not stored; compute from equation
            if data_type == "tolerance":
                eq = (tf.get("tolerance_equation") or "").strip()
                display_text = "—"
                if eq:
                    nominal = 0.0
                    nominal_str = tf.get("nominal_value")
                    if nominal_str not in (None, ""):
                        try:
                            nominal = float(str(nominal_str).strip())
                        except (TypeError, ValueError):
                            pass
                    vars_map = {"nominal": nominal, "reading": 0.0}
                    for i in range(1, 13):
                        ref_name = tf.get(f"calc_ref{i}_name")
                        if ref_name:
                            rv = record_values_by_name.get(ref_name) or record_values_by_name.get((ref_name or "").strip().lower())
                            if rv not in (None, ""):
                                try:
                                    vars_map[f"ref{i}"] = float(str(rv).strip())
                                    vars_map[f"val{i}"] = vars_map[f"ref{i}"]
                                except (TypeError, ValueError):
                                    pass
                    try:
                        from tolerance_service import list_variables
                        if "reading" in list_variables(eq):
                            ref1 = tf.get("calc_ref1_name")
                            if ref1:
                                rv1 = record_values_by_name.get(ref1) or record_values_by_name.get((ref1 or "").strip().lower())
                                if rv1 not in (None, ""):
                                    try:
                                        vars_map["reading"] = float(str(rv1).strip())
                                    except (TypeError, ValueError):
                                        pass
                    except ImportError:
                        pass
                    for i in range(1, 13):
                        rk, vk = f"ref{i}", f"val{i}"
                        if rk in vars_map and vk not in vars_map:
                            vars_map[vk] = vars_map[rk]
                    try:
                        from tolerance_service import equation_tolerance_display, list_variables, format_calculation_display
                        required = list_variables(eq)
                        if not any(var not in vars_map for var in required):
                            parts = equation_tolerance_display(eq, vars_map)
                            if parts is not None:
                                lhs, op_str, rhs, pass_ = parts
                                dec = max(0, min(4, int(tf.get("sig_figs") or 3)))
                                display_text = f"{format_calculation_display(lhs, decimal_places=dec)} {op_str} {format_calculation_display(rhs, decimal_places=dec)}, {'Pass' if pass_ else 'Fail'}"
                            else:
                                from tolerance_service import evaluate_pass_fail
                                reading = vars_map.get("reading", 0.0)
                                pass_, _, _ = evaluate_pass_fail(
                                    "equation", None, eq, nominal, reading,
                                    vars_map=vars_map, tolerance_lookup_json=None,
                                )
                                display_text = "Pass" if pass_ else "Fail"
                    except (ImportError, ValueError, TypeError):
                        pass
                data_cells.append(Paragraph(display_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_cell_style))
                continue

            # Stored types: number, text, bool, date, signature, reference
            v = by_field_id.get(fid)
            if not v:
                data_cells.append(Paragraph("—", table_cell_style))
                continue
            is_signature = (v.get("data_type") or "").lower() == "signature"
            if is_signature:
                sig_flowable = _make_signature_flowable(v.get("value_text"))
                data_cells.append(sig_flowable if sig_flowable else Paragraph("—", table_cell_style))
            else:
                val_text = _format_value_for_pdf(v, values_by_name)
                if not val_text:
                    val_text = "—"
                val_text = val_text.replace("\n", " ")
                data_cells.append(Paragraph(val_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), table_cell_style))

        num_cols = len(header_cells)
        if num_cols > 0:
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

        # Plot-type fields: render inline when we process the group that has their data.
        # - Plots in this group: render here
        # - Plots with stat_value_group pointing here: render here (so plot appears after its data table)
        plot_fields_in_group = [tf for tf in fields_in_group if (tf.get("data_type") or "").strip().lower() == "plot"]
        stat_value_group_plots = [
            tf for tf in plot_fields
            if ((tf.get("stat_value_group") or "").strip() == group_name)
            and tf not in plot_fields_in_group
        ]
        plot_fields_to_render = plot_fields_in_group + stat_value_group_plots
        if plot_fields_to_render and evaluate_plot_equation:
            plot_width = 5.0 * inch
            if not _plot_deps_available:
                _plot_last_error = "Plot charts require matplotlib and numpy. Install with: py -m pip install matplotlib numpy"
                if not _plot_deps_message_shown:
                    story.append(Paragraph(_plot_last_error, small_style))
                    story.append(Spacer(1, 0.1 * inch))
                    _plot_deps_message_shown = True
            else:
                for tf in plot_fields_to_render:
                    eq = (tf.get("tolerance_equation") or "").strip()
                    if not eq:
                        _plot_last_error = "Plot field has no equation. Set PLOT([x refs], [y refs]) in the field editor."
                        continue
                    vars_map = _vars_map_for_plot(
                        tf,
                        values,
                        template_fields,
                        template_fields_by_id,
                        record_values_by_name,
                        stat_computed=stat_computed,
                    )
                    try:
                        xs, ys = evaluate_plot_equation(eq, vars_map)
                    except (ValueError, TypeError) as e:
                        err_msg = str(e)
                        try:
                            from tolerance_service import parse_plot_equation
                            x_names, y_names = parse_plot_equation(eq)
                            required = set(x_names + y_names)
                            missing = [n for n in required if n not in vars_map]
                            if missing:
                                err_msg += f" Missing: {', '.join(sorted(missing))}. Ensure refs in the field editor point to fields with numeric data."
                        except Exception:
                            pass
                        _plot_last_error = err_msg
                        continue
                    if not xs or not ys:
                        _plot_last_error = "Plot equation returned no data. Check that all val1–val12 refs are assigned to numeric fields."
                        continue
                    try:
                        png_bytes = _render_plot_to_png(
                            xs,
                            ys,
                            title=tf.get("plot_title"),
                            x_axis_name=tf.get("plot_x_axis_name"),
                            y_axis_name=tf.get("plot_y_axis_name"),
                            x_min=tf.get("plot_x_min"),
                            x_max=tf.get("plot_x_max"),
                            y_min=tf.get("plot_y_min"),
                            y_max=tf.get("plot_y_max"),
                            show_best_fit=bool(tf.get("plot_best_fit")),
                        )
                    except Exception as ex:
                        _plot_last_error = str(ex)
                        continue
                    if png_bytes:
                        img_flowable = Image(io.BytesIO(png_bytes))
                        img_flowable.drawWidth = plot_width
                        img_flowable.drawHeight = plot_width * 0.8
                        story.append(img_flowable)
                        story.append(Spacer(1, 0.15 * inch))
                        # Page break after plot only if a non-Signature group follows
                        idx = template_group_order.index(group_name)
                        groups_after = template_group_order[idx + 1:]
                        if any((g or "").strip() != "Signature" for g in groups_after):
                            story.append(PageBreak())
                        plots_added_total += 1

    if plot_fields and plots_added_total == 0:
        msg = "No plot could be generated."
        if _plot_last_error:
            msg += f" {_plot_last_error}"
        else:
            msg += (
                " Check that the plot equation uses PLOT([x refs], [y refs]) with "
                "val1–val12 assigned in the field editor. For X and Y side by side (e.g. Certified Weight, Balance Response), "
                "use odd refs for X and even for Y: PLOT([val1, val3, val5, ...], [val2, val4, val6, ...])."
            )
        story.append(Paragraph(msg, small_style))
        story.append(Spacer(1, 0.1 * inch))

    # Record notes at bottom
    notes = rec.get("notes")
    if notes:
        story.append(Paragraph(f"<b>Notes:</b><br/>{notes}", small_style))

    # Template notes at bottom (in-house templates only; skip external calibration file)
    template_name = rec.get("template_name") or ""
    template_notes = (rec.get("template_notes") or "").strip()
    is_in_house = template_name != "External calibration file" and "External calibration (file only)" not in template_name
    if is_in_house and template_notes:
        story.append(Spacer(1, 0.12 * inch))
        notes_escaped = template_notes.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(f"<b>Template notes:</b><br/>{notes_escaped}", small_style))

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
