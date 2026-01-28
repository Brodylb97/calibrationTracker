# Calibration Tracker - Build Instructions

This document provides step-by-step instructions for creating a distribution package and installer for the Calibration Tracker application.

## One-command release (recommended)

To run the full release sequence in order (update version, build exe, build update zip, build installer, git commit), use:

```batch
py release.py              REM prompts for version
py release.py 1.3.6        REM use version 1.3.6
py release.py --no-commit  REM do everything except git commit
```

This runs: 1) Update VERSION and CalibrationTracker.iss, 2) Build executable (PyInstaller), 3) Build update package (CalibrationTracker-windows.zip), 4) Build installer (Inno Setup), 5) Git commit. You can then create a GitHub Release and upload the zip, and `git push` if desired.

## Prerequisites

1. **Python 3.8 or higher** - [Download Python](https://www.python.org/downloads/)
2. **PyInstaller** - Will be installed automatically by the build script
3. **Inno Setup** - [Download Inno Setup](https://jrsoftware.org/isdl.php) (free, open-source installer creator)

## Step 1: Prepare the Environment

1. Open a command prompt in the project directory
2. Install Python dependencies:
   ```batch
   py -m pip install -r requirements.txt
   ```
3. Install PyInstaller (if not already installed):
   ```batch
   py -m pip install pyinstaller
   ```

## Step 2: Build the Executable (for installer)

Run the executable build script (uses `py` and PyInstaller):
```batch
build_executable.bat
```

This will:
- Use PyInstaller to create a standalone executable
- Bundle all dependencies
- Include the Signatures folder
- Create `dist\CalibrationTracker.exe`

**Note:** The first build may take several minutes. Subsequent builds are faster.

**Optional – build exe and installer in one go:**
```batch
build_installer.bat
```
This runs `build_executable.bat` then compiles `CalibrationTracker.iss` with Inno Setup (if ISCC is on PATH or in the default Inno install). Otherwise it reminds you to compile the .iss file manually.

## Step 3: Build the Distribution Package (optional, for source bundle)

To create a source distribution folder (e.g. for archives or running from source), run:
```batch
build_distribution.bat
```

This creates a `dist\CalibrationTracker` folder containing:
- All Python source files (including database_backup.py for automatic backups)
- **Update checker files**: update_app.py, update_checker.py, update_config.json, update_config.example.json, VERSION
- Signatures folder, requirements.txt, USER_GUIDE.md, BUILD_INSTRUCTIONS.md, README.txt

**Note:** For the Windows installer you do **not** need to run build_distribution; run `build_executable.bat` then Inno Setup. The installer packs the exe from `dist\` and other files from the project root.

**Note:** The update checker (Help → Check for Updates) uses update_config.json and VERSION. These are installed by the Inno Setup installer so in-app update checks work.

### In-app updates (Check for Updates)

For **Check for Updates** to deliver new UI and features (not just a new VERSION number), the update package must contain the **built** CalibrationTracker.exe, not just source code. Do this for each release:

1. Update `VERSION` and `CalibrationTracker.iss` (MyAppVersion) to the new version (e.g. 1.3.0).
2. Run `build_executable.bat` (and `restart_helper\build.bat` if needed) so `dist\` has the new exe.
3. Create the update zip:
   ```batch
   py build_update_package.py
   ```
   This creates `installer\CalibrationTracker-windows.zip` with the exe, RestartHelper, and runtime files.
4. Create a **GitHub Release** for that version (e.g. v1.3.0), and **upload** `CalibrationTracker-windows.zip` as the release asset. Use the **exact** asset name: `CalibrationTracker-windows.zip`.
5. In-app "Check for Updates" will then download that zip and replace the installed exe, so users get the new themes, PDF export, and other code changes.

If you skip the release zip and only push source to GitHub, the updater would download the source zip (no exe), so the installed app would still run the old exe and new UI would not appear.

## Step 4: Create the Installer with Inno Setup

1. **Install Inno Setup** (if not already installed)  
   - Download from: https://jrsoftware.org/isdl.php  
   - Run the installer  

2. **Build the installer** (either method):
   - **Option A:** Run `build_installer.bat` (builds exe then compiles the .iss if ISCC is available), or  
   - **Option B:** Build the exe with `build_executable.bat`, then open Inno Setup Compiler, open `CalibrationTracker.iss`, and use Build → Compile (F9).

3. **Output:** The installer is created in the `installer` folder as `installer\CalibrationTracker_Setup.exe`.

4. **Customize the script** (optional) before compiling:
   - Update `MyAppPublisher` with your company name
   - Update `MyAppURL` with your website
   - Update `MyAppId` with a unique GUID (Tools → Generate GUID in Inno)
   - Keep `MyAppVersion` in CalibrationTracker.iss in sync with the `VERSION` file

## Step 5: Test the Executable

Before creating the installer, test the executable:
1. Navigate to the `dist` folder
2. Run `CalibrationTracker.exe`
3. Verify all features work correctly:
   - Application launches
   - Database is created on first run
   - Signatures folder is accessible
   - PDF export works
   - All dialogs function properly

## Step 6: Test the Installer

1. Run the installer on a test machine (or VM)
2. Verify:
   - Installation completes successfully
   - Application launches from Start Menu
   - Application creates database on first run
   - Signatures folder is accessible
   - All features work correctly

## Troubleshooting

### Executable won't run
- Check that all dependencies are included
- Verify Python version compatibility
- Check Windows Event Viewer for error details
- Ensure all required DLLs are bundled

### Missing dependencies
- Add missing modules to `--hidden-import` in `build_executable.bat`
- Rebuild the executable

### Installer issues
- Verify file paths in `CalibrationTracker.iss` are correct
- Ensure the executable exists in the `dist` folder
- Check that Inno Setup has write permissions

### Database location
- The application creates the database in the installation directory by default
- Users can specify a different location via command-line arguments
- For network installations, modify `database.py` to use a network path

## Distribution Checklist

Before distributing the installer:

- [ ] Executable has been tested on clean Windows systems
- [ ] All features work correctly
- [ ] Signatures folder is included and accessible
- [ ] Documentation (USER_GUIDE.md) is included
- [ ] Installer has been tested
- [ ] Application creates database on first run
- [ ] Database backup system works (check backups/ folder after first run)
- [ ] PDF export functionality works
- [ ] No console window appears (windowed mode)
- [ ] Application icon is set (if available)
- [ ] Version information is correct
- [ ] Publisher information is correct
- [ ] Update checker files (update_app.py, update_checker.py, update_config.json, VERSION) are included in installer
- [ ] Help → Check for Updates works (uses VERSION and update_config.json from install dir)

## New Features in This Version

### Database Backup System
- **Automatic daily backups**: The application automatically creates a database backup once per day
- **Backup location**: Backups are stored in a `backups/` folder next to the database file
- **Automatic cleanup**: Old backups are automatically removed after 30 days
- **Backup format**: Files are named `calibration_backup_YYYYMMDD_HHMMSS.db`
- **No user action required**: Backups happen automatically on application startup

### Database Optimizations
- **Performance improvements**: Added indexes to speed up common queries
- **Better concurrency**: Enabled WAL (Write-Ahead Logging) mode
- **Data integrity**: Improved foreign key constraints
- **Optimized queries**: Better query performance for large datasets

## Advanced: Customizing the Build

### Adding an Icon
1. Create or obtain a `.ico` file
2. Update `build_executable.bat`:
   ```batch
   --icon=path\to\your\icon.ico ^
   ```
3. Update `CalibrationTracker.iss`:
   ```
   SetupIconFile=path\to\your\icon.ico
   ```

### Including Additional Files
1. Add files to the `[Files]` section in `CalibrationTracker.iss`:
   ```
   Source: "path\to\file"; DestDir: "{app}"; Flags: ignoreversion
   ```
   The installer already includes update checker files: update_app.py, update_checker.py, update_config.json, update_config.example.json, VERSION.

### Network Database Setup
If using a network database, modify `database.py` before building to set the correct network path.

## Support

For issues or questions:
- Check the USER_GUIDE.md for usage instructions
- Review error logs in the `logs` folder
- Check the application's built-in help dialogs
