# scripts/build_update_package.py
"""
Create the zip package used by the in-app updater.
The zip must contain the *built* CalibrationTracker.exe and RestartHelper.exe
(not just source code), so that when users update, they get the new UI and features.

Run after build_executable.bat (and restart_helper\\build.bat). Output:
  installer\\CalibrationTracker-windows.zip

Run from project root: python scripts/build_update_package.py
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUTPUT_ZIP = ROOT / "installer" / "CalibrationTracker-windows.zip"

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
SIGNATURES_DIR = ROOT / "Signatures"


def main():
    if not (ROOT / "dist" / "CalibrationTracker.exe").exists():
        print("ERROR: dist/CalibrationTracker.exe not found. Run build_executable.bat first.")
        raise SystemExit(1)
    if not (ROOT / "dist" / "RestartHelper.exe").exists():
        print("WARNING: dist/RestartHelper.exe not found. Run restart_helper\\build.bat and copy to dist\\")

    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for src_rel, arc_name in FILES:
            src = ROOT / src_rel
            if not src.exists():
                print(f"WARNING: skipping missing {src_rel}")
                continue
            zf.write(src, arc_name)

        for f in SIGNATURES_DIR.iterdir():
            if f.is_file():
                zf.write(f, f"Signatures/{f.name}")

    print(f"Created: {OUTPUT_ZIP}")
    print("Upload this file to GitHub Releases as asset name: CalibrationTracker-windows.zip")
    print("URL will be: https://github.com/Brodylb97/calibrationTracker/releases/latest/download/CalibrationTracker-windows.zip")


if __name__ == "__main__":
    main()
