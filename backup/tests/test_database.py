"""Tests for database backup handlers."""

import os
import sys
import sqlite3
from unittest.mock import patch, MagicMock, mock_open

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import (
    DatabaseHandler, SQLiteHandler, PostgreSQLHandler, MySQLHandler,
    get_database_handler
)


class TestDatabaseHandlerAbstract:
    """Tests for abstract DatabaseHandler base class."""

    def test_cannot_instantiate_abstract(self):
        """Test that DatabaseHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DatabaseHandler()


class TestSQLiteHandler:
    """Tests for SQLiteHandler class."""

    def test_init(self, sample_data_dir):
        """Test SQLiteHandler initialization."""
        handler = SQLiteHandler(sample_data_dir)

        assert str(handler.data_dir) == sample_data_dir
        assert str(handler.db_path) == os.path.join(sample_data_dir, 'shiori.db')

    def test_backup_success(self, sample_data_dir, temp_dir):
        """Test successful SQLite backup."""
        handler = SQLiteHandler(sample_data_dir)
        output_path = os.path.join(temp_dir, 'backup.db')

        result = handler.backup(output_path)

        assert result is True
        assert os.path.exists(output_path)

        # Verify backup is valid SQLite database
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        assert ('bookmarks',) in tables

    def test_backup_missing_database(self, temp_dir):
        """Test backup when database doesn't exist."""
        handler = SQLiteHandler(temp_dir)
        output_path = os.path.join(temp_dir, 'backup.db')

        result = handler.backup(output_path)

        assert result is False

    def test_backup_failure(self, sample_data_dir, temp_dir):
        """Test backup failure handling."""
        handler = SQLiteHandler(sample_data_dir)
        output_path = os.path.join(temp_dir, 'backup.db')

        with patch('sqlite3.connect', side_effect=sqlite3.Error('Permission denied')):
            result = handler.backup(output_path)

        assert result is False

    def test_restore_success(self, sample_data_dir, temp_dir):
        """Test successful SQLite restore."""
        handler = SQLiteHandler(sample_data_dir)
        backup_path = os.path.join(temp_dir, 'backup.db')

        # Create a backup first
        handler.backup(backup_path)

        # Modify original database
        conn = sqlite3.connect(str(handler.db_path))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO bookmarks (url, title) VALUES (?, ?)",
                      ('https://new.com', 'New'))
        conn.commit()
        conn.close()

        # Restore
        result = handler.restore(backup_path)

        assert result is True

    def test_restore_failure(self, sample_data_dir, temp_dir):
        """Test restore failure handling."""
        handler = SQLiteHandler(sample_data_dir)

        with patch('shutil.copy2', side_effect=PermissionError('Access denied')):
            result = handler.restore('/some/path')

        assert result is False

    def test_get_info_with_database(self, sample_data_dir):
        """Test getting database info with valid database."""
        handler = SQLiteHandler(sample_data_dir)

        info = handler.get_info()

        assert info['type'] == 'sqlite'
        assert 'page_count' in info
        assert 'page_size' in info
        assert 'journal_mode' in info

    def test_get_info_without_database(self, temp_dir):
        """Test getting database info without valid database."""
        handler = SQLiteHandler(temp_dir)

        info = handler.get_info()

        assert info['type'] == 'sqlite'
        # When no database exists, page_count may not be present in info

    def test_get_info_handles_errors(self, sample_data_dir):
        """Test that get_info handles database errors gracefully."""
        handler = SQLiteHandler(sample_data_dir)

        with patch('sqlite3.connect', side_effect=sqlite3.Error('Connection failed')):
            info = handler.get_info()

        assert info['type'] == 'sqlite'


class TestPostgreSQLHandler:
    """Tests for PostgreSQLHandler class."""

    def test_init(self):
        """Test PostgreSQLHandler initialization."""
        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        assert handler.connection_url == url
        assert handler.parsed['type'] == 'postgresql'
        assert handler.parsed['user'] == 'user'

    def test_backup_success(self, mock_subprocess_run):
        """Test successful PostgreSQL backup."""
        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.backup('/tmp/backup.dump')

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert 'pg_dump' in call_args[0][0]

    def test_backup_with_ssl(self, mock_subprocess_run):
        """Test PostgreSQL backup with SSL options."""
        url = 'postgres://user:pass@localhost:5432/shiori?sslmode=require'
        handler = PostgreSQLHandler(url)

        handler.backup('/tmp/backup.dump')

        call_args = mock_subprocess_run.call_args[0][0]
        assert '--sslmode' in call_args
        assert 'require' in call_args

    def test_backup_failure(self, mock_subprocess_run):
        """Test PostgreSQL backup failure."""
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = 'pg_dump: connection refused'

        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.backup('/tmp/backup.dump')

        assert result is False

    def test_backup_exception(self, mock_subprocess_run):
        """Test PostgreSQL backup exception handling."""
        mock_subprocess_run.side_effect = Exception('pg_dump not found')

        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.backup('/tmp/backup.dump')

        assert result is False

    def test_restore_success(self, mock_subprocess_run):
        """Test successful PostgreSQL restore."""
        mock_subprocess_run.return_value.returncode = 0

        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.restore('/tmp/backup.dump')

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert 'pg_restore' in call_args[0][0]

    def test_restore_with_warnings(self, mock_subprocess_run):
        """Test PostgreSQL restore with warnings (return code 1)."""
        mock_subprocess_run.return_value.returncode = 1

        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.restore('/tmp/backup.dump')

        assert result is True  # Return code 1 is acceptable

    def test_restore_failure(self, mock_subprocess_run):
        """Test PostgreSQL restore failure."""
        mock_subprocess_run.return_value.returncode = 2
        mock_subprocess_run.return_value.stderr = 'pg_restore: error'

        url = 'postgres://user:pass@localhost:5432/shiori'
        handler = PostgreSQLHandler(url)

        result = handler.restore('/tmp/backup.dump')

        assert result is False

    def test_get_info(self):
        """Test getting PostgreSQL database info."""
        url = 'postgres://user:pass@db.example.com:5433/mydb'
        handler = PostgreSQLHandler(url)

        info = handler.get_info()

        assert info['type'] == 'postgresql'
        assert info['host'] == 'db.example.com'
        assert info['port'] == 5433
        assert info['database'] == 'mydb'


