"""Tests for notification functions."""

import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from notifications import NotificationManager, get_notification_manager


class TestNotificationManagerInit:
    """Tests for NotificationManager initialization."""

    def test_init_reads_env_vars(self, mock_env):
        """Test that constructor reads environment variables."""
        mock_env(
            BACKUP_WEBHOOK_URL='https://hooks.example.com/backup',
            SMTP_HOST='smtp.example.com',
            SMTP_PORT='587',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )

        nm = NotificationManager()

        assert nm.webhook_url == 'https://hooks.example.com/backup'
        assert nm.smtp_host == 'smtp.example.com'
        assert nm.smtp_port == 587
        assert nm.smtp_user == 'backup@example.com'
        assert nm.smtp_password == 'secret'
        assert nm.smtp_to == 'admin@example.com'

    def test_init_defaults(self):
        """Test default values when env vars not set."""
        # Temporarily unset env vars
        backup_webhook = os.environ.pop('BACKUP_WEBHOOK_URL', None)
        smtp_host = os.environ.pop('SMTP_HOST', None)
        smtp_port = os.environ.pop('SMTP_PORT', None)

        try:
            nm = NotificationManager()

            assert nm.webhook_url is None
            assert nm.smtp_host is None
            assert nm.smtp_port == 587  # Default port
        finally:
            # Restore env vars
            if backup_webhook is not None:
                os.environ['BACKUP_WEBHOOK_URL'] = backup_webhook
            if smtp_host is not None:
                os.environ['SMTP_HOST'] = smtp_host
            if smtp_port is not None:
                os.environ['SMTP_PORT'] = smtp_port


class TestSendWebhook:
    """Tests for _send_webhook method."""

    def test_send_webhook_success(self, mock_env, mock_requests):
        """Test successful webhook delivery."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')

        nm = NotificationManager()
        payload = {'event': 'test', 'data': 'value'}

        result = nm._send_webhook(payload)

        assert result is True
        mock_requests.assert_called_once()
        call_args = mock_requests.call_args
        assert call_args[0][0] == 'https://hooks.example.com/backup'
        assert call_args[1]['json'] == payload

    def test_send_webhook_no_url(self, mock_env):
        """Test webhook when no URL configured."""
        mock_env()

        nm = NotificationManager()
        result = nm._send_webhook({'event': 'test'})

        assert result is False

    def test_send_webhook_failure(self, mock_env, mock_requests):
        """Test webhook delivery failure."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')
        mock_requests.side_effect = Exception('Connection timeout')

        nm = NotificationManager()
        result = nm._send_webhook({'event': 'test'})

        assert result is False

    def test_send_webhook_http_error(self, mock_env, mock_requests):
        """Test webhook HTTP error response."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')
        mock_requests.return_value.raise_for_status.side_effect = Exception('404 Not Found')

        nm = NotificationManager()
        result = nm._send_webhook({'event': 'test'})

        assert result is False


class TestSendEmail:
    """Tests for _send_email method."""

    def test_send_email_success(self, mock_env, mock_smtp):
        """Test successful email delivery."""
        mock_env(
            SMTP_HOST='smtp.example.com',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )

        nm = NotificationManager()
        result = nm._send_email('Test Subject', 'Test body')

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with('backup@example.com', 'secret')
        mock_smtp.send_message.assert_called_once()

    def test_send_email_html(self, mock_env, mock_smtp):
        """Test HTML email delivery."""
        mock_env(
            SMTP_HOST='smtp.example.com',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )

        nm = NotificationManager()
        result = nm._send_email('Test', '<p>HTML body</p>', is_html=True)

        assert result is True

    def test_send_email_not_configured(self, mock_env):
        """Test email when SMTP not configured."""
        mock_env()

        nm = NotificationManager()
        result = nm._send_email('Test', 'Body')

        assert result is False

    def test_send_email_failure(self, mock_env, mock_smtp):
        """Test email delivery failure."""
        mock_env(
            SMTP_HOST='smtp.example.com',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )
        mock_smtp.login.side_effect = Exception('Authentication failed')

        nm = NotificationManager()
        result = nm._send_email('Test', 'Body')

        assert result is False


class TestNotifyBackupSuccess:
    """Tests for notify_backup_success method."""

    def test_notify_success_webhook_only(self, mock_env, mock_requests):
        """Test success notification via webhook only."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')
        mock_env(SMTP_HOST=None)

        nm = NotificationManager()

        with patch.object(nm, '_send_email') as mock_email:
            nm.notify_backup_success('backup-123', '/path/backup.tar.gz', 1024, 10.5)

            mock_requests.assert_called_once()
            mock_email.assert_not_called()

            # Verify webhook payload
            call_args = mock_requests.call_args
            payload = call_args[1]['json']
            assert payload['event'] == 'backup_success'
            assert payload['backup_id'] == 'backup-123'
            assert payload['duration_seconds'] == 10.5
            assert payload['archive']['size_bytes'] == 1024

    def test_notify_success_email_only(self, mock_env, mock_smtp):
        """Test success notification via email only."""
        mock_env(
            SMTP_HOST='smtp.example.com',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )

        nm = NotificationManager()

        with patch.object(nm, '_send_webhook') as mock_webhook:
            nm.notify_backup_success('backup-123', '/path/backup.tar.gz', 1024, 10.5)

            mock_webhook.assert_not_called()
            mock_smtp.send_message.assert_called_once()

    def test_notify_success_both(self, mock_env, mock_requests, mock_smtp):
        """Test success notification via both webhook and email."""
        mock_env(
            BACKUP_WEBHOOK_URL='https://hooks.example.com/backup',
            SMTP_HOST='smtp.example.com',
            SMTP_USER='backup@example.com',
            SMTP_PASSWORD='secret',
            SMTP_TO='admin@example.com'
        )

        nm = NotificationManager()
        nm.notify_backup_success('backup-123', '/path/backup.tar.gz', 1024, 10.5)

        mock_requests.assert_called_once()
        mock_smtp.send_message.assert_called_once()

    def test_notify_success_no_config(self):
        """Test success notification with no configuration."""
        # Temporarily unset env vars
        backup_webhook = os.environ.pop('BACKUP_WEBHOOK_URL', None)
        smtp_host = os.environ.pop('SMTP_HOST', None)
        smtp_port = os.environ.pop('SMTP_PORT', None)

        try:
            nm = NotificationManager()

            with patch.object(nm, '_send_webhook') as mock_webhook:
                with patch.object(nm, '_send_email') as mock_email:
                    nm.notify_backup_success('backup-123', '/path/backup.tar.gz', 1024, 10.5)

                    mock_webhook.assert_not_called()
                    mock_email.assert_not_called()
        finally:
            # Restore env vars
            if backup_webhook is not None:
                os.environ['BACKUP_WEBHOOK_URL'] = backup_webhook
            if smtp_host is not None:
                os.environ['SMTP_HOST'] = smtp_host
            if smtp_port is not None:
                os.environ['SMTP_PORT'] = smtp_port


