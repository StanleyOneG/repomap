"""Tests for repository AST tree generation."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from repomap.repo_tree import RepoTreeGenerator
from gitlab import Gitlab

@pytest.fixture
def repo_tree_generator():
    """Create a RepoTreeGenerator instance for testing."""
    return RepoTreeGenerator()

@pytest.fixture
def mock_python_content():
    """Mock Python file content for testing."""
    return """
def outer_function():
    print("Start")
    inner_result = inner_function()
    process_result(inner_result)
    return inner_result

def inner_function():
    helper_function()
    return "result"

def helper_function():
    print("Helper")

def process_result(result):
    validate(result)
    transform(result)
    
def validate(data):
    print("Validating")
    
def transform(data):
    print("Transforming")

class DataProcessor:
    def __init__(self):
        self.data = None
        
    def process(self):
        self.validate_data()
        result = self.transform_data()
        self.save_result(result)
        outer_function()
    
    def validate_data(self):
        validate(self.data)
        self._internal_validate()
    
    def transform_data(self):
        result = transform(self.data)
        processed = self._internal_transform(result)
        return processed
    
    def save_result(self, result):
        self.data = result
        self._internal_save()
        
    def _internal_validate(self):
        print("Internal validation")
        
    def _internal_transform(self, data):
        print("Internal transform")
        return data
        
    def _internal_save(self):
        print("Internal save")
"""

def test_detect_language(repo_tree_generator):
    """Test language detection from file extensions."""
    assert repo_tree_generator._detect_language("test.py") == "python"
    assert repo_tree_generator._detect_language("test.cpp") == "cpp"
    assert repo_tree_generator._detect_language("test.unknown") is None

@patch("gitlab.Gitlab")
@patch("repomap.core.fetch_repo_structure")
@pytest.fixture
def mock_c_content():
    """Mock C file content for testing."""
    return """
#include <stdio.h>
#include <stdlib.h>
#include "local_header.h"

typedef struct {
    int x;
    int y;
} Point;

struct Rectangle {
    Point top_left;
    Point bottom_right;
};

typedef struct Shape {
    int type;
    union {
        Point point;
        struct Rectangle rect;
    } data;
} Shape;

static void init_point(Point *p, int x, int y) {
    p->x = x;
    p->y = y;
    validate_point(p);
}

int calculate_area(struct Rectangle *rect) {
    int width = rect->bottom_right.x - rect->top_left.x;
    int height = rect->bottom_right.y - rect->top_left.y;
    return width * height;
}

void process_shape(Shape *shape) {
    switch(shape->type) {
        case 0:
            init_point(&shape->data.point, 0, 0);
            break;
        case 1:
            calculate_area(&shape->data.rect);
            transform_shape(shape);
            break;
    }
}

