"""Tests for command-line interface."""

from unittest.mock import MagicMock, patch

import pytest

from repomap.cli import main, parse_args


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
def test_main_print_function(mock_generator, capsys):
    """Test main function with print-function feature."""
    # Setup mock generator
    mock_instance = MagicMock()
    mock_instance.get_function_content_by_line.return_value = "def test():\n    pass\n"
    mock_generator.return_value = mock_instance

    # Test successful function printing
    with patch(
        'sys.argv',
        ['repomap', '--print-function', '--target-file', 'test.py', '--line', '1'],
    ):
        assert main() == 0
        mock_instance.get_function_content_by_line.assert_called_once_with('test.py', 1)

    # Test function not found
    mock_instance.get_function_content_by_line.side_effect = ValueError(
        "No function found"
    )
    with patch(
        'sys.argv',
        ['repomap', '--print-function', '--target-file', 'test.py', '--line', '1'],
    ):
        assert main() == 1


@patch('repomap.cli.fetch_repo_structure')
def test_main_repo_map(mock_fetch, tmp_path):
    """Test main function with repository mapping."""
    mock_fetch.return_value = {"src": {"main.py": {"type": "blob"}}}
    temp_output = tmp_path / "repomap.json"

    with patch(
        'sys.argv',
        ['repomap', 'https://example.com/repo', '--output', str(temp_output)],
    ):
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


@patch('repomap.cli.CallStackGenerator')
def test_main_print_function_by_name(mock_generator, capsys):
    """Test main function with print-function-by-name feature."""
    # Setup mock generator
    mock_instance = MagicMock()
    mock_instance.get_function_content_by_name.return_value = {
        "global": "def global_func():\n    pass\n",
        "ClassA": "def class_method(self):\n    pass\n",
        "ClassB": "def class_method(self):\n    return True\n",
    }
    mock_generator.return_value = mock_instance

    # Test successful function printing with multiple implementations
    with patch(
        'sys.argv',
        [
            'repomap',
            '--print-function-by-name',
            '--name',
            'class_method',
            '--repo-tree-path',
            'repo_tree.json',
        ],
    ):
        assert main() == 0
        mock_instance.get_function_content_by_name.assert_called_once_with(
            'repo_tree.json', 'class_method'
        )
        captured = capsys.readouterr()
        assert "In class ClassA:" in captured.out
        assert "In class ClassB:" in captured.out
        assert "def class_method(self):" in captured.out

    # Test function not found
    mock_instance.get_function_content_by_name.side_effect = ValueError(
        "No function found with name: nonexistent"
    )
    with patch(
        'sys.argv',
        [
            'repomap',
            '--print-function-by-name',
            '--name',
            'nonexistent',
            '--repo-tree-path',
            'repo_tree.json',
        ],
    ):
        assert main() == 1
        captured = capsys.readouterr()
        assert "No function found with name: nonexistent" in captured.err


def test_print_function_by_name_args():
    """Test parsing print function by name arguments."""
    args = parse_args(
        [
            "--print-function-by-name",
            "--name",
            "interpret_filename",
            "--repo-tree-path",
            "repo_tree.json",
        ]
    )
    assert args.print_function_by_name
    assert args.name == "interpret_filename"
    assert args.repo_tree_path == "repo_tree.json"


def test_print_function_by_name_missing_args():
    """Test error when required arguments are missing."""
    with pytest.raises(SystemExit):
        parse_args(["--print-function-by-name"])

    with pytest.raises(SystemExit):
        parse_args(["--print-function-by-name", "--name", "func"])

    with pytest.raises(SystemExit):
        parse_args(["--print-function-by-name", "--repo-tree-path", "tree.json"])


def test_print_function_mutually_exclusive():
    """Test that print function arguments are mutually exclusive."""
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--print-function",
                "--print-function-by-name",
                "--name",
                "func",
                "--repo-tree-path",
                "tree.json",
            ]
        )


def test_print_function_original_functionality():
    """Test that original print function functionality still works."""
    args = parse_args(["--print-function", "--target-file", "file.c", "--line", "42"])
    assert args.print_function
    assert args.target_file == "file.c"
    assert args.line == 42


def test_repo_url_not_required_with_print_function():
    """Test that repo_url is not required when using print function options."""
    # With print-function
    args = parse_args(["--print-function", "--target-file", "file.c", "--line", "42"])
    assert args.repo_url is None

    # With print-function-by-name
    args = parse_args(
        ["--print-function-by-name", "--name", "func", "--repo-tree-path", "tree.json"]
    )
    assert args.repo_url is None


def test_repo_url_required_without_special_args():
    """Test that repo_url is required when not using special arguments."""
    with pytest.raises(SystemExit):
        parse_args([])
