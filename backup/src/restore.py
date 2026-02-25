#!/usr/bin/env python3
"""
Shiori Backup - Restore script.

Restore Shiori data from backup archives with integrity verification.
Supports both local and cloud backups.
"""

import os
import sys
import argparse
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import setup_logging, load_config, get_env, format_bytes, detect_database_type
from database import get_database_handler
from archive import extract_archive, list_archive_contents
from encryption import decrypt_file, is_encrypted
from storage import RcloneStorage, get_destinations, download_from_destination
from notifications import get_notification_manager

logger = setup_logging()


def extract_db_type_from_filename(filename: str) -> str:
    """
    Extract database type from backup filename.

    Supports formats:
    - Old: shiori-backup-YYYYMMDD_HHMMSS.tar.gz.gpg -> returns 'unknown'
    - New: shiori-backup-YYYYMMDD_HHMMSS-sqlite.tar.gz.gpg -> returns 'sqlite'
    """
    # Remove extensions
    base = filename
    for ext in ['.tar.gz.gpg', '.tar.gz']:
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # Split and look for database type (last part after timestamp)
    parts = base.split('-')
    if len(parts) >= 4:
        # New format: shiori-backup-YYYYMMDD_HHMMSS-<dbtype>
        potential_type = parts[-1]
        if potential_type in ['sqlite', 'postgres', 'mysql']:
            return potential_type

    # Check for old format without type or unknown type
    return 'unknown'


def list_available_backups(source: str = 'cloud', db_type: str = None, include_all: bool = False) -> list:
    """
    List available backups from specified source.

    Args:
        source: 'cloud' or 'local'
        db_type: Filter by database type (sqlite/postgres/mysql). If None, uses current config.
        include_all: If True, include all backups regardless of type

    Returns:
        List of backup information dictionaries
    """
    # Determine current database type if not specified
    if db_type is None and not include_all:
        current_type = detect_database_type()
        # Map to our expected types
        db_type_map = {
            'sqlite': 'sqlite',
            'postgresql': 'postgres',
            'mysql': 'mysql'
        }
        db_type = db_type_map.get(current_type, 'unknown')

    backups = []

    if source == 'local':
        backup_dir = get_env('BACKUP_DIR', '/backups')
        backup_path = Path(backup_dir)

        if backup_path.exists():
            for file_path in sorted(backup_path.glob('shiori-backup-*'), reverse=True):
                if file_path.is_file():
                    backup_info = {
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': file_path.stat().st_size,
                        'mod_time': file_path.stat().st_mtime
                    }
                    # Filter by database type unless showing all
                    if include_all or db_type == 'unknown':
                        backups.append(backup_info)
                    else:
                        backup_db_type = extract_db_type_from_filename(file_path.name)
                        # Include if matches or if backup has unknown type (backward compat)
                        if backup_db_type == db_type or backup_db_type == 'unknown':
                            backups.append(backup_info)

    elif source == 'cloud':
        storage = RcloneStorage()
        destinations = get_destinations()

        for destination in destinations:
            cloud_backups = storage.list_backups(destination)
            for backup in cloud_backups:
                backup['full_remote'] = f"{destination}/{backup['name']}"
                # Filter by database type unless showing all
                if include_all or db_type == 'unknown':
                    backups.append(backup)
                else:
                    backup_db_type = extract_db_type_from_filename(backup['name'])
                    # Include if matches or if backup has unknown type (backward compat)
                    if backup_db_type == db_type or backup_db_type == 'unknown':
                        backups.append(backup)

        # Sort by modification time (newest first)
        backups.sort(key=lambda x: x.get('mod_time', ''), reverse=True)

    return backups


def download_backup(backup_spec: str, temp_dir: str) -> str:
    """
    Download a backup to the temp directory.

    Args:
        backup_spec: Either a full remote path (remote:path/file) or local path
        temp_dir: Temporary directory to download to

    Returns:
        Path to the downloaded/decrypted file
    """
    # Check if it's a remote spec
    if ':' in backup_spec and not backup_spec.startswith('/'):
        # It's a remote file
        local_path = download_from_destination(backup_spec, temp_dir)
        if not local_path:
            raise RuntimeError(f"Failed to download backup from {backup_spec}")
        return local_path
    else:
        # It's a local file
        if not os.path.exists(backup_spec):
            raise FileNotFoundError(f"Backup not found: {backup_spec}")

        # Copy to temp directory
        filename = os.path.basename(backup_spec)
        local_path = os.path.join(temp_dir, filename)

        # Avoid SameFileError if source is already in temp_dir
        if os.path.abspath(backup_spec) == os.path.abspath(local_path):
            return local_path

        shutil.copy2(backup_spec, local_path)
        return local_path


