"""Tests for call stack generation functionality."""

import json
import os
import pytest
import gitlab
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from repomap.callstack import CallStackGenerator
from repomap.config import settings

# Mock settings for tests
settings.GITLAB_BASE_URL = "https://git-testing.devsec.astralinux.ru"

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

@patch('gitlab.Gitlab')
def test_get_file_content(mock_gitlab, generator):
    """Test fetching file content."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_PYTHON_CONTENT
    
    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    # Test with a GitLab URL
    url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/src/file.py"
    content = generator._get_file_content(url)
    
    assert content == SAMPLE_PYTHON_CONTENT
    mock_project.files.get.assert_called_once_with(file_path="src/file.py", ref="main")

@patch('gitlab.Gitlab')
def test_generate_call_stack(mock_gitlab, generator):
    """Test generating call stack from Python code."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_PYTHON_CONTENT
    
    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/src/file.py"
    call_stack = generator.generate_call_stack(url, 7)
    
    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'main'
    assert call_stack[0]['file'] == url
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

@patch('gitlab.Gitlab')
def test_generate_call_stack_minimal(mock_gitlab):
    """Test generating call stack with minimal arguments."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_PYTHON_CONTENT
    
    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    # Create generator without structure file
    generator = CallStackGenerator()
    url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/src/file.py"
    call_stack = generator.generate_call_stack(url, 7)
    
    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'main'
    assert call_stack[0]['file'] == url
    assert call_stack[0]['line'] == 7
    assert 'helper' in call_stack[0]['calls']

def test_unsupported_language(generator):
    """Test handling of unsupported file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/test.unsupported"
        generator.generate_call_stack(url, 1)

@patch('gitlab.Gitlab')
def test_invalid_line_number(mock_gitlab, generator):
    """Test handling of invalid line numbers."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_PYTHON_CONTENT
    
    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    # Line 4 is between functions, should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/src/file.py"
        generator.generate_call_stack(url, 4)
    assert "No function found at line 4" in str(exc_info.value)

def test_load_structure(structure_file):
    """Test loading repository structure."""
    generator = CallStackGenerator(structure_file)
    assert generator.repo_structure == SAMPLE_STRUCTURE

@patch('gitlab.Gitlab')
def test_get_function_content(mock_gitlab):
    """Test getting function content."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_PYTHON_CONTENT
    
    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    generator = CallStackGenerator()  # No structure file needed for testing
    url = "https://git-testing.devsec.astralinux.ru/group/project/-/blob/main/src/file.py"
    
    # Test getting main function content
    content = generator.get_function_content(url, 7)  # Line inside main()
    assert "def main():" in content
    assert "x = helper()" in content
    assert "return x" in content
    
    # Test getting helper function content
    content = generator.get_function_content(url, 2)  # Line inside helper()
    assert "def helper():" in content
    assert 'print("Helper function")' in content
    assert "return 42" in content
    
    # Test invalid line number
    with pytest.raises(ValueError, match="No function found at line"):
        generator.get_function_content(url, 10)  # Line outside any function
    
    # Test unsupported file type
    with pytest.raises(ValueError, match="Unsupported file type"):
        generator.get_function_content("test.unsupported", 1)
