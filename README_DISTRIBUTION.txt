Calibration Tracker - Distribution Package
==========================================

This package contains everything needed to build and distribute the Calibration Tracker application.

QUICK START
-----------
1. Install Python 3.8+ and dependencies:
   pip install -r requirements.txt

2. Build executable:
   build_executable.bat

3. Create installer:
   - Install Inno Setup from https://jrsoftware.org/isdl.php
   - Open CalibrationTracker.iss in Inno Setup
   - Build > Compile (F9)

FILES INCLUDED
--------------
- *.py                    : Python source files (including database_backup.py)
- requirements.txt         : Python dependencies
- build_executable.bat     : Script to build standalone executable
- build_distribution.bat   : Script to create distribution folder
- CalibrationTracker.iss   : Inno Setup installer script
- BUILD_INSTRUCTIONS.md    : Detailed build instructions
- USER_GUIDE.md           : User documentation

NEW FEATURES
------------
- database_backup.py      : Automatic daily database backup system
- Optimized database schema with indexes for better performance
- Automatic backup cleanup (keeps last 30 days)

DEPENDENCIES
------------
- PyQt5 >= 5.15.0
- reportlab >= 3.6.0
- Pillow >= 9.0.0

For detailed instructions, see BUILD_INSTRUCTIONS.md
