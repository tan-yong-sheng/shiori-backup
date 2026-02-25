"""Tests for encryption and decryption functions."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from encryption import encrypt_file, decrypt_file, is_encrypted


class TestIsEncrypted:
    """Tests for is_encrypted function."""

    def test_is_encrypted_true(self):
        """Test that .gpg extension is detected as encrypted."""
        assert is_encrypted('/path/to/file.tar.gz.gpg') is True
        assert is_encrypted('backup.gpg') is True

    def test_is_encrypted_false(self):
        """Test that non-.gpg files are not encrypted."""
        assert is_encrypted('/path/to/file.tar.gz') is False
        assert is_encrypted('backup.zip') is False
        assert is_encrypted('plain.txt') is False

    def test_is_encrypted_edge_cases(self):
        """Test edge cases for encryption detection."""
        assert is_encrypted('') is False
        assert is_encrypted('.gpg') is True
        assert is_encrypted('file.gpg.backup') is False


class TestEncryptFile:
    """Tests for encrypt_file function."""

    def test_encrypt_file_success(self, temp_dir, temp_file, mock_subprocess_run):
        """Test successful file encryption."""
        input_path = temp_file(content=b'secret data')
        output_path = os.path.join(temp_dir, 'encrypted.gpg')
        passphrase = 'mysecretkey'

        result = encrypt_file(input_path, output_path, passphrase)

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert 'gpg' in call_args[0][0][0]

    def test_encrypt_file_uses_default_output(self, temp_dir, temp_file, mock_subprocess_run):
        """Test encryption with default output path."""
        input_path = temp_file(content=b'secret data')
        passphrase = 'mysecretkey'

        result = encrypt_file(input_path, passphrase=passphrase)

        assert result is True
        # Should use input_path + '.gpg' as default output

    def test_encrypt_file_uses_env_passphrase(self, temp_file, mock_env, mock_subprocess_run):
        """Test encryption using passphrase from environment."""
        mock_env(BACKUP_ENCRYPTION_KEY='env_secret_key')
        input_path = temp_file(content=b'secret data')

        result = encrypt_file(input_path)

        assert result is True
        # Passphrase should come from environment

    def test_encrypt_file_no_passphrase(self, temp_file, mock_env, mock_subprocess_run):
        """Test encryption fails without passphrase."""
        # Temporarily unset encryption key
        backup_key = os.environ.pop('BACKUP_ENCRYPTION_KEY', None)

        try:
            input_path = temp_file(content=b'secret data')

            result = encrypt_file(input_path)

            assert result is False
        finally:
            if backup_key is not None:
                os.environ['BACKUP_ENCRYPTION_KEY'] = backup_key

    def test_encrypt_file_gpg_failure(self, temp_file, mock_subprocess_run):
        """Test encryption handles GPG failure."""
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = b'gpg: encryption failed'

        input_path = temp_file(content=b'secret data')
        result = encrypt_file(input_path, passphrase='key')

        assert result is False

    def test_encrypt_file_exception(self, temp_file, mock_subprocess_run):
        """Test encryption handles exceptions."""
        mock_subprocess_run.side_effect = Exception('Command not found')

        input_path = temp_file(content=b'secret data')
        result = encrypt_file(input_path, passphrase='key')

        assert result is False

    def test_encrypt_file_passes_correct_algorithm(self, temp_file, mock_subprocess_run):
        """Test that correct cipher and compression algorithms are used."""
        input_path = temp_file(content=b'secret data')
        encrypt_file(input_path, passphrase='key')

        call_args = mock_subprocess_run.call_args[0][0]
        assert '--cipher-algo' in call_args
        assert 'AES256' in call_args
        assert '--compress-algo' in call_args


class TestDecryptFile:
    """Tests for decrypt_file function."""

    def test_decrypt_file_success(self, temp_dir, temp_file, mock_subprocess_run):
        """Test successful file decryption."""
        input_path = temp_file(content=b'encrypted data', suffix='.gpg')
        output_path = os.path.join(temp_dir, 'decrypted.txt')
        passphrase = 'mysecretkey'

        result = decrypt_file(input_path, output_path, passphrase)

        assert result is True
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert '--decrypt' in call_args[0][0]

    def test_decrypt_file_strips_gpg_extension(self, temp_file, mock_subprocess_run):
        """Test that default output strips .gpg extension."""
        input_path = temp_file(content=b'encrypted', suffix='.gpg')

        result = decrypt_file(input_path, passphrase='key')

        assert result is True

    def test_decrypt_file_non_gpg_input(self, temp_file, mock_subprocess_run):
        """Test decryption with non-.gpg input adds .decrypted suffix."""
        input_path = temp_file(content=b'encrypted')

        result = decrypt_file(input_path, passphrase='key')

        assert result is True

    def test_decrypt_file_uses_env_passphrase(self, temp_file, mock_env, mock_subprocess_run):
        """Test decryption using passphrase from environment."""
        mock_env(BACKUP_ENCRYPTION_KEY='env_secret_key')
        input_path = temp_file(content=b'encrypted', suffix='.gpg')

        result = decrypt_file(input_path)

        assert result is True

    def test_decrypt_file_no_passphrase(self, temp_file, mock_env, mock_subprocess_run):
        """Test decryption fails without passphrase."""
        # Temporarily unset encryption key
        backup_key = os.environ.pop('BACKUP_ENCRYPTION_KEY', None)

        try:
            input_path = temp_file(content=b'encrypted', suffix='.gpg')

            result = decrypt_file(input_path)

            assert result is False
        finally:
            if backup_key is not None:
                os.environ['BACKUP_ENCRYPTION_KEY'] = backup_key

    def test_decrypt_file_gpg_failure(self, temp_file, mock_subprocess_run):
        """Test decryption handles GPG failure."""
        mock_subprocess_run.return_value.returncode = 2
        mock_subprocess_run.return_value.stderr = b'gpg: decryption failed'

        input_path = temp_file(content=b'encrypted', suffix='.gpg')
        result = decrypt_file(input_path, passphrase='key')

        assert result is False

    def test_decrypt_file_exception(self, temp_file, mock_subprocess_run):
        """Test decryption handles exceptions."""
        mock_subprocess_run.side_effect = Exception('GPG not installed')

        input_path = temp_file(content=b'encrypted', suffix='.gpg')
        result = decrypt_file(input_path, passphrase='key')

        assert result is False


class TestEncryptDecryptIntegration:
    """Integration-style tests for encryption/decryption workflow."""

    def test_encrypt_decrypt_roundtrip(self, temp_dir, temp_file, mock_subprocess_run):
        """Test encrypt and decrypt work together."""
        original_content = b'super secret data'
        input_path = temp_file(content=original_content)
        encrypted_path = os.path.join(temp_dir, 'encrypted.gpg')
        decrypted_path = os.path.join(temp_dir, 'decrypted.txt')
        passphrase = 'strong_passphrase_123'

        # Mock successful encryption
        encrypt_file(input_path, encrypted_path, passphrase)

        # Reset mock for decryption
        mock_subprocess_run.reset_mock()

        # Mock successful decryption
        decrypt_file(encrypted_path, decrypted_path, passphrase)

        # Both operations should succeed
        assert mock_subprocess_run.call_count == 1

    def test_is_encrypted_after_encryption(self, temp_dir, temp_file, mock_subprocess_run):
        """Test that encrypted files are correctly identified."""
        input_path = temp_file(content=b'data')
        encrypted_path = os.path.join(temp_dir, 'file.gpg')

        assert is_encrypted(encrypted_path) is True
        assert is_encrypted(input_path) is False
