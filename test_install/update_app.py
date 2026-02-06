# update_app.py
"""
Automated application update script (Part 1).
Compares local version with remote, downloads and installs updates, backs up
existing files, then restarts the application. Intended to be run after the
main application has exited (e.g. launched with --wait-pid <pid>).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

# Optional: use requests if available for downloads; otherwise urllib
try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError, HTTPError
    HTTP_ERROR = HTTPError
    URL_ERROR = URLError
except ImportError:
    urlopen = Request = None
    HTTP_ERROR = URL_ERROR = Exception

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# -----------------------------------------------------------------------------
# Configuration paths (no hardcoded credentials)
# -----------------------------------------------------------------------------
# When frozen (PyInstaller exe), use exe's dir; otherwise script's dir
SCRIPT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "update_config.json"
CONFIG_PATH_ENV = "CALIBRATION_TRACKER_UPDATE_CONFIG"

# Log file for diagnosing crashes when run without a console (e.g. from frozen exe)
_UPDATER_LOG = None


def _log(msg, also_stderr=True):
    """Write a line to the updater log file and optionally to stderr."""
    global _UPDATER_LOG
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    if _UPDATER_LOG is None:
        try:
            log_path = Path(tempfile.gettempdir()) / "CalibrationTracker_updater.log"
            _UPDATER_LOG = open(log_path, "a", encoding="utf-8")
        except Exception:
            _UPDATER_LOG = False
    if _UPDATER_LOG and _UPDATER_LOG is not True:
        try:
            _UPDATER_LOG.write(line)
            _UPDATER_LOG.flush()
        except Exception:
            pass
    if also_stderr:
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            pass


def load_config(config_path=None):
    """Load update configuration from JSON. Path from env or default."""
    path = config_path or os.environ.get(CONFIG_PATH_ENV) or DEFAULT_CONFIG_PATH
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Update config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Resolve app_dir relative to config file
    app_dir = data.get("app_dir", ".")
    if not os.path.isabs(app_dir):
        app_dir = path.parent / app_dir
    data["_app_dir_resolved"] = Path(app_dir).resolve()
    return data


def parse_version(version_string):
    """Parse a version string into a comparable tuple (e.g. '1.2.3' -> (1, 2, 3))."""
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


def is_newer_version(local_tuple, remote_tuple):
    """Return True if remote_tuple is newer than local_tuple."""
    return remote_tuple > local_tuple


def get_current_version(config):
    """Read current installed version from the file specified in config."""
    app_dir = config["_app_dir_resolved"]
    version_file = config.get("current_version_file", "VERSION")
    path = app_dir / version_file
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _fetch_via_github_api(owner, repo, branch, path, timeout_seconds=15):
    """Fetch file via GitHub Contents API (avoids cached raw CDN). Returns None on failure."""
    import base64
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path or 'VERSION'}?ref={branch}"
    headers = {"User-Agent": "CalibrationTracker-Updater/1.0", "Cache-Control": "no-cache", "Pragma": "no-cache"}
    try:
        if HAS_REQUESTS:
            r = requests.get(api_url, headers=headers, timeout=timeout_seconds)
            if r.status_code == 200:
                data = r.json()
                raw = base64.b64decode(data.get("content", "") or "").decode("utf-8", errors="replace").strip()
                if raw:
                    return raw
        elif urlopen and Request:
            req = Request(api_url, headers=headers)
            with urlopen(req, timeout=timeout_seconds) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            raw = base64.b64decode(data.get("content", "") or "").decode("utf-8", errors="replace").strip()
            if raw:
                return raw
    except Exception:
        pass
    return None


def _parse_github_latest_download_url(url):
    """
    If url is https://github.com/OWNER/REPO/releases/latest/download/ASSET.zip
    return (owner, repo, asset_name); otherwise return None.
    """
    if not url or "github.com" not in url or "/releases/latest/download/" not in url:
        return None
    try:
        # https://github.com/owner/repo/releases/latest/download/filename.zip
        after = url.split("github.com/", 1)[-1]
        parts = after.split("/releases/latest/download/", 1)
        if len(parts) != 2:
            return None
        owner_repo = parts[0].strip("/").split("/")
        if len(owner_repo) < 2:
            return None
        owner, repo = owner_repo[0], owner_repo[1]
        asset_name = (parts[1].split("?")[0] or "").strip("/") or None
        if not asset_name:
            return None
        return (owner, repo, asset_name)
    except Exception:
        return None


def resolve_github_latest_release(owner, repo, asset_name, timeout_seconds=15):
    """
    Use GitHub API GET /repos/OWNER/REPO/releases/latest to get the actual
    latest release version (tag_name) and download URL for the given asset.
    Returns (version_string, download_url) or (None, None) on failure.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {"User-Agent": "CalibrationTracker-Updater/1.0", "Accept": "application/vnd.github.v3+json"}
    try:
        if HAS_REQUESTS:
            r = requests.get(api_url, headers=headers, timeout=timeout_seconds)
            if r.status_code != 200:
                return None, None
            data = r.json()
        elif urlopen and Request:
            req = Request(api_url, headers=headers)
            with urlopen(req, timeout=timeout_seconds) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
        else:
            return None, None
        tag = (data.get("tag_name") or "").strip()
        if tag.startswith("v"):
            tag = tag[1:]
        if not tag:
            return None, None
        for asset in data.get("assets") or []:
            if (asset.get("name") or "") == asset_name:
                url = (asset.get("browser_download_url") or "").strip()
                if url:
                    return tag, url
        return None, None
    except Exception:
        return None, None


