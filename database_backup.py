# database_backup.py
# Automatic database backup functionality

import sqlite3
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def backup_database(db_path: Path, backup_dir: Optional[Path] = None, 
                   max_backups: int = 30) -> Optional[Path]:
    """
    Create a backup of the database.
    
    Args:
        db_path: Path to the database file to backup
        backup_dir: Directory to store backups (defaults to db_path.parent / "backups")
        max_backups: Maximum number of backups to keep (default 30 days)
    
    Returns:
        Path to the created backup file, or None if backup failed
    """
    if not db_path.exists():
        logger.warning(f"Database file not found: {db_path}")
        return None
    
    # Determine backup directory
    if backup_dir is None:
        backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{db_path.stem}_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename
    
    try:
        # Use SQLite backup API for safe backup while database might be in use
        source_conn = sqlite3.connect(str(db_path))
        backup_conn = sqlite3.connect(str(backup_path))
        
        # Use SQLite's backup API for atomic backup
        source_conn.backup(backup_conn)
        
        backup_conn.close()
        source_conn.close()
        
        # Verify backup: open and run integrity_check
        verified = verify_backup(backup_path)
        if not verified:
            logger.warning(f"Backup integrity check failed: {backup_path}")
        
        logger.info(f"Database backup created: {backup_path}" + (" (verified)" if verified else " (unverified)"))
        
        # Clean up old backups
        cleanup_old_backups(backup_dir, max_backups)
        
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create database backup: {e}", exc_info=True)
        # Try simple file copy as fallback
        try:
            shutil.copy2(str(db_path), str(backup_path))
            logger.info(f"Database backup created (fallback method): {backup_path}")
            cleanup_old_backups(backup_dir, max_backups)
            return backup_path
        except Exception as e2:
            logger.error(f"Fallback backup also failed: {e2}", exc_info=True)
            if backup_path.exists():
                backup_path.unlink()
            return None


def verify_backup(backup_path: Path) -> bool:
    """
    Open backup and run PRAGMA integrity_check.
    Returns True if OK, False on failure or error.
    """
    if not backup_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(backup_path))
        cur = conn.execute("PRAGMA integrity_check")
        row = cur.fetchone()
        conn.close()
        result = row[0] if row else ""
        return result == "ok"
    except Exception as e:
        logger.warning(f"Backup verification error for {backup_path}: {e}")
        return False


def cleanup_old_backups(backup_dir: Path, max_backups: int):
    """
    Remove old backup files, keeping only the most recent max_backups.
    
    Args:
        backup_dir: Directory containing backup files
        max_backups: Maximum number of backups to keep
    """
    try:
        # Get all backup files sorted by modification time (newest first)
        backup_files = sorted(
            backup_dir.glob("*_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove files beyond max_backups
        if len(backup_files) > max_backups:
            for old_backup in backup_files[max_backups:]:
                try:
                    old_backup.unlink()
                    logger.info(f"Removed old backup: {old_backup}")
                except Exception as e:
                    logger.warning(f"Failed to remove old backup {old_backup}: {e}")
    except Exception as e:
        logger.warning(f"Failed to cleanup old backups: {e}")


def should_run_daily_backup(db_path: Path, backup_dir: Optional[Path] = None) -> bool:
    """
    Check if a daily backup should be run (hasn't been run today).
    
    Args:
        db_path: Path to the database file
        backup_dir: Directory containing backups
    
    Returns:
        True if backup should run, False if already backed up today
    """
    if backup_dir is None:
        backup_dir = db_path.parent / "backups"
    
    if not backup_dir.exists():
        return True
    
    today_str = date.today().strftime("%Y%m%d")
    # Check if a backup exists for today
    today_backups = list(backup_dir.glob(f"*_backup_{today_str}_*.db"))
    
    return len(today_backups) == 0


def perform_daily_backup_if_needed(db_path: Path, backup_dir: Optional[Path] = None,
                                   max_backups: int = 30) -> Optional[Path]:
    """
    Perform a daily backup if one hasn't been done today.
    
    Args:
        db_path: Path to the database file
        backup_dir: Directory to store backups
        max_backups: Maximum number of backups to keep
    
    Returns:
        Path to backup file if created, None otherwise
    """
    if should_run_daily_backup(db_path, backup_dir):
        return backup_database(db_path, backup_dir, max_backups)
    return None


def get_backup_info(backup_dir: Path) -> dict:
    """
    Get information about existing backups.
    
    Args:
        backup_dir: Directory containing backups
    
    Returns:
        Dictionary with backup statistics
    """
    if not backup_dir.exists():
        return {
            "count": 0,
            "total_size": 0,
            "oldest": None,
            "newest": None,
        }
    
    backup_files = sorted(
        backup_dir.glob("*_backup_*.db"),
        key=lambda p: p.stat().st_mtime
    )
    
    if not backup_files:
        return {
            "count": 0,
            "total_size": 0,
            "oldest": None,
            "newest": None,
        }
    
    total_size = sum(f.stat().st_size for f in backup_files)
    
    return {
        "count": len(backup_files),
        "total_size": total_size,
        "oldest": backup_files[0].stat().st_mtime if backup_files else None,
        "newest": backup_files[-1].stat().st_mtime if backup_files else None,
    }
