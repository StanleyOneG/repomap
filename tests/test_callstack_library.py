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


@pytest.fixture
def mock_cpp_file_content():
    """Sample C++ file content for testing."""
    return '''
namespace test {
    class TestClass {
    public:
        void method1() {
            doSomething();
        }

        void method2();
    };
}

void test::TestClass::method2() {
    doSomethingElse();
}
'''


@pytest.fixture
def mock_c_pointer_file_content():
    """Sample C file content with pointer in function name for testing."""
    return '''
static struct sec_request_el
*sec_alg_alloc_and_fill_el(struct sec_bd_info *template, int encrypt,
               int el_size, bool different_dest,
               struct scatterlist *sgl_in, int n_ents_in,
               struct scatterlist *sgl_out, int n_ents_out,
               struct sec_dev_info *info, gfp_t gfp)
{
    struct sec_request_el *el;
    el = kzalloc(sizeof(*el), gfp);
    return el;
}

int regular_function(int param) {
    return param * 2;
}

void* get_memory(size_t size) {
    return malloc(size);
}

char *parse_string(const char *input) {
    return strdup(input);
}
'''


def test_callstack_generator_import():
    """Test that CallStackGenerator can be imported and instantiated."""
    generator = CallStackGenerator(token="test_token")
    assert generator is not None
    assert generator.token == "test_token"


@patch('repomap.callstack.get_provider')
def test_get_cpp_function_content_by_line(mock_get_provider, mock_cpp_file_content):
    """Test getting C++ function content by line number."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.return_value = mock_cpp_file_content
    mock_get_provider.return_value = mock_provider

    # Create generator instance
    generator = CallStackGenerator()

    # Get function content by line - in-class method
    content1 = generator.get_function_content_by_line("test.cpp", line_number=5)
    assert "void method1()" in content1
    assert "doSomething();" in content1

    # Get function content by line - out-of-class method
    content2 = generator.get_function_content_by_line("test.cpp", line_number=13)
    assert "void test::TestClass::method2()" in content2
    assert "doSomethingElse();" in content2


@patch('repomap.callstack.get_provider')
def test_get_c_pointer_function_content_by_line(
    mock_get_provider, mock_c_pointer_file_content
):
    """Test getting C function with pointer in name by line number."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.return_value = mock_c_pointer_file_content
    mock_get_provider.return_value = mock_provider

    # Create generator instance
    generator = CallStackGenerator()

    # Get function content by line - function with pointer in name (pointer on separate line)
    content = generator.get_function_content_by_line("test.c", line_number=5)
    assert "*sec_alg_alloc_and_fill_el" in content
    assert "struct sec_request_el" in content
    assert "return el;" in content

    # Get regular function content to ensure we didn't break existing functionality
    content2 = generator.get_function_content_by_line("test.c", line_number=14)
    assert "int regular_function(int param)" in content2
    assert "return param * 2;" in content2

    # Test function with pointer in return type (void*)
    content3 = generator.get_function_content_by_line("test.c", line_number=18)
    assert "void* get_memory" in content3
    assert "return malloc(size);" in content3

    # Test function with pointer in return type (char *)
    content4 = generator.get_function_content_by_line("test.c", line_number=22)
    assert "char *parse_string" in content4
    assert "return strdup(input);" in content4


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

    # Verify content - key format is now "file_path:class_or_global"
    expected_key = "test.py:TestClass"
    assert expected_key in contents
    assert "def method1(self):" in contents[expected_key]
    assert "self.method2()" in contents[expected_key]


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


@pytest.fixture
def mock_repo_tree_multiple_funcs():
    """Sample repository tree with multiple files having same function."""
    return {
        "metadata": {"url": "https://github.com/user/repo", "ref": "main"},
        "files": {
            "file1.py": {
                "language": "python",
                "ast": {
                    "functions": {
                        "helper": {
                            "name": "helper",
                            "start_line": 1,
                            "end_line": 3,
                            "class": None,
                            "calls": [],
                        },
                    }
                },
            },
            "file2.py": {
                "language": "python",
                "ast": {
                    "functions": {
                        "helper": {
                            "name": "helper",
                            "start_line": 1,
                            "end_line": 3,
                            "class": None,
                            "calls": [],
                        },
                    }
                },
            },
        },
    }


@patch('repomap.callstack.get_provider')
def test_get_function_content_by_name_with_file_path(
    mock_get_provider, mock_repo_tree_multiple_funcs, tmp_path
):
    """Test getting function content by name with file_path filter."""

    def mock_content(url):
        if "file1.py" in url:
            return '''def helper():
    print("Helper from file1")
    return 1'''
        elif "file2.py" in url:
            return '''def helper():
    print("Helper from file2")
    return 2'''
        return None

    # Mock the provider
    mock_provider = Mock()
    mock_provider.get_file_content.side_effect = mock_content
    mock_get_provider.return_value = mock_provider

    # Create a temporary repo tree file
    repo_tree_file = tmp_path / "repo_tree.json"
    repo_tree_file.write_text(json.dumps(mock_repo_tree_multiple_funcs))

    # Create generator instance
    generator = CallStackGenerator(token="test_token")

    # Get all helper functions (without file_path filter)
    all_contents = generator.get_function_content_by_name(str(repo_tree_file), "helper")
    assert len(all_contents) == 2
    assert "file1.py:global" in all_contents
    assert "file2.py:global" in all_contents

    # Get helper function from specific file
    filtered_contents = generator.get_function_content_by_name(
        str(repo_tree_file), "helper", file_path="file1.py"
    )
    assert len(filtered_contents) == 1
    assert "file1.py:global" in filtered_contents
    assert "Helper from file1" in filtered_contents["file1.py:global"]


@patch('repomap.callstack.get_provider')
def test_get_function_content_by_name_file_not_in_tree(
    mock_get_provider, mock_repo_tree, tmp_path
):
    """Test error when file_path is not in repository tree."""
    # Mock the provider
    mock_provider = Mock()
    mock_get_provider.return_value = mock_provider

    # Create a temporary repo tree file
    repo_tree_file = tmp_path / "repo_tree.json"
    repo_tree_file.write_text(json.dumps(mock_repo_tree))

    # Create generator instance
    generator = CallStackGenerator(token="test_token")

    # Try to get function with non-existent file_path
    with pytest.raises(ValueError, match="File not found in repository tree"):
        generator.get_function_content_by_name(
            str(repo_tree_file), "method1", file_path="nonexistent.py"
        )
