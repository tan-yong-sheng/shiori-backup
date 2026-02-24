"""Tests for cloud storage operations."""

import os
import sys
import json
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from storage import (
    RcloneStorage, get_destinations, upload_to_all_destinations,
    download_from_destination
)


class TestRcloneStorageInit:
    """Tests for RcloneStorage initialization."""

    def test_default_config_path(self):
        """Test default configuration path."""
        with patch('storage.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            storage = RcloneStorage()
            assert storage.config_path == '/config/rclone/rclone.conf'

    def test_custom_config_path(self):
        """Test custom configuration path."""
        with patch('storage.subprocess.run'):
            storage = RcloneStorage('/custom/path/rclone.conf')
            assert storage.config_path == '/custom/path/rclone.conf'

    def test_check_rclone_success(self):
        """Test rclone availability check success."""
        with patch('storage.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            with patch('storage.logger') as mock_logger:
                RcloneStorage()
                mock_logger.debug.assert_called()

    def test_check_rclone_failure(self):
        """Test rclone availability check failure."""
        with patch('storage.subprocess.run', side_effect=FileNotFoundError()):
            with patch('storage.logger') as mock_logger:
                RcloneStorage()
                mock_logger.warning.assert_called()


class TestRcloneStorageRunRclone:
    """Tests for _run_rclone method."""

    def test_run_success(self, mock_subprocess_run):
        """Test successful rclone command."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = '/config/rclone/rclone.conf'

        success, output = storage._run_rclone(['ls', 'remote:'])

        assert success is True
        assert output == 'success output'

    def test_run_failure(self, mock_subprocess_run):
        """Test failed rclone command."""
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = 'error message'

        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = '/config/rclone/rclone.conf'

        success, output = storage._run_rclone(['ls', 'remote:'])

        assert success is False
        assert output == 'error message'

    def test_run_exception(self, mock_subprocess_run):
        """Test rclone command exception."""
        mock_subprocess_run.side_effect = Exception('Command failed')

        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = '/config/rclone/rclone.conf'

        success, output = storage._run_rclone(['ls', 'remote:'])

        assert success is False
        assert 'Command failed' in output


class TestRcloneStorageUpload:
    """Tests for upload method."""

    def test_upload_success(self, temp_file, mock_subprocess_run):
        """Test successful upload."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = '/config/rclone/rclone.conf'
        storage._run_rclone = MagicMock(return_value=(True, 'success'))

        local_path = temp_file(content=b'test data')
        result = storage.upload(local_path, 's3:bucket/backups/')

        assert result is True
        storage._run_rclone.assert_called_once()
        call_args = storage._run_rclone.call_args[0][0]
        assert 'copy' in call_args

    def test_upload_failure(self, temp_file):
        """Test failed upload."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(False, 'upload failed'))

        local_path = temp_file(content=b'test data')
        result = storage.upload(local_path, 's3:bucket/backups/')

        assert result is False


class TestRcloneStorageDownload:
    """Tests for download method."""

    def test_download_success(self, temp_dir):
        """Test successful download."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(True, 'success'))

        local_path = os.path.join(temp_dir, 'downloaded.txt')
        result = storage.download('s3:bucket/file.txt', local_path)

        assert result is True
        assert os.path.exists(temp_dir)

    def test_download_creates_directory(self, temp_dir):
        """Test that download creates local directory."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(True, 'success'))

        nested_dir = os.path.join(temp_dir, 'nested', 'dir')
        local_path = os.path.join(nested_dir, 'file.txt')

        result = storage.download('s3:bucket/file.txt', local_path)

        assert result is True
        assert os.path.exists(os.path.dirname(nested_dir))

    def test_download_failure(self, temp_dir):
        """Test failed download."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(False, 'download failed'))

        local_path = os.path.join(temp_dir, 'file.txt')
        result = storage.download('s3:bucket/file.txt', local_path)

        assert result is False


class TestRcloneStorageListBackups:
    """Tests for list_backups method."""

    def test_list_backups_success(self):
        """Test successful backup listing."""
        storage = RcloneStorage.__new__(RcloneStorage)

        mock_files = [
            {'Name': 'shiori-backup-20240101_120000.tar.gz', 'IsDir': False,
             'Path': 'shiori-backup-20240101_120000.tar.gz',
             'ModTime': '2024-01-01T12:00:00Z', 'Size': 1024},
            {'Name': 'other-file.txt', 'IsDir': False,
             'Path': 'other-file.txt', 'ModTime': '2024-01-01T10:00:00Z', 'Size': 100},
            {'Name': 'shiori-backup-20240101_110000.tar.gz.gpg', 'IsDir': False,
             'Path': 'shiori-backup-20240101_110000.tar.gz.gpg',
             'ModTime': '2024-01-01T11:00:00Z', 'Size': 2048},
            {'Name': 'backup_dir', 'IsDir': True}
        ]

        storage._run_rclone = MagicMock(return_value=(True, json.dumps(mock_files)))

        result = storage.list_backups('s3:bucket')

        assert len(result) == 2  # Only tar.gz files
        assert result[0]['name'] == 'shiori-backup-20240101_120000.tar.gz'
        assert result[1]['name'] == 'shiori-backup-20240101_110000.tar.gz.gpg'

    def test_list_backups_sorted(self):
        """Test that backups are sorted by modification time."""
        storage = RcloneStorage.__new__(RcloneStorage)

        mock_files = [
            {'Name': 'shiori-backup-20240101_100000.tar.gz', 'IsDir': False,
             'Path': 'path1', 'ModTime': '2024-01-01T10:00:00Z', 'Size': 1024},
            {'Name': 'shiori-backup-20240101_120000.tar.gz', 'IsDir': False,
             'Path': 'path2', 'ModTime': '2024-01-01T12:00:00Z', 'Size': 1024},
            {'Name': 'shiori-backup-20240101_110000.tar.gz', 'IsDir': False,
             'Path': 'path3', 'ModTime': '2024-01-01T11:00:00Z', 'Size': 1024}
        ]

        storage._run_rclone = MagicMock(return_value=(True, json.dumps(mock_files)))

        result = storage.list_backups('s3:bucket')

        # Should be sorted newest first
        assert result[0]['mod_time'] == '2024-01-01T12:00:00Z'
        assert result[1]['mod_time'] == '2024-01-01T11:00:00Z'
        assert result[2]['mod_time'] == '2024-01-01T10:00:00Z'

    def test_list_backups_command_failure(self):
        """Test handling of failed list command."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(False, 'connection error'))

        result = storage.list_backups('s3:bucket')

        assert result == []

    def test_list_backups_invalid_json(self):
        """Test handling of invalid JSON response."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(True, 'not valid json'))

        result = storage.list_backups('s3:bucket')

        assert result == []


class TestRcloneStorageDelete:
    """Tests for delete method."""

    def test_delete_success(self):
        """Test successful deletion."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(True, 'success'))

        result = storage.delete('s3:bucket/old-backup.tar.gz')

        assert result is True
        storage._run_rclone.assert_called_once_with([
            'delete', 's3:bucket/old-backup.tar.gz'
        ])

    def test_delete_failure(self):
        """Test failed deletion."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage._run_rclone = MagicMock(return_value=(False, 'permission denied'))

        result = storage.delete('s3:bucket/old-backup.tar.gz')

        assert result is False


class TestRcloneStorageCheckConfigured:
    """Tests for check_configured method."""

    def test_check_configured_success(self, temp_file):
        """Test successful configuration check."""
        config_path = temp_file(content=b'[s3]\ntype = s3\n')
        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = config_path
        storage._run_rclone = MagicMock(return_value=(True, 's3:\n'))

        result = storage.check_configured()

        assert result is True

    def test_check_configured_missing_file(self, temp_dir):
        """Test when config file doesn't exist."""
        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = '/nonexistent/rclone.conf'

        result = storage.check_configured()

        assert result is False

    def test_check_configured_no_remotes(self, temp_file):
        """Test when no remotes are configured."""
        config_path = temp_file(content=b'empty config')
        storage = RcloneStorage.__new__(RcloneStorage)
        storage.config_path = config_path
        storage._run_rclone = MagicMock(return_value=(True, ''))

        result = storage.check_configured()

        assert result is False


class TestGetDestinations:
    """Tests for get_destinations function."""

    def test_get_single_destination(self, mock_env):
        """Test getting single destination."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket/backups')

        result = get_destinations()

        assert result == ['s3:bucket/backups']

    def test_get_multiple_destinations(self, mock_env):
        """Test getting multiple destinations."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket,r2:backups,gcs:archive')

        result = get_destinations()

        assert result == ['s3:bucket', 'r2:backups', 'gcs:archive']

    def test_get_destinations_with_whitespace(self, mock_env):
        """Test that whitespace is trimmed."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='  s3:bucket  ,  r2:backups  ')

        result = get_destinations()

        assert result == ['s3:bucket', 'r2:backups']

    def test_get_destinations_empty(self, mock_env):
        """Test empty destinations."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='')

        result = get_destinations()

        assert result == []

    def test_get_destinations_not_set(self, mock_env):
        """Test when env var is not set."""
        mock_env()

        result = get_destinations()

        assert result == []


class TestUploadToAllDestinations:
    """Tests for upload_to_all_destinations function."""

    def test_upload_all_success(self, mock_env, temp_file):
        """Test successful upload to all destinations."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket,r2:backups')

        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.upload.return_value = True
            mock_storage_class.return_value = mock_storage

            local_path = temp_file(content=b'backup data')
            success, failed = upload_to_all_destinations(local_path)

        assert success is True
        assert failed == []

    def test_upload_partial_failure(self, mock_env, temp_file):
        """Test partial upload failure."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket,r2:backups,gcs:archive')

        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            # First succeeds, second fails, third succeeds
            mock_storage.upload.side_effect = [True, False, True]
            mock_storage_class.return_value = mock_storage

            local_path = temp_file(content=b'backup data')
            success, failed = upload_to_all_destinations(local_path)

        assert success is True  # At least one succeeded
        assert failed == ['r2:backups']

    def test_upload_all_failure(self, mock_env, temp_file):
        """Test complete upload failure."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket,r2:backups')

        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.upload.return_value = False
            mock_storage_class.return_value = mock_storage

            local_path = temp_file(content=b'backup data')
            success, failed = upload_to_all_destinations(local_path)

        assert success is False
        assert len(failed) == 2

    def test_upload_no_destinations(self, mock_env, temp_file):
        """Test upload with no destinations configured."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='')

        local_path = temp_file(content=b'backup data')
        success, failed = upload_to_all_destinations(local_path)

        assert success is False
        assert failed == []

    def test_upload_adds_trailing_slash(self, mock_env, temp_file):
        """Test that trailing slash is added to destination."""
        mock_env(BACKUP_RCLONE_DESTINATIONS='s3:bucket')

        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.upload.return_value = True
            mock_storage_class.return_value = mock_storage

            local_path = temp_file(content=b'backup data')
            upload_to_all_destinations(local_path)

            # Check that destination ends with /
            call_args = mock_storage.upload.call_args
            assert call_args[0][1].endswith('/')


class TestDownloadFromDestination:
    """Tests for download_from_destination function."""

    def test_download_success(self, temp_dir):
        """Test successful download."""
        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.download.return_value = True
            mock_storage_class.return_value = mock_storage

            result = download_from_destination('s3:bucket/backup.tar.gz', temp_dir)

            assert result is not None
            assert 'backup.tar.gz' in result

    def test_download_failure(self, temp_dir):
        """Test failed download."""
        with patch('storage.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.download.return_value = False
            mock_storage_class.return_value = mock_storage

            result = download_from_destination('s3:bucket/backup.tar.gz', temp_dir)

            assert result is None
