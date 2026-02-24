"""Database backup handlers for SQLite and PostgreSQL."""

import os
import subprocess
import sqlite3
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from utils import parse_database_url

logger = logging.getLogger('shiori-backup')


class DatabaseHandler(ABC):
    """Abstract base class for database handlers."""

    @abstractmethod
    def backup(self, output_path: str) -> bool:
        """Create a database backup to the specified path."""
        pass

    @abstractmethod
    def restore(self, backup_path: str) -> bool:
        """Restore database from the specified backup path."""
        pass

    @abstractmethod
    def get_info(self) -> dict:
        """Get database information for metadata."""
        pass


class SQLiteHandler(DatabaseHandler):
    """Handler for SQLite database backups using hot backup."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / 'shiori.db'

    def backup(self, output_path: str) -> bool:
        """Create a hot backup of SQLite database."""
        if not self.db_path.exists():
            logger.warning(f"SQLite database not found at {self.db_path}")
            return False

        try:
            # Use SQLite's .backup command for hot backup
            conn = sqlite3.connect(str(self.db_path))
            backup_conn = sqlite3.connect(output_path)

            with backup_conn:
                conn.backup(backup_conn)

            backup_conn.close()
            conn.close()

            logger.info(f"SQLite database backed up to {output_path}")
            return True

        except Exception as e:
            logger.error(f"SQLite backup failed: {e}")
            return False

    def restore(self, backup_path: str) -> bool:
        """Restore SQLite database from backup."""
        try:
            # Simply copy the backup file to the database location
            import shutil
            shutil.copy2(backup_path, self.db_path)
            logger.info(f"SQLite database restored from {backup_path}")
            return True

        except Exception as e:
            logger.error(f"SQLite restore failed: {e}")
            return False

    def get_info(self) -> dict:
        """Get SQLite database information."""
        info = {'type': 'sqlite'}

        if self.db_path.exists():
            info['page_count'] = 0
            info['page_size'] = 0
            info['journal_mode'] = 'unknown'

            try:
                conn = sqlite3.connect(str(self.db_path))
                cursor = conn.cursor()

                cursor.execute("PRAGMA page_count")
                info['page_count'] = cursor.fetchone()[0]

                cursor.execute("PRAGMA page_size")
                info['page_size'] = cursor.fetchone()[0]

                cursor.execute("PRAGMA journal_mode")
                info['journal_mode'] = cursor.fetchone()[0]

                conn.close()
            except Exception as e:
                logger.warning(f"Could not get SQLite info: {e}")

        return info


class PostgreSQLHandler(DatabaseHandler):
    """Handler for PostgreSQL database backups using pg_dump."""

    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.parsed = parse_database_url(connection_url)

    def backup(self, output_path: str) -> bool:
        """Create a PostgreSQL backup using pg_dump."""
        try:
            # Build pg_dump command
            env = os.environ.copy()
            env['PGPASSWORD'] = self.parsed.get('password', '')

            cmd = [
                'pg_dump',
                '--host', self.parsed.get('host', 'localhost'),
                '--port', str(self.parsed.get('port', 5432)),
                '--username', self.parsed.get('user', 'postgres'),
                '--dbname', self.parsed.get('database', 'shiori'),
                '--format', 'custom',  # Custom format for pg_restore
                '--verbose',
                '--file', output_path
            ]

            # Add SSL mode if specified
            ssl_mode = self.parsed.get('options', {}).get('sslmode')
            if ssl_mode:
                cmd.extend(['--sslmode', ssl_mode])

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"PostgreSQL database backed up to {output_path}")
                return True
            else:
                logger.error(f"pg_dump failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"PostgreSQL backup failed: {e}")
            return False

    def restore(self, backup_path: str) -> bool:
        """Restore PostgreSQL database from backup using pg_restore."""
        try:
            env = os.environ.copy()
            env['PGPASSWORD'] = self.parsed.get('password', '')

            cmd = [
                'pg_restore',
                '--host', self.parsed.get('host', 'localhost'),
                '--port', str(self.parsed.get('port', 5432)),
                '--username', self.parsed.get('user', 'postgres'),
                '--dbname', self.parsed.get('database', 'shiori'),
                '--verbose',
                '--clean',  # Clean (drop) database objects before recreating
                '--if-exists',
                backup_path
            ]

            ssl_mode = self.parsed.get('options', {}).get('sslmode')
            if ssl_mode:
                cmd.extend(['--sslmode', ssl_mode])

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True
            )

            # pg_restore returns 1 if some warnings occurred but restore succeeded
            if result.returncode in [0, 1]:
                logger.info(f"PostgreSQL database restored from {backup_path}")
                return True
            else:
                logger.error(f"pg_restore failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"PostgreSQL restore failed: {e}")
            return False

    def get_info(self) -> dict:
        """Get PostgreSQL database information."""
        return {
            'type': 'postgresql',
            'host': self.parsed.get('host'),
            'port': self.parsed.get('port'),
            'database': self.parsed.get('database')
        }


class MySQLHandler(DatabaseHandler):
    """Handler for MySQL/MariaDB database backups using mysqldump."""

    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.parsed = parse_database_url(connection_url)

    def backup(self, output_path: str) -> bool:
        """Create a MySQL backup using mysqldump."""
        try:
            cmd = [
                'mysqldump',
                '--host', self.parsed.get('host', 'localhost'),
                '--port', str(self.parsed.get('port', 3306)),
                '--user', self.parsed.get('user', 'root'),
                '--password=' + self.parsed.get('password', ''),
                '--single-transaction',  # For consistent backup without locking
                '--routines',
                '--triggers',
                self.parsed.get('database', 'shiori')
            ]

            with open(output_path, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )

            if result.returncode == 0:
                logger.info(f"MySQL database backed up to {output_path}")
                return True
            else:
                logger.error(f"mysqldump failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MySQL backup failed: {e}")
            return False

    def restore(self, backup_path: str) -> bool:
        """Restore MySQL database from backup."""
        try:
            cmd = [
                'mysql',
                '--host', self.parsed.get('host', 'localhost'),
                '--port', str(self.parsed.get('port', 3306)),
                '--user', self.parsed.get('user', 'root'),
                '--password=' + self.parsed.get('password', ''),
                self.parsed.get('database', 'shiori')
            ]

            with open(backup_path, 'r') as f:
                result = subprocess.run(
                    cmd,
                    stdin=f,
                    capture_output=True,
                    text=True
                )

            if result.returncode == 0:
                logger.info(f"MySQL database restored from {backup_path}")
                return True
            else:
                logger.error(f"MySQL restore failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MySQL restore failed: {e}")
            return False

    def get_info(self) -> dict:
        """Get MySQL database information."""
        return {
            'type': 'mysql',
            'host': self.parsed.get('host'),
            'port': self.parsed.get('port'),
            'database': self.parsed.get('database')
        }


def get_database_handler() -> Optional[DatabaseHandler]:
    """Factory function to get appropriate database handler based on config."""
    database_url = os.getenv('SHIORI_DATABASE_URL')
    data_dir = os.getenv('SHIORI_DATA_DIR')

    if database_url:
        if database_url.startswith('postgres://') or database_url.startswith('postgresql://'):
            logger.info("Using PostgreSQL handler")
            return PostgreSQLHandler(database_url)
        elif database_url.startswith('mysql://'):
            logger.info("Using MySQL handler")
            return MySQLHandler(database_url)
        else:
            logger.error(f"Unsupported database URL: {database_url}")
            return None

    elif data_dir:
        logger.info(f"Using SQLite handler with data dir: {data_dir}")
        return SQLiteHandler(data_dir)

    else:
        # Default to SQLite in standard location
        default_dir = '/srv/shiori'
        if os.path.exists(default_dir):
            logger.info(f"Using default SQLite handler with data dir: {default_dir}")
            return SQLiteHandler(default_dir)
        else:
            logger.error("No database configuration found. Set SHIORI_DATABASE_URL or SHIORI_DATA_DIR")
            return None
