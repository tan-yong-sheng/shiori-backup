"""Tests for restore functionality."""

import os
import sys
import argparse
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import restore as restore_module
from restore import (
    list_available_backups, download_backup, restore_backup, main
)


class TestListAvailableBackups:
    """Tests for list_available_backups function."""

    def test_list_local_backups(self, temp_dir):
        """Test listing local backups."""
        # Create sample backup files
        for i in range(3):
            filename = f'shiori-backup-2024010{i+1}_120000.tar.gz'
            with open(os.path.join(temp_dir, filename), 'w') as f:
                f.write(f'backup {i}')

        with patch('restore.get_env', return_value=temp_dir):
            backups = list_available_backups('local')

        assert len(backups) == 3
        # Should be sorted newest first
        assert '20240103' in backups[0]['name']

    def test_list_local_backups_empty_directory(self, temp_dir):
        """Test listing local backups from empty directory."""
        with patch('restore.get_env', return_value=temp_dir):
            backups = list_available_backups('local')

        assert backups == []

    def test_list_cloud_backups(self):
        """Test listing cloud backups."""
        mock_backups = [
            {'name': 'backup1.tar.gz', 'mod_time': '2024-01-02T12:00:00Z', 'size': 1024},
            {'name': 'backup2.tar.gz', 'mod_time': '2024-01-01T12:00:00Z', 'size': 2048}
        ]

        with patch('restore.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.list_backups.return_value = mock_backups
            mock_storage_class.return_value = mock_storage

            with patch('restore.get_destinations', return_value=['s3:bucket']):
                backups = list_available_backups('cloud')

        assert len(backups) == 2
        assert backups[0]['full_remote'] == 's3:bucket/backup1.tar.gz'

    def test_list_cloud_backups_multiple_destinations(self):
        """Test listing cloud backups from multiple destinations."""
        mock_backups_s3 = [
            {'name': 's3-backup.tar.gz', 'mod_time': '2024-01-02T12:00:00Z', 'size': 1024}
        ]
        mock_backups_r2 = [
            {'name': 'r2-backup.tar.gz', 'mod_time': '2024-01-03T12:00:00Z', 'size': 2048}
        ]

        with patch('restore.RcloneStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.list_backups.side_effect = [mock_backups_s3, mock_backups_r2]
            mock_storage_class.return_value = mock_storage

            with patch('restore.get_destinations', return_value=['s3:bucket', 'r2:backups']):
                backups = list_available_backups('cloud')

        assert len(backups) == 2
        # Should be sorted by time
        assert 'r2-backup' in backups[0]['name']

    def test_list_cloud_backups_no_destinations(self):
        """Test listing cloud backups with no destinations configured."""
        with patch('restore.get_destinations', return_value=[]):
            backups = list_available_backups('cloud')

        assert backups == []


class TestDownloadBackup:
    """Tests for download_backup function."""

    def test_download_remote_backup(self, temp_dir):
        """Test downloading from remote destination."""
        with patch('restore.download_from_destination') as mock_download:
            mock_download.return_value = os.path.join(temp_dir, 'backup.tar.gz')

            result = download_backup('s3:bucket/backup.tar.gz', temp_dir)

        assert result == os.path.join(temp_dir, 'backup.tar.gz')
        mock_download.assert_called_once_with('s3:bucket/backup.tar.gz', temp_dir)

    def test_download_remote_failure(self, temp_dir):
        """Test handling of remote download failure."""
        with patch('restore.download_from_destination', return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                download_backup('s3:bucket/backup.tar.gz', temp_dir)

            assert 'Failed to download' in str(exc_info.value)

    def test_download_local_backup(self, temp_dir, temp_file):
        """Test copying local backup."""
        local_file = temp_file(content=b'backup data', suffix='.tar.gz')

        result = download_backup(local_file, temp_dir)

        assert os.path.exists(result)
        with open(result, 'rb') as f:
            assert f.read() == b'backup data'

    def test_download_local_not_found(self, temp_dir):
        """Test handling of missing local file."""
        with pytest.raises(FileNotFoundError):
            download_backup('/nonexistent/backup.tar.gz', temp_dir)


class TestRestoreBackup:
    """Tests for restore_backup function."""

    def test_restore_backup_success(self, mock_env, sample_data_dir, temp_dir, temp_file):
        """Test successful restore."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        # Create a mock backup archive
        archive_path = temp_file(content=b'fake archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=True):
                    with patch('restore.list_archive_contents', return_value=['database_backup', 'archive', 'thumb', 'ebook']):
                        with patch('restore.get_database_handler') as mock_get_handler:
                            mock_handler = MagicMock()
                            mock_handler.restore.return_value = True
                            mock_get_handler.return_value = mock_handler

                            with patch('restore.get_notification_manager') as mock_notify:
                                mock_notifier = MagicMock()
                                mock_notify.return_value = mock_notifier

                                with patch('restore.shutil.copytree'):
                                    result = restore_backup(archive_path, force=True)

        assert result is True
        mock_handler.restore.assert_called_once()
        mock_notifier.notify_restore_success.assert_called_once()

    def test_restore_backup_user_cancel(self, temp_file):
        """Test restore cancelled by user."""
        archive_path = temp_file(content=b'fake archive', suffix='.tar.gz')

        with patch('builtins.input', return_value='no'):
            result = restore_backup(archive_path, force=False)

        assert result is False

    def test_restore_backup_force_no_prompt(self, mock_env, sample_data_dir, temp_file):
        """Test restore with force flag skips confirmation."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'fake archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=True):
                    with patch('restore.list_archive_contents', return_value=['database_backup']):
                        with patch('restore.get_database_handler') as mock_get_handler:
                            mock_handler = MagicMock()
                            mock_handler.restore.return_value = True
                            mock_get_handler.return_value = mock_handler

                            with patch('restore.get_notification_manager') as mock_notify:
                                mock_notifier = MagicMock()
                                mock_notify.return_value = mock_notifier

                                with patch('restore.shutil.copytree'):
                                    # force=True should not call input
                                    with patch('builtins.input') as mock_input:
                                        result = restore_backup(archive_path, force=True)

        assert result is True
        mock_input.assert_not_called()

    def test_restore_backup_decrypts_encrypted(self, mock_env, sample_data_dir, temp_file):
        """Test restore handles encrypted backup."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'encrypted archive', suffix='.tar.gz.gpg')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=True):
                with patch('restore.decrypt_file', return_value=True):
                    with patch('restore.extract_archive', return_value=True):
                        with patch('restore.list_archive_contents', return_value=['database_backup']):
                            with patch('restore.get_database_handler') as mock_get_handler:
                                mock_handler = MagicMock()
                                mock_handler.restore.return_value = True
                                mock_get_handler.return_value = mock_handler

                                with patch('restore.get_notification_manager') as mock_notify:
                                    mock_notifier = MagicMock()
                                    mock_notify.return_value = mock_notifier

                                    with patch('restore.shutil.copytree'):
                                        result = restore_backup(archive_path, force=True)

        assert result is True

    def test_restore_backup_decrypt_failure(self, mock_env, sample_data_dir, temp_file):
        """Test restore fails when decryption fails."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'encrypted archive', suffix='.tar.gz.gpg')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=True):
                with patch('restore.decrypt_file', return_value=False):
                    with patch('restore.get_notification_manager') as mock_notify:
                        mock_notifier = MagicMock()
                        mock_notify.return_value = mock_notifier

                        with pytest.raises(RuntimeError) as exc_info:
                            restore_backup(archive_path, force=True)

                        assert 'Failed to decrypt' in str(exc_info.value)

    def test_restore_backup_extract_failure(self, mock_env, sample_data_dir, temp_file):
        """Test restore fails when extraction fails."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=False):
                    with patch('restore.get_notification_manager') as mock_notify:
                        mock_notifier = MagicMock()
                        mock_notify.return_value = mock_notifier

                        with pytest.raises(RuntimeError) as exc_info:
                            restore_backup(archive_path, force=True)

                        assert 'Failed to extract' in str(exc_info.value)

    def test_restore_backup_no_database_backup(self, mock_env, sample_data_dir, temp_file):
        """Test restore fails when database backup not found in archive."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=True):
                    with patch('restore.list_archive_contents', return_value=['some_file.txt']):
                        with patch('os.path.exists', return_value=False):
                            with patch('restore.get_notification_manager') as mock_notify:
                                mock_notifier = MagicMock()
                                mock_notify.return_value = mock_notifier

                                with pytest.raises(FileNotFoundError):
                                    restore_backup(archive_path, force=True)

    def test_restore_backup_database_restore_failure(self, mock_env, sample_data_dir, temp_file):
        """Test restore fails when database restore fails."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=True):
                    with patch('restore.list_archive_contents', return_value=['database_backup']):
                        with patch('restore.get_database_handler') as mock_get_handler:
                            mock_handler = MagicMock()
                            mock_handler.restore.return_value = False
                            mock_get_handler.return_value = mock_handler

                            with patch('restore.get_notification_manager') as mock_notify:
                                mock_notifier = MagicMock()
                                mock_notify.return_value = mock_notifier

                                with pytest.raises(RuntimeError) as exc_info:
                                    restore_backup(archive_path, force=True)

                                assert 'Database restore failed' in str(exc_info.value)

    def test_restore_backup_creates_safety_backup(self, mock_env, sample_data_dir, temp_file):
        """Test that restore creates a safety backup."""
        mock_env(SHIORI_DATA_DIR=sample_data_dir)

        archive_path = temp_file(content=b'archive', suffix='.tar.gz')

        with patch('restore.download_backup', return_value=archive_path):
            with patch('restore.is_encrypted', return_value=False):
                with patch('restore.extract_archive', return_value=True):
                    with patch('restore.list_archive_contents', return_value=['database_backup', 'archive']):
                        with patch('restore.get_database_handler') as mock_get_handler:
                            mock_handler = MagicMock()
                            mock_handler.restore.return_value = True
                            mock_get_handler.return_value = mock_handler

                            with patch('restore.get_notification_manager') as mock_notify:
                                mock_notifier = MagicMock()
                                mock_notify.return_value = mock_notifier

                                with patch('restore.shutil.copytree') as mock_copy:
                                    restore_backup(archive_path, force=True)

                                    # Should create safety backup
                                    mock_copy.assert_called()


class TestMain:
    """Tests for main function."""

    def test_main_list_backups(self, mock_env, temp_dir):
        """Test --list command."""
        mock_env(BACKUP_DIR=temp_dir)

        # Create sample backup files
        for i in range(3):
            filename = f'shiori-backup-2024010{i+1}_120000.tar.gz'
            with open(os.path.join(temp_dir, filename), 'w') as f:
                f.write(f'backup {i}')

        with patch.object(sys, 'argv', ['restore.py', '--list', '--source', 'local']):
            with patch('restore.load_config'):
                with patch('restore.get_env', return_value=temp_dir):
                    # Should not raise
                    main()

    def test_main_list_empty(self, mock_env):
        """Test --list with no backups."""
        mock_env()

        with patch.object(sys, 'argv', ['restore.py', '--list', '--source', 'cloud']):
            with patch('restore.load_config'):
                with patch('restore.list_available_backups', return_value=[]):
                    # Should not raise
                    main()

    def test_main_restore_latest(self, mock_env):
        """Test --restore-latest command."""
        mock_env()

        mock_backups = [
            {'name': 'backup.tar.gz', 'path': '/backups/backup.tar.gz', 'full_remote': 's3:bucket/backup.tar.gz'}
        ]

        with patch.object(sys, 'argv', ['restore.py', '--restore-latest']):
            with patch('restore.load_config'):
                with patch('restore.list_available_backups', return_value=mock_backups):
                    with patch('restore.restore_backup', return_value=True):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

                        assert exc_info.value.code == 0

    def test_main_restore_latest_no_backups(self, mock_env):
        """Test --restore-latest with no backups available."""
        mock_env()

        with patch.object(sys, 'argv', ['restore.py', '--restore-latest']):
            with patch('restore.load_config'):
                with patch('restore.list_available_backups', return_value=[]):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 1

    def test_main_restore_specific(self, mock_env):
        """Test --restore command with specific backup."""
        mock_env()

        with patch.object(sys, 'argv', ['restore.py', '--restore', 's3:bucket/backup.tar.gz']):
            with patch('restore.load_config'):
                with patch('restore.restore_backup', return_value=True):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 0

    def test_main_restore_specific_failure(self, mock_env):
        """Test --restore command with failure."""
        mock_env()

        with patch.object(sys, 'argv', ['restore.py', '--restore', 's3:bucket/backup.tar.gz']):
            with patch('restore.load_config'):
                with patch('restore.restore_backup', return_value=False):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 1

    def test_main_no_args(self, mock_env):
        """Test main with no arguments prints help."""
        mock_env()

        with patch.object(sys, 'argv', ['restore.py']):
            with patch('restore.load_config'):
                with patch('restore.ArgumentParser.print_help') as mock_help:
                    main()
                    mock_help.assert_called_once()
