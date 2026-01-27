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
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "update_config.json"
CONFIG_PATH_ENV = "CALIBRATION_TRACKER_UPDATE_CONFIG"


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
        # GitHub source zips have a top-level dir like repo-master/
        names = zf.namelist()
        if not names:
            return
        top_dirs = {n.split("/")[0] for n in names if "/" in n} or {n.split("\\")[0] for n in names if "\\" in n}
        extract_root = next(iter(top_dirs)) if len(top_dirs) == 1 else ""

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


def run_update(config, wait_pid=None, skip_version_check=False, restore_db_path=None):
    """
    Perform full update flow: optional wait for PID, version check, download,
    backup, replace, cleanup, restart. Raises on fatal errors.
    restore_db_path: if set, the restarted app is launched with --db <path>
    so it reopens on the same database (e.g. server DB) instead of the local one.
    """
    app_dir = config["_app_dir_resolved"]
    remote_version_url = config.get("remote_version_url")
    remote_package_url = config.get("remote_package_url")
    current_version_file = config.get("current_version_file", "VERSION")
    app_executable = config.get("app_executable", "CalibrationTracker.exe")

    if wait_pid is not None:
        try:
            pid = int(wait_pid)
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.5)
            else:
                print("Timeout waiting for process to exit.", file=sys.stderr)
        except (ValueError, TypeError):
            pass

    if not skip_version_check and remote_version_url:
        try:
            current_str = get_current_version(config)
            remote_str = fetch_remote_version(remote_version_url)
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
        print("Downloading update...")
        download_file(remote_package_url, zip_path)

        print("Creating backup...")
        backup_path = backup_app_directory(app_dir, backup_parent_dir=Path(tempfile.gettempdir()))

        # Exclude db, logs, backups, and config from overwrite to avoid data loss
        replace_with_extracted(
            zip_path,
            app_dir,
            exclude_patterns=["*.db", "*.db-journal", "*.db-wal", "*.db-shm", "logs", "backups", "update_config.json", ".update_temp"],
        )

        # Persist new version if we have it
        try:
            remote_str = fetch_remote_version(remote_version_url)
            (app_dir / current_version_file).write_text(remote_str, encoding="utf-8")
        except Exception:
            pass

        print("Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)

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
    parser = argparse.ArgumentParser(description="Calibration Tracker – automated update script")
    parser.add_argument("--config", type=Path, help="Path to update_config.json")
    parser.add_argument("--wait-pid", type=int, metavar="PID", help="Wait for this process ID to exit before updating")
    parser.add_argument("--skip-version-check", action="store_true", help="Install package even if version is not newer")
    parser.add_argument("--restore-db", type=str, metavar="PATH", help="Restart app with --db PATH so it reopens on the same database")
    parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        if sys.platform == "win32" and not getattr(args, "elevated", False):
            try:
                if _try_relaunch_elevated(args):
                    sys.exit(0)
            except Exception:
                pass
        config = load_config(args.config)
        run_update(
            config,
            wait_pid=args.wait_pid,
            skip_version_check=args.skip_version_check,
            restore_db_path=getattr(args, "restore_db", None),
        )
    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        if sys.platform == "win32":
            try:
                input("Press Enter to close...")
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