def restore_backup(backup_path: str, force: bool = False) -> bool:
    """
    Restore Shiori from a backup archive.

    Args:
        backup_path: Path to the backup file (local or remote)
        force: Skip confirmation prompt if True

    Returns:
        True if successful, False otherwise
    """
    temp_dir = None

    try:
        logger.info(f"Starting restore from: {backup_path}")

        # Confirmation prompt
        if not force:
            print(f"\nWARNING: This will overwrite current Shiori data!")
            print(f"Backup: {backup_path}")
            confirmation = input('Type "RESTORE" to continue: ')
            if confirmation.strip() != "RESTORE":
                logger.info("Restore cancelled by user")
                return False

        # Create temp directory
        temp_dir = tempfile.mkdtemp(prefix='shiori-restore-')

        # Download/copy backup
        local_backup = download_backup(backup_path, temp_dir)
        logger.info(f"Backup available at: {local_backup}")

        # Decrypt if necessary
        if is_encrypted(local_backup):
            logger.info("Decrypting backup...")
            decrypted_path = local_backup + '.decrypted'
            if not decrypt_file(local_backup, decrypted_path):
                raise RuntimeError("Failed to decrypt backup")
            local_backup = decrypted_path

        # Extract archive
        extract_dir = os.path.join(temp_dir, 'extracted')
        logger.info(f"Extracting archive to {extract_dir}...")
        if not extract_archive(local_backup, extract_dir):
            raise RuntimeError("Failed to extract archive")

        # List extracted contents
        contents = list_archive_contents(local_backup)
        logger.info(f"Extracted contents: {contents}")

        # Get database handler
        db_handler = get_database_handler()
        if not db_handler:
            raise RuntimeError("Failed to initialize database handler")

        # Find database backup
        db_backup_path = os.path.join(extract_dir, 'database_backup')
        if not os.path.exists(db_backup_path):
            raise FileNotFoundError("Database backup not found in archive")

        # Create safety backup of current data
        data_dir = get_env('SHIORI_DATA_DIR', '/srv/shiori')
        safety_backup_dir = f"{data_dir}.safety-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if os.path.exists(data_dir):
            logger.info(f"Creating safety backup at: {safety_backup_dir}")
            shutil.copytree(data_dir, safety_backup_dir, ignore=shutil.ignore_patterns('*.safety-backup*'))

        # Restore database
        logger.info("Restoring database...")
        if not db_handler.restore(db_backup_path):
            raise RuntimeError("Database restore failed")

        # Restore data directories
        for item in ['archive', 'thumb', 'ebook']:
            src_path = os.path.join(extract_dir, item)
            dst_path = os.path.join(data_dir, item)

            if os.path.exists(src_path):
                # Remove existing directory
                if os.path.exists(dst_path):
                    shutil.rmtree(dst_path)

                # Copy restored data
                shutil.copytree(src_path, dst_path)
                logger.info(f"Restored {item} directory")

        # Send notification
        backup_id = os.path.basename(backup_path).replace('.tar.gz.gpg', '').replace('.tar.gz', '')
        notifier = get_notification_manager()
        notifier.notify_restore_success(backup_id, data_dir)

        logger.info(f"Restore completed successfully!")
        logger.info(f"Safety backup available at: {safety_backup_dir}")

        return True

    except Exception as e:
        logger.exception(f"Restore failed: {e}")

        # Send failure notification
        backup_id = os.path.basename(backup_path).replace('.tar.gz.gpg', '').replace('.tar.gz', '')
        notifier = get_notification_manager()
        notifier.notify_restore_failure(backup_id, str(e))

        return False

    finally:
        # Clean up temp directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")


