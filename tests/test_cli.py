"""Tests for command-line interface."""

import pytest
from unittest.mock import patch, MagicMock

from repomap.cli import parse_args, main


def test_parse_args_defaults():
    """Test argument parsing with default values."""
    args = parse_args(["https://example.com/repo"])
    assert args.repo_url == "https://example.com/repo"
    assert args.token is None
    assert args.output == "repomap.json"
    assert not args.verbose


def test_parse_args_custom():
    """Test argument parsing with custom values."""
    args = parse_args(
        [
            "https://example.com/repo",
            "--token",
            "abc123",
            "--output",
            "custom.json",
            "--verbose",
        ]
    )
    assert args.repo_url == "https://example.com/repo"
    assert args.token == "abc123"
    assert args.output == "custom.json"
    assert args.verbose


def test_parse_args_missing_url():
    """Test argument parsing with missing repository URL."""
    with pytest.raises(SystemExit):
        parse_args([])


def test_parse_args_call_stack():
    """Test argument parsing for call stack feature."""
    args = parse_args(
        [
            "--call-stack",
            "--target-file",
            "test.py",
            "--line",
            "10",
            "--structure-file",
            "structure.json",
            "--output-stack",
            "stack.json",
        ]
    )
    assert args.call_stack
    assert args.target_file == "test.py"
    assert args.line == 10
    assert args.structure_file == "structure.json"
    assert args.output_stack == "stack.json"


def test_parse_args_call_stack_missing_args():
    """Test argument parsing with missing call stack arguments."""
    with pytest.raises(SystemExit):
        parse_args(["--call-stack"])


def test_parse_args_print_function():
    """Test argument parsing for print-function feature."""
    args = parse_args(["--print-function", "--target-file", "test.py", "--line", "10"])
    assert args.print_function
    assert args.target_file == "test.py"
    assert args.line == 10


def test_parse_args_print_function_missing_args():
    """Test argument parsing with missing print-function arguments."""
    with pytest.raises(SystemExit):
        parse_args(["--print-function"])
    with pytest.raises(SystemExit):
        parse_args(["--print-function", "--target-file", "test.py"])
    with pytest.raises(SystemExit):
        parse_args(["--print-function", "--line", "10"])


@patch('repomap.cli.CallStackGenerator')
def test_main_print_function(mock_generator):
    """Test main function with print-function feature."""
    # Setup mock generator
    mock_instance = MagicMock()
    mock_instance.get_function_content.return_value = "def test():\n    pass\n"
    mock_generator.return_value = mock_instance

    # Test successful function printing
    with patch(
        'sys.argv',
        ['repomap', '--print-function', '--target-file', 'test.py', '--line', '1'],
    ):
        assert main() == 0
        mock_instance.get_function_content.assert_called_once_with('test.py', 1)

    # Test function not found
    mock_instance.get_function_content.side_effect = ValueError("No function found")
    with patch(
        'sys.argv',
        ['repomap', '--print-function', '--target-file', 'test.py', '--line', '1'],
    ):
        assert main() == 1


@patch('repomap.cli.fetch_repo_structure')
def test_main_repo_map(mock_fetch):
    """Test main function with repository mapping."""
    mock_fetch.return_value = {"src": {"main.py": {"type": "blob"}}}

    with patch('sys.argv', ['repomap', 'https://example.com/repo']):
        assert main() == 0
        mock_fetch.assert_called_once_with('https://example.com/repo', None)


@patch('repomap.cli.CallStackGenerator')
def test_main_call_stack(mock_generator):
    """Test main function with call stack generation."""
    mock_instance = MagicMock()
    mock_generator.return_value = mock_instance

    with patch(
        'sys.argv',
        [
            'repomap',
            '--call-stack',
            '--target-file',
            'test.py',
            '--line',
            '1',
            '--structure-file',
            'structure.json',
            '--output-stack',
            'stack.json',
        ],
    ):
        assert main() == 0
        mock_instance.generate_call_stack.assert_called_once_with('test.py', 1)
        mock_instance.save_call_stack.assert_called_once()
