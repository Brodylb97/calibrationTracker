# Calibration Tracker

A desktop application for managing instrument calibrations: track instruments, record calibrations with templates and signatures, export to CSV/PDF, and send LAN reminders for due calibrations.

## Features

- **Instrument management** — ID, location, type, serial number, next due date, status
- **Calibration records** — Templates with custom fields, signatures, autofill, and external-file attachments
- **Visual indicators** — Color-coded table for overdue and upcoming due dates
- **Export** — Current view to CSV; calibrations to PDF (including attachments)
- **LAN reminders** — Broadcast reminders for instruments due for calibration
- **Automatic backups** — Daily database backups in `backups/` (30-day retention)
- **Check for updates** — Help → Check for Updates (manual check shows “already current” or offers update; startup check only prompts when an update is available or the check fails)

## Requirements

- Python 3.8+
- PyQt5, reportlab, Pillow (see `requirements.txt`)

## Run from source

```bash
py -m pip install -r requirements.txt
py main.py
```

## Build executable and installer

1. **Executable only:**  
   `build_executable.bat` → produces `dist\CalibrationTracker.exe`

2. **Executable + installer:**  
   `build_installer.bat` (builds exe then compiles `CalibrationTracker.iss` with Inno Setup if ISCC is available), or run `build_executable.bat` then open `CalibrationTracker.iss` in Inno Setup and compile.

3. **Source distribution folder:**  
   `build_distribution.bat` → creates `dist\CalibrationTracker\` with all sources and docs.

See **BUILD_INSTRUCTIONS.md** for full steps and **USER_GUIDE.md** for usage.

## Documentation

- **USER_GUIDE.md** — Full user guide (getting started, instruments, calibrations, templates, export, settings, updates, troubleshooting)
- **BUILD_INSTRUCTIONS.md** — Build and distribution instructions
- **README_DISTRIBUTION.txt** — Short overview for the distribution package

## Version

The current version is in the **VERSION** file and is used by the in-app update check (Help → Check for Updates).
