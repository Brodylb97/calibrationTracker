@echo off
REM Build CalibrationTrackerUpdater.exe - standalone updater (no Python on PATH needed).
REM Run after build_executable.bat. Output: dist\CalibrationTrackerUpdater.exe

echo ========================================
echo Calibration Tracker - Build Updater
echo ========================================
echo.

py -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not installed. Run build_executable.bat first.
    pause
    exit /b 1
)

if not exist dist\CalibrationTracker.exe (
    echo dist\CalibrationTracker.exe not found. Run build_executable.bat first.
    pause
    exit /b 1
)

echo Building CalibrationTrackerUpdater.exe...
py -m PyInstaller --name=CalibrationTrackerUpdater ^
    --onefile ^
    --noconsole ^
    --hidden-import=requests ^
    update_app.py

if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo Updater built: dist\CalibrationTrackerUpdater.exe
echo Include this in the installer and update zip so "Update now" works without Python on PATH.
echo.
pause
