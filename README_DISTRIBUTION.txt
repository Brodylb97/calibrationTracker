Calibration Tracker - Distribution Package
==========================================

This package contains everything needed to build and distribute the Calibration Tracker application.

QUICK START
-----------
1. Install Python 3.8+ and dependencies:
   py -m pip install -r requirements.txt

2. Build executable:
   build_executable.bat

3. Create installer:
   - Install Inno Setup from https://jrsoftware.org/isdl.php
   - Open CalibrationTracker.iss in Inno Setup and use Build > Compile (F9)
   - Or run build_installer.bat to build the exe and compile the installer in one go (if ISCC is on PATH or in default install)

FILES INCLUDED
--------------
- *.py                    : Python source files (including database_backup.py, update_checker.py, update_app.py, pdf_export.py)
- requirements.txt       : Python dependencies
- build_executable.bat    : Script to build standalone executable (uses py)
- scripts/build_update_package.py : Script to create update zip (run after build_executable.bat; upload to GitHub Releases)
- build_distribution.bat  : Script to create source distribution folder
- build_installer.bat     : Script to build exe then compile Inno installer in one go
- CalibrationTracker.iss : Inno Setup installer script
- BUILD_INSTRUCTIONS.md   : Detailed build instructions
- USER_GUIDE.md           : User documentation
- update_config.json      : Update checker config (remote version URL, package URL, etc.)
- VERSION                 : Current version (used by Help > Check for Updates)

FEATURES
--------
- Instrument and calibration tracking with templates, signatures, and PDF export (single or all calibrations)
- Themes: Help > Theme (Fusion, Taylor's Theme, Tess's Theme, Retina Seering, Vice); choice saved
- Text size: Help > Text Size (Small, Medium, Large, Extra Large); choice saved
- Automatic daily database backups (stored in backups/, kept 30 days)
- Help > Check for Updates: manual check shows "already current" or offers update; startup check only prompts when an update is available or the check fails
- LAN reminders for instruments due for calibration

DEPENDENCIES
------------
- PyQt5 >= 5.15.0
- reportlab >= 3.6.0
- Pillow >= 9.0.0

For detailed build steps, see BUILD_INSTRUCTIONS.md.
For usage, see USER_GUIDE.md.
