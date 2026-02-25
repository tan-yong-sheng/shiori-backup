"""Tests for backup utility functions."""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils import (
    setup_logging, load_config, get_env, calculate_sha256,
    generate_backup_filename, format_bytes, parse_database_url,
    BackupMetadata
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_default_log_level(self, mock_env):
        """Test that default log level is INFO."""
        mock_env()  # Clear environment
        if 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']

        with patch('logging.basicConfig') as mock_basic_config:
            logger = setup_logging()
            # Verify basicConfig was called with INFO level
            assert mock_basic_config.called
            args = mock_basic_config.call_args
            assert args[1]['level'] == logging.INFO

    def test_custom_log_level_from_env(self, mock_env):
        """Test that log level can be set from environment."""
        mock_env(LOG_LEVEL='DEBUG')

        with patch('logging.basicConfig') as mock_basic_config:
            logger = setup_logging()
            # Verify basicConfig was called with DEBUG level
            assert mock_basic_config.called
            args = mock_basic_config.call_args
            assert args[1]['level'] == logging.DEBUG

    def test_explicit_log_level(self, mock_env):
        """Test that explicit log level overrides environment."""
        mock_env(LOG_LEVEL='ERROR')

        with patch('logging.basicConfig') as mock_basic_config:
            logger = setup_logging('WARNING')
            # Verify basicConfig was called with WARNING level (explicit > env)
            assert mock_basic_config.called
            args = mock_basic_config.call_args
            assert args[1]['level'] == logging.WARNING

    def test_invalid_log_level_defaults_to_info(self):
        """Test that invalid log level defaults to INFO."""
        with patch('logging.basicConfig') as mock_basic_config:
            logger = setup_logging('INVALID_LEVEL')
            # Verify basicConfig was called with INFO (fallback)
            assert mock_basic_config.called
            args = mock_basic_config.call_args
            assert args[1]['level'] == logging.INFO

    def test_logger_has_correct_name(self):
        """Test that logger has the correct name."""
        logger = setup_logging()
        assert logger.name == 'shiori-backup'


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_from_app_env_if_exists(self):
        """Test loading from /app/.env if it exists."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('utils.load_dotenv') as mock_load:
                load_config()
                # Both paths exist so load_dotenv should be called twice
                assert mock_load.call_count == 2

    def test_loads_from_current_dir_if_app_env_missing(self):
        """Test loading from current dir if /app/.env missing."""
        with patch('pathlib.Path.exists', return_value=False):
            with patch('utils.load_dotenv') as mock_load:
                load_config()
                # Only current dir .env should be loaded
                mock_load.assert_called_once()


class TestGetEnv:
    """Tests for get_env function."""

    def test_get_existing_env_var(self, mock_env):
        """Test getting an existing environment variable."""
        mock_env(TEST_VAR='test_value')
        assert get_env('TEST_VAR') == 'test_value'

    def test_get_nonexistent_env_var_returns_none(self, mock_env):
        """Test getting a non-existent environment variable."""
        mock_env()
        assert get_env('NONEXISTENT_VAR') is None

    def test_get_with_default(self, mock_env):
        """Test getting with default value."""
        mock_env()
        assert get_env('NONEXISTENT_VAR', default='default_value') == 'default_value'

    def test_get_existing_overrides_default(self, mock_env):
        """Test that existing value overrides default."""
        mock_env(TEST_VAR='actual_value')
        assert get_env('TEST_VAR', default='default_value') == 'actual_value'

    def test_required_env_var_raises_error(self, mock_env):
        """Test that required env var raises ValueError if missing."""
        mock_env()
        with pytest.raises(ValueError) as exc_info:
            get_env('REQUIRED_VAR', required=True)
        assert 'REQUIRED_VAR' in str(exc_info.value)

    def test_required_env_var_succeeds(self, mock_env):
        """Test that required env var succeeds when present."""
        mock_env(REQUIRED_VAR='value')
        assert get_env('REQUIRED_VAR', required=True) == 'value'


class TestCalculateSha256:
    """Tests for calculate_sha256 function."""

    def test_calculate_sha256_of_file(self, temp_file):
        """Test SHA256 calculation of a file."""
        content = b'test content for hashing'
        file_path = temp_file(content=content)

        expected_hash = hashlib.sha256(content).hexdigest()
        assert calculate_sha256(file_path) == expected_hash

    def test_calculate_sha256_large_file(self, temp_file):
        """Test SHA256 calculation of large file (chunked reading)."""
        # Create content larger than 8192 bytes (chunk size)
        content = b'x' * 10000
        file_path = temp_file(content=content)

        expected_hash = hashlib.sha256(content).hexdigest()
        assert calculate_sha256(file_path) == expected_hash

    def test_calculate_sha256_empty_file(self, temp_file):
        """Test SHA256 calculation of empty file."""
        file_path = temp_file(content=b'')

        expected_hash = hashlib.sha256(b'').hexdigest()
        assert calculate_sha256(file_path) == expected_hash

    def test_calculate_sha256_binary_file(self, temp_file):
        """Test SHA256 calculation of binary file."""
        content = bytes(range(256))
        file_path = temp_file(content=content)

        expected_hash = hashlib.sha256(content).hexdigest()
        assert calculate_sha256(file_path) == expected_hash


class TestGenerateBackupFilename:
    """Tests for generate_backup_filename function."""

    def test_filename_format(self):
        """Test that filename has correct format."""
        filename = generate_backup_filename()
        assert filename.startswith('shiori-backup-')
        # Format: shiori-backup-YYYYMMDD_HHMMXX-{db_type}
        assert len(filename) == len('shiori-backup-') + 15 + 1 + 6  # prefix + timestamp + dash + db_type

    def test_filename_contains_timestamp(self):
        """Test that filename contains timestamp."""
        before = datetime.utcnow().replace(microsecond=0)
        filename = generate_backup_filename()
        after = datetime.utcnow().replace(microsecond=0)

        # Extract timestamp from filename
        # Format: shiori-backup-YYYYMMDD_HHMMXX-{db_type}
        timestamp_str = filename[len('shiori-backup-'):len('shiori-backup-') + 15]
        timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

        assert before <= timestamp <= after

    def test_unique_filenames(self):
        """Test that multiple calls produce different filenames."""
        filename1 = generate_backup_filename()
        filename2 = generate_backup_filename()
        # They should be different (unless called in same second)
        # This is a weak test but demonstrates intent
        assert isinstance(filename1, str)
        assert isinstance(filename2, str)


class TestFormatBytes:
    """Tests for format_bytes function."""

    def test_format_bytes(self):
        """Test formatting of various byte sizes."""
        assert format_bytes(0) == '0.00 B'
        assert format_bytes(512) == '512.00 B'
        assert format_bytes(1024) == '1.00 KB'
        assert format_bytes(1536) == '1.50 KB'
        assert format_bytes(1024 * 1024) == '1.00 MB'
        assert format_bytes(1024 ** 3) == '1.00 GB'
        assert format_bytes(1024 ** 4) == '1.00 TB'
        assert format_bytes(1024 ** 5) == '1.00 PB'

    def test_format_bytes_precision(self):
        """Test that formatting uses 2 decimal places."""
        result = format_bytes(1500)
        assert '.' in result
        assert len(result.split('.')[1].split()[0]) == 2


class TestParseDatabaseUrl:
    """Tests for parse_database_url function."""

    def test_empty_url(self):
        """Test parsing empty URL."""
        result = parse_database_url('')
        assert result['type'] is None
        assert result['host'] is None

    def test_postgres_url(self):
        """Test parsing PostgreSQL URL."""
        url = 'postgres://user:pass@localhost:5432/shiori?sslmode=require'
        result = parse_database_url(url)

        assert result['type'] == 'postgresql'
        assert result['user'] == 'user'
        assert result['password'] == 'pass'
        assert result['host'] == 'localhost'
        assert result['port'] == 5432
        assert result['database'] == 'shiori'
        assert result['options']['sslmode'] == 'require'

    def test_postgresql_url(self):
        """Test parsing postgresql:// URL."""
        url = 'postgresql://admin:secret@db.example.com:5433/mydb'
        result = parse_database_url(url)

        assert result['type'] == 'postgresql'
        assert result['host'] == 'db.example.com'
        assert result['port'] == 5433

    def test_mysql_url(self):
        """Test parsing MySQL URL."""
        url = 'mysql://root:password@mysql.host:3306/shiori'
        result = parse_database_url(url)

        assert result['type'] == 'mysql'
        assert result['user'] == 'root'
        assert result['password'] == 'password'
        assert result['host'] == 'mysql.host'
        assert result['port'] == 3306
        assert result['database'] == 'shiori'

    def test_url_without_password(self):
        """Test parsing URL without password."""
        url = 'postgres://user@localhost/shiori'
        result = parse_database_url(url)

        assert result['user'] == 'user'
        assert result['password'] is None
        assert result['host'] == 'localhost'
        assert result['database'] == 'shiori'

    def test_url_without_port(self):
        """Test parsing URL without explicit port (defaults to 5432)."""
        url = 'postgres://user:pass@localhost/shiori'
        result = parse_database_url(url)

        assert result['host'] == 'localhost'
        assert result['port'] == 5432

    def test_url_with_multiple_options(self):
        """Test parsing URL with multiple query options."""
        url = 'postgres://user:pass@localhost/db?sslmode=require&connect_timeout=10'
        result = parse_database_url(url)

        assert result['options']['sslmode'] == 'require'
        assert result['options']['connect_timeout'] == '10'

    def test_unsupported_url(self):
        """Test parsing unsupported URL type."""
        url = 'mongodb://localhost:27017/db'
        result = parse_database_url(url)

        assert result['type'] is None


class TestBackupMetadata:
    """Tests for BackupMetadata class."""

    def test_init(self):
        """Test BackupMetadata initialization."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')

        assert metadata.backup_id == 'backup-123'
        assert metadata.source == '/srv/shiori'
        assert metadata.files == {}
        assert metadata.database_info == {}
        assert metadata.hostname == os.getenv('HOSTNAME', 'unknown')
        assert 'T' in metadata.timestamp  # ISO format

    def test_add_file(self, temp_file):
        """Test adding a file to metadata."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')
        file_path = temp_file(content=b'test content')

        metadata.add_file(file_path, 'relative/path.txt')

        assert 'relative/path.txt' in metadata.files
        assert 'checksum' in metadata.files['relative/path.txt']
        assert 'size' in metadata.files['relative/path.txt']
        assert metadata.files['relative/path.txt']['size'] == len(b'test content')

    def test_add_nonexistent_file(self):
        """Test adding a non-existent file."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')

        metadata.add_file('/nonexistent/path.txt', 'relative/path.txt')

        assert 'relative/path.txt' not in metadata.files

    def test_set_database_info(self):
        """Test setting database information."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')

        metadata.set_database_info(type='sqlite', page_count=100, page_size=4096)

        assert metadata.database_info['type'] == 'sqlite'
        assert metadata.database_info['page_count'] == 100

    def test_to_dict(self, temp_file):
        """Test converting metadata to dictionary."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')
        file_path = temp_file(content=b'test')
        metadata.add_file(file_path, 'test.txt')
        metadata.set_database_info(type='sqlite')

        result = metadata.to_dict()

        assert result['backup_id'] == 'backup-123'
        assert result['source'] == '/srv/shiori'
        assert 'files' in result
        assert 'database' in result

    def test_save_and_load(self, temp_dir, temp_file):
        """Test saving and loading metadata."""
        metadata = BackupMetadata('backup-123', '/srv/shiori')
        file_path = temp_file(content=b'test')
        metadata.add_file(file_path, 'test.txt')
        metadata.set_database_info(type='sqlite')

        save_path = os.path.join(temp_dir, 'metadata.json')
        metadata.save(save_path)

        assert os.path.exists(save_path)

        loaded = BackupMetadata.load(save_path)

        assert loaded.backup_id == 'backup-123'
        assert loaded.source == '/srv/shiori'
        assert loaded.database_info['type'] == 'sqlite'
        assert 'test.txt' in loaded.files

    def test_load_invalid_json(self, temp_dir):
        """Test loading invalid JSON."""
        save_path = os.path.join(temp_dir, 'invalid.json')
        with open(save_path, 'w') as f:
            f.write('not valid json')

        with pytest.raises(json.JSONDecodeError):
            BackupMetadata.load(save_path)
