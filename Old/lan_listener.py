# lan_listener.py – no win10toast, just native Windows message boxes

import socket
import threading
import time
import ctypes

BROADCAST_PORT = 50555  # must match sender
BUFFER_SIZE = 8192

def show_notification(message: str):
    """
    Simple, bulletproof Windows popup.
    """
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
