# lan_notify.py

import socket
from database import CalibrationRepository  # optional, for type hints


BROADCAST_PORT = 50555
BROADCAST_ADDR = "<broadcast>"


def build_due_message(due_instruments, days: int) -> str:
    lines = [
        "Calibration reminder",
        f"Instruments due within {days} day(s):",
        "",
    ]
    for inst in due_instruments:
        lines.append(
            f"- {inst['tag_number']} "
            f"(Loc: {inst.get('location','')}, "
            f"Type: {inst.get('calibration_type','')}, "
            f"Due: {inst.get('next_due_date','')}, "
            f"Dest: {inst.get('destination_name','')})"
        )
    return "\n".join(lines)


def send_lan_broadcast(message: str) -> None:
    data = message.encode("utf-8", errors="replace")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(data, (BROADCAST_ADDR, BROADCAST_PORT))
    finally:
        sock.close()


def send_due_reminders_via_lan(repo: CalibrationRepository) -> int:
    """
    Get instruments due within reminder_days and broadcast a LAN message.
    Returns number of instruments included.
    """
    days = int(repo.get_setting("reminder_days", 14))
    due = repo.get_due_instruments(days)
    if not due:
        return 0

    msg = build_due_message(due, days)
    send_lan_broadcast(msg)

    # No log_reminders call: every run will resend for anything in date range
    return len(due)
