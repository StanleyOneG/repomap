"""Tests for call stack generation functionality."""

import json
import os
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from repomap.callstack import CallStackGenerator

# Sample repository structure for testing
SAMPLE_STRUCTURE = {
    "metadata": {
        "url": "https://example.com/repo",
        "version": "0.1.0"
    },
    "structure": {
        "src": {
            "main.py": {
                "type": "blob",
                "path": "src/main.py"
            }
        }
    }
}

# Sample Python file content for testing
SAMPLE_PYTHON_CONTENT = '''
def helper():
    print("Helper function")
    return 42

def main():
    x = helper()  # Line 7
    print(x)
    return x

if __name__ == "__main__":
    main()
'''

@pytest.fixture
def structure_file(tmp_path):
    """Create a temporary structure file for testing."""
    file_path = tmp_path / "structure.json"
    with open(file_path, "w") as f:
        json.dump(SAMPLE_STRUCTURE, f)
    return str(file_path)

@pytest.fixture
def generator(structure_file):
    """Create a CallStackGenerator instance for testing."""
    return CallStackGenerator(structure_file)

def test_init_parsers(generator):
    """Test parser initialization."""
    assert 'python' in generator.parsers
    assert 'python' in generator.queries
    assert generator.parsers['python'] is not None
    assert generator.queries['python'] is not None

def test_detect_language(generator):
    """Test language detection from file extensions."""
    assert generator._detect_language("test.py") == "python"
    assert generator._detect_language("test.cpp") == "cpp"
    assert generator._detect_language("test.unknown") is None

@patch('requests.get')
def test_get_file_content(mock_get, generator):
    """Test fetching file content."""
    mock_response = Mock()
    mock_response.text = SAMPLE_PYTHON_CONTENT
    mock_get.return_value = mock_response
    
    content = generator._get_file_content("https://example.com/file.py")
    assert content == SAMPLE_PYTHON_CONTENT
    mock_get.assert_called_once_with("https://example.com/file.py")

@patch('requests.get')
def test_generate_call_stack(mock_get, generator):
    """Test generating call stack from Python code."""
    mock_response = Mock()
    mock_response.text = SAMPLE_PYTHON_CONTENT
    mock_get.return_value = mock_response
    
    call_stack = generator.generate_call_stack("https://example.com/file.py", 7)
    
    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'main'
    assert call_stack[0]['file'] == 'https://example.com/file.py'
    assert call_stack[0]['line'] == 7
    assert 'helper' in call_stack[0]['calls']

def test_save_call_stack(generator, tmp_path):
    """Test saving call stack to file."""
    output_file = tmp_path / "call_stack.json"
    call_stack = [{
        'function': 'main',
        'file': 'test.py',
        'line': 10,
        'calls': ['helper']
    }]
    
    generator.save_call_stack(call_stack, str(output_file))
    
    assert output_file.exists()
    with open(output_file) as f:
        saved_data = json.load(f)
    assert saved_data == call_stack

def test_unsupported_language(generator):
    """Test handling of unsupported file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        generator.generate_call_stack("test.unsupported", 1)

@patch('requests.get')
def test_invalid_line_number(mock_get, generator):
    """Test handling of invalid line numbers."""
    mock_response = Mock()
    mock_response.text = SAMPLE_PYTHON_CONTENT
    mock_get.return_value = mock_response
    
    with pytest.raises(ValueError, match="No function found at line"):
        generator.generate_call_stack("test.py", 4)  # Line 4 is between functions

def test_load_structure(structure_file):
    """Test loading repository structure."""
    generator = CallStackGenerator(structure_file)
    assert generator.repo_structure == SAMPLE_STRUCTURE
