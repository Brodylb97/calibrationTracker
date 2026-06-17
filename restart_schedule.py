# restart_schedule.py - Schedule RestartHelper.exe in the interactive user session

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _run_at(delay_seconds: int) -> datetime:
    """Earliest run time for schtasks (minute precision, at least 2 minutes ahead)."""
    delay_seconds = max(int(delay_seconds), 120)
    run_at = datetime.now() + timedelta(seconds=delay_seconds)
    min_at = datetime.now() + timedelta(minutes=2)
    return run_at if run_at >= min_at else min_at


def _schedule_via_schtasks(stub_exe: str, run_at: datetime, *, run_as_user: str | None = None) -> bool:
    """Create a one-shot task; RestartHelper reads paths from restart_params.txt (no /tr args)."""
    stub = str(Path(stub_exe).resolve())
    tr = f'"{stub}"'
    sd = run_at.strftime("%m/%d/%Y")
    st = run_at.strftime("%H:%M")
    args = [
        "schtasks", "/create",
        "/tn", "CalTrackerPostUpdate",
        "/tr", tr,
        "/sc", "once",
        "/st", st,
        "/sd", sd,
        "/ed", sd,
        "/it",
        "/f",
    ]
    attempts = [args + ["/ru", run_as_user]] if run_as_user else []
    attempts.append(args)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    for task_args in attempts:
        try:
            subprocess.run(task_args, check=True, capture_output=True, creationflags=flags)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            continue
    return False


def _schedule_via_powershell(stub_exe: str, delay_seconds: int) -> bool:
    """Fallback when schtasks.exe rejects the task XML (e.g. EndBoundary with /Z)."""
    stub = str(Path(stub_exe).resolve()).replace("'", "''")
    delay_seconds = max(int(delay_seconds), 120)
    ps = (
        f"$action = New-ScheduledTaskAction -Execute '{stub}'; "
        f"$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds({delay_seconds}); "
        f"$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME "
        f"-LogonType Interactive -RunLevel Limited; "
        f"Register-ScheduledTask -TaskName 'CalTrackerPostUpdate' -Action $action "
        f"-Trigger $trigger -Principal $principal -Force | Out-Null"
    )
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=True,
            capture_output=True,
            creationflags=flags,
            timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def schedule_restart_helper(
    stub_exe,
    delay_seconds: int = 120,
    *,
    run_as_user: str | None = None,
    log_fn=None,
) -> bool:
    """
    Schedule RestartHelper.exe with no command-line args.
    Paths are read from %APPDATA%\\CalibrationTracker\\restart_params.txt
    (written by the main app before the updater starts).
    """
    stub = Path(stub_exe).resolve()
    if sys.platform != "win32" or not stub.is_file():
        return False
    run_at = _run_at(delay_seconds)
    delay = max(int((run_at - datetime.now()).total_seconds()), 120)

    if _schedule_via_schtasks(str(stub), run_at, run_as_user=run_as_user):
        if log_fn:
            log_fn("Scheduled post-update restart at %s (schtasks)" % run_at.strftime("%H:%M:%S"))
        return True
    if _schedule_via_powershell(str(stub), delay):
        if log_fn:
            log_fn("Scheduled post-update restart via PowerShell in ~%s s" % delay)
        return True
    if log_fn:
        log_fn("Failed to schedule post-update restart (schtasks and PowerShell)")
    return False
