"""Tests for the command-line interface."""

import pytest
from repomap.cli import parse_args

def test_print_function_by_name_args():
    """Test parsing print function by name arguments."""
    args = parse_args([
        "--print-function-by-name",
        "--name", "interpret_filename",
        "--repo-tree-path", "repo_tree.json"
    ])
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
        parse_args([
            "--print-function",
            "--print-function-by-name",
            "--name", "func",
            "--repo-tree-path", "tree.json"
        ])

def test_print_function_original_functionality():
    """Test that original print function functionality still works."""
    args = parse_args([
        "--print-function",
        "--target-file", "file.c",
        "--line", "42"
    ])
    assert args.print_function
    assert args.target_file == "file.c"
    assert args.line == 42

def test_repo_url_not_required_with_print_function():
    """Test that repo_url is not required when using print function options."""
    # With print-function
    args = parse_args([
        "--print-function",
        "--target-file", "file.c",
        "--line", "42"
    ])
    assert args.repo_url is None

    # With print-function-by-name
    args = parse_args([
        "--print-function-by-name",
        "--name", "func",
        "--repo-tree-path", "tree.json"
    ])
    assert args.repo_url is None

def test_repo_url_required_without_special_args():
    """Test that repo_url is required when not using special arguments."""
    with pytest.raises(SystemExit):
        parse_args([])
