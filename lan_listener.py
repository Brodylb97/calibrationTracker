# lan_listener.py – no win10toast, just native Windows message boxes

import os
import socket
import threading
import time
import ctypes

BROADCAST_PORT = 50555  # must match sender
BUFFER_SIZE = 8192


def _quiet_hours_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "CalibrationTracker", "quiet_hours.txt")


def _in_quiet_hours():
    """True if current time is within quiet hours (no popup)."""
    try:
        path = _quiet_hours_path()
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if len(lines) < 2:
            return False
        start_s, end_s = lines[0].strip(), lines[1].strip()
        if not start_s or not end_s or (start_s == "00:00" and end_s == "00:00"):
            return False
        now = time.localtime()
        now_min = now.tm_hour * 60 + now.tm_min
        def parse(s):
            parts = s.split(":")
            return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
        start_min, end_min = parse(start_s), parse(end_s)
        if start_min <= end_min:
            return start_min <= now_min < end_min
        return now_min >= start_min or now_min < end_min
    except Exception:
        return False


def show_notification(message: str):
    """
    Simple, bulletproof Windows popup. Skipped during quiet hours (still logged).
    """
    if _in_quiet_hours():
        return
    ctypes.windll.user32.MessageBoxW(
        0,
        message,
        "Calibration Reminder",
        0x40,  # MB_ICONINFORMATION
    )


def listen_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", BROADCAST_PORT))  # listen on all interfaces
    print(f"Listening for calibration broadcasts on UDP port {BROADCAST_PORT}...")
    while True:
        data, addr = sock.recvfrom(BUFFER_SIZE)
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = "<invalid utf-8 data>"
        print(f"Message from {addr}:")
        print(text)
        if _in_quiet_hours():
            print("(Quiet hours: popup suppressed)")
        else:
            show_notification(text)

def main():
    t = threading.Thread(target=listen_loop, daemon=True)
    t.start()

    print("LAN notification listener running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting listener.")

if __name__ == "__main__":
    main()
