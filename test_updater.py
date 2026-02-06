#!/usr/bin/env python
"""
One-off script to test the updater path without starting the full GUI.
Run from project root:  python test_updater.py
"""
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

def main():
    print("=== Calibration Tracker – Updater diagnostic ===\n")
    # 1. Update checker
    from update_checker import is_update_available, get_current_version, trigger_update_script, _app_base_dir
    app_dir = _app_base_dir()
    print("1. App dir (install/source):", app_dir)
    print("2. Running from frozen exe:", getattr(sys, "frozen", False))
    updater_exe = app_dir / "CalibrationTrackerUpdater.exe"
    updater_script = app_dir / "update_app.py"
    print("3. CalibrationTrackerUpdater.exe exists:", updater_exe.is_file(), "(no Python on PATH needed)" if updater_exe.is_file() else "")
    print("4. update_app.py exists:", updater_script.is_file())
    print("5. update_config.json exists:", (app_dir / "update_config.json").is_file())
    try:
        import shutil
        py = shutil.which("python") or shutil.which("python3")
        print("6. Python on PATH:", py or "(not needed if CalibrationTrackerUpdater.exe exists)" if updater_exe.is_file() else "(required if no updater exe)")
    except Exception as e:
        print("6. Python on PATH: (check failed)", e)
    avail, cur, latest, err = is_update_available()
    print("7. Current version:", cur)
    print("8. Latest version (remote):", latest)
    print("9. Update available:", avail)
    print("10. Error from check:", err or "(none)")
    log_path = Path(os.environ.get("TEMP", ".")) / "CalibrationTracker_updater.log"
    print("11. Updater log file:", log_path)
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        print("    Last 5 lines:")
        for line in lines[-5:]:
            print("   ", line.rstrip())
    else:
        print("    (log not created yet – run Help > Check for Updates > Update now once)")
    print("\nTo test the updater (no GUI): run:")
    print("  python update_app.py --config update_config.json --wait-pid 999999")
    print("(999999 is a non-existent PID so it continues immediately; it will only check version and exit.)")

if __name__ == "__main__":
    main()
