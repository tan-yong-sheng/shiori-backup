"""Cloud storage operations using rclone."""

import os
import subprocess
import logging
from typing import List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger('shiori-backup')


class RcloneStorage:
    """Handler for rclone cloud storage operations."""

    def __init__(self, config_path: str = '/config/rclone/rclone.conf'):
        self.config_path = config_path
        self._check_rclone()

    def _check_rclone(self):
        """Verify rclone is installed and accessible."""
        try:
            result = subprocess.run(
                ['rclone', 'version'],
                capture_output=True,
                check=True
            )
            logger.debug("rclone is available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("rclone not found or not working")

    def _run_rclone(self, args: List[str]) -> Tuple[bool, str]:
        """Run an rclone command with the specified arguments."""
        cmd = ['rclone', '--config', self.config_path] + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr

        except Exception as e:
            return False, str(e)

    def upload(self, local_path: str, remote_path: str) -> bool:
        """
        Upload a file to cloud storage.

        Args:
            local_path: Path to the local file
            remote_path: Remote destination (format: remote:path)

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Uploading {local_path} to {remote_path}")

        success, output = self._run_rclone([
            'copy',
            local_path,
            remote_path,
            '--progress',
            '--stats-one-line'
        ])

        if success:
            logger.info(f"Successfully uploaded to {remote_path}")
        else:
            logger.error(f"Upload failed: {output}")

        return success

    def download(self, remote_path: str, local_path: str) -> bool:
        """
        Download a file from cloud storage.

        Args:
            remote_path: Remote source (format: remote:path)
            local_path: Path to save the file locally

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Downloading {remote_path} to {local_path}")

        # Create local directory if it doesn't exist
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

        success, output = self._run_rclone([
            'copy',
            remote_path,
            os.path.dirname(local_path) or '.',
            '--progress',
            '--stats-one-line'
        ])

        if success:
            logger.info(f"Successfully downloaded from {remote_path}")
        else:
            logger.error(f"Download failed: {output}")

        return success

    def list_backups(self, remote_path: str, pattern: str = '*.tar.gz*') -> List[dict]:
        """
        List backup files in cloud storage.

        Args:
            remote_path: Remote path to list (format: remote:path)
            pattern: File pattern to filter

        Returns:
            List of backup file information dictionaries
        """
        import json

        success, output = self._run_rclone([
            'lsjson',
            remote_path,
            '--files-only'
        ])

        if not success:
            logger.error(f"Failed to list remote files: {output}")
            return []

        try:
            files = json.loads(output)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse remote file list: {output}")
            return []

        backups = []
        for file_info in files:
            # Skip directories
            if file_info.get('IsDir', False):
                continue

            name = file_info.get('Name', '')
            if name.endswith(('.tar.gz', '.tar.gz.gpg')):
                backups.append({
                    'name': name,
                    'path': file_info.get('Path', name),
                    'remote': remote_path,
                    'mod_time': file_info.get('ModTime', ''),
                    'size': file_info.get('Size', 0)
                })

        # Sort by modification time (newest first)
        backups.sort(key=lambda x: x.get('mod_time', ''), reverse=True)
        return backups

    def delete(self, remote_path: str) -> bool:
        """
        Delete a file from cloud storage.

        Args:
            remote_path: Remote file to delete (format: remote:path)

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Deleting {remote_path}")

        success, output = self._run_rclone([
            'delete',
            remote_path
        ])

        if success:
            logger.info(f"Successfully deleted {remote_path}")
        else:
            logger.error(f"Delete failed: {output}")

        return success

    def check_configured(self) -> bool:
        """Check if rclone is properly configured."""
        if not os.path.exists(self.config_path):
            logger.warning(f"rclone config not found at {self.config_path}")
            return False

        success, output = self._run_rclone(['listremotes'])
        if success and output.strip():
            logger.info(f"Configured remotes: {output.strip().split()}")
            return True
        else:
            logger.warning("No rclone remotes configured")
            return False


def get_destinations() -> List[str]:
    """
    Get list of configured backup destinations from environment.

    Returns:
        List of destination strings (format: remote:path)
    """
    destinations = os.getenv('BACKUP_RCLONE_DESTINATIONS', '')
    if not destinations:
        return []

    return [d.strip() for d in destinations.split(',') if d.strip()]


def upload_to_all_destinations(local_path: str) -> Tuple[bool, List[str]]:
    """
    Upload a file to all configured destinations.

    Args:
        local_path: Path to the local file

    Returns:
        Tuple of (overall_success, list_of_failed_destinations)
    """
    destinations = get_destinations()
    if not destinations:
        logger.warning("No backup destinations configured")
        return False, []

    storage = RcloneStorage()
    failed = []

    for destination in destinations:
        # Ensure destination ends with / for directory copy
        remote_path = destination if destination.endswith('/') else destination + '/'
        if not storage.upload(local_path, remote_path):
            failed.append(destination)

    success = len(failed) < len(destinations)
    return success, failed


def download_from_destination(remote_spec: str, local_dir: str = '/tmp') -> Optional[str]:
    """
    Download a backup from a remote destination.

    Args:
        remote_spec: Full remote path (format: remote:path/to/file)
        local_dir: Local directory to save to

    Returns:
        Path to the downloaded file, or None if failed
    """
    storage = RcloneStorage()

    filename = os.path.basename(remote_spec)
    local_path = os.path.join(local_dir, filename)

    if storage.download(remote_spec, local_path):
        return local_path
    return None