def fetch_remote_version(remote_version_url, timeout_seconds=15):
    """Fetch latest version string. Tries GitHub API first when URL is raw GitHub to avoid cache."""
    owner = repo = branch = path = None
    if "raw.githubusercontent.com" in (remote_version_url or ""):
        parts = (remote_version_url or "").replace("https://raw.githubusercontent.com/", "").split("/")
        if len(parts) >= 4:
            owner, repo, branch, path = parts[0], parts[1], parts[2], "/".join(parts[3:])
            text = _fetch_via_github_api(owner, repo, branch, path or "VERSION", timeout_seconds)
            if text:
                return text
    headers = {"User-Agent": "CalibrationTracker-Updater/1.0", "Cache-Control": "no-cache", "Pragma": "no-cache"}
    if HAS_REQUESTS:
        resp = requests.get(remote_version_url, headers=headers, timeout=timeout_seconds)
        resp.raise_for_status()
        return resp.text.strip()
    if urlopen is None:
        raise RuntimeError("Neither requests nor urllib available for HTTP.")
    req = Request(remote_version_url, headers=headers)
    with urlopen(req, timeout=timeout_seconds) as r:
        return r.read().decode("utf-8", errors="replace").strip()


def download_file(url, dest_path, timeout_seconds=120):
    """Download a file from url to dest_path."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if HAS_REQUESTS:
        resp = requests.get(url, stream=True, timeout=timeout_seconds)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return
    req = Request(url, headers={"User-Agent": "CalibrationTracker-Updater/1.0"})
    with urlopen(req, timeout=timeout_seconds) as r:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(r, f)


def backup_app_directory(app_dir, backup_parent_dir=None):
    """Create a timestamped backup of the application directory. Returns backup path."""
    app_dir = Path(app_dir)
    backup_parent_dir = Path(backup_parent_dir or app_dir.parent)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"{app_dir.name}_backup_{timestamp}"
    backup_path = backup_parent_dir / backup_name
    shutil.copytree(app_dir, backup_path, ignore=shutil.ignore_patterns("*.tmp", "*.temp", "__pycache__"))
    return backup_path


def replace_with_extracted(archive_path, app_dir, exclude_patterns=None):
    """
    Extract zip archive into a temp dir, then copy contents into app_dir.
    exclude_patterns: list of glob patterns for paths to skip (e.g. ['*.db', 'backups']).
    """
    exclude_patterns = exclude_patterns or []
    app_dir = Path(app_dir)
    archive_path = Path(archive_path)

    with zipfile.ZipFile(archive_path, "r") as zf:
        # GitHub source zips have a single top-level dir (e.g. repo-main/); our update zip is flat
        names = zf.namelist()
        if not names:
            return
        top_dirs = {n.split("/")[0] for n in names if "/" in n} or {n.split("\\")[0] for n in names if "\\" in n}
        extract_root = ""
        if len(top_dirs) == 1:
            root = next(iter(top_dirs))
            if all(n.endswith("/") or n == root or n.startswith(root + "/") for n in names):
                extract_root = root

        def should_skip(rel_path):
            for pat in exclude_patterns:
                if pat.startswith("*.") and "/" not in pat and "\\" not in pat:
                    if rel_path.endswith(pat[1:]) or "/" + pat[1:] in rel_path or "\\" + pat[1:] in rel_path:
                        return True
                if rel_path == pat or rel_path.startswith(pat + "/") or rel_path.startswith(pat + "\\"):
                    return True
            return False

        for name in names:
            if name.endswith("/"):
                continue
            rel = name[len(extract_root) + 1:] if extract_root else name
            rel = rel.replace("\\", "/")
            if should_skip(rel):
                continue
            dest = app_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(name) as src:
                    with open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
            except OSError as e:
                # File in use or permission: log and continue
                print(f"Warning: could not write {dest}: {e}", file=sys.stderr)


def run_update(config, wait_pid=None, skip_version_check=False, restore_db_path=None, no_restart=False):
    """
    Perform full update flow: optional wait for PID, version check, download,
    backup, replace, cleanup, restart. Raises on fatal errors.
    restore_db_path: if set, the restarted app is launched with --db <path>
    so it reopens on the same database (e.g. server DB) instead of the local one.
    no_restart: if True, do not start the app (caller scheduled a user-session restart).
    """
    app_dir = config["_app_dir_resolved"]
    remote_version_url = config.get("remote_version_url")
    remote_package_url = config.get("remote_package_url")
    current_version_file = config.get("current_version_file", "VERSION")
    app_executable = config.get("app_executable", "CalibrationTracker.exe")

    if wait_pid is not None:
        try:
            pid = int(wait_pid)
            _log("Waiting for process %s to exit..." % pid)
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                except OSError:
                    _log("Process %s has exited." % pid)
                    break
                time.sleep(0.5)
            else:
                _log("Timeout waiting for process %s to exit; aborting update." % pid)
                raise RuntimeError(
                    "The application did not close in time. Please close it manually and try Update again."
                )
        except (ValueError, TypeError):
            pass

    # When package URL is GitHub releases/latest, resolve to actual latest version and URL
    # so we update to the real latest in one step and write the correct version.
    resolved_version = None
    resolved_download_url = None
    gh = _parse_github_latest_download_url(remote_package_url)
    if gh:
        owner, repo, asset_name = gh
        resolved_version, resolved_download_url = resolve_github_latest_release(owner, repo, asset_name)
    if resolved_download_url:
        remote_package_url = resolved_download_url

    if not skip_version_check:
        try:
            current_str = get_current_version(config)
            if resolved_version is not None:
                remote_str = resolved_version
            elif remote_version_url:
                remote_str = fetch_remote_version(remote_version_url)
            else:
                remote_str = None
            if remote_str is not None:
                local_tup = parse_version(current_str)
                remote_tup = parse_version(remote_str)
                if not is_newer_version(local_tup, remote_tup):
                    print("No update required: already at latest version.")
                    return
        except Exception as e:
            print(f"Version check failed: {e}", file=sys.stderr)
            raise

    if not remote_package_url:
        raise ValueError("remote_package_url is required in config.")

    # Use user temp dir so we don't need write access to Program Files for download/extract
    temp_base = Path(tempfile.gettempdir()) / "CalibrationTracker_update"
    temp_base.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_base / f"{os.getpid()}_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = temp_dir / "update.zip"

    try:
        _log("Downloading update from %s" % (remote_package_url[:80] + "..." if len(remote_package_url) > 80 else remote_package_url))
        download_file(remote_package_url, zip_path)
        _log("Download complete.")

        _log("Creating backup...")
        backup_path = backup_app_directory(app_dir, backup_parent_dir=Path(tempfile.gettempdir()))
        _log("Backup created: %s" % backup_path)

        # Exclude db, logs, backups, and config from overwrite to avoid data loss
        _log("Extracting and replacing files...")
        replace_with_extracted(
            zip_path,
            app_dir,
            exclude_patterns=["*.db", "*.db-journal", "*.db-wal", "*.db-shm", "logs", "backups", "update_config.json", ".update_temp"],
        )
        _log("Replace complete.")

        # Persist new version if we have it (prefer resolved release version)
        try:
            if resolved_version is not None:
                (app_dir / current_version_file).write_text(resolved_version, encoding="utf-8")
            elif remote_version_url:
                remote_str = fetch_remote_version(remote_version_url)
                if remote_str:
                    (app_dir / current_version_file).write_text(remote_str, encoding="utf-8")
        except Exception:
            pass

        print("Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)

        if not no_restart:
            app_exe = app_dir / app_executable
            if app_exe.exists():
                print("Restarting application...")
                cmd = [str(app_exe)]
                if restore_db_path:
                    cmd.extend(["--db", str(restore_db_path)])
                subprocess.Popen(cmd, cwd=str(app_dir), shell=False)
            else:
                # Run as Python if no exe (developer mode)
                main_py = app_dir / "main.py"
                if main_py.exists():
                    cmd = [sys.executable, str(main_py)]
                    if restore_db_path:
                        cmd.extend(["--db", str(restore_db_path)])
                    subprocess.Popen(cmd, cwd=str(app_dir), shell=False)
        else:
            # Run RestartHelper with exe + db path so it reopens on the same DB (avoids APPDATA mismatch when elevated).
            stub_exe = app_dir / "RestartHelper.exe"
            app_exe = app_dir / app_executable
            if stub_exe.is_file() and app_exe.is_file():
                print("Restarting application via RestartHelper...")
                try:
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    cmd = [str(stub_exe), str(app_exe)]
                    if restore_db_path:
                        cmd.append(str(restore_db_path))
                    subprocess.Popen(
                        cmd,
                        cwd=str(app_dir),
                        creationflags=creationflags,
                    )
                except Exception as e:
                    print(f"Could not run RestartHelper: {e}", file=sys.stderr)
            else:
                print("RestartHelper.exe or main exe not found; please start the application manually.")

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def _try_relaunch_elevated(args):
    """On Windows, if app is in Program Files, re-launch this script as Administrator. Return True if we relaunched."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        config = load_config(args.config)
        app_dir = config["_app_dir_resolved"]
        app_dir_str = str(app_dir).lower()
        if "program files" not in app_dir_str and "programfiles" not in app_dir_str.replace(" ", ""):
            return False
        # Need elevation to write to Program Files; re-launch with "runas"
        script_path = os.path.normpath(os.path.abspath(__file__))
        params_list = [script_path, "--config", str(args.config), "--elevated"]
        if args.wait_pid is not None:
            params_list.extend(["--wait-pid", str(args.wait_pid)])
        if args.skip_version_check:
            params_list.append("--skip-version-check")
        if getattr(args, "restore_db", None):
            params_list.extend(["--restore-db", str(args.restore_db)])
        if getattr(args, "no_restart", False):
            params_list.append("--no-restart")
        params = " ".join('"{}"'.format(p) if " " in str(p) else str(p) for p in params_list)
        exe = sys.executable if sys.executable else "python"
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, str(app_dir), 1
        )
        if ret > 32:
            return True
    except Exception:
        pass
    return False


