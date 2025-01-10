"""Tests for command-line interface."""

import json
import os
from pathlib import Path
import pytest
from unittest.mock import Mock, patch

from repomap.cli import main, parse_args

def test_parse_args_repo_url():
    """Test repo_url argument validation."""
    # repo_url is required when not using --call-stack
    with pytest.raises(SystemExit):
        parse_args([])

    # repo_url is optional when using --call-stack
    with pytest.raises(SystemExit):
        parse_args(['--call-stack'])  # Fails because other required args are missing

    # repo_url works normally for repository mapping
    args = parse_args(['https://example.com/repo'])
    assert args.repo_url == 'https://example.com/repo'

def test_parse_args_call_stack(capsys):
    """Test parsing call stack arguments."""
    # Missing required arguments
    with pytest.raises(SystemExit):
        parse_args(['--call-stack'])
    captured = capsys.readouterr()
    assert "--call-stack requires --target-file" in captured.err

    with pytest.raises(SystemExit):
        parse_args(['--call-stack', '--target-file', 'file.py'])
    captured = capsys.readouterr()
    assert "--call-stack requires" in captured.err

    # All required arguments provided
    args = parse_args([
        '--call-stack',
        '--target-file', 'file.py',
        '--line', '42',
        '--structure-file', 'structure.json',
        '--output-stack', 'output.json'
    ])
    assert args.call_stack
    assert args.target_file == 'file.py'
    assert args.line == 42
    assert args.structure_file == 'structure.json'
    assert args.output_stack == 'output.json'
    assert args.repo_url is None  # repo_url is not required for call stack

@patch('repomap.cli.CallStackGenerator')
def test_main_call_stack(mock_generator, tmp_path):
    """Test main function with call stack generation."""
    # Create a temporary structure file
    structure_file = tmp_path / "structure.json"
    structure_file.write_text("{}")
    
    # Create a mock generator instance
    mock_instance = Mock()
    mock_instance.generate_call_stack.return_value = [{
        'function': 'main',
        'file': 'test.py',
        'line': 42,
        'calls': ['helper']
    }]
    mock_generator.return_value = mock_instance
    
    # Run main with call stack arguments
    output_file = tmp_path / "output.json"
    args = [
        '--call-stack',
        '--target-file', 'test.py',
        '--line', '42',
        '--structure-file', str(structure_file),
        '--output-stack', str(output_file)
    ]
    
    with patch('sys.argv', ['repomap'] + args):
        assert main() == 0
    
    # Verify the generator was called correctly
    mock_generator.assert_called_once_with(str(structure_file))
    mock_instance.generate_call_stack.assert_called_once_with('test.py', 42)
    mock_instance.save_call_stack.assert_called_once()
