# Multi-User Safety Improvements

Implemented changes from the multi-user readiness analysis to improve data integrity and robustness, including in single-user mode.

## Summary of Changes

### 1. Atomic Writes
- **themes.json**: Write to temp file, then replace (prevents torn reads).
- **last_db.txt**: Same atomic write pattern.
- **quiet_hours.txt**: Same atomic write pattern.
- **New module**: `file_utils.py` with `atomic_write_text()`.

### 2. Unique Attachment Filenames
- Attachments now use `{stem}_{uuid8}{suffix}` (e.g. `report_a1b2c3d4.pdf`).
- Prevents overwrite when two users attach files with the same name to the same instrument.
- `filename` column still stores the original display name.

### 3. Optimistic Locking
- **Instruments**: `update_instrument()` accepts optional `updated_at`; UPDATE uses `WHERE id=? AND updated_at=?`. Raises `StaleDataError` if no row updated.
- **Calibration records**: Same pattern for `update_calibration_record()`.
- **UI**: InstrumentDialog and CalibrationFormDialog pass `updated_at` from loaded data; both handle `StaleDataError` with a clear message and suggest refreshing.

### 4. Retry on SQLITE_BUSY
- `get_connection()` retries up to 3 times with exponential backoff when "database is locked" or "sqlite_busy".
- Reduces transient lock failures under concurrency.

### 5. Advisory Lock During Migrations
- `run_migrations()` creates `.migrating` next to the database before running.
- Waits up to ~6 seconds if another process holds the lock.
- Removes `.migrating` on success or failure.
- Prevents concurrent migration races.

### 6. Refresh Hint in Main Window
- Status bar has a permanent "Refresh" link.
- Clicking it reloads data; briefly shows "Refreshed" then reverts.
- Tooltip: "Reload data from database (data may have changed)".

## New Exceptions

- **`StaleDataError`** (in `database.py`): Raised when optimistic lock fails. UI catches and shows a friendly message.

## Files Modified

- `file_utils.py` (new)
- `database.py` – atomic persist_last_db_path, unique attachments, StaleDataError, optimistic lock, retry, DATA_MODE
- `ui/theme/storage.py` – atomic write for themes
- `ui/dialogs/all_dialogs.py` – atomic quiet_hours, StaleDataError handling, pass updated_at, disable OK during write, use calibration_service
- `ui/main_window.py` – StaleDataError handling, refresh hint, use instrument_service, wait cursor during save
- `migrations.py` – advisory lock
- `.gitignore` – `.migrating`
- `main.py` – atomic crash flag, log failures, integrity check on startup (user-visible on failure)
- `services/identity.py` (new) – get_current_user_id placeholder
- `services/instrument_service.py` (new) – thin validation + repo delegation
- `services/calibration_service.py` (new) – thin validation + repo delegation
- `services/future_hooks.py` (new) – inert placeholders (READ_ONLY_MODE, check_conflict_before_update)
