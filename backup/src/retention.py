"""Backup retention and cleanup functions."""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple
from storage import RcloneStorage, get_destinations

logger = logging.getLogger('shiori-backup')


def parse_backup_timestamp(filename: str) -> datetime:
    """
    Extract timestamp from backup filename.

    Expected format: shiori-backup-YYYYMMDD_HHMMSS.tar.gz[.gpg]
    E.g.: shiori-backup-20260224_155255.tar.gz.gpg
    """
    try:
        # Remove extensions (.tar.gz.gpg or .tar.gz)
        base = filename
        for ext in ['.tar.gz.gpg', '.tar.gz']:
            if base.endswith(ext):
                base = base[:-len(ext)]
                break

        # The base is like: shiori-backup-YYYYMMDD_HHMMSS
        # Split by '-' and take the last part which contains date_time
        parts = base.split('-')
        if len(parts) >= 3:
            timestamp_str = parts[-1]  # This is YYYYMMDD_HHMMSS
            return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except (ValueError, IndexError):
        pass

    # Fallback to file modification time
    return datetime.fromtimestamp(0)


def cleanup_local_backups(backup_dir: str, retention_days: int) -> Tuple[int, int]:
    """
    Remove local backups older than retention period.

    Args:
        backup_dir: Directory containing backups
        retention_days: Number of days to retain backups

    Returns:
        Tuple of (number_deleted, bytes_freed)
    """
    if retention_days <= 0:
        logger.debug("Local retention disabled (retention_days <= 0)")
        return 0, 0

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        return 0, 0

    deleted = 0
    bytes_freed = 0

    for file_path in backup_path.glob('shiori-backup-*'):
        if not file_path.is_file():
            continue

        file_time = parse_backup_timestamp(file_path.name)

        if file_time < cutoff_date:
            try:
                file_size = file_path.stat().st_size
                file_path.unlink()
                deleted += 1
                bytes_freed += file_size
                logger.info(f"Deleted old local backup: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} local backups, freed {bytes_freed} bytes")

    return deleted, bytes_freed


def cleanup_cloud_backups(destination: str, retention_days: int) -> Tuple[int, int]:
    """
    Remove cloud backups older than retention period.

    Args:
        destination: Remote destination (format: remote:path)
        retention_days: Number of days to retain backups

    Returns:
        Tuple of (number_deleted, bytes_freed)
    """
    if retention_days <= 0:
        logger.debug(f"Cloud retention disabled for {destination}")
        return 0, 0

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    storage = RcloneStorage()

    # List all backups in the destination
    backups = storage.list_backups(destination)

    deleted = 0
    bytes_freed = 0

    for backup in backups:
        backup_time = parse_backup_timestamp(backup['name'])

        if backup_time < cutoff_date:
            remote_path = f"{destination}/{backup['name']}"
            if storage.delete(remote_path):
                deleted += 1
                bytes_freed += backup.get('size', 0)
                logger.info(f"Deleted old cloud backup: {backup['name']}")

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} cloud backups from {destination}")

    return deleted, bytes_freed


def cleanup_all_backups(retention_days: int) -> dict:
    """
    Clean up old backups from all locations.

    Args:
        retention_days: Number of days to retain backups

    Returns:
        Dictionary with cleanup statistics
    """
    backup_dir = os.getenv('BACKUP_DIR', '/backups')

    stats = {
        'local_deleted': 0,
        'local_bytes_freed': 0,
        'cloud_stats': {}
    }

    # Clean up local backups
    local_deleted, local_bytes = cleanup_local_backups(backup_dir, retention_days)
    stats['local_deleted'] = local_deleted
    stats['local_bytes_freed'] = local_bytes

    # Clean up cloud backups
    destinations = get_destinations()
    for destination in destinations:
        cloud_deleted, cloud_bytes = cleanup_cloud_backups(destination, retention_days)
        stats['cloud_stats'][destination] = {
            'deleted': cloud_deleted,
            'bytes_freed': cloud_bytes
        }

    return stats


def should_delete_local_after_upload() -> bool:
    """Check if local backups should be deleted after successful upload."""
    return os.getenv('BACKUP_DELETE_LOCAL_AFTER_UPLOAD', 'false').lower() == 'true'
