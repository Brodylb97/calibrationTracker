# build_update_package.py
"""
Create the zip package used by the in-app updater.
The zip must contain the *built* CalibrationTracker.exe and RestartHelper.exe
(not just source code), so that when users update, they get the new UI and features.

Run after build_executable.bat (and restart_helper\\build.bat). Output:
  installer\\CalibrationTracker-windows.zip

Upload that file to GitHub Releases as the release asset (e.g. for v1.3.0).
Name the asset exactly: CalibrationTracker-windows.zip
Then in-app "Check for updates" will download it and replace the exe.
"""

import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DIST = SCRIPT_DIR / "dist"
OUTPUT_ZIP = SCRIPT_DIR / "installer" / "CalibrationTracker-windows.zip"

# Same files the installer puts in {app} (plus pdf_export for runtime)
FILES = [
    ("dist/CalibrationTracker.exe", "CalibrationTracker.exe"),
    ("dist/RestartHelper.exe", "RestartHelper.exe"),
    ("update_app.py", "update_app.py"),
    ("update_checker.py", "update_checker.py"),
    ("update_config.example.json", "update_config.example.json"),
    ("VERSION", "VERSION"),
    ("AHI_logo.png", "AHI_logo.png"),
    ("USER_GUIDE.md", "USER_GUIDE.md"),
    ("pdf_export.py", "pdf_export.py"),
]
# Signatures folder
SIGNATURES_DIR = SCRIPT_DIR / "Signatures"


def main():
    if not (DIST / "CalibrationTracker.exe").exists():
        print("ERROR: dist/CalibrationTracker.exe not found. Run build_executable.bat first.")
        raise SystemExit(1)
    if not (DIST / "RestartHelper.exe").exists():
        print("WARNING: dist/RestartHelper.exe not found. Run restart_helper\\build.bat and copy to dist\\")

    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for src_rel, arc_name in FILES:
            src = SCRIPT_DIR / src_rel
            if not src.exists():
                print(f"WARNING: skipping missing {src_rel}")
                continue
            zf.write(src, arc_name)

        for f in SIGNATURES_DIR.iterdir():
            if f.is_file():
                zf.write(f, f"Signatures/{f.name}")

    print(f"Created: {OUTPUT_ZIP}")
    print("")
    print("REQUIRED for in-app 'Check for Updates' to deliver this build:")
    print("  1. Create a new GitHub Release (tag version to match VERSION file)")
    print("  2. Upload this file as asset name exactly: CalibrationTracker-windows.zip")
    print("  URL will be: https://github.com/Brodylb97/calibrationTracker/releases/latest/download/CalibrationTracker-windows.zip")
    print("  Without uploading, users will not receive this update when they click Update.")


if __name__ == "__main__":
    main()
