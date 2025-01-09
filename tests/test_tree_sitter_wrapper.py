"""Tests for tree-sitter wrapper functionality."""

import pytest
from unittest.mock import Mock, patch

from repomap.tree_sitter_wrapper import TreeSitterWrapper, parse_source_file

def test_get_language_by_extension():
    """Test language detection by file extension."""
    wrapper = TreeSitterWrapper()
    
    # Test supported languages
    assert wrapper._get_language_by_extension("test.py") == "python"
    assert wrapper._get_language_by_extension("test.js") == "javascript"
    assert wrapper._get_language_by_extension("test.ts") == "typescript"
    assert wrapper._get_language_by_extension("test.cpp") == "cpp"
    assert wrapper._get_language_by_extension("test.hpp") == "cpp"
    assert wrapper._get_language_by_extension("test.c") == "c"
    assert wrapper._get_language_by_extension("test.h") == "c"
    assert wrapper._get_language_by_extension("test.java") == "java"
    assert wrapper._get_language_by_extension("test.rb") == "ruby"
    assert wrapper._get_language_by_extension("test.go") == "go"
    assert wrapper._get_language_by_extension("test.rs") == "rust"
    assert wrapper._get_language_by_extension("test.php") == "php"
    
    # Test unsupported extensions
    assert wrapper._get_language_by_extension("test.txt") is None
    assert wrapper._get_language_by_extension("test.unknown") is None
    assert wrapper._get_language_by_extension("test") is None

@patch('repomap.tree_sitter_wrapper.get_language')
@patch('repomap.tree_sitter_wrapper.get_parser')
def test_get_parser(mock_get_parser, mock_get_language):
    """Test parser initialization."""
    # Setup mocks
    mock_language = Mock()
    mock_parser = Mock()
    mock_get_language.return_value = mock_language
    mock_get_parser.return_value = mock_parser
    
    wrapper = TreeSitterWrapper()
    
    # Test successful parser initialization
    parser = wrapper._get_parser("python")
    assert parser == mock_parser
    mock_get_language.assert_called_with("python")
    mock_get_parser.assert_called_with("python")
    mock_parser.set_language.assert_called_with(mock_language)
    
    # Test parser caching
    wrapper._get_parser("python")
    assert mock_get_language.call_count == 1  # Should use cached parser
    
    # Test error handling
    mock_get_language.side_effect = Exception("Language not found")
    with pytest.raises(ValueError):
        wrapper._get_parser("unsupported")

def test_parse_source_file():
    """Test source file parsing."""
    wrapper = TreeSitterWrapper()
    
    # Test unsupported file type
    result = wrapper.parse_source_file("test.txt", "content")
    assert result is None
    
    # Test Python file parsing
    python_code = """
def hello():
    print("Hello, World!")
    """
    
    with patch.object(wrapper, '_get_parser') as mock_get_parser:
        mock_parser = Mock()
        mock_tree = Mock()
        mock_root_node = Mock()
        
        # Setup mock node structure
        mock_root_node.type = "module"
        mock_root_node.start_point = (0, 0)
        mock_root_node.end_point = (3, 0)
        mock_root_node.children = []
        mock_root_node.start_byte = 0
        mock_root_node.end_byte = len(python_code)
        
        mock_tree.root_node = mock_root_node
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser
        
        result = wrapper.parse_source_file("test.py", python_code)
        
        assert result is not None
        assert result["type"] == "module"
        assert "children" in result
        assert isinstance(result["children"], list)

def test_convenience_function():
    """Test the convenience function."""
    with patch('repomap.tree_sitter_wrapper.TreeSitterWrapper') as mock_wrapper_class:
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        mock_wrapper.parse_source_file.return_value = {"test": "data"}
        
        result = parse_source_file("test.py", "content")
        
        assert result == {"test": "data"}
        mock_wrapper_class.assert_called_once()
        mock_wrapper.parse_source_file.assert_called_with("test.py", "content")

@pytest.mark.parametrize("code,expected_node_types", [
    (
        "def hello(): pass",
        ["module", "function_definition", "identifier", "parameters", "block", "pass_statement"]
    ),
    (
        "class Test: pass",
        ["module", "class_definition", "identifier", "block", "pass_statement"]
    ),
])
def test_node_structure(code, expected_node_types):
    """Test parsing of different Python constructs."""
    wrapper = TreeSitterWrapper()
    
    with patch.object(wrapper, '_get_parser') as mock_get_parser:
        mock_parser = Mock()
        mock_tree = Mock()
        mock_root_node = Mock()
        
        def create_mock_node(node_type, start, end, children=None):
            node = Mock()
            node.type = node_type
            node.start_point = start
            node.end_point = end
            node.start_byte = start[1]
            node.end_byte = end[1]
            node.children = children or []
            return node
        
        # Create mock node structure based on expected_node_types
        nodes = [create_mock_node(t, (0, i), (0, i + 1)) for i, t in enumerate(expected_node_types)]
        for i in range(len(nodes) - 1):
            nodes[i].children = [nodes[i + 1]]
        
        mock_root_node = nodes[0]
        mock_tree.root_node = mock_root_node
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser
        
        result = wrapper.parse_source_file("test.py", code)
        
        assert result is not None
        assert result["type"] == expected_node_types[0]
        
        # Verify node structure
        current = result
        for expected_type in expected_node_types[1:]:
            assert len(current["children"]) > 0
            current = current["children"][0]
            assert current["type"] == expected_type
