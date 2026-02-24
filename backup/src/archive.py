"""Archive creation and extraction functions."""

import os
import tarfile
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger('shiori-backup')


def create_archive(
    source_paths: List[str],
    output_path: str,
    compression: str = 'gz'
) -> bool:
    """
    Create a compressed tar archive from source paths.

    Args:
        source_paths: List of paths to include in the archive
        output_path: Path for the output archive
        compression: Compression type ('gz', 'bz2', 'xz', or '')

    Returns:
        True if successful, False otherwise
    """
    try:
        mode = 'w:' + compression if compression else 'w'

        with tarfile.open(output_path, mode) as tar:
            for source_path in source_paths:
                if not os.path.exists(source_path):
                    logger.warning(f"Source path does not exist: {source_path}")
                    continue

                # Add to archive with relative path
                tar.add(source_path, arcname=os.path.basename(source_path))
                logger.debug(f"Added {source_path} to archive")

        archive_size = os.path.getsize(output_path)
        logger.info(f"Created archive: {output_path} ({archive_size} bytes)")
        return True

    except Exception as e:
        logger.error(f"Failed to create archive: {e}")
        return False


def extract_archive(
    archive_path: str,
    output_dir: str,
    specific_files: Optional[List[str]] = None
) -> bool:
    """
    Extract a tar archive to the specified directory.

    Args:
        archive_path: Path to the archive file
        output_dir: Directory to extract to
        specific_files: Optional list of specific files to extract

    Returns:
        True if successful, False otherwise
    """
    try:
        os.makedirs(output_dir, exist_ok=True)

        with tarfile.open(archive_path, 'r:*') as tar:
            if specific_files:
                for member in specific_files:
                    try:
                        tar.extract(member, output_dir)
                        logger.debug(f"Extracted {member}")
                    except KeyError:
                        logger.warning(f"File not found in archive: {member}")
            else:
                tar.extractall(output_dir)
                logger.debug(f"Extracted all files to {output_dir}")

        logger.info(f"Extracted archive: {archive_path} to {output_dir}")
        return True

    except Exception as e:
        logger.error(f"Failed to extract archive: {e}")
        return False


def list_archive_contents(archive_path: str) -> List[str]:
    """
    List the contents of a tar archive.

    Args:
        archive_path: Path to the archive file

    Returns:
        List of file names in the archive
    """
    try:
        with tarfile.open(archive_path, 'r:*') as tar:
            return tar.getnames()
    except Exception as e:
        logger.error(f"Failed to list archive contents: {e}")
        return []


def collect_shiori_data(data_dir: str) -> List[str]:
    """
    Collect all Shiori data directories and files for backup.

    Args:
        data_dir: Path to Shiori data directory

    Returns:
        List of paths to include in backup
    """
    data_path = Path(data_dir)
    paths_to_backup = []

    if not data_path.exists():
        logger.warning(f"Shiori data directory does not exist: {data_dir}")
        return paths_to_backup

    # Always include these directories if they exist
    shiori_dirs = ['archive', 'thumb', 'ebook']

    for dir_name in shiori_dirs:
        dir_path = data_path / dir_name
        if dir_path.exists():
            paths_to_backup.append(str(dir_path))
            logger.debug(f"Found {dir_name} directory")

    # Include SQLite database if it exists
    db_path = data_path / 'shiori.db'
    if db_path.exists():
        # Don't add directly, it will be backed up via SQLite handler
        logger.debug("Found SQLite database (will be backed up separately)")

    return paths_to_backup
