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
    assert not args.no_local_clone  # Default is to use local clone


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


def test_parse_args_no_local_clone():
    """Test argument parsing with --no-local-clone flag."""
    args = parse_args(
        [
            "https://example.com/repo",
            "--repo-tree",
            "--no-local-clone",
        ]
    )
    assert args.repo_url == "https://example.com/repo"
    assert args.repo_tree
    assert args.no_local_clone


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
        ]
    )
    assert args.call_stack
    assert args.target_file == "test.py"
    assert args.line == 10


def test_parse_args_repo_tree():
    """Test argument parsing for repository tree feature."""
    args = parse_args(
        [
            "https://example.com/repo",
            "--repo-tree",
            "--ref",
            "develop",
        ]
    )
    assert args.repo_url == "https://example.com/repo"
    assert args.repo_tree
    assert args.ref == "develop"


def test_parse_args_print_function():
    """Test argument parsing for print function feature."""
    args = parse_args(
        [
            "--print-function",
            "--target-file",
            "test.py",
            "--line",
            "10",
        ]
    )
    assert args.print_function
    assert args.target_file == "test.py"
    assert args.line == 10


def test_parse_args_print_function_by_name():
    """Test argument parsing for print function by name feature."""
    args = parse_args(
        [
            "--print-function-by-name",
            "--name",
            "test_function",
            "--repo-tree-path",
            "tree.json",
        ]
    )
    assert args.print_function_by_name
    assert args.name == "test_function"
    assert args.repo_tree_path == "tree.json"


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_with_local_clone(mock_generator):
    """Test main function with repo-tree generation using local clone."""
    mock_instance = MagicMock()
    mock_instance.generate_repo_tree.return_value = {"files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree']):
        result = main()

    assert result == 0
    mock_generator.assert_called_with(None, use_local_clone=True)
    mock_instance.generate_repo_tree.assert_called_once()
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_without_local_clone(mock_generator):
    """Test main function with repo-tree generation without local clone."""
    mock_instance = MagicMock()
    mock_instance.generate_repo_tree.return_value = {"files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '--no-local-clone']):
        result = main()

    assert result == 0
    mock_generator.assert_called_with(None, use_local_clone=False)
    mock_instance.generate_repo_tree.assert_called_once()
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_with_branch_ref(mock_generator):
    """Test main function with repo-tree generation using specific branch ref."""
    mock_instance = MagicMock()
    mock_instance.generate_repo_tree.return_value = {"files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '--ref', 'develop']):
        result = main()

    assert result == 0
    mock_generator.assert_called_with(None, use_local_clone=True)
    # Verify that generate_repo_tree was called with the correct ref
    args, kwargs = mock_instance.generate_repo_tree.call_args
    assert args[1] == 'develop'  # ref is the second positional argument
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_with_tag_ref(mock_generator):
    """Test main function with repo-tree generation using specific tag ref."""
    mock_instance = MagicMock()
    mock_instance.generate_repo_tree.return_value = {"files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '--ref', 'v2.1.0']):
        result = main()

    assert result == 0
    mock_generator.assert_called_with(None, use_local_clone=True)
    # Verify that generate_repo_tree was called with the correct ref
    args, kwargs = mock_instance.generate_repo_tree.call_args
    assert args[1] == 'v2.1.0'  # ref is the second positional argument
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_with_ref_no_local_clone(mock_generator):
    """Test main function with repo-tree generation using ref and no local clone."""
    mock_instance = MagicMock()
    mock_instance.generate_repo_tree.return_value = {"files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '--ref', 'feature-branch', '--no-local-clone']):
        result = main()

    assert result == 0
    mock_generator.assert_called_with(None, use_local_clone=False)
    # Verify that generate_repo_tree was called with the correct ref
    args, kwargs = mock_instance.generate_repo_tree.call_args
    assert args[1] == 'feature-branch'  # ref is the second positional argument
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.CallStackGenerator')
def test_main_call_stack(mock_generator):
    """Test main function with call stack generation."""
    mock_instance = MagicMock()
    mock_instance.generate_call_stack.return_value = {"call_stack": []}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', '--call-stack', '--target-file', 'test.py', '--line', '10']):
        result = main()

    assert result == 0
    mock_generator.assert_called_once()
    mock_instance.generate_call_stack.assert_called_once()


@patch('repomap.cli.CallStackGenerator')
def test_main_print_function(mock_generator):
    """Test main function with print function."""
    mock_instance = MagicMock()
    mock_instance.get_function_content_by_line.return_value = "def test(): pass"
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', '--print-function', '--target-file', 'test.py', '--line', '10']):
        result = main()

    assert result == 0
    mock_generator.assert_called_once()
    mock_instance.get_function_content_by_line.assert_called_once()


@patch('repomap.cli.CallStackGenerator')
def test_main_print_function_by_name(mock_generator):
    """Test main function with print function by name."""
    mock_instance = MagicMock()
    mock_instance.get_function_content_by_name.return_value = {"global": "def test(): pass"}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', '--print-function-by-name', '--name', 'test', '--repo-tree-path', 'tree.json']):
        result = main()

    assert result == 0
    mock_generator.assert_called_once()
    mock_instance.get_function_content_by_name.assert_called_once()


def test_main_keyboard_interrupt():
    """Test main function handling keyboard interrupt."""
    with patch('repomap.cli.parse_args') as mock_parse:
        mock_parse.side_effect = KeyboardInterrupt()
        result = main()
        assert result == 130


@patch('repomap.cli.parse_args')
def test_main_exception(mock_parse):
    """Test main function handling general exception."""
    mock_parse.side_effect = Exception("Test error")
    result = main()
    assert result == 1


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_up_to_date(mock_generator):
    """Test main function skips generation when repo-tree is up to date."""
    mock_instance = MagicMock()
    mock_instance.is_repo_tree_up_to_date.return_value = True
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '-o', 'output.json']):
        result = main()

    assert result == 0
    mock_instance.is_repo_tree_up_to_date.assert_called_once_with(
        'https://example.com/repo', None, 'output.json'
    )
    # Should not call generate_repo_tree when up to date
    mock_instance.generate_repo_tree.assert_not_called()
    mock_instance.save_repo_tree.assert_not_called()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_outdated(mock_generator):
    """Test main function generates new tree when repo-tree is outdated."""
    mock_instance = MagicMock()
    mock_instance.is_repo_tree_up_to_date.return_value = False
    mock_instance.generate_repo_tree.return_value = {"metadata": {"last_commit_hash": "new123"}, "files": {}}
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '-o', 'output.json']):
        result = main()

    assert result == 0
    mock_instance.is_repo_tree_up_to_date.assert_called_once_with(
        'https://example.com/repo', None, 'output.json'
    )
    # Should call generate_repo_tree when outdated
    mock_instance.generate_repo_tree.assert_called_once()
    mock_instance.save_repo_tree.assert_called_once()


@patch('repomap.cli.RepoTreeGenerator')
def test_main_repo_tree_with_ref_up_to_date(mock_generator):
    """Test main function skips generation when repo-tree with ref is up to date."""
    mock_instance = MagicMock()
    mock_instance.is_repo_tree_up_to_date.return_value = True
    mock_generator.return_value = mock_instance

    with patch('sys.argv', ['repomap', 'https://example.com/repo', '--repo-tree', '--ref', 'develop', '-o', 'output.json']):
        result = main()

    assert result == 0
    mock_instance.is_repo_tree_up_to_date.assert_called_once_with(
        'https://example.com/repo', 'develop', 'output.json'
    )
    # Should not call generate_repo_tree when up to date
    mock_instance.generate_repo_tree.assert_not_called()
    mock_instance.save_repo_tree.assert_not_called()