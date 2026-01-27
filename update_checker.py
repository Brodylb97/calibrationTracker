# update_checker.py
"""
In-app update check (Part 2).
Provides functions to check for updates from the same remote as update_app.py,
and to trigger the external update script. Use on startup or from a
"Check for Updates" menu/button.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Reuse config/version logic from update_app without circular imports
CONFIG_PATH_ENV = "CALIBRATION_TRACKER_UPDATE_CONFIG"


def _app_base_dir():
    """Directory containing the app (install dir when frozen, script dir when run from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_config_path():
    return _app_base_dir() / "update_config.json"


def _load_config(config_path=None):
    path = config_path or os.environ.get(CONFIG_PATH_ENV) or _default_config_path()
    path = Path(path)
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    app_dir = data.get("app_dir", ".")
    if not os.path.isabs(app_dir):
        app_dir = path.parent / app_dir
    data["_app_dir_resolved"] = Path(app_dir).resolve()
    return data


def _parse_version(version_string):
    if not version_string or not isinstance(version_string, str):
        return (0,)
    parts = version_string.strip().split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result) if result else (0,)


def get_current_version(config=None):
    """Return the current installed version string, or None if unknown."""
    if config is None:
        config = _load_config()
    if config is None:
        return None
    app_dir = config["_app_dir_resolved"]
    version_file = config.get("current_version_file", "VERSION")
    path = app_dir / version_file
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