class TestMySQLHandler:
    """Tests for MySQLHandler class."""

    def test_init(self):
        """Test MySQLHandler initialization."""
        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        assert handler.connection_url == url
        assert handler.parsed['type'] == 'mysql'

    def test_backup_success(self, mock_subprocess_run):
        """Test successful MySQL backup."""
        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        with patch('builtins.open', mock_open()):
            result = handler.backup('/tmp/backup.sql')

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert 'mysqldump' in call_args[0][0]

    def test_backup_includes_routines(self, mock_subprocess_run):
        """Test that backup includes routines and triggers."""
        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        with patch('builtins.open', mock_open()):
            handler.backup('/tmp/backup.sql')

        call_args = mock_subprocess_run.call_args[0][0]
        assert '--routines' in call_args
        assert '--triggers' in call_args
        assert '--single-transaction' in call_args

    def test_backup_failure(self, mock_subprocess_run):
        """Test MySQL backup failure."""
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = 'mysqldump: access denied'

        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        with patch('builtins.open', mock_open()):
            result = handler.backup('/tmp/backup.sql')

        assert result is False

    def test_restore_success(self, mock_subprocess_run):
        """Test successful MySQL restore."""
        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        with patch('builtins.open', mock_open(read_data='SQL dump content')):
            result = handler.restore('/tmp/backup.sql')

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert 'mysql' in call_args[0][0]

    def test_restore_failure(self, mock_subprocess_run):
        """Test MySQL restore failure."""
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = 'mysql: error'

        url = 'mysql://root:password@localhost:3306/shiori'
        handler = MySQLHandler(url)

        with patch('builtins.open', mock_open(read_data='SQL')):
            result = handler.restore('/tmp/backup.sql')

        assert result is False

    def test_get_info(self):
        """Test getting MySQL database info."""
        url = 'mysql://admin:secret@mysql.example.com:3307/mydb'
        handler = MySQLHandler(url)

        info = handler.get_info()

        assert info['type'] == 'mysql'
        assert info['host'] == 'mysql.example.com'
        assert info['port'] == 3307
        assert info['database'] == 'mydb'


class TestGetDatabaseHandler:
    """Tests for get_database_handler factory function."""

    def test_postgres_url(self, mock_env):
        """Test handler creation for PostgreSQL URL."""
        mock_env(SHIORI_DATABASE_URL='postgres://user:pass@localhost/db')

        with patch('database.logger'):
            handler = get_database_handler()

        assert isinstance(handler, PostgreSQLHandler)

    def test_mysql_url(self, mock_env):
        """Test handler creation for MySQL URL."""
        mock_env(SHIORI_DATABASE_URL='mysql://root:pass@localhost/db')

        with patch('database.logger'):
            handler = get_database_handler()

        assert isinstance(handler, MySQLHandler)

    def test_sqlite_from_data_dir(self, mock_env):
        """Test handler creation from data directory."""
        mock_env(SHIORI_DATA_DIR='/srv/shiori')

        with patch('database.logger'):
            handler = get_database_handler()

        assert isinstance(handler, SQLiteHandler)

    def test_sqlite_default_location(self, mock_env):
        """Test handler creation with default location."""
        mock_env()  # Clear env

        with patch('os.path.exists', return_value=True):
            with patch('database.logger'):
                handler = get_database_handler()

        assert isinstance(handler, SQLiteHandler)

    def test_no_configuration(self, mock_env):
        """Test handler returns None with no configuration."""
        mock_env()

        with patch('os.path.exists', return_value=False):
            with patch('database.logger'):
                handler = get_database_handler()

        assert handler is None

    def test_unsupported_database_url(self, mock_env):
        """Test handler returns None for unsupported URL."""
        mock_env(SHIORI_DATABASE_URL='mongodb://localhost/db')

        with patch('database.logger'):
            handler = get_database_handler()

        assert handler is None
