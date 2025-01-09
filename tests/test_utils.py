"""Tests for utility functions."""

import json
import logging
import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from repomap.utils import store_repo_map, load_repo_map, setup_logging

@pytest.fixture
def sample_repo_map():
    """Sample repository map data for testing."""
    return {
        "metadata": {
            "url": "https://git-testing.devsec.astralinux.ru/user/repo",
            "version": "0.1.0"
        },
        "structure": {
            "src": {
                "main.py": {
                    "type": "blob",
                    "path": "src/main.py",
                    "mode": "100644"
                }
            },
            "README.md": {
                "type": "blob",
                "path": "README.md",
                "mode": "100644"
            }
        },
        "ast_data": {
            "src/main.py": {
                "type": "module",
                "children": []
            }
        }
    }

def test_store_repo_map(sample_repo_map, tmp_path):
    """Test storing repository map to file."""
    # Test with default output path
    with patch("pathlib.Path.mkdir"):  # Mock directory creation
        with patch("builtins.open", mock_open()) as mock_file:
            output_path = store_repo_map(sample_repo_map)
            assert output_path == "repomap.json"
            mock_file.assert_called_once_with(Path("repomap.json"), "w", encoding="utf-8")
            
            # Get all write calls and combine their content
            written_content = ''
            for call in mock_file().write.call_args_list:
                written_content += call[0][0]
            
            # Verify JSON content
            assert json.loads(written_content) == sample_repo_map
    
    # Test with custom output path
    test_output = tmp_path / "test_output" / "map.json"
    output_path = store_repo_map(sample_repo_map, str(test_output))
    assert output_path == str(test_output)
    assert test_output.exists()
    
    # Verify file content
    with open(test_output, "r", encoding="utf-8") as f:
        stored_data = json.load(f)
        assert stored_data == sample_repo_map

def test_store_repo_map_error_handling(sample_repo_map):
    """Test error handling when storing repository map."""
    # Test IOError handling
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Test error")
        with pytest.raises(IOError):
            store_repo_map(sample_repo_map)

def test_load_repo_map(sample_repo_map, tmp_path):
    """Test loading repository map from file."""
    # Create a test file
    test_file = tmp_path / "test_map.json"
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(sample_repo_map, f)
    
    # Test successful load
    loaded_data = load_repo_map(str(test_file))
    assert loaded_data == sample_repo_map
    
    # Test file not found
    with pytest.raises(FileNotFoundError):
        load_repo_map("nonexistent.json")
    
    # Test invalid JSON
    invalid_json = tmp_path / "invalid.json"
    with open(invalid_json, "w", encoding="utf-8") as f:
        f.write("invalid json content")
    
    with pytest.raises(json.JSONDecodeError):
        load_repo_map(str(invalid_json))

def test_setup_logging():
    """Test logging setup."""
    # Reset logging configuration before test
    logging.root.handlers = []
    logging.root.setLevel(logging.NOTSET)
    
    # Test default level
    setup_logging()
    assert logging.getLogger().level == logging.INFO
    
    # Reset again before testing custom level
    logging.root.handlers = []
    logging.root.setLevel(logging.NOTSET)
    
    # Test custom level
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    
    # Test invalid level handling
    with pytest.raises(ValueError):
        setup_logging("INVALID_LEVEL")

def test_logging_output():
    """Test logging output format."""
    # Reset logging to default state
    logging.root.handlers = []
    
    # Setup logging and capture log records
    setup_logging()
    with patch("logging.getLogger", return_value=logging.getLogger()) as mock_get_logger:
        logger = mock_get_logger()
        
        # Add a handler that captures log records
        log_capture = []
        test_handler = logging.Handler()
        test_handler.emit = lambda record: log_capture.append(record)
        logger.addHandler(test_handler)
        
        # Test log message
        test_message = "Test log message"
        logger.info(test_message)
        
        # Verify log message was captured
        assert len(log_capture) == 1
        assert log_capture[0].getMessage() == test_message

def test_store_repo_map_creates_directories(sample_repo_map, tmp_path):
    """Test that store_repo_map creates necessary directories."""
    nested_path = tmp_path / "deep" / "nested" / "path" / "map.json"
    
    # Store map in nested directory structure
    output_path = store_repo_map(sample_repo_map, str(nested_path))
    
    # Verify directories were created
    assert nested_path.parent.exists()
    assert nested_path.exists()
    
    # Verify content
    with open(nested_path, "r", encoding="utf-8") as f:
        stored_data = json.load(f)
        assert stored_data == sample_repo_map