# Headers that avoid 404s from GitHub raw CDN when it treats some clients as bots
_VERSION_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/plain,*/*",
}


def get_latest_version_from_remote(config=None, timeout_seconds=15):
    """
    Fetch the latest version string from the remote source (version URL in config).
    Tries the configured URL first, then GitHub API as fallback if the URL looks like raw.githubusercontent.
    Returns (version_string or None, error_message or None).
    """
    if config is None:
        config = _load_config()
    if config is None:
        return None, "Update config not found"
    url = config.get("remote_version_url")
    if not url:
        return None, "remote_version_url not set"

    def _fetch(u, headers=None):
        h = headers or _VERSION_FETCH_HEADERS
        try:
            import requests
            resp = requests.get(u, headers=h, timeout=timeout_seconds)
            if resp.status_code == 404:
                return None, "404"
            resp.raise_for_status()
            return resp.text.strip(), None
        except ImportError:
            from urllib.request import Request, urlopen
            req = Request(u, headers=h)
            with urlopen(req, timeout=timeout_seconds) as r:
                return r.read().decode("utf-8", errors="replace").strip(), None
        except Exception as e:
            return None, str(e)

    def _is_404(e):
        return e == "404" or (e and "404" in str(e))

    def _try_github_fallbacks(owner, repo, branch, path):
        # Try jsDelivr, then raw, then API
        for u in [
            f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}",
            f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}",
        ]:
            t, e = _fetch(u)
            if t is not None:
                return t
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            import requests
            r = requests.get(api_url, headers=_VERSION_FETCH_HEADERS, timeout=timeout_seconds)
            if r.status_code == 200:
                data = r.json()
                import base64
                raw = base64.b64decode(data.get("content", "") or "").decode("utf-8", errors="replace").strip()
                if raw:
                    return raw
        except Exception:
            pass
        return None

    try:
        text, err = _fetch(url)
        if not _is_404(err) and text is not None:
            return text, None
        # Fallbacks: derive owner/repo/branch/path from raw or jsDelivr URL
        owner = repo = branch = path = None
        if "raw.githubusercontent.com" in url:
            parts = url.replace("https://raw.githubusercontent.com/", "").split("/")
            if len(parts) >= 4:
                owner, repo, branch, path = parts[0], parts[1], parts[2], "/".join(parts[3:])
        elif "cdn.jsdelivr.net/gh/" in url:
            # cdn.jsdelivr.net/gh/owner/repo@branch/path
            rest = url.split("cdn.jsdelivr.net/gh/", 1)[-1]
            if "@" in rest and "/" in rest:
                mid = rest.split("@", 1)
                owner_repo = mid[0].split("/")
                branch_path = mid[1].split("/", 1)
                if len(owner_repo) >= 2 and len(branch_path) >= 1:
                    owner, repo = owner_repo[0], owner_repo[1]
                    branch = branch_path[0]
                    path = branch_path[1] if len(branch_path) > 1 else ""
        if owner and repo and branch is not None:
            text = _try_github_fallbacks(owner, repo, branch, path or "VERSION")
            if text is not None:
                return text, None
        return None, (
            "Update server returned 404. Ensure VERSION is in the repo root. Tried: " + url
            if _is_404(err) else (err or "Unknown error")
        )
    except Exception as e:
        err = str(e)
        if "404" in err:
            return None, "Update URL not found (404). Check that VERSION is in the repo root: " + url
        return None, err


def is_update_available(config=None):
    """
    Compare current and remote versions.
    Returns (update_available: bool, current_version: str or None, latest_version: str or None, error: str or None).
    """
    cfg = config or _load_config()
    if cfg is None:
        return False, None, None, "Update config not found"
    current = get_current_version(cfg)
    latest, err = get_latest_version_from_remote(cfg)
    if err:
        return False, current, None, err
    if latest is None:
        return False, current, None, "Could not read remote version"
    if current is None:
        return True, None, latest, None
    local_tup = _parse_version(current)
    remote_tup = _parse_version(latest)
    return remote_tup > local_tup, current, latest, None


def trigger_update_script(wait_for_pid=None, config_path=None):
    """
    Start the external update script (update_app.py). Optionally pass the current
    process PID so the script waits for this process to exit before applying updates.
    Returns True if the script was started, False on error.
    When run from the frozen exe, sys.executable is the exe so we run Python with
    update_app.py if python is on PATH; otherwise "Update now" will not apply updates.
    """
    app_dir = _app_base_dir()
    config_path = Path(config_path or os.environ.get(CONFIG_PATH_ENV) or _default_config_path())
    updater_script = app_dir / "update_app.py"
    if not updater_script.is_file():
        return False
    # When frozen: must run "python update_app.py" (Python on PATH); when from source: sys.executable is python
    if getattr(sys, "frozen", False):
        try:
            import shutil
            python_exe = shutil.which("python") or shutil.which("python3")
        except Exception:
            python_exe = None
        if not python_exe:
            return False  # "Update now" requires Python on PATH when running the installed exe
        cmd = [python_exe, str(updater_script)]
    else:
        cmd = [sys.executable, str(updater_script)]
    if config_path.is_file():
        cmd.extend(["--config", str(config_path)])
    if wait_for_pid is not None:
        cmd.extend(["--wait-pid", str(wait_for_pid)])
    try:
        subprocess.Popen(
            cmd,
            cwd=str(app_dir),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        return True
    except Exception:
        return False


def trigger_update_and_exit():
    """
    Start the update script with --wait-pid <current pid>, then exit so the
    updater can replace files and restart the app. Call this when the user
    chooses "Update now" in the UI.
    When running the installed exe, Python must be on PATH to run the updater;
    otherwise the user can download the new installer from GitHub.
    """
    pid = os.getpid()
    if trigger_update_script(wait_for_pid=pid):
        sys.exit(0)
    if getattr(sys, "frozen", False):
        raise RuntimeError(
            "Could not start update script. When using the installed app, "
            "Python must be on PATH to run updates. Alternatively download the "
            "new installer from GitHub and run it."
        )
    raise RuntimeError("Could not start update script.")


def show_update_dialog(parent_widget=None, on_update_now=None, on_later=None):
    """
    Check for updates and, if available, show a prompt. Runs on the calling thread.
    - parent_widget: Qt widget for dialog parent (optional).
    - on_update_now: callable to run when user chooses "Update now" (default: trigger_update_and_exit).
    - on_later: callable when user chooses "Later" (optional).

    Uses PyQt5 if available; otherwise logs or prints. Returns True if an update
    was available and the user was prompted, False otherwise.
    """
    available, current, latest, error = is_update_available()
    if not available:
        if error and parent_widget:
            _show_message(parent_widget, "Check for Updates", f"Could not check for updates: {error}", is_error=False)
        return False

    title = "Update Available"
    msg = f"A new version is available.\n\nCurrent: {current or 'Unknown'}\nLatest:  {latest}\n\nUpdate now? The application will close and the updater will run."
    choice = _show_yes_no(parent_widget, title, msg)
    if choice == "yes":
        if on_update_now is None:
            on_update_now = trigger_update_and_exit
        try:
            on_update_now()
        except Exception as e:
            _show_message(parent_widget, "Update Error", str(e), is_error=True)
        return True
    if callable(on_later):
        on_later()
    return True


def _show_message(parent, title, text, is_error=True):
    try:
        from PyQt5 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if is_error:
            QtWidgets.QMessageBox.critical(parent or None, title, text)
        else:
            QtWidgets.QMessageBox.information(parent or None, title, text)
    except Exception:
        print(f"{title}: {text}")


def _show_yes_no(parent, title, text):
    try:
        from PyQt5 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return "no"
        reply = QtWidgets.QMessageBox.question(
            parent or None,
            title,
            text,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return "yes" if reply == QtWidgets.QMessageBox.Yes else "no"
    except Exception:
        return "no"


def check_for_updates_silent():
    """
    Non-blocking check for updates. Use on startup if you only want to
    set a flag or show a tray hint, not a modal. Returns same as is_update_available.
    """
    return is_update_available()


def install_update_check_into_main_window(main_window, *, check_on_startup=False):
    """
    Add "Check for Updates" to the Help or File menu of the main window,
    and optionally run the update check once on startup.
    Call this from run_gui() after creating the MainWindow, e.g.:
        win = MainWindow(repo)
        install_update_check_into_main_window(win, check_on_startup=True)
        win.show()
    """
    try:
        from PyQt5 import QtWidgets
    except ImportError:
        return
    menu_bar = getattr(main_window, "menuBar", None)
    if menu_bar is None or not callable(menu_bar):
        return
    menubar = main_window.menuBar()
    help_menu = None
    for a in menubar.actions():
        t = a.text() if a.text() else ""
        if "help" in t.lower() or "&Help" in t:
            help_menu = a.menu()
            break
    if help_menu is None:
        help_menu = menubar.addMenu("&Help")
    act = QtWidgets.QAction("Check for Updates...", main_window)
    act.triggered.connect(lambda: show_update_dialog(main_window))
    help_menu.addAction(act)
    if check_on_startup:
        from PyQt5 import QtCore
        def do_startup_check():
            show_update_dialog(main_window)
        QtCore.QTimer.singleShot(500, do_startup_check)