static void transform_shape(Shape *shape) {
    if (shape->type == 0) {
        shape->data.point.x *= 2;
        shape->data.point.y *= 2;
    }
}
"""

def test_generate_repo_tree_python(mock_fetch, mock_gitlab, repo_tree_generator, mock_python_content):
    # Mock GitLab client
    mock_gl = MagicMock()
    mock_gitlab.return_value = mock_gl
    mock_project = MagicMock()
    mock_gl.projects.get.return_value = mock_project
    """Test repository AST tree generation."""
    # Mock repository structure
    mock_fetch.return_value = {
        "src": {
            "main.py": {
                "type": "blob",
                "size": 100
            }
        }
    }
    
    # Mock file content fetching
    with patch.object(repo_tree_generator, '_get_file_content', return_value=mock_python_content):
        repo_tree = repo_tree_generator.generate_repo_tree("https://example.com/group/repo")
        
        # Verify repository tree structure
        assert "metadata" in repo_tree
        assert "files" in repo_tree
        assert "src/main.py" in repo_tree["files"]
        
        # Verify AST data for the Python file
        file_data = repo_tree["files"]["src/main.py"]
        assert file_data["language"] == "python"
        
        ast_data = file_data["ast"]
        assert "functions" in ast_data
        assert "classes" in ast_data
        assert "calls" in ast_data
        
        # Verify functions
        functions = ast_data["functions"]
        assert "outer_function" in functions
        assert "inner_function" in functions
        assert "helper_function" in functions
        assert "process_result" in functions
        
        # Verify outer_function calls
        outer_calls = functions["outer_function"]["calls"]
        assert "inner_function" in outer_calls
        assert "process_result" in outer_calls
        
        # Verify process_result calls
        process_calls = functions["process_result"]["calls"]
        assert "validate" in process_calls
        assert "transform" in process_calls
        
        # Verify inner_function calls
        inner_calls = functions["inner_function"]["calls"]
        assert "helper_function" in inner_calls
        
        # Verify classes
        classes = ast_data["classes"]
        assert "DataProcessor" in classes
        
        # Verify class methods
        methods = classes["DataProcessor"]["methods"]
        assert "process" in methods
        assert "validate_data" in methods
        assert "transform_data" in methods
        assert "save_result" in methods
        assert "_internal_validate" in methods
        assert "_internal_transform" in methods
        assert "_internal_save" in methods
        
        # Verify method calls
        process_method = functions["process"]
        assert process_method["class"] == "DataProcessor"
        assert "validate_data" in process_method["calls"]
        assert "transform_data" in process_method["calls"]
        assert "save_result" in process_method["calls"]
        assert "outer_function" in process_method["calls"]
        
        validate_data_method = functions["validate_data"]
        assert validate_data_method["class"] == "DataProcessor"
        assert "validate" in validate_data_method["calls"]
        assert "_internal_validate" in validate_data_method["calls"]
        
        transform_data_method = functions["transform_data"]
        assert transform_data_method["class"] == "DataProcessor"
        assert "transform" in transform_data_method["calls"]
        assert "_internal_transform" in transform_data_method["calls"]

def test_save_repo_tree(repo_tree_generator, tmp_path):
    """Test saving repository AST tree to file."""
    # Create test data
    repo_tree = {
        "metadata": {"url": "https://example.com/repo"},
        "files": {
            "test.py": {
                "language": "python",
                "ast": {
                    "functions": {},
                    "classes": {},
                    "calls": []
                }
            }
        }
    }
    
    # Save to temporary file
    output_file = tmp_path / "repo_tree.json"
    repo_tree_generator.save_repo_tree(repo_tree, str(output_file))
    
    # Verify file was created and contains correct data
    assert output_file.exists()
    with open(output_file) as f:
        saved_data = json.loads(f.read())
        assert saved_data == repo_tree

@patch("gitlab.Gitlab")
@patch("repomap.core.fetch_repo_structure")
def test_generate_repo_tree_c(mock_fetch, mock_gitlab, repo_tree_generator, mock_c_content):
    """Test repository AST tree generation for C code."""
    # Mock GitLab client
    mock_gl = MagicMock()
    mock_gitlab.return_value = mock_gl
    mock_project = MagicMock()
    mock_gl.projects.get.return_value = mock_project
    
    # Mock repository structure
    mock_fetch.return_value = {
        "src": {
            "shapes.c": {
                "type": "blob",
                "size": 100
            }
        }
    }
    
    # Mock file content fetching
    with patch.object(repo_tree_generator, '_get_file_content', return_value=mock_c_content):
        repo_tree = repo_tree_generator.generate_repo_tree("https://example.com/group/repo")
        
        # Verify repository tree structure
        assert "metadata" in repo_tree
        assert "files" in repo_tree
        assert "src/shapes.c" in repo_tree["files"]
        
        # Verify AST data for the C file
        file_data = repo_tree["files"]["src/shapes.c"]
        assert file_data["language"] == "c"
        
        ast_data = file_data["ast"]
        assert "functions" in ast_data
        assert "classes" in ast_data
        assert "calls" in ast_data
        assert "imports" in ast_data
        
        # Verify functions
        functions = ast_data["functions"]
        assert "init_point" in functions
        assert "calculate_area" in functions
        assert "process_shape" in functions
        assert "transform_shape" in functions
        
        # Verify function calls
        init_point_calls = functions["init_point"]["calls"]
        assert "validate_point" in init_point_calls
        
        process_shape_calls = functions["process_shape"]["calls"]
        assert "init_point" in process_shape_calls
        assert "calculate_area" in process_shape_calls
        assert "transform_shape" in process_shape_calls
        
        # Verify structs/typedefs as classes
        classes = ast_data["classes"]
        assert "Point" in classes
        assert "Rectangle" in classes
        assert "Shape" in classes
        
        # Verify imports (#includes)
        imports = ast_data["imports"]
        assert "stdio.h" in imports
        assert "stdlib.h" in imports
        assert "local_header.h" in imports

@patch("gitlab.Gitlab")
@patch("repomap.core.fetch_repo_structure")
def test_generate_repo_tree_with_unsupported_files(mock_fetch, mock_gitlab, repo_tree_generator):
    # Mock GitLab client
    mock_gl = MagicMock()
    mock_gitlab.return_value = mock_gl
    mock_project = MagicMock()
    mock_gl.projects.get.return_value = mock_project
    """Test repository AST tree generation with unsupported file types."""
    # Mock repository structure with unsupported file
    mock_fetch.return_value = {
        "src": {
            "data.txt": {
                "type": "blob",
                "size": 100
            }
        }
    }
    
    repo_tree = repo_tree_generator.generate_repo_tree("https://example.com/group/repo")
    
    # Verify unsupported file was skipped
    assert len(repo_tree["files"]) == 0

@patch("gitlab.Gitlab")
@patch("repomap.core.fetch_repo_structure")
def test_generate_repo_tree_with_failed_content_fetch(mock_fetch, mock_gitlab, repo_tree_generator):
    # Mock GitLab client
    mock_gl = MagicMock()
    mock_gitlab.return_value = mock_gl
    mock_project = MagicMock()
    mock_gl.projects.get.return_value = mock_project
    """Test repository AST tree generation when file content fetch fails."""
    # Mock repository structure
    mock_fetch.return_value = {
        "src": {
            "main.py": {
                "type": "blob",
                "size": 100
            }
        }
    }
    
    # Mock file content fetch failure
    with patch.object(repo_tree_generator, '_get_file_content', return_value=None):
        repo_tree = repo_tree_generator.generate_repo_tree("https://example.com/group/repo")
        
        # Verify file was skipped
        assert len(repo_tree["files"]) == 0
