@echo off
REM Build RestartHelper.exe with MinGW gcc. Run from repo root or from restart_helper\.
cd /d "%~dp0"
where gcc >nul 2>&1
if errorlevel 1 (
    echo gcc not found. Install MinGW or add it to PATH.
    echo Then run: gcc -O2 -o RestartHelper.exe restart_helper.c -mwindows
    exit /b 1
)
gcc -O2 -o RestartHelper.exe restart_helper.c -mwindows
if errorlevel 1 exit /b 1
echo Built RestartHelper.exe
echo Copy to dist\RestartHelper.exe before building the installer.
