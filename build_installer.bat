@echo off
REM Build executable then compile Inno Setup installer in one go.
REM Requires: py, PyInstaller, and Inno Setup (ISCC) on PATH or in default install dir.

echo ========================================
echo Calibration Tracker - Build Executable + Installer
echo ========================================
echo.

call build_executable.bat
if errorlevel 1 (
    echo Installer build aborted (executable build failed).
    pause
    exit /b 1
)

echo.
echo Compiling installer with Inno Setup...
echo.

set ISCC=
where iscc >nul 2>&1
if %errorlevel% equ 0 (
    set ISCC=iscc
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    "%ISCC%" "CalibrationTracker.iss"
    if errorlevel 1 (
        echo Inno Setup compile failed!
        pause
        exit /b 1
    )
    echo.
    echo ========================================
    echo Installer built: installer\CalibrationTracker_Setup.exe
    echo ========================================
) else (
    echo Inno Setup compiler (ISCC) not found on PATH or in default install.
    echo Open CalibrationTracker.iss in Inno Setup and compile manually (Build ^> Compile).
    pause
    exit /b 0
)

pause
