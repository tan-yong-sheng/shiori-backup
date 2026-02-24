"""GPG encryption and decryption functions."""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger('shiori-backup')


def encrypt_file(
    input_path: str,
    output_path: Optional[str] = None,
    passphrase: Optional[str] = None
) -> bool:
    """
    Encrypt a file using GPG symmetric encryption (AES256).

    Args:
        input_path: Path to the file to encrypt
        output_path: Path for the encrypted output (default: input_path + '.gpg')
        passphrase: Encryption passphrase (default: from BACKUP_ENCRYPTION_KEY env var)

    Returns:
        True if successful, False otherwise
    """
    if passphrase is None:
        passphrase = os.getenv('BACKUP_ENCRYPTION_KEY')

    if not passphrase:
        logger.error("No encryption passphrase provided")
        return False

    if output_path is None:
        output_path = input_path + '.gpg'

    try:
        cmd = [
            'gpg',
            '--symmetric',
            '--cipher-algo', 'AES256',
            '--compress-algo', '1',  # ZIP compression
            '--batch',
            '--yes',
            '--passphrase-fd', '0',
            '--output', output_path,
            input_path
        ]

        # Pass passphrase via stdin for security
        result = subprocess.run(
            cmd,
            input=passphrase.encode(),
            capture_output=True
        )

        if result.returncode == 0:
            logger.info(f"Encrypted: {input_path} -> {output_path}")
            return True
        else:
            logger.error(f"GPG encryption failed: {result.stderr.decode()}")
            return False

    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return False


def decrypt_file(
    input_path: str,
    output_path: Optional[str] = None,
    passphrase: Optional[str] = None
) -> bool:
    """
    Decrypt a GPG encrypted file.

    Args:
        input_path: Path to the encrypted file
        output_path: Path for the decrypted output (default: input_path without .gpg)
        passphrase: Decryption passphrase (default: from BACKUP_ENCRYPTION_KEY env var)

    Returns:
        True if successful, False otherwise
    """
    if passphrase is None:
        passphrase = os.getenv('BACKUP_ENCRYPTION_KEY')

    if not passphrase:
        logger.error("No decryption passphrase provided")
        return False

    if output_path is None:
        if input_path.endswith('.gpg'):
            output_path = input_path[:-4]
        else:
            output_path = input_path + '.decrypted'

    try:
        cmd = [
            'gpg',
            '--decrypt',
            '--batch',
            '--yes',
            '--passphrase-fd', '0',
            '--output', output_path,
            input_path
        ]

        result = subprocess.run(
            cmd,
            input=passphrase.encode(),
            capture_output=True
        )

        if result.returncode == 0:
            logger.info(f"Decrypted: {input_path} -> {output_path}")
            return True
        else:
            logger.error(f"GPG decryption failed: {result.stderr.decode()}")
            return False

    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return False


def is_encrypted(file_path: str) -> bool:
    """
    Check if a file is GPG encrypted.

    Args:
        file_path: Path to check

    Returns:
        True if file has .gpg extension, False otherwise
    """
    return file_path.endswith('.gpg')
