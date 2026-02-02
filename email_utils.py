# email_utils.py
# DEPRECATED: Not imported anywhere. Kept for potential future email reminder feature.
# Consider moving to scripts/ if needed later.

from email.message import EmailMessage
import smtplib
from typing import List
from datetime import date

from database import CalibrationRepository


def build_html_body(instruments: List[dict], reminder_days: int) -> str:
    rows = []
    for inst in instruments:
        rows.append(
            f"<tr>"
            f"<td>{inst['tag_number']}</td>"
            f"<td>{inst.get('description','')}</td>"
            f"<td>{inst.get('location','')}</td>"
            f"<td>{inst.get('calibration_type','')}</td>"
            f"<td>{inst.get('destination_name','')}</td>"
            f"<td>{inst.get('next_due_date','')}</td>"
            f"</tr>"
        )

    table_html = (
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr>"
        "<th>Tag</th><th>Description</th><th>Location</th>"
        "<th>Type</th><th>Destination</th><th>Next Due</th>"
        "</tr>"
        + "".join(rows)
        + "</table>"
    )

    body = (
        f"<p>The following instruments are due for calibration within the next "
        f"{reminder_days} day(s):</p>"
        f"{table_html}"
        "<p>This is an automated reminder.</p>"
    )
    return body


def build_text_body(instruments: List[dict], reminder_days: int) -> str:
    lines = [
        f"Instruments due for calibration within the next {reminder_days} day(s):",
        "",
    ]
    for inst in instruments:
        line = (
            f"Tag: {inst['tag_number']}, "
            f"Desc: {inst.get('description','')}, "
            f"Loc: {inst.get('location','')}, "
            f"Type: {inst.get('calibration_type','')}, "
            f"Dest: {inst.get('destination_name','')}, "
            f"Next Due: {inst.get('next_due_date','')}"
        )
        lines.append(line)
    lines.append("")
    lines.append("This is an automated reminder.")
    return "\n".join(lines)


def send_email(smtp_conf: dict, recipients: List[str],
               subject: str, html_body: str, text_body: str):
    if not recipients:
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_conf["from"]
    msg["To"] = ", ".join(recipients)

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    host = smtp_conf.get("host")
    port = int(smtp_conf.get("port", 587))
    username = smtp_conf.get("username")
    password = smtp_conf.get("password")
    use_tls = smtp_conf.get("tls", "1") != "0"

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls()
        if username:
            server.login(username, password)
        server.send_message(msg)


def send_due_reminders(repo: CalibrationRepository) -> int:
    """Headless reminder logic. Returns number of instruments included."""
    reminder_days = int(repo.get_setting("reminder_days", 14))
    instruments = repo.get_due_instruments(reminder_days)
    if not instruments:
        return 0

    recipients = repo.get_active_recipient_emails()
    if not recipients:
        # No one to email. Very effective notification strategy.
        return 0

    subject_template = repo.get_setting(
        "email_subject",
        "Calibration Reminder: {COUNT} instrument(s) due in {DAYS} day(s)",
    )
    body_template = repo.get_setting(
        "email_body",
        "This is an automated calibration reminder for {COUNT} instrument(s) "
        "due in the next {DAYS} day(s).\n\n{LIST}\n",
    )

    count = len(instruments)
    subject = subject_template.format(COUNT=count, DAYS=reminder_days)

    # Basic text list for template
    text_list = []
    for inst in instruments:
        text_list.append(
            f"{inst['tag_number']} - {inst.get('description','')} "
            f"(Due {inst.get('next_due_date','')})"
        )
    list_text = "\n".join(text_list)

    text_body = body_template.format(COUNT=count, DAYS=reminder_days, LIST=list_text)
    html_body = build_html_body(instruments, reminder_days)

    smtp_conf = {
        "host": repo.get_setting("smtp_host"),
        "port": repo.get_setting("smtp_port", "587"),
        "username": repo.get_setting("smtp_username", ""),
        "password": repo.get_setting("smtp_password", ""),
        "from": repo.get_setting("smtp_from", "calibration@localhost"),
        "tls": repo.get_setting("smtp_tls", "1"),
    }

    if not smtp_conf["host"]:
        # Misconfigured SMTP; bail.
        return 0

    send_email(smtp_conf, recipients, subject, html_body, text_body)

    ids = [inst["id"] for inst in instruments]
    repo.log_reminders(ids)
    return len(instruments)
