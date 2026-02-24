"""Tests for archive creation and extraction functions."""

import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from archive import (
    create_archive, extract_archive, list_archive_contents,
    collect_shiori_data
)


class TestCreateArchive:
    """Tests for create_archive function."""

    def test_create_archive_single_file(self, temp_dir, temp_file):
        """Test creating archive with single file."""
        source = temp_file(content=b'test content')
        archive_path = os.path.join(temp_dir, 'test.tar.gz')

        result = create_archive([source], archive_path, compression='gz')

        assert result is True
        assert os.path.exists(archive_path)

        # Verify archive contents
        with tarfile.open(archive_path, 'r:gz') as tar:
            names = tar.getnames()
            assert len(names) == 1
            assert os.path.basename(source) in names[0]

    def test_create_archive_multiple_files(self, temp_dir, temp_file):
        """Test creating archive with multiple files."""
        sources = [
            temp_file(content=b'content 1', suffix='.txt'),
            temp_file(content=b'content 2', suffix='.txt'),
            temp_file(content=b'content 3', suffix='.txt')
        ]
        archive_path = os.path.join(temp_dir, 'test.tar.gz')

        result = create_archive(sources, archive_path)

        assert result is True
        with tarfile.open(archive_path, 'r:gz') as tar:
            assert len(tar.getnames()) == 3

    def test_create_archive_directory(self, temp_dir):
        """Test creating archive from directory."""
        source_dir = os.path.join(temp_dir, 'source')
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'file.txt'), 'w') as f:
            f.write('test')

        archive_path = os.path.join(temp_dir, 'test.tar.gz')

        result = create_archive([source_dir], archive_path)

        assert result is True

    def test_create_archive_missing_source(self, temp_dir, temp_file, caplog):
        """Test creating archive with missing source file."""
        existing_file = temp_file(content=b'exists')
        missing_file = '/nonexistent/path.txt'

        archive_path = os.path.join(temp_dir, 'test.tar.gz')

        with patch('archive.logger') as mock_logger:
            result = create_archive([existing_file, missing_file], archive_path)

        assert result is True  # Should still succeed with partial archive
        assert os.path.exists(archive_path)

    def test_create_archive_different_compression(self, temp_dir, temp_file):
        """Test creating archive with different compression types."""
        source = temp_file(content=b'test content')

        for compression in ['gz', 'bz2', 'xz', '']:
            archive_path = os.path.join(temp_dir, f'test.{compression or "tar"}')

            result = create_archive([source], archive_path, compression=compression)

            assert result is True, f"Failed for compression: {compression}"
            assert os.path.exists(archive_path)

    def test_create_archive_failure(self, temp_dir):
        """Test archive creation failure."""
        source = '/nonexistent/directory'
        archive_path = os.path.join(temp_dir, 'test.tar.gz')

        with patch('tarfile.open', side_effect=PermissionError('Access denied')):
            result = create_archive([source], archive_path)

        assert result is False


