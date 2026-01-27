# RestartHelper stub

Small native executable used to reopen Calibration Tracker after an update. The app writes `exe_path` and `db_path` to `%APPDATA%\CalibrationTracker\restart_params.txt`, then a scheduled task runs `RestartHelper.exe`. The stub reads the file and launches the main exe with `--db <path>` and the correct working directory.

## Build

**From PowerShell (tries gcc then clang):**
```powershell
.\restart_helper\build.ps1
```
If you see “gcc/clang not found”, install a compiler then rerun in a **new** terminal:
- **winget:** `winget install -e --id MartinStorsjo.LLVM-MinGW.UCRT` (uses `clang`)
- **MSYS2:** open “MSYS2 MinGW 64-bit”, run `pacman -S mingw-w64-x86_64-gcc`, then build in that shell.

**MinGW / MSYS2 (gcc):**
```bash
gcc -O2 -o RestartHelper.exe restart_helper.c -mwindows
```

**MSVC:**
```cmd
cl /O2 restart_helper.c /link /SUBSYSTEM:WINDOWS /OUT:RestartHelper.exe
```

Place `RestartHelper.exe` in the same directory as `CalibrationTracker.exe` and include it in your installer/zip so the update flow can run it via the task.

**Build before installer:** From `restart_helper\`, run `build.ps1` or `build.bat`, then copy `RestartHelper.exe` to `dist\` so Inno Setup can include it.
