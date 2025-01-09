"""Tests for command-line interface."""

import pytest
from unittest.mock import patch, Mock
import argparse
import logging

from repomap.cli import parse_args, main

def test_parse_args():
    """Test command line argument parsing."""
    # Test with minimal arguments
    with patch('sys.argv', ['repomap', 'https://gitlab.com/user/repo']):
        args = parse_args()
        assert args.repo_url == 'https://gitlab.com/user/repo'
        assert args.token is None
        assert args.output == 'repomap.json'
        assert not args.verbose
    
    # Test with all arguments
    with patch('sys.argv', [
        'repomap',
        'https://gitlab.com/user/repo',
        '-t', 'test-token',
        '-o', 'output.json',
        '-v'
    ]):
        args = parse_args()
        assert args.repo_url == 'https://gitlab.com/user/repo'
        assert args.token == 'test-token'
        assert args.output == 'output.json'
        assert args.verbose

def test_parse_args_missing_required():
    """Test handling of missing required arguments."""
    with patch('sys.argv', ['repomap']):
        with pytest.raises(SystemExit):
            parse_args()

@patch('repomap.cli.fetch_repo_structure')
@patch('repomap.cli.store_repo_map')
def test_main_success(mock_store_map, mock_fetch_repo):
    """Test successful execution of main function."""
    # Setup mocks
    mock_fetch_repo.return_value = {
        'src': {
            'main.py': {'type': 'blob', 'path': 'src/main.py'}
        }
    }
    mock_store_map.return_value = 'output.json'
    
    # Test with minimal arguments
    with patch('sys.argv', ['repomap', 'https://gitlab.com/user/repo']):
        exit_code = main()
        
        assert exit_code == 0
        mock_fetch_repo.assert_called_once_with(
            'https://gitlab.com/user/repo',
            None
        )
        mock_store_map.assert_called_once()
        
        # Verify stored map structure
        stored_map = mock_store_map.call_args[0][0]
        assert 'metadata' in stored_map
        assert 'structure' in stored_map
        assert 'ast_data' in stored_map

@patch('repomap.cli.fetch_repo_structure')
def test_main_network_error(mock_fetch_repo):
    """Test handling of network errors."""
    mock_fetch_repo.side_effect = Exception("Network error")
    
    with patch('sys.argv', ['repomap', 'https://gitlab.com/user/repo']):
        exit_code = main()
        assert exit_code == 1

def test_main_keyboard_interrupt():
    """Test handling of keyboard interrupt."""
    with patch('sys.argv', ['repomap', 'https://gitlab.com/user/repo']):
        with patch('repomap.cli.fetch_repo_structure', side_effect=KeyboardInterrupt):
            exit_code = main()
            assert exit_code == 130

@patch('repomap.cli.fetch_repo_structure')
@patch('repomap.cli.store_repo_map')
def test_main_verbose_logging(mock_store_map, mock_fetch_repo, caplog):
    """Test verbose logging output."""
    mock_fetch_repo.return_value = {'test': 'data'}
    mock_store_map.return_value = 'output.json'
    
    with patch('sys.argv', ['repomap', 'https://gitlab.com/user/repo', '-v']):
        with caplog.at_level(logging.DEBUG):
            main()
            
            # Verify debug logs were captured
            assert any(record.levelno == logging.DEBUG for record in caplog.records)

@patch('repomap.cli.fetch_repo_structure')
@patch('repomap.cli.store_repo_map')
def test_main_custom_output(mock_store_map, mock_fetch_repo):
    """Test using custom output path."""
    mock_fetch_repo.return_value = {'test': 'data'}
    mock_store_map.return_value = 'custom/path/map.json'
    
    with patch('sys.argv', [
        'repomap',
        'https://gitlab.com/user/repo',
        '-o', 'custom/path/map.json'
    ]):
        exit_code = main()
        
        assert exit_code == 0
        mock_store_map.assert_called_once()
        assert mock_store_map.call_args[0][1] == 'custom/path/map.json'

@patch('repomap.cli.fetch_repo_structure')
@patch('repomap.cli.store_repo_map')
def test_main_with_token(mock_store_map, mock_fetch_repo):
    """Test using GitLab token."""
    mock_fetch_repo.return_value = {'test': 'data'}
    
    with patch('sys.argv', [
        'repomap',
        'https://gitlab.com/user/repo',
        '-t', 'test-token'
    ]):
        exit_code = main()
        
        assert exit_code == 0
        mock_fetch_repo.assert_called_once_with(
            'https://gitlab.com/user/repo',
            'test-token'
        )

def test_version_argument():
    """Test --version argument."""
    with patch('sys.argv', ['repomap', '--version']):
        with pytest.raises(SystemExit) as exc_info:
            parse_args()
        assert exc_info.value.code == 0
