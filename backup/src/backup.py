#!/usr/bin/env python3
"""
Shiori Backup - Main backup script.

Creates automated, encrypted, cloud-backed backups of Shiori bookmark manager data.
Supports both SQLite and PostgreSQL databases.
"""

import os
import sys
import time
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import (
    setup_logging, load_config, get_env, generate_backup_filename,
    format_bytes, BackupMetadata
)
from database import get_database_handler
from archive import create_archive, collect_shiori_data
from encryption import encrypt_file
from storage import upload_to_all_destinations
from retention import cleanup_all_backups, should_delete_local_after_upload
from notifications import get_notification_manager

try:
    from croniter import croniter
except ImportError:
    print("Error: croniter not installed. Run: pip install croniter")
    sys.exit(1)

logger = setup_logging()


def create_backup() -> bool:
    """
    Execute a complete backup operation.

    Returns:
        True if successful, False otherwise
    """
    start_time = time.time()
    temp_dir = None
    backup_id = 'unknown'

    try:
        # Get configuration
        backup_dir = get_env('BACKUP_DIR', '/backups')
        data_dir = get_env('SHIORI_DATA_DIR', '/srv/shiori')
        encryption_key = get_env('BACKUP_ENCRYPTION_KEY')

        # Ensure backup directory exists
        os.makedirs(backup_dir, exist_ok=True)

        # Create temp directory for staging
        temp_dir = tempfile.mkdtemp(prefix='shiori-backup-')
        logger.debug(f"Using temp directory: {temp_dir}")

        # Get database handler first to determine database type
        db_handler = get_database_handler()
        if not db_handler:
            raise RuntimeError("Failed to initialize database handler")

        db_info = db_handler.get_info()
        db_type = db_info.get('type', 'unknown')

        # Generate filename with database type
        backup_id = generate_backup_filename(db_type)
        logger.info(f"Starting backup: {backup_id}")

        # Initialize metadata
        metadata = BackupMetadata(backup_id, data_dir)
        metadata.set_database_info(**db_info)

        db_backup_path = os.path.join(temp_dir, 'database_backup')
        if not db_handler.backup(db_backup_path):
            raise RuntimeError("Database backup failed")

        metadata.add_file(db_backup_path, 'database_backup')
        logger.info(f"Database backed up: {db_backup_path}")

        # Collect Shiori data directories
        data_paths = collect_shiori_data(data_dir)

        # Build list of items to archive
        archive_items = [db_backup_path] + data_paths

        # Create archive
        archive_name = f"{backup_id}.tar.gz"
        archive_path = os.path.join(backup_dir, archive_name)

        if not create_archive(archive_items, archive_path, compression='gz'):
            raise RuntimeError("Failed to create archive")

        metadata.add_file(archive_path, archive_name)
        archive_size = os.path.getsize(archive_path)
        logger.info(f"Archive created: {archive_path} ({format_bytes(archive_size)})")

        # Save metadata
        metadata_path = os.path.join(temp_dir, 'backup-metadata.json')
        metadata.save(metadata_path)

        # Encrypt if key is provided
        if encryption_key:
            encrypted_path = archive_path + '.gpg'
            if not encrypt_file(archive_path, encrypted_path, encryption_key):
                raise RuntimeError("Encryption failed")

            # Remove unencrypted file
            os.remove(archive_path)
            archive_path = encrypted_path
            archive_size = os.path.getsize(archive_path)
            logger.info(f"Archive encrypted: {archive_path}")

        # Upload to cloud destinations
        logger.info("Uploading to cloud destinations...")
        upload_success, failed_destinations = upload_to_all_destinations(archive_path)

        if not upload_success:
            logger.warning(f"Failed to upload to some destinations: {failed_destinations}")
        else:
            logger.info("Upload completed successfully")

        # Clean up local file if configured
        if should_delete_local_after_upload() and upload_success and not failed_destinations:
            os.remove(archive_path)
            logger.info("Local backup deleted after successful upload")

        # Run retention cleanup
        retention_days = int(get_env('BACKUP_RETENTION_DAYS', '30'))
        if retention_days > 0:
            logger.info(f"Running retention cleanup (retention: {retention_days} days)...")
            cleanup_stats = cleanup_all_backups(retention_days)
            logger.info(f"Retention cleanup completed: {cleanup_stats}")

        # Send success notification
        duration = time.time() - start_time
        notifier = get_notification_manager()
        notifier.notify_backup_success(backup_id, archive_path, archive_size, duration)

        logger.info(f"Backup completed successfully in {duration:.2f} seconds")
        return True

    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"Backup failed: {e}")

        # Send failure notification
        notifier = get_notification_manager()
        notifier.notify_backup_failure(backup_id, str(e), duration)

        return False

    finally:
        # Clean up temp directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")


def run_scheduler():
    """Run the backup scheduler loop."""
    schedule = get_env('BACKUP_SCHEDULE', '0 2 * * *')

    try:
        itr = croniter(schedule, datetime.utcnow())
        logger.info(f"Backup scheduler started with schedule: {schedule}")
    except Exception as e:
        logger.error(f"Invalid cron schedule: {schedule} - {e}")
        sys.exit(1)

    # Check if we should run on startup
    if get_env('BACKUP_RUN_ON_START', 'false').lower() == 'true':
        logger.info("Running backup on startup (BACKUP_RUN_ON_START=true)")
        create_backup()

    while True:
        next_run = itr.get_next(datetime)
        wait_seconds = (next_run - datetime.utcnow()).total_seconds()

        if wait_seconds > 0:
            logger.info(f"Next backup scheduled for: {next_run.isoformat()} (in {wait_seconds:.0f} seconds)")
            time.sleep(wait_seconds)

        logger.info("Starting scheduled backup...")
        create_backup()

        # Recalculate iterator from now
        itr = croniter(schedule, datetime.utcnow())


def main():
    """Main entry point."""
    load_config()

    # Check for immediate run argument
    if len(sys.argv) > 1 and sys.argv[1] == '--now':
        logger.info("Running backup immediately (--now flag)")
        success = create_backup()
        sys.exit(0 if success else 1)

    # Start scheduler
    run_scheduler()


if __name__ == '__main__':
    main()
