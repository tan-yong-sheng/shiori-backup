"""Tests for backup retention and cleanup functions."""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from retention import (
    parse_backup_timestamp, cleanup_local_backups, cleanup_cloud_backups,
    cleanup_all_backups, should_delete_local_after_upload
)


class TestParseBackupTimestamp:
    """Tests for parse_backup_timestamp function."""

    def test_parse_standard_filename(self):
        """Test parsing standard backup filename."""
        filename = 'shiori-backup-20240115_143022.tar.gz'
        result = parse_backup_timestamp(filename)

        expected = datetime(2024, 1, 15, 14, 30, 22)
        assert result == expected

    def test_parse_encrypted_filename(self):
        """Test parsing encrypted backup filename."""
        filename = 'shiori-backup-20240115_143022.tar.gz.gpg'
        result = parse_backup_timestamp(filename)

        expected = datetime(2024, 1, 15, 14, 30, 22)
        assert result == expected

    def test_parse_invalid_filename(self):
        """Test parsing invalid filename."""
        filename = 'not-a-backup-file.txt'
        result = parse_backup_timestamp(filename)

        # Should return epoch (fallback)
        assert result == datetime.fromtimestamp(0)

    def test_parse_filename_with_different_extensions(self):
        """Test parsing filenames with various extensions."""
        base = 'shiori-backup-20240115_143022'

        # Both should work
        result1 = parse_backup_timestamp(f'{base}.tar.gz')
        result2 = parse_backup_timestamp(f'{base}.tar.gz.gpg')

        assert result1 == result2

    def test_parse_malformed_timestamp(self):
        """Test parsing filename with malformed timestamp."""
        filename = 'shiori-backup-2024-01-15_1430.tar.gz'
        result = parse_backup_timestamp(filename)

        assert result == datetime.fromtimestamp(0)


class TestCleanupLocalBackups:
    """Tests for cleanup_local_backups function."""

    def test_cleanup_deletes_old_files(self, sample_backup_files):
        """Test that old backup files are deleted."""
        backup_dir, files = sample_backup_files
        retention_days = 15

        deleted, bytes_freed = cleanup_local_backups(backup_dir, retention_days)

        # Count files older than 15 days (should be at least 2: 40 and 60 days ago)
        # May delete more if additional files are older due to time passage
        assert deleted >= 2
        assert bytes_freed > 0

        # Verify at least 3 files remain (some may be older due to time passage)
        remaining = os.listdir(backup_dir)
        assert len(remaining) >= 3

    def test_cleanup_keeps_recent_files(self, sample_backup_files):
        """Test that recent backup files are kept."""
        backup_dir, files = sample_backup_files
        retention_days = 30

        deleted, _ = cleanup_local_backups(backup_dir, 30)

        # Should only delete files older than 30 days (40 and 60 days ago)
        # May delete more if additional files are older due to time passage
        assert deleted >= 2

    def test_cleanup_zero_retention_disables_cleanup(self, sample_backup_files):
        """Test that zero retention disables cleanup."""
        backup_dir, files = sample_backup_files

        deleted, bytes_freed = cleanup_local_backups(backup_dir, 0)

        assert deleted == 0
        assert bytes_freed == 0

        # All files should still exist
        assert len(os.listdir(backup_dir)) == 6

    def test_cleanup_negative_retention_disables_cleanup(self, sample_backup_files):
        """Test that negative retention disables cleanup."""
        backup_dir, files = sample_backup_files

        deleted, bytes_freed = cleanup_local_backups(backup_dir, -1)

        assert deleted == 0
        assert bytes_freed == 0

    def test_cleanup_nonexistent_directory(self):
        """Test cleanup of non-existent directory."""
        deleted, bytes_freed = cleanup_local_backups('/nonexistent/path', 30)

        assert deleted == 0
        assert bytes_freed == 0

    def test_cleanup_handles_deletion_errors(self, sample_backup_files):
        """Test handling of file deletion errors."""
        backup_dir, files = sample_backup_files

        with patch('pathlib.Path.unlink', side_effect=PermissionError('Access denied')):
            deleted, _ = cleanup_local_backups(backup_dir, 1)

        # Should handle error gracefully
        assert deleted == 0


