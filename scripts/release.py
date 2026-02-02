#!/usr/bin/env python3
"""
Run the full release sequence in order:
  1. Update version (prompt if not given)
  2. Build executable (PyInstaller)
  3. Build update package (CalibrationTracker-windows.zip)
  4. Build installer (Inno Setup)
  5. Git commit (VERSION + CalibrationTracker.iss)

Run from project root: python scripts/release.py

Usage:
  py scripts/release.py              # prompt for version
  py scripts/release.py 1.3.6        # use version 1.3.6
  py scripts/release.py --no-commit  # do everything except git commit
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
ISS_FILE = PROJECT_ROOT / "CalibrationTracker.iss"
VERSION_DEFINE_RE = re.compile(r'^#define\s+MyAppVersion\s+"[^"]*"', re.MULTILINE)


def get_current_version() -> str:
    if not VERSION_FILE.is_file():
        return "0.0.0"
    return VERSION_FILE.read_text(encoding="utf-8").strip().split("\n")[0].strip()


def set_version(version: str) -> None:
    version = version.strip()
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise SystemExit(f"Invalid version format. Use e.g. 1.3.6 (major.minor.patch). Got: {version!r}")
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    print(f"  Updated {VERSION_FILE.name} -> {version}")

    text = ISS_FILE.read_text(encoding="utf-8")
    new_line = f'#define MyAppVersion "{version}"'
    if not VERSION_DEFINE_RE.search(text):
        raise SystemExit(f"Could not find MyAppVersion in {ISS_FILE.name}")
    text = VERSION_DEFINE_RE.sub(new_line, text, count=1)
    ISS_FILE.write_text(text, encoding="utf-8")
    print(f"  Updated {ISS_FILE.name} MyAppVersion -> {version}")


def run_cmd(cmd: list[str], step_name: str) -> None:
    print(f"\n--- {step_name} ---")
    try:
        subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise SystemExit(e.returncode or 1)


def build_executable() -> None:
    """Run PyInstaller build (same as build_executable.bat, no pause)."""
    print("\n--- 2. Build executable ---")
    build_dir = PROJECT_ROOT / "build"
    dist_dir = PROJECT_ROOT / "dist"
    spec_file = PROJECT_ROOT / "CalibrationTracker.spec"
    for p in [build_dir, dist_dir]:
        if p.exists():
            import shutil
            shutil.rmtree(p)
    if spec_file.exists():
        spec_file.unlink()
    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name=CalibrationTracker",
        "--onefile",
        "--windowed",
        "--icon=cal_tracker.ico",
        "--add-data", "Signatures;Signatures",
        "--hidden-import=PyQt5",
        "--hidden-import=reportlab",
        "--hidden-import=requests",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=sqlite3",
        "--hidden-import=database_backup",
        "--collect-all", "reportlab",
        "--collect-all", "PyQt5",
        "main.py",
    ]
    run_cmd(pyinstaller_args, "PyInstaller build")
    restart_helper = PROJECT_ROOT / "restart_helper" / "RestartHelper.exe"
    dist_exe = PROJECT_ROOT / "dist" / "RestartHelper.exe"
    if restart_helper.is_file():
        import shutil
        shutil.copy2(restart_helper, dist_exe)
        print("  RestartHelper.exe copied to dist\\")
    else:
        print("  WARNING: restart_helper\\RestartHelper.exe not found.")


def find_iscc() -> Path | None:
    import shutil
    exe = shutil.which("iscc")
    if exe:
        return Path(exe)
    pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", "C:\\Program Files")
    for base in [Path(pf86), Path(pf)]:
        p = base / "Inno Setup 6" / "ISCC.exe"
        if p.is_file():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full release: update version, build exe, update zip, installer, git commit."
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="New version (e.g. 1.3.6). If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not run git commit at the end.",
    )
    args = parser.parse_args()

    version = args.version
    if not version:
        current = get_current_version()
        version = input(f"New version (current {current}, e.g. 1.3.6): ").strip()
        if not version:
            raise SystemExit("No version provided. Aborting.")

    print("========================================")
    print("Calibration Tracker - Full Release")
    print("========================================")

    # 1. Update version
    print("\n1. Updating version...")
    set_version(version)

    # 2. Build executable
    build_executable()

    # 3. Build update package
    run_cmd([sys.executable, "scripts/build_update_package.py"], "3. Build update package")

    # 4. Build installer
    iscc = find_iscc()
    if not iscc:
        print("\n--- 4. Build installer ---")
        print("Inno Setup (ISCC) not found. Skipping installer.")
        print("  To build manually: open CalibrationTracker.iss in Inno Setup and compile.")
    else:
        run_cmd([str(iscc), str(ISS_FILE)], "4. Build installer")

    # 5. Git commit
    if args.no_commit:
        print("\n--- 5. Git commit ---")
        print("Skipped (--no-commit).")
    else:
        print("\n--- 5. Git commit ---")
        run_cmd(["git", "add", str(VERSION_FILE), str(ISS_FILE)], "  git add")
        r = subprocess.run(
            ["git", "commit", "-m", f"v{version}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            if "nothing to commit" in (r.stderr or "") or "nothing to commit" in (r.stdout or ""):
                print("  Nothing to commit (version unchanged).")
            else:
                print(r.stderr or r.stdout)
                raise SystemExit(r.returncode)
        else:
            print(r.stdout or "  Committed.")

    print("\n========================================")
    print("Release complete.")
    print("  - Executable: dist\\CalibrationTracker.exe")
    print("  - Update zip: installer\\CalibrationTracker-windows.zip")
    if iscc:
        print("  - Installer:  installer\\CalibrationTracker_Setup.exe")
    print("  Next: create GitHub Release, upload the zip, then git push if desired.")
    print("========================================")


if __name__ == "__main__":
    main()
