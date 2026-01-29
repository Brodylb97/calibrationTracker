# lan_notify.py

import logging
import socket
import time
from database import CalibrationRepository  # optional, for type hints

logger = logging.getLogger(__name__)

BROADCAST_PORT = 50555
BROADCAST_ADDR = "<broadcast>"
DEFAULT_RETRIES = 3
RETRY_DELAY_SEC = 0.5


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


def send_lan_broadcast(message: str, retries: int = DEFAULT_RETRIES) -> bool:
    """
    Broadcast message on LAN. Retries on failure. Returns True if sent at least once.
    Logs failures.
    """
    data = message.encode("utf-8", errors="replace")
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(2.0)
                sock.sendto(data, (BROADCAST_ADDR, BROADCAST_PORT))
                logger.info("LAN broadcast sent (attempt %s)", attempt + 1)
                return True
            finally:
                sock.close()
        except Exception as e:
            last_err = e
            logger.warning("LAN broadcast attempt %s failed: %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY_SEC)
    if last_err:
        logger.error("LAN broadcast failed after %s attempts: %s", retries, last_err)
    return False


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
    if not send_lan_broadcast(msg):
        logger.warning("LAN reminder broadcast failed for %s instrument(s)", len(due))

    # No log_reminders call: every run will resend for anything in date range
    return len(due)
