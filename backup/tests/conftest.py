"""Pytest configuration and fixtures for shiori-backup tests."""

import os
import sys
import json
import sqlite3
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmpdir = tempfile.mkdtemp(prefix='shiori-test-')
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_file(temp_dir):
    """Create a temporary file with content."""
    def _create_temp_file(content=b'test content', suffix='.txt'):
        fd, path = tempfile.mkstemp(dir=temp_dir, suffix=suffix)
        os.write(fd, content if isinstance(content, bytes) else content.encode())
        os.close(fd)
        return path
    return _create_temp_file


@pytest.fixture
def mock_env():
    """Fixture to temporarily set environment variables."""
    original_env = dict(os.environ)
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
    yield _set_env
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def sample_data_dir(temp_dir):
    """Create a sample Shiori data directory structure."""
    # Create directories
    archive_dir = os.path.join(temp_dir, 'archive')
    thumb_dir = os.path.join(temp_dir, 'thumb')
    ebook_dir = os.path.join(temp_dir, 'ebook')

    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)
    os.makedirs(ebook_dir, exist_ok=True)

    # Create some sample files
    with open(os.path.join(archive_dir, 'page1.html'), 'w') as f:
        f.write('<html><body>Test</body></html>')

    with open(os.path.join(thumb_dir, 'thumb1.jpg'), 'wb') as f:
        f.write(b'fake image data')

    with open(os.path.join(ebook_dir, 'book1.epub'), 'wb') as f:
        f.write(b'fake epub data')

    # Create a sample SQLite database
    db_path = os.path.join(temp_dir, 'shiori.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE bookmarks (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT
        )
    ''')
    cursor.execute('INSERT INTO bookmarks (url, title) VALUES (?, ?)',
                   ('https://example.com', 'Example'))
    conn.commit()
    conn.close()

    return temp_dir


@pytest.fixture
def mock_database_handler():
    """Create a mock database handler."""
    handler = MagicMock()
    handler.backup.return_value = True
    handler.restore.return_value = True
    handler.get_info.return_value = {
        'type': 'sqlite',
        'page_count': 10,
        'page_size': 4096
    }
    return handler


@pytest.fixture
def mock_rclone_storage():
    """Create a mock RcloneStorage instance."""
    with patch('storage.RcloneStorage') as mock_class:
        instance = MagicMock()
        instance.upload.return_value = True
        instance.download.return_value = True
        instance.delete.return_value = True
        instance.list_backups.return_value = [
            {
                'name': 'shiori-backup-20240101_120000.tar.gz',
                'path': 'shiori-backup-20240101_120000.tar.gz',
                'remote': 's3:backups',
                'mod_time': '2024-01-01T12:00:00Z',
                'size': 1024
            }
        ]
        instance.check_configured.return_value = True
        mock_class.return_value = instance
        yield instance


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for external command testing."""
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'success output'
        mock_result.stderr = ''
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def sample_backup_files(temp_dir):
    """Create sample backup files for retention testing."""
    # Create backup files with different dates
    files = []
    now = datetime.utcnow()

    for days_ago in [1, 5, 10, 20, 40, 60]:
        date = now - timedelta(days=days_ago)
        filename = f"shiori-backup-{date.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        filepath = os.path.join(temp_dir, filename)

        with open(filepath, 'w') as f:
            f.write(f'backup data {days_ago} days ago')

        # Set modification time
        mod_time = (now - timedelta(days=days_ago)).timestamp()
        os.utime(filepath, (mod_time, mod_time))
        files.append(filepath)

    return temp_dir, files


@pytest.fixture
def sample_metadata():
    """Return sample backup metadata dictionary."""
    return {
        'backup_id': 'shiori-backup-20240101_120000',
        'timestamp': '2024-01-01T12:00:00Z',
        'source': '/srv/shiori',
        'hostname': 'test-host',
        'database': {
            'type': 'sqlite',
            'page_count': 10,
            'page_size': 4096
        },
        'files': {
            'database_backup': {
                'checksum': 'abc123',
                'size': 1024
            },
            'shiori-backup-20240101_120000.tar.gz': {
                'checksum': 'def456',
                'size': 2048
            }
        }
    }


@pytest.fixture
def mock_requests():
    """Mock requests library for webhook testing."""
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        yield mock_post


@pytest.fixture
def mock_smtp():
    """Mock SMTP library for email testing."""
    with patch('smtplib.SMTP') as mock_smtp_class:
        instance = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=instance)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_smtp_class.return_value = instance
        yield instance


@pytest.fixture
def mock_tarfile():
    """Mock tarfile module for archive testing."""
    with patch('tarfile.open') as mock_open:
        mock_tar = MagicMock()
        mock_tar.getnames.return_value = ['file1.txt', 'file2.txt']
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_tar)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_open, mock_tar


@pytest.fixture
def mock_gpg_encrypt(temp_dir):
    """Create a mock GPG encryption result."""
    def _create_encrypted(input_path, output_path=None):
        if output_path is None:
            output_path = input_path + '.gpg'
        with open(output_path, 'w') as f:
            f.write('encrypted content')
        return output_path
    return _create_encrypted