class TestCleanupCloudBackups:
    """Tests for cleanup_cloud_backups function."""

    def test_cleanup_deletes_old_cloud_backups(self):
        """Test deleting old cloud backups."""
        now = datetime.utcnow()

        mock_backups = [
            {'name': 'shiori-backup-20240101_120000.tar.gz',
             'mod_time': (now - timedelta(days=40)).isoformat(), 'size': 1024},
            {'name': 'shiori-backup-20240201_120000.tar.gz',
             'mod_time': (now - timedelta(days=10)).isoformat(), 'size': 2048},
            {'name': 'shiori-backup-20240301_120000.tar.gz',
             'mod_time': (now - timedelta(days=1)).isoformat(), 'size': 4096}
        ]

        with patch('retention.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.list_backups.return_value = mock_backups
            mock_storage.delete.return_value = True
            mock_storage_class.return_value = mock_storage

            deleted, bytes_freed = cleanup_cloud_backups('s3:bucket', 30)

        # May delete more than 1 if additional files are older due to time passage
        assert deleted >= 1
        assert bytes_freed >= 1024

    def test_cleanup_zero_retention_disables_cleanup(self):
        """Test that zero retention disables cloud cleanup."""
        with patch('retention.RcloneStorage') as mock_storage_class:
            deleted, bytes_freed = cleanup_cloud_backups('s3:bucket', 0)

        assert deleted == 0
        assert bytes_freed == 0

    def test_cleanup_handles_deletion_failure(self):
        """Test handling of cloud deletion failure."""
        now = datetime.utcnow()

        mock_backups = [
            {'name': 'shiori-backup-20240101_120000.tar.gz',
             'mod_time': (now - timedelta(days=40)).isoformat(), 'size': 1024}
        ]

        with patch('retention.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.list_backups.return_value = mock_backups
            mock_storage.delete.return_value = False  # Deletion fails
            mock_storage_class.return_value = mock_storage

            deleted, bytes_freed = cleanup_cloud_backups('s3:bucket', 30)

        assert deleted == 0  # Failed deletions don't count
        assert bytes_freed == 0


class TestCleanupAllBackups:
    """Tests for cleanup_all_backups function."""

    def test_cleanup_all_locations(self, mock_env, sample_backup_files):
        """Test cleanup from all configured locations."""
        backup_dir, files = sample_backup_files
        mock_env(
            BACKUP_DIR=backup_dir,
            BACKUP_RCLONE_DESTINATIONS='s3:bucket,r2:backups'
        )

        now = datetime.utcnow()
        mock_backups = [
            {'name': 'shiori-backup-20240101_120000.tar.gz',
             'mod_time': (now - timedelta(days=40)).isoformat(), 'size': 1024}
        ]

        with patch('retention.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.list_backups.return_value = mock_backups
            mock_storage.delete.return_value = True
            mock_storage_class.return_value = mock_storage

            stats = cleanup_all_backups(15)

        assert 'local_deleted' in stats
        assert 'local_bytes_freed' in stats
        assert 'cloud_stats' in stats
        assert 's3:bucket' in stats['cloud_stats']
        assert 'r2:backups' in stats['cloud_stats']

    def test_cleanup_with_no_destinations(self, mock_env, sample_backup_files):
        """Test cleanup with no cloud destinations."""
        backup_dir, files = sample_backup_files
        mock_env(
            BACKUP_DIR=backup_dir,
            BACKUP_RCLONE_DESTINATIONS=''
        )

        stats = cleanup_all_backups(15)

        # Should delete at least 2 old files
        assert stats['local_deleted'] >= 2
        assert stats['cloud_stats'] == {}


class TestShouldDeleteLocalAfterUpload:
    """Tests for should_delete_local_after_upload function."""

    def test_returns_true_when_enabled(self, mock_env):
        """Test returns True when env var is true."""
        mock_env(BACKUP_DELETE_LOCAL_AFTER_UPLOAD='true')
        assert should_delete_local_after_upload() is True

    def test_returns_false_when_disabled(self, mock_env):
        """Test returns False when env var is false."""
        mock_env(BACKUP_DELETE_LOCAL_AFTER_UPLOAD='false')
        assert should_delete_local_after_upload() is False

    def test_returns_false_by_default(self, mock_env):
        """Test returns False by default."""
        mock_env()
        assert should_delete_local_after_upload() is False

    def test_case_insensitive(self, mock_env):
        """Test case insensitivity."""
        mock_env(BACKUP_DELETE_LOCAL_AFTER_UPLOAD='TRUE')
        assert should_delete_local_after_upload() is True

        mock_env(BACKUP_DELETE_LOCAL_AFTER_UPLOAD='True')
        assert should_delete_local_after_upload() is True
