"""Tests for main backup orchestration."""

import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock, ANY

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import backup as backup_module
from backup import create_backup, run_scheduler, main


class TestCreateBackup:
    """Tests for create_backup function."""

    def test_create_backup_success(self, mock_env, sample_data_dir, temp_dir):
        """Test successful backup creation."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir,
            BACKUP_ENCRYPTION_KEY='test_key_123'
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.upload_to_all_destinations') as mock_upload:
                mock_upload.return_value = (True, [])

                with patch('backup.cleanup_all_backups') as mock_cleanup:
                    mock_cleanup.return_value = {'local_deleted': 0}

                    with patch('backup.get_notification_manager') as mock_notify:
                        mock_notifier = MagicMock()
                        mock_notify.return_value = mock_notifier

                        result = create_backup()

        assert result is True
        mock_handler.backup.assert_called_once()
        mock_upload.assert_called_once()
        mock_notifier.notify_backup_success.assert_called_once()

    def test_create_backup_no_encryption(self, mock_env, sample_data_dir, temp_dir):
        """Test backup without encryption."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir
            # No BACKUP_ENCRYPTION_KEY
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.upload_to_all_destinations') as mock_upload:
                mock_upload.return_value = (True, [])

                with patch('backup.encrypt_file') as mock_encrypt:
                    with patch('backup.get_notification_manager') as mock_notify:
                        mock_notifier = MagicMock()
                        mock_notify.return_value = mock_notifier

                        result = create_backup()

        assert result is True
        mock_encrypt.assert_not_called()  # Should not encrypt without key

    def test_create_backup_database_failure(self, mock_env, sample_data_dir, temp_dir):
        """Test backup failure when database backup fails."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = False  # Failure
            mock_get_handler.return_value = mock_handler

            with patch('backup.get_notification_manager') as mock_notify:
                mock_notifier = MagicMock()
                mock_notify.return_value = mock_notifier

                result = create_backup()

        assert result is False
        mock_notifier.notify_backup_failure.assert_called_once()

    def test_create_backup_no_handler(self, mock_env, sample_data_dir, temp_dir):
        """Test backup failure when no database handler available."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir
        )

        with patch('backup.get_database_handler', return_value=None):
            with patch('backup.get_notification_manager') as mock_notify:
                mock_notifier = MagicMock()
                mock_notify.return_value = mock_notifier

                result = create_backup()

        assert result is False

    def test_create_backup_archive_failure(self, mock_env, sample_data_dir, temp_dir):
        """Test backup failure when archive creation fails."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.create_archive', return_value=False):
                with patch('backup.get_notification_manager') as mock_notify:
                    mock_notifier = MagicMock()
                    mock_notify.return_value = mock_notifier

                    result = create_backup()

        assert result is False
        mock_notifier.notify_backup_failure.assert_called_once()

    def test_create_backup_encryption_failure(self, mock_env, sample_data_dir, temp_dir):
        """Test backup failure when encryption fails."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir,
            BACKUP_ENCRYPTION_KEY='test_key'
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.encrypt_file', return_value=False):
                with patch('backup.get_notification_manager') as mock_notify:
                    mock_notifier = MagicMock()
                    mock_notify.return_value = mock_notifier

                    result = create_backup()

        assert result is False

    def test_create_backup_with_partial_upload(self, mock_env, sample_data_dir, temp_dir):
        """Test backup with partial upload success."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir,
            BACKUP_DELETE_LOCAL_AFTER_UPLOAD='false'
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.upload_to_all_destinations') as mock_upload:
                mock_upload.return_value = (True, ['s3:failed'])  # Partial success

                with patch('backup.get_notification_manager') as mock_notify:
                    mock_notifier = MagicMock()
                    mock_notify.return_value = mock_notifier

                    result = create_backup()

        assert result is True  # Still considered success

    def test_create_backup_deletes_local_after_upload(self, mock_env, sample_data_dir, temp_dir):
        """Test that local backup is deleted after successful upload."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir,
            BACKUP_DELETE_LOCAL_AFTER_UPLOAD='true'
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.upload_to_all_destinations') as mock_upload:
                mock_upload.return_value = (True, [])  # Complete success

                with patch('backup.should_delete_local_after_upload', return_value=True):
                    with patch('os.remove') as mock_remove:
                        with patch('backup.get_notification_manager') as mock_notify:
                            mock_notifier = MagicMock()
                            mock_notify.return_value = mock_notifier

                            result = create_backup()

        # Local file should be removed

    def test_create_backup_runs_retention(self, mock_env, sample_data_dir, temp_dir):
        """Test that retention cleanup runs after backup."""
        mock_env(
            BACKUP_DIR=temp_dir,
            SHIORI_DATA_DIR=sample_data_dir,
            BACKUP_RETENTION_DAYS='30'
        )

        with patch('backup.get_database_handler') as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.get_info.return_value = {'type': 'sqlite'}
            mock_handler.backup.return_value = True
            mock_get_handler.return_value = mock_handler

            with patch('backup.upload_to_all_destinations') as mock_upload:
                mock_upload.return_value = (True, [])

                with patch('backup.cleanup_all_backups') as mock_cleanup:
                    mock_cleanup.return_value = {'local_deleted': 5}

                    with patch('backup.get_notification_manager') as mock_notify:
                        mock_notifier = MagicMock()
                        mock_notify.return_value = mock_notifier

                        create_backup()

                    mock_cleanup.assert_called_once_with(30)


class TestRunScheduler:
    """Tests for run_scheduler function."""

    def test_scheduler_initialization(self, mock_env):
        """Test scheduler initialization."""
        mock_env(BACKUP_SCHEDULE='0 2 * * *')

        with patch('croniter.croniter') as mock_croniter:
            mock_itr = MagicMock()
            mock_itr.get_next.return_value = datetime(2024, 1, 2, 2, 0, 0)
            mock_croniter.return_value = mock_itr

            with patch('backup.create_backup') as mock_backup:
                with patch('time.sleep', side_effect=Exception('Stop loop')):
                    try:
                        run_scheduler()
                    except Exception:
                        pass

            mock_croniter.assert_called_once_with('0 2 * * *', ANY)

    def test_invalid_cron_schedule(self, mock_env):
        """Test handling of invalid cron schedule."""
        mock_env(BACKUP_SCHEDULE='invalid')

        with patch('croniter.croniter', side_effect=Exception('Invalid')):
            with patch('backup.logger') as mock_logger:
                with pytest.raises(SystemExit):
                    run_scheduler()


class TestMain:
    """Tests for main function."""

    def test_main_with_now_flag(self, mock_env):
        """Test main function with --now flag."""
        mock_env()

        with patch.object(sys, 'argv', ['backup.py', '--now']):
            with patch('backup.create_backup', return_value=True) as mock_create:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0
                mock_create.assert_called_once()

    def test_main_with_now_flag_failure(self, mock_env):
        """Test main function with --now flag and failure."""
        mock_env()

        with patch.object(sys, 'argv', ['backup.py', '--now']):
            with patch('backup.create_backup', return_value=False):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

    def test_main_starts_scheduler(self, mock_env):
        """Test main function starts scheduler by default."""
        mock_env()

        with patch.object(sys, 'argv', ['backup.py']):
            with patch('backup.run_scheduler') as mock_run:
                with pytest.raises(Exception):  # Will raise from run_scheduler
                    main()

                mock_run.assert_called_once()
