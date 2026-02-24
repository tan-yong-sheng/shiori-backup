"""Notification functions for backup events."""

import os
import json
import logging
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

logger = logging.getLogger('shiori-backup')


class NotificationManager:
    """Manages backup notifications via webhook and email."""

    def __init__(self):
        self.webhook_url = os.getenv('BACKUP_WEBHOOK_URL')
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.smtp_to = os.getenv('SMTP_TO')

    def _send_webhook(self, payload: dict) -> bool:
        """Send notification to webhook URL."""
        if not self.webhook_url:
            return False

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            logger.debug(f"Webhook notification sent: {response.status_code}")
            return True

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False

    def _send_email(self, subject: str, body: str, is_html: bool = False) -> bool:
        """Send notification via email."""
        if not all([self.smtp_host, self.smtp_user, self.smtp_password, self.smtp_to]):
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = self.smtp_to

            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.debug("Email notification sent")
            return True

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False

    def notify_backup_success(
        self,
        backup_id: str,
        archive_path: str,
        archive_size: int,
        duration_seconds: float
    ):
        """Send notification for successful backup."""
        timestamp = datetime.utcnow().isoformat()

        # Webhook notification
        if self.webhook_url:
            payload = {
                'event': 'backup_success',
                'timestamp': timestamp,
                'backup_id': backup_id,
                'archive': {
                    'path': archive_path,
                    'size_bytes': archive_size
                },
                'duration_seconds': duration_seconds
            }
            self._send_webhook(payload)

        # Email notification
        if self.smtp_host:
            subject = f"[Shiori Backup] Success - {backup_id}"
            body = f"""Shiori Backup Completed Successfully

Backup ID: {backup_id}
Timestamp: {timestamp}
Archive: {archive_path}
Size: {archive_size} bytes
Duration: {duration_seconds:.2f} seconds
"""
            self._send_email(subject, body)

    def notify_backup_failure(
        self,
        backup_id: str,
        error_message: str,
        duration_seconds: Optional[float] = None
    ):
        """Send notification for failed backup."""
        timestamp = datetime.utcnow().isoformat()

        # Webhook notification
        if self.webhook_url:
            payload = {
                'event': 'backup_failure',
                'timestamp': timestamp,
                'backup_id': backup_id,
                'error': error_message,
                'duration_seconds': duration_seconds
            }
            self._send_webhook(payload)

        # Email notification
        if self.smtp_host:
            subject = f"[Shiori Backup] FAILED - {backup_id}"
            body = f"""Shiori Backup FAILED

Backup ID: {backup_id}
Timestamp: {timestamp}
Error: {error_message}
"""
            if duration_seconds:
                body += f"Duration: {duration_seconds:.2f} seconds\n"

            self._send_email(subject, body)

    def notify_restore_success(
        self,
        backup_id: str,
        restore_path: str
    ):
        """Send notification for successful restore."""
        timestamp = datetime.utcnow().isoformat()

        if self.webhook_url:
            payload = {
                'event': 'restore_success',
                'timestamp': timestamp,
                'backup_id': backup_id,
                'restored_to': restore_path
            }
            self._send_webhook(payload)

        if self.smtp_host:
            subject = f"[Shiori Backup] Restore Success - {backup_id}"
            body = f"""Shiori Restore Completed Successfully

Backup ID: {backup_id}
Timestamp: {timestamp}
Restored to: {restore_path}
"""
            self._send_email(subject, body)

    def notify_restore_failure(
        self,
        backup_id: str,
        error_message: str
    ):
        """Send notification for failed restore."""
        timestamp = datetime.utcnow().isoformat()

        if self.webhook_url:
            payload = {
                'event': 'restore_failure',
                'timestamp': timestamp,
                'backup_id': backup_id,
                'error': error_message
            }
            self._send_webhook(payload)

        if self.smtp_host:
            subject = f"[Shiori Backup] Restore FAILED - {backup_id}"
            body = f"""Shiori Restore FAILED

Backup ID: {backup_id}
Timestamp: {timestamp}
Error: {error_message}
"""
            self._send_email(subject, body)


def get_notification_manager() -> NotificationManager:
    """Get a configured notification manager instance."""
    return NotificationManager()
