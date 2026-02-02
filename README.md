# Calibration Tracker

A desktop application for managing instrument calibrations: track instruments, record calibrations with templates and signatures, export to CSV/PDF, and send LAN reminders for due calibrations.

## Features

- **Instrument management** — ID, location, type, serial number, next due date, status
- **Calibration records** — Templates with custom fields, signatures, autofill, and external-file attachments
- **Visual indicators** — Color-coded table for overdue and upcoming due dates
- **Export** — Current view to CSV; single calibration or all calibrations to PDF (instrument info, template, values; AHI logo on in-house exports)
- **LAN reminders** — Broadcast reminders for instruments due for calibration
- **Automatic backups** — Daily database backups in `backups/` (30-day retention)
- **Themes** — Help → Theme: Fusion, Taylor's Theme, Tess's Theme, Retina Seering, Vice (choice saved locally)
- **Text size** — Help → Text Size: Small, Medium, Large, Extra Large (choice saved locally)
- **Check for updates** — Help → Check for Updates (manual check shows “already current” or offers update; startup check only prompts when an update is available or the check fails). For installed users to receive new UI and features, releases must include a built update zip; see BUILD_INSTRUCTIONS.md.

## Requirements

- Python 3.8+
- PyQt5, reportlab, Pillow (see `requirements.txt`)

## Run from source

```bash
py -m pip install -r requirements.txt
py main.py
```

## Configuration

The database path can be configured for different environments (dev, staging, other sites):

1. **Config file**: Copy `config.example.json` to `config.json` and set `db_path` to your database path (absolute or relative to the config file).
2. **Alternative**: Add `db_path` to `update_config.json` if you already use it for update settings.
3. **Environment variable**: Set `CALIBRATION_TRACKER_DB_PATH` to override any config file.

If none of these are set, the app uses the default path (see `config.example.json`). The config file must be in the same directory as the executable or script.

## Build executable and installer

1. **Executable only:**  
   `build_executable.bat` → produces `dist\CalibrationTracker.exe` (run `restart_helper\build.bat` first if you need RestartHelper for updates).

2. **Executable + installer:**  
   `build_installer.bat` (builds exe then compiles `CalibrationTracker.iss` with Inno Setup if ISCC is available), or run `build_executable.bat` then open `CalibrationTracker.iss` in Inno Setup and compile.

3. **Update package (for in-app updates):**  
   After building the exe, run `py scripts/build_update_package.py` → produces `installer\CalibrationTracker-windows.zip`. Upload that file to a GitHub Release (asset name: `CalibrationTracker-windows.zip`) so “Check for Updates” delivers the new exe and UI to installed users.

4. **Source distribution folder:**  
   `build_distribution.bat` → creates `dist\CalibrationTracker\` with all sources and docs.

See **BUILD_INSTRUCTIONS.md** for full steps and **USER_GUIDE.md** for usage.

## Documentation

- **USER_GUIDE.md** — Full user guide (getting started, instruments, calibrations, templates, export, settings, updates, troubleshooting)
- **BUILD_INSTRUCTIONS.md** — Build and distribution instructions
- **README_DISTRIBUTION.txt** — Short overview for the distribution package

## Version

The current version is in the **VERSION** file and is used by the in-app update check (Help → Check for Updates).
