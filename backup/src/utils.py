"""Utility functions for shiori-backup."""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


def setup_logging(log_level: Optional[str] = None) -> logging.Logger:
    """Configure logging with proper formatting."""
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout
    )
    return logging.getLogger('shiori-backup')


def load_config():
    """Load environment variables from .env file if present."""
    # Try loading from /app/.env first (container path)
    env_path = Path('/app/.env')
    if env_path.exists():
        load_dotenv(env_path)
    # Also try to load from current directory
    load_dotenv(Path('.env'))


def get_env(key: str, default=None, required: bool = False):
    """Get environment variable with optional default and required check."""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def detect_database_type() -> str:
    """Auto-detect database type from environment variables."""
    database_url = os.getenv('SHIORI_DATABASE_URL')
    data_dir = os.getenv('SHIORI_DATA_DIR', '/srv/shiori')

    if database_url:
        if database_url.startswith(('postgres://', 'postgresql://')):
            return 'postgres'
        elif database_url.startswith('mysql://'):
            return 'mysql'

    # Check for SQLite database file
    if os.path.exists(os.path.join(data_dir, 'shiori.db')):
        return 'sqlite'

    # Default to sqlite if we can't determine
    return 'sqlite'


def generate_backup_filename(db_type: str = None) -> str:
    """Generate a timestamped backup filename with database type."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    if db_type is None:
        db_type = detect_database_type()
    return f"shiori-backup-{timestamp}-{db_type}"


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def parse_database_url(url: str) -> dict:
    """Parse database connection URL into components."""
    # postgres://user:pass@host:port/db?options
    # mysql://user:pass@host:port/db?options
    result = {
        'type': None,
        'host': None,
        'port': None,
        'database': None,
        'user': None,
        'password': None,
        'options': {}
    }

    if not url:
        return result

    if url.startswith('postgres://') or url.startswith('postgresql://'):
        result['type'] = 'postgresql'
    elif url.startswith('mysql://'):
        result['type'] = 'mysql'
    else:
        return result

    # Remove protocol
    rest = url.split('://', 1)[1]

    # Parse credentials
    if '@' in rest:
        creds, rest = rest.rsplit('@', 1)
        if ':' in creds:
            result['user'], result['password'] = creds.split(':', 1)
        else:
            result['user'] = creds

    # Parse options
    if '?' in rest:
        rest, opts = rest.split('?', 1)
        for opt in opts.split('&'):
            if '=' in opt:
                k, v = opt.split('=', 1)
                result['options'][k] = v

    # Parse host:port/db
    if '/' in rest:
        host_port, result['database'] = rest.split('/', 1)
    else:
        host_port = rest

    # MySQL URL may use tcp(host[:port]) form
    if result['type'] == 'mysql' and host_port.startswith('tcp(') and host_port.endswith(')'):
        host_port = host_port[4:-1]

    if ':' in host_port:
        result['host'], port_str = host_port.rsplit(':', 1)
        try:
            result['port'] = int(port_str)
        except ValueError:
            result['port'] = None
    else:
        result['host'] = host_port

    if result['type'] == 'mysql' and result['port'] is None:
        result['port'] = 3306
    elif result['type'] == 'postgresql' and result['port'] is None:
        result['port'] = 5432

    return result


class BackupMetadata:
    """Class to handle backup metadata."""

    def __init__(self, backup_id: str, source: str):
        self.backup_id = backup_id
        self.source = source
        self.timestamp = datetime.utcnow().isoformat()
        self.files = {}
        self.database_info = {}
        self.hostname = os.getenv('HOSTNAME', 'unknown')

    def add_file(self, file_path: str, relative_path: str):
        """Add a file to metadata with checksum."""
        if os.path.exists(file_path):
            self.files[relative_path] = {
                'checksum': calculate_sha256(file_path),
                'size': os.path.getsize(file_path)
            }

    def set_database_info(self, **kwargs):
        """Set database backup information."""
        self.database_info = kwargs

    def to_dict(self) -> dict:
        """Convert metadata to dictionary."""
        return {
            'backup_id': self.backup_id,
            'timestamp': self.timestamp,
            'source': self.source,
            'hostname': self.hostname,
            'database': self.database_info,
            'files': self.files
        }

    def save(self, output_path: str):
        """Save metadata to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, metadata_path: str):
        """Load metadata from JSON file."""
        with open(metadata_path, 'r') as f:
            data = json.load(f)

        instance = cls(data['backup_id'], data['source'])
        instance.timestamp = data['timestamp']
        instance.hostname = data['hostname']
        instance.database_info = data.get('database', {})
        instance.files = data.get('files', {})
        return instance
