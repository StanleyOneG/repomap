"""Tests for the CallStackGenerator class."""

import json
import os
import pytest
from repomap.callstack import CallStackGenerator

# Mock data for testing
MOCK_REPO_TREE = {
    "metadata": {
        "url": "https://example.com/group/repo",
        "ref": "main"
    },
    "files": {
        "alsalisp/alsalisp.c": {
            "language": "c",
            "ast": {
                "functions": {
                    "interpret_filename": {
                        "name": "interpret_filename",
                        "start_line": 34,
                        "end_line": 70,
                        "class": None,
                        "calls": []
                    }
                }
            }
        }
    }
}

@pytest.fixture
def mock_repo_tree_file(tmp_path):
    """Create a mock repository tree file for testing."""
    file_path = tmp_path / "repo_tree.json"
    with open(file_path, "w") as f:
        json.dump(MOCK_REPO_TREE, f)
    return str(file_path)

@pytest.fixture
def mock_generator(monkeypatch):
    """Create a CallStackGenerator with mocked file content."""
    def mock_get_file_content(self, file_url):
        return """int interpret_filename(const char *filename)
{
    int err;
    struct alisp_cfg cfg;
    
    memset(&cfg, 0, sizeof(cfg));
    if (strcmp(filename, "-") == 0) {
        err = snd_input_stdio_attach(&cfg.in, stdin, 0);
        if (err < 0) {
            fprintf(stderr, "stdin open error: %s\n", snd_strerror(err));
            return err;
        }
        err = snd_output_stdio_attach(&cfg.out, stdout, 0);
        if (err < 0) {
            snd_input_close(cfg.in);
            fprintf(stderr, "stdout open error: %s\n", snd_strerror(err));
            return err;
        }
    } else {
        err = snd_input_stdio_open(&cfg.in, filename, "r");
        if (err < 0) {
            fprintf(stderr, "%s open error: %s\n", filename, snd_strerror(err));
            return err;
        }
        err = snd_output_stdio_attach(&cfg.out, stdout, 0);
        if (err < 0) {
            snd_input_close(cfg.in);
            fprintf(stderr, "stdout open error: %s\n", snd_strerror(err));
            return err;
        }
    }
    err = alsa_lisp(&cfg);
    snd_output_close(cfg.out);
    snd_input_close(cfg.in);
    return err;
}"""

    monkeypatch.setattr(CallStackGenerator, "_get_file_content", mock_get_file_content)
    return CallStackGenerator()

def test_get_function_content_by_name(mock_repo_tree_file, mock_generator):
    """Test getting function content by name."""
    content = mock_generator.get_function_content_by_name(mock_repo_tree_file, "interpret_filename")
    assert "int interpret_filename(const char *filename)" in content
    assert "return err;" in content

def test_get_function_content_by_name_not_found(mock_repo_tree_file, mock_generator):
    """Test error when function name is not found."""
    with pytest.raises(ValueError, match="No function found with name: nonexistent_function"):
        mock_generator.get_function_content_by_name(mock_repo_tree_file, "nonexistent_function")

def test_get_function_content_by_name_invalid_tree(tmp_path):
    """Test error with invalid repo tree file."""
    # Create invalid repo tree file
    file_path = tmp_path / "invalid_tree.json"
    with open(file_path, "w") as f:
        json.dump({}, f)
    
    generator = CallStackGenerator()
    with pytest.raises(ValueError, match="Invalid repository tree file: missing metadata.url"):
        generator.get_function_content_by_name(str(file_path), "any_function")
