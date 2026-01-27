@echo off
REM Build script for Calibration Tracker distribution
REM Prepares a distribution-ready folder for building the executable and Inno Setup installer.
REM Includes update checker files (update_app.py, update_checker.py, update_config.json, VERSION).

echo ========================================
echo Calibration Tracker - Build Distribution
echo ========================================
echo.

set APP_NAME=CalibrationTracker
set DIST_DIR=dist
set BUILD_DIR=%DIST_DIR%\%APP_NAME%

REM Clean previous distribution folder (keep dist if it only has the exe from build_executable)
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
if not exist %DIST_DIR% mkdir %DIST_DIR%

REM Create directory structure
echo Creating directory structure...
mkdir %BUILD_DIR%
mkdir %BUILD_DIR%\Signatures
mkdir %BUILD_DIR%\logs

REM Copy Python source files
echo Copying Python source files...
copy *.py %BUILD_DIR%\ >nul 2>&1
if exist %BUILD_DIR%\__pycache__ rmdir /s /q %BUILD_DIR%\__pycache__

REM Copy icon and logo
if exist cal_tracker.ico copy cal_tracker.ico %BUILD_DIR%\ >nul 2>&1
if exist AHI_logo.png copy AHI_logo.png %BUILD_DIR%\ >nul 2>&1

REM Copy update checker files (for "Check for Updates" and in-app updater)
echo Copying update checker files...
if exist update_app.py copy update_app.py %BUILD_DIR%\ >nul 2>&1
if exist update_checker.py copy update_checker.py %BUILD_DIR%\ >nul 2>&1
if exist update_config.json copy update_config.json %BUILD_DIR%\ >nul 2>&1
if exist update_config.example.json copy update_config.example.json %BUILD_DIR%\ >nul 2>&1
if exist VERSION copy VERSION %BUILD_DIR%\ >nul 2>&1

REM Copy Signatures folder
if exist Signatures\*.png (
    copy Signatures\*.png %BUILD_DIR%\Signatures\ >nul 2>&1
)
if exist Signatures\*.jpg (
    copy Signatures\*.jpg %BUILD_DIR%\Signatures\ >nul 2>&1
)

REM Copy documentation
echo Copying documentation...
if exist USER_GUIDE.md copy USER_GUIDE.md %BUILD_DIR%\ >nul 2>&1
if exist INTEGRATE_UPDATES.md copy INTEGRATE_UPDATES.md %BUILD_DIR%\ >nul 2>&1

REM Copy requirements
if exist requirements.txt copy requirements.txt %BUILD_DIR%\ >nul 2>&1

REM Create README for distribution
(
echo Calibration Tracker - Distribution Package
echo =========================================
echo.
echo Includes update checker: Help - Check for Updates, update_app.py, VERSION, update_config.json.
echo.
echo To build the installer:
echo 1. Run build_executable.bat to create dist\CalibrationTracker.exe
echo 2. Run Inno Setup with CalibrationTracker.iss
echo.
) > %BUILD_DIR%\README.txt

echo.
echo ========================================
echo Build complete!
echo Distribution folder: %BUILD_DIR%
echo ========================================
echo.
echo Next steps:
echo 1. Run build_executable.bat to create dist\CalibrationTracker.exe
echo 2. Create installer using Inno Setup with CalibrationTracker.iss
echo.
pause