def main():
    """Main entry point."""
    load_config()

    parser = argparse.ArgumentParser(
        description='Restore Shiori from backup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python restore.py --list                    # List cloud backups (current DB type only)
  python restore.py --list --all              # List all backups (all DB types)
  python restore.py --list --source local     # List local backups
  python restore.py --restore-latest          # Restore latest cloud backup (same DB type only)
  python restore.py --restore-latest --source local
  python restore.py --restore r2:bucket/shiori-backup-20240115_020000.tar.gz.gpg

Note: Backups are filtered by database type (sqlite/postgres/mysql).
      Use --all to see backups for all database types (reference only).
      Restores only work within the same database type.
        """
    )

    parser.add_argument('--list', action='store_true',
                        help='List available backups for current database type')
    parser.add_argument('--all', action='store_true',
                        help='Show all backups regardless of database type (for reference only)')
    parser.add_argument('--source', choices=['cloud', 'local'], default='cloud',
                        help='Backup source (default: cloud)')
    parser.add_argument('--restore-latest', action='store_true',
                        help='Restore the most recent backup (same database type only)')
    parser.add_argument('--restore', metavar='BACKUP',
                        help='Restore specific backup (local path or remote:path)')
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt')

    args = parser.parse_args()

    if args.list:
        # Get current database type for display
        current_db_type = detect_database_type()
        db_type_map = {
            'sqlite': 'sqlite',
            'postgresql': 'postgres',
            'mysql': 'mysql'
        }
        expected_type = db_type_map.get(current_db_type, 'unknown')

        # List backups (filtered or all)
        backups = list_available_backups(args.source, include_all=args.all)

        if not backups:
            if args.all:
                print(f"No backups found in {args.source}")
            else:
                print(f"No {expected_type} backups found in {args.source}")
                print(f"Current database type: {current_db_type}")
                print("Use --all to see all backups (for reference only)")
            return

        # Filter display by type
        filtered_backups = []
        other_count = 0
        for backup in backups:
            backup_db_type = extract_db_type_from_filename(backup['name'])
            if args.all or backup_db_type == expected_type or backup_db_type == 'unknown':
                filtered_backups.append(backup)
            else:
                other_count += 1

        if args.all:
            header = f"Available backups ({args.source}) - ALL TYPES"
        else:
            header = f"Available backups ({args.source}) - {expected_type.upper()} only"

        print(f"\n{header}:")
        print("-" * 100)
        print(f"{'Name':<50} {'Size':>12} {'Modified':>20}")
        print("-" * 100)

        for backup in filtered_backups:
            name = backup['name'][:49]
            size = format_bytes(backup.get('size', 0))
            mod_time = backup.get('mod_time', 'unknown')
            if isinstance(mod_time, (int, float)):
                from datetime import datetime
                mod_time = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{name:<50} {size:>12} {mod_time:>20}")

        print("-" * 100)
        print(f"Total: {len(filtered_backups)} backup(s) displayed")

        if not args.all and other_count > 0:
            print(f"Note: {len([b for b in backups if extract_db_type_from_filename(b['name']) != expected_type])} backup(s) for other database types hidden")
        print()

    elif args.restore_latest:
        # Get current database type
        current_db_type = detect_database_type()
        db_type_map = {
            'sqlite': 'sqlite',
            'postgresql': 'postgres',
            'mysql': 'mysql'
        }
        expected_type = db_type_map.get(current_db_type, 'unknown')

        backups = list_available_backups(args.source, db_type=expected_type)

        if not backups:
            logger.error(f"No {expected_type} backups found in {args.source}")
            logger.error(f"Current database type: {current_db_type}")
            logger.error("Use --all to see all backups (for reference only)")
            sys.exit(1)

        latest = backups[0]
        backup_spec = latest.get('full_remote', latest['path'])
        backup_db_type = extract_db_type_from_filename(latest['name'])

        # Strict type checking for restore
        if backup_db_type != 'unknown' and backup_db_type != expected_type:
            logger.error(f"Database type mismatch!")
            logger.error(f"Current database: {current_db_type} ({expected_type})")
            logger.error(f"Backup database: {backup_db_type}")
            logger.error("Cannot restore across database types.")
            sys.exit(1)

        logger.info(f"Restoring latest {expected_type} backup: {latest['name']}")
        success = restore_backup(backup_spec, args.force)
        sys.exit(0 if success else 1)

    elif args.restore:
        success = restore_backup(args.restore, args.force)
        sys.exit(0 if success else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