class TestNotifyBackupFailure:
    """Tests for notify_backup_failure method."""

    def test_notify_failure(self, mock_env, mock_requests):
        """Test failure notification."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')

        nm = NotificationManager()
        nm.notify_backup_failure('backup-123', 'Database connection failed', 5.0)

        mock_requests.assert_called_once()
        payload = mock_requests.call_args[1]['json']
        assert payload['event'] == 'backup_failure'
        assert payload['error'] == 'Database connection failed'
        assert payload['duration_seconds'] == 5.0

    def test_notify_failure_no_duration(self, mock_env, mock_requests):
        """Test failure notification without duration."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')

        nm = NotificationManager()
        nm.notify_backup_failure('backup-123', 'Error occurred')

        payload = mock_requests.call_args[1]['json']
        assert payload['error'] == 'Error occurred'
        assert payload['duration_seconds'] is None


class TestNotifyRestoreSuccess:
    """Tests for notify_restore_success method."""

    def test_notify_restore_success(self, mock_env, mock_requests):
        """Test restore success notification."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')

        nm = NotificationManager()
        nm.notify_restore_success('backup-123', '/srv/shiori')

        mock_requests.assert_called_once()
        payload = mock_requests.call_args[1]['json']
        assert payload['event'] == 'restore_success'
        assert payload['backup_id'] == 'backup-123'
        assert payload['restored_to'] == '/srv/shiori'


class TestNotifyRestoreFailure:
    """Tests for notify_restore_failure method."""

    def test_notify_restore_failure(self, mock_env, mock_requests):
        """Test restore failure notification."""
        mock_env(BACKUP_WEBHOOK_URL='https://hooks.example.com/backup')

        nm = NotificationManager()
        nm.notify_restore_failure('backup-123', 'Archive extraction failed')

        mock_requests.assert_called_once()
        payload = mock_requests.call_args[1]['json']
        assert payload['event'] == 'restore_failure'
        assert payload['error'] == 'Archive extraction failed'


class TestGetNotificationManager:
    """Tests for get_notification_manager function."""

    def test_returns_instance(self):
        """Test that function returns NotificationManager instance."""
        nm = get_notification_manager()

        assert isinstance(nm, NotificationManager)

    def test_returns_new_instance_each_call(self):
        """Test that each call returns a new instance."""
        nm1 = get_notification_manager()
        nm2 = get_notification_manager()

        assert nm1 is not nm2
        assert isinstance(nm1, NotificationManager)
        assert isinstance(nm2, NotificationManager)
