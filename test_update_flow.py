"""
Simulate the installed exe triggering an update.
Run from project root. Uses test_install/ as the "installed" app dir.
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_INSTALL = ROOT / "test_install"

def main():
    if not TEST_INSTALL.is_dir():
        print("ERROR: test_install/ not found. Create it first.")
        sys.exit(1)
    exe = TEST_INSTALL / "CalibrationTracker.exe"
    updater_exe = TEST_INSTALL / "CalibrationTrackerUpdater.exe"
    if not exe.is_file():
        print("ERROR: CalibrationTracker.exe not in test_install/")
        sys.exit(1)
    if not updater_exe.is_file():
        print("ERROR: CalibrationTrackerUpdater.exe not in test_install/")
        sys.exit(1)

    # Simulate frozen app: update_checker uses _app_base_dir() = Path(sys.executable).parent
    sys.frozen = True
    sys.executable = str(exe)

    # Must import after mocking, and we need the module to see test_install as app dir
    sys.path.insert(0, str(ROOT))
    os.chdir(str(TEST_INSTALL))

    from update_checker import trigger_update_script, _app_base_dir

    app_dir = _app_base_dir()
    print("Simulated app dir (frozen):", app_dir)
    print("Updater exe exists:", (app_dir / "CalibrationTrackerUpdater.exe").is_file())

    # Trigger update (fake PID so updater doesn't wait)
    ok = trigger_update_script(wait_for_pid=999999, config_path=TEST_INSTALL / "update_config.json")
    print("trigger_update_script returned:", ok)

    if ok:
        print("Updater was started. Check %TEMP%\\CalibrationTracker_updater.log for output.")
        # Give updater a moment to run
        import time
        time.sleep(5)
    else:
        print("FAIL: Updater was NOT started.")
        sys.exit(1)

if __name__ == "__main__":
    main()
