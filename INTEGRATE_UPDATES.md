# Integrating the Update Mechanism

## Configuration

- **Remote version URL**: Set in `update_config.json` as `remote_version_url` (e.g. `https://raw.githubusercontent.com/USER/REPO/BRANCH/VERSION`).
- **Remote package URL**: Set in `update_config.json` as `remote_package_url`. For installed users to receive **new UI and features** (not just a new version number), this must point to a **release zip that contains the built CalibrationTracker.exe**, e.g. `https://github.com/USER/REPO/releases/latest/download/CalibrationTracker-windows.zip`. Create that zip with `py scripts/build_update_package.py` (after `build_executable.bat`) and upload it to each GitHub Release as an asset named `CalibrationTracker-windows.zip`. See BUILD_INSTRUCTIONS.md.
- **Current version file**: Set in `update_config.json` as `current_version_file` (default: `VERSION`). The repo and the installed app should each have a `VERSION` file with a single line like `1.1`.

## Part 1 – Automated script

Run the updater manually or from the in-app "Update now" flow:

```bash
python update_app.py [--config path/to/update_config.json] [--wait-pid PID] [--skip-version-check]
```

When the user chooses "Update now", the app starts this script with `--wait-pid <current_pid>` and then exits so the script can replace files and restart the app.

## Part 2 – In-app update check

In your GUI entry point (e.g. `run_gui()` in `ui_main.py`), after creating the main window, call:

```python
try:
    from update_checker import install_update_check_into_main_window
    install_update_check_into_main_window(win, check_on_startup=True)
except Exception:
    pass
```

This adds a **Help → Check for Updates...** action and, if `check_on_startup=True`, runs the update check once shortly after the window is shown. When an update is available, the user sees a dialog with **Yes** (update now) / **No** (later). Choosing **Yes** starts `update_app.py` with `--wait-pid` and the app exits so the updater can run.

You can also use the functions directly:

- `is_update_available()` → `(available, current_str, latest_str, error)`
- `show_update_dialog(parent_widget)` → shows the prompt if an update is available
- `trigger_update_and_exit()` → start updater and exit (use when user clicks "Update now")

## Security

- Do not put credentials in `update_config.json`. Use public URLs (e.g. raw GitHub, or a public API).
- The example config uses GitHub raw/content URLs and does not require authentication.
