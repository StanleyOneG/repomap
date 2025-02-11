"""Tests for CallStackGenerator library usage."""

import json
from unittest.mock import Mock, patch

import pytest

from repomap import CallStackGenerator


@pytest.fixture
def mock_file_content():
    """Sample Python file content for testing."""
    return '''
def outer_function():
    print("Hello")
    inner_function()

def inner_function():
    print("World")

class TestClass:
    def method1(self):
        print("Method 1")
        self.method2()

    def method2(self):
        print("Method 2")
'''


@pytest.fixture
def mock_repo_tree():
    """Sample repository tree for testing."""
    return {
        "metadata": {"url": "https://github.com/user/repo", "ref": "main"},
        "files": {
            "test.py": {
                "language": "python",
                "ast": {
                    "functions": {
                        "outer_function": {
                            "name": "outer_function",
                            "start_line": 1,
                            "end_line": 4,
                            "class": None,
                            "calls": ["inner_function"],
                        },
                        "TestClass.method1": {
                            "name": "method1",
                            "start_line": 9,
                            "end_line": 11,
                            "class": "TestClass",
                            "calls": ["method2"],
                        },
                    }
                },
            }
        },
    }


def test_callstack_generator_import():
    """Test that CallStackGenerator can be imported and instantiated."""
    generator = CallStackGenerator(token="test_token")
    assert generator is not None
    assert generator.token == "test_token"


@patch('repomap.callstack.get_provider')
def test_get_function_content_by_line(mock_get_provider, mock_file_content):
    """Test getting function content by line number."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.return_value = mock_file_content
    mock_get_provider.return_value = mock_provider

    # Create generator instance
    generator = CallStackGenerator(token="test_token")

    # Get function content by line
    content = generator.get_function_content_by_line(
        "https://github.com/user/repo/test.py", line_number=2
    )

    # Verify content
    assert "def outer_function():" in content
    assert "inner_function()" in content


@patch('repomap.callstack.get_provider')
def test_get_function_content_by_name(
    mock_get_provider, mock_file_content, mock_repo_tree, tmp_path
):
    """Test getting function content by name."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.return_value = mock_file_content
    mock_get_provider.return_value = mock_provider

    # Create a temporary repo tree file
    repo_tree_file = tmp_path / "repo_tree.json"
    repo_tree_file.write_text(json.dumps(mock_repo_tree))

    # Create generator instance
    generator = CallStackGenerator(token="test_token")

    # Get function content by name
    contents = generator.get_function_content_by_name(str(repo_tree_file), "method1")

    # Verify content
    assert "TestClass" in contents
    assert "def method1(self):" in contents["TestClass"]
    assert "self.method2()" in contents["TestClass"]


@patch('repomap.callstack.get_provider')
def test_generate_call_stack(mock_get_provider, mock_file_content):
    """Test generating call stack."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.return_value = mock_file_content
    mock_get_provider.return_value = mock_provider

    # Create generator instance
    generator = CallStackGenerator(token="test_token")

    # Generate call stack
    call_stack = generator.generate_call_stack(
        "https://github.com/user/repo/test.py", line_number=2
    )

    # Verify call stack
    assert len(call_stack) == 1
    assert call_stack[0]["function"] == "outer_function"
    assert "inner_function" in call_stack[0]["calls"]