def main():
    global _UPDATER_LOG
    parser = argparse.ArgumentParser(description="Calibration Tracker – automated update script")
    parser.add_argument("--config", type=Path, help="Path to update_config.json")
    parser.add_argument("--wait-pid", type=int, metavar="PID", help="Wait for this process ID to exit before updating")
    parser.add_argument("--skip-version-check", action="store_true", help="Install package even if version is not newer")
    parser.add_argument("--restore-db", type=str, metavar="PATH", help="Restart app with --db PATH so it reopens on the same database")
    parser.add_argument("--no-restart", action="store_true", help="Do not start the app after update (caller scheduled user-session restart)")
    parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    _log("Updater started (pid=%s, cwd=%s)" % (os.getpid(), os.getcwd()))

    try:
        if sys.platform == "win32" and not getattr(args, "elevated", False):
            try:
                if _try_relaunch_elevated(args):
                    _log("Relaunched elevated; exiting.")
                    sys.exit(0)
            except Exception as e:
                _log("Relaunch elevated failed: %s" % e)
        _log("Loading config (config=%s)" % (args.config or "default"))
        config = load_config(args.config)
        _log("App dir: %s" % config["_app_dir_resolved"])
        run_update(
            config,
            wait_pid=args.wait_pid,
            skip_version_check=args.skip_version_check,
            restore_db_path=getattr(args, "restore_db", None),
            no_restart=getattr(args, "no_restart", False),
        )
        _log("Update completed successfully.")
        if _UPDATER_LOG and _UPDATER_LOG is not True:
            try:
                _UPDATER_LOG.close()
            except Exception:
                pass
            _UPDATER_LOG = None
    except Exception as e:
        import traceback
        err_msg = str(e)
        tb = traceback.format_exc()
        _log("Update failed: %s" % err_msg)
        _log("Traceback:\n%s" % tb)
        if _UPDATER_LOG and _UPDATER_LOG is not True:
            try:
                _UPDATER_LOG.close()
            except Exception:
                pass
            _UPDATER_LOG = None
        try:
            print(f"Update failed: {err_msg}", file=sys.stderr)
            print(tb, file=sys.stderr)
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                import ctypes
                log_hint = "\nSee %TEMP%\\CalibrationTracker_updater.log for details."
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "Update failed:\n\n%s%s" % (err_msg, log_hint),
                    "Calibration Tracker – Update Failed",
                    0x10,  # MB_ICONERROR
                )
            except Exception:
                try:
                    input("Press Enter to close...")
                except Exception:
                    pass
        sys.exit(1)


if __name__ == "__main__":
    main()
