@echo off
REM Build executable using PyInstaller
REM This creates a standalone executable that can be packaged with Inno Setup

echo ========================================
echo Calibration Tracker - Build Executable
echo ========================================
echo.

REM Check if PyInstaller is installed
py -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed!
    echo Installing PyInstaller...
    py -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller!
        pause
        exit /b 1
    )
)

REM Clean previous build
echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist CalibrationTracker.spec del CalibrationTracker.spec

REM Build executable
echo Building executable with PyInstaller...
echo.

py -m PyInstaller --name=CalibrationTracker ^
    --onefile ^
    --windowed ^
    --icon=cal_tracker.ico ^
    --add-data "Signatures;Signatures" ^
    --hidden-import=PyQt5 ^
    --hidden-import=reportlab ^
    --hidden-import=requests ^
    --hidden-import=PIL ^
    --hidden-import=PIL.Image ^
    --hidden-import=sqlite3 ^
    --hidden-import=database_backup ^
    --collect-all reportlab ^
    --collect-all PyQt5 ^
    main.py

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo Executable location: dist\CalibrationTracker.exe
echo ========================================
echo.
echo Next steps:
echo 1. Test the executable
echo 2. Create installer using Inno Setup with CalibrationTracker.iss
echo.
pause