class TestExtractArchive:
    """Tests for extract_archive function."""

    def test_extract_archive_all_files(self, temp_dir, temp_file):
        """Test extracting all files from archive."""
        # Create archive first
        source = temp_file(content=b'test content')
        archive_path = os.path.join(temp_dir, 'test.tar.gz')
        create_archive([source], archive_path)

        # Extract
        extract_dir = os.path.join(temp_dir, 'extracted')
        result = extract_archive(archive_path, extract_dir)

        assert result is True
        assert os.path.exists(extract_dir)

        extracted_files = os.listdir(extract_dir)
        assert len(extracted_files) >= 1

    def test_extract_archive_specific_files(self, temp_dir, temp_file):
        """Test extracting specific files from archive."""
        # Create archive
        sources = [
            temp_file(content=b'content 1', suffix='1.txt'),
            temp_file(content=b'content 2', suffix='2.txt')
        ]
        archive_path = os.path.join(temp_dir, 'test.tar.gz')
        create_archive(sources, archive_path)

        # Extract specific file
        extract_dir = os.path.join(temp_dir, 'extracted')
        with tarfile.open(archive_path, 'r:gz') as tar:
            specific_file = tar.getnames()[0]

        result = extract_archive(archive_path, extract_dir, [specific_file])

        assert result is True

    def test_extract_archive_missing_member(self, temp_dir, temp_file):
        """Test extracting non-existent member from archive."""
        source = temp_file(content=b'test')
        archive_path = os.path.join(temp_dir, 'test.tar.gz')
        create_archive([source], archive_path)

        extract_dir = os.path.join(temp_dir, 'extracted')

        with patch('archive.logger') as mock_logger:
            result = extract_archive(archive_path, extract_dir, ['nonexistent.txt'])

        assert result is True  # Should not fail, just warn

    def test_extract_archive_creates_directory(self, temp_dir, temp_file):
        """Test that extraction creates output directory."""
        source = temp_file(content=b'test')
        archive_path = os.path.join(temp_dir, 'test.tar.gz')
        create_archive([source], archive_path)

        extract_dir = os.path.join(temp_dir, 'new', 'nested', 'dir')
        result = extract_archive(archive_path, extract_dir)

        assert result is True
        assert os.path.exists(extract_dir)

    def test_extract_archive_failure(self, temp_dir):
        """Test archive extraction failure."""
        archive_path = os.path.join(temp_dir, 'invalid.tar.gz')
        with open(archive_path, 'w') as f:
            f.write('not a valid tar file')

        extract_dir = os.path.join(temp_dir, 'extracted')
        result = extract_archive(archive_path, extract_dir)

        assert result is False


class TestListArchiveContents:
    """Tests for list_archive_contents function."""

    def test_list_contents(self, temp_dir, temp_file):
        """Test listing archive contents."""
        sources = [
            temp_file(content=b'content 1', suffix='1.txt'),
            temp_file(content=b'content 2', suffix='2.txt')
        ]
        archive_path = os.path.join(temp_dir, 'test.tar.gz')
        create_archive(sources, archive_path)

        contents = list_archive_contents(archive_path)

        assert len(contents) == 2

    def test_list_empty_archive(self, temp_dir):
        """Test listing empty archive."""
        archive_path = os.path.join(temp_dir, 'empty.tar.gz')
        with tarfile.open(archive_path, 'w:gz') as tar:
            pass

        contents = list_archive_contents(archive_path)

        assert contents == []

    def test_list_invalid_archive(self, temp_dir):
        """Test listing invalid archive."""
        archive_path = os.path.join(temp_dir, 'invalid.tar.gz')
        with open(archive_path, 'w') as f:
            f.write('not a tar file')

        contents = list_archive_contents(archive_path)

        assert contents == []


class TestCollectShioriData:
    """Tests for collect_shiori_data function."""

    def test_collect_shiori_data_all_dirs(self, sample_data_dir):
        """Test collecting data from all standard directories."""
        paths = collect_shiori_data(sample_data_dir)

        assert len(paths) == 3

        path_strs = [str(p) for p in paths]
        assert any('archive' in p for p in path_strs)
        assert any('thumb' in p for p in path_strs)
        assert any('ebook' in p for p in path_strs)

    def test_collect_shiori_data_missing_dirs(self, temp_dir):
        """Test collecting data with missing directories."""
        # Create only one directory
        os.makedirs(os.path.join(temp_dir, 'archive'))

        paths = collect_shiori_data(temp_dir)

        assert len(paths) == 1
        assert 'archive' in paths[0]

    def test_collect_shiori_data_nonexistent_dir(self, temp_dir):
        """Test collecting data from non-existent directory."""
        nonexistent = os.path.join(temp_dir, 'does_not_exist')

        with patch('archive.logger') as mock_logger:
            paths = collect_shiori_data(nonexistent)

        assert paths == []

    def test_collect_shiori_data_logs_sqlite_found(self, sample_data_dir):
        """Test that SQLite database detection is logged."""
        with patch('archive.logger') as mock_logger:
            collect_shiori_data(sample_data_dir)

            # Should log that SQLite was found but will be backed up separately
            debug_calls = [call for call in mock_logger.debug.call_args_list
                          if 'SQLite' in str(call)]
            assert len(debug_calls) > 0
