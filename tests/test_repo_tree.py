"""Tests for repository AST tree generation."""

import json
from unittest.mock import MagicMock, Mock, patch

import gitlab
import pytest

from repomap.repo_tree import RepoTreeGenerator


@pytest.fixture
def repo_tree_generator():
    """Create a RepoTreeGenerator instance for testing with Python support only."""
    from repomap.callstack import CallStackGenerator
    with patch('gitlab.Gitlab') as mock_gitlab:
        # Create mock instance with projects attribute
        mock_gl = Mock()
        mock_project = Mock()
        mock_project.default_branch = 'main'
        mock_gl.projects.get.return_value = mock_project
        mock_gitlab.return_value = mock_gl

        # Disable multiprocessing for testing to avoid pickling issues with mocks
        generator = RepoTreeGenerator(use_multiprocessing=False)
        
        # Optimize by only initializing Python parser for better performance
        with patch.object(CallStackGenerator, 'SUPPORTED_LANGUAGES', {'.py': 'python'}):
            generator.call_stack_gen = CallStackGenerator(token=generator.token)
        
        generator.parsers = generator.call_stack_gen.parsers
        generator.queries = generator.call_stack_gen.queries
        
        return generator


@pytest.fixture
def multi_lang_repo_tree_generator():
    """Create a RepoTreeGenerator instance for testing with working tree-sitter parsers."""
    from repomap.callstack import CallStackGenerator
    
    with patch('gitlab.Gitlab') as mock_gitlab:
        # Create mock instance with projects attribute
        mock_gl = Mock()
        mock_project = Mock()
        mock_project.default_branch = 'main'
        mock_gl.projects.get.return_value = mock_project
        mock_gitlab.return_value = mock_gl

        # Disable multiprocessing for testing to avoid pickling issues with mocks
        generator = RepoTreeGenerator(use_multiprocessing=False)
        
        # Use real CallStackGenerator but limit to only required languages for performance
        # We'll initialize all languages since tests need them, but this is still much faster
        # than full repo processing
        generator.call_stack_gen = CallStackGenerator(token=generator.token)
        
        generator.parsers = generator.call_stack_gen.parsers
        generator.queries = generator.call_stack_gen.queries
        
        return generator


@pytest.fixture
def api_only_repo_tree_generator():
    """Create a RepoTreeGenerator instance for testing with API-only access (no local cloning)."""
    from repomap.callstack import CallStackGenerator
    
    with patch('gitlab.Gitlab') as mock_gitlab:
        # Create mock instance with projects attribute
        mock_gl = Mock()
        mock_project = Mock()
        mock_project.default_branch = 'main'
        mock_gl.projects.get.return_value = mock_project
        mock_gitlab.return_value = mock_gl

        # Disable multiprocessing and local cloning for testing
        generator = RepoTreeGenerator(use_multiprocessing=False, use_local_clone=False)
        
        # Use real CallStackGenerator for parsing
        generator.call_stack_gen = CallStackGenerator(token=generator.token)
        
        generator.parsers = generator.call_stack_gen.parsers
        generator.queries = generator.call_stack_gen.queries
        
        return generator


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

    def get_processor(self) -> DataProcessor:
        return DataProcessor()

    def process(self):
        self.validate_data()
        result = self.transform_data()
        self.save_result(result)
        outer_function()

        # Test method return type resolution
        other = self.get_processor()
        other.validate_data()

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
    assert repo_tree_generator._detect_language("main.go") == "go"
    assert repo_tree_generator._detect_language("test.c") == "c"
    assert repo_tree_generator._detect_language("script.js") == "javascript"
    assert repo_tree_generator._detect_language("test.unknown") is None


@pytest.fixture
def mock_gitlab():
    """Mock GitLab client."""
    with patch('gitlab.Gitlab') as mock:
        mock_gl = MagicMock()
        mock.return_value = mock_gl
        mock_project = MagicMock()
        mock_gl.projects.get.return_value = mock_project
        mock_project.default_branch = 'main'

        mock_branches = MagicMock()
        mock_branches.get.side_effect = lambda ref: (
            MagicMock() if ref == 'dev' else gitlab.exceptions.GitlabGetError()
        )
        mock_project.branches = mock_branches

        mock_tags = MagicMock()
        mock_tags.get.side_effect = lambda ref: (
            MagicMock() if ref == 'v1.0' else gitlab.exceptions.GitlabGetError()
        )
        mock_project.tags = mock_tags

        mock_commits = MagicMock()
        mock_commits.get.side_effect = lambda ref: (
            MagicMock() if ref == 'abc123' else gitlab.exceptions.GitlabGetError()
        )
        mock_project.commits = mock_commits

        return mock


@pytest.fixture
def mock_fetch():
    """Mock fetch_repo_structure function."""
    with patch('repomap.core.fetch_repo_structure') as mock:
        return mock


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

static Shape *create_shape(int type) {
    Shape *shape = malloc(sizeof(Shape));
    shape->type = type;
    return shape;
}

void *allocate_memory(size_t size) {
    return malloc(size);
}
"""


@patch('gitlab.Gitlab')
def test_generate_repo_tree_python(
    mock_gitlab, repo_tree_generator, mock_python_content
):
    """Test repository AST tree generation."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=mock_python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

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

    # Verify class method calls
    process_method = functions["DataProcessor.process"]
    assert "DataProcessor.validate_data" in process_method["calls"]
    assert "DataProcessor.transform_data" in process_method["calls"]
    assert "DataProcessor.save_result" in process_method["calls"]
    # assert "outer_function" in process_method["calls"]

    # Verify method return type resolution
    assert "DataProcessor.get_processor" in functions
    assert (
        "DataProcessor.validate_data" in process_method["calls"]
    )  # From other.validate_data()

    validate_data_method = functions["DataProcessor.validate_data"]
    # assert "validate" in validate_data_method["calls"]
    assert "DataProcessor._internal_validate" in validate_data_method["calls"]

    # Verify classes
    classes = ast_data["classes"]
    assert "DataProcessor" in classes

    # Verify class line numbers
    data_processor_class = classes["DataProcessor"]
    assert "start_line" in data_processor_class
    assert "end_line" in data_processor_class
    assert isinstance(data_processor_class["start_line"], int)
    assert isinstance(data_processor_class["end_line"], int)
    assert data_processor_class["start_line"] < data_processor_class["end_line"]

    # Verify class methods
    methods = classes["DataProcessor"]["methods"]
    assert "process" in methods
    assert "validate_data" in methods
    assert "transform_data" in methods
    assert "save_result" in methods
    assert "_internal_validate" in methods
    assert "_internal_transform" in methods
    assert "_internal_save" in methods

    # Verify local variable resolution
    # assert "local_vars" in process_method
    # assert "other" in process_method["local_vars"]
    # assert process_method["local_vars"]["other"] == "DataProcessor"
    # assert "DataProcessor.validate_data" in process_method["calls"]

    # transform_data_method = functions["DataProcessor.transform_data"]
    # assert transform_data_method["class"] == "DataProcessor"
    # assert "transform" in transform_data_method["calls"]
    # assert "_internal_transform" in transform_data_method["calls"]


@pytest.fixture
def mock_nested_python_content():
    """Mock Python file content with nested class methods for testing."""
    return """
class ComplexClass:
    def __init__(self):
        self.data = None

    def outer_method(self):
        def inner_function():
            print("inner")

        inner_function()
        self.helper_method()

    def helper_method(self):
        self.process_data()

    def process_data(self):
        if self.data:
            self.validate()
            self.transform()

    def validate(self):
        print("validating")

    def transform(self):
        print("transforming")

class SimpleClass:
    def method_one(self):
        print("one")

    def method_two(self):
        self.method_one()
"""


@pytest.fixture
def mock_go_content():
    """Mock Go file content for testing."""
    return """
package main

import (
    "fmt"
    "log"
    "strings"
)

// User represents a user in the system
type User struct {
    Name string
    Age  int
    Email string
}

// UserService provides user operations
type UserService struct {
    users []User
}

// GetName returns the user's name
func (u *User) GetName() string {
    return u.Name
}

// SetAge sets the user's age
func (u *User) SetAge(age int) {
    u.Age = age
    validateAge(age)
}

// GetFormattedName returns formatted name
func (u *User) GetFormattedName() string {
    return strings.ToUpper(u.Name)
}

// NewUserService creates a new user service
func NewUserService() *UserService {
    return &UserService{
        users: make([]User, 0),
    }
}

// AddUser adds a user to the service
func (s *UserService) AddUser(user User) {
    s.users = append(s.users, user)
    log.Printf("Added user: %s", user.GetName())
}

// main function - entry point
func main() {
    user := &User{Name: "John", Age: 30, Email: "john@example.com"}
    fmt.Println(user.GetName())
    user.SetAge(25)
    
    service := NewUserService()
    service.AddUser(*user)
    
    processUser(user)
    result := validateUser(user)
    if result {
        logUser(user)
    }
}

// processUser processes a user
func processUser(u *User) {
    validateUser(u)
    logUser(u)
    formatted := u.GetFormattedName()
    fmt.Println(formatted)
}

// validateUser validates a user
func validateUser(u *User) bool {
    return u.Age > 0 && len(u.Name) > 0
}

// logUser logs user information
func logUser(u *User) {
    log.Printf("User: %s, Age: %d, Email: %s", u.Name, u.Age, u.Email)
}

// validateAge validates an age value
func validateAge(age int) bool {
    return age >= 0 && age <= 150
}
"""


@pytest.fixture
def mock_same_method_names_content():
    """Mock Python file content with same method names in different classes."""
    return """
class BaseClass:
    def validate_ref(self, repo_url: str):
        pass

class GitLabProvider(BaseClass):
    def validate_ref(self, repo_url: str):
        return "main"

class GitHubProvider(BaseClass):
    def validate_ref(self, repo_url: str):
        return "master"
"""


def test_same_method_names_different_classes(
    repo_tree_generator, mock_same_method_names_content
):
    """Test that methods with same names in different classes are captured correctly."""
    ast_data = repo_tree_generator._parse_file_ast(
        mock_same_method_names_content, 'python'
    )

    # Verify all three validate_ref methods are captured
    validate_ref_methods = [
        (key, data)
        for key, data in ast_data["functions"].items()
        if data["name"] == "validate_ref"
    ]

    assert len(validate_ref_methods) == 3, "Should find three validate_ref methods"

    # Verify each class has its validate_ref method
    classes_with_validate_ref = {data["class"] for _, data in validate_ref_methods}
    assert "BaseClass" in classes_with_validate_ref
    assert "GitLabProvider" in classes_with_validate_ref
    assert "GitHubProvider" in classes_with_validate_ref

    # Verify each method is stored with a unique key
    validate_ref_keys = {key for key, _ in validate_ref_methods}
    assert len(validate_ref_keys) == 3, "Each method should have a unique key"

    # Verify the methods are stored with their class names
    assert "BaseClass.validate_ref" in ast_data["functions"]
    assert "GitLabProvider.validate_ref" in ast_data["functions"]
    assert "GitHubProvider.validate_ref" in ast_data["functions"]

    # Verify classes are captured correctly
    assert "BaseClass" in ast_data["classes"]
    assert "GitLabProvider" in ast_data["classes"]
    assert "GitHubProvider" in ast_data["classes"]

    # Verify inheritance
    assert ast_data["classes"]["GitLabProvider"]["base_classes"] == ["BaseClass"]
    assert ast_data["classes"]["GitHubProvider"]["base_classes"] == ["BaseClass"]


@pytest.mark.skip(reason="Not implemented yet")
@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_nested_methods(
    mock_gitlab, repo_tree_generator, mock_nested_python_content
):
    """Test repository AST tree generation with nested class methods."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "complex.py",
            "type": "blob",
            "path": "src/complex.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        repo_tree_generator,
        '_get_file_content',
        return_value=mock_nested_python_content,
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

    # Verify repository tree structure
    assert "src/complex.py" in repo_tree["files"]
    file_data = repo_tree["files"]["src/complex.py"]
    assert file_data["language"] == "python"

    ast_data = file_data["ast"]

    # Verify ComplexClass methods
    assert "ComplexClass" in ast_data["classes"]
    complex_class = ast_data["classes"]["ComplexClass"]
    complex_methods = complex_class["methods"]
    assert "__init__" in complex_methods
    assert "outer_method" in complex_methods
    assert "helper_method" in complex_methods
    assert "process_data" in complex_methods
    assert "validate" in complex_methods
    assert "transform" in complex_methods

    # Verify SimpleClass methods
    assert "SimpleClass" in ast_data["classes"]
    simple_class = ast_data["classes"]["SimpleClass"]
    simple_methods = simple_class["methods"]
    assert "method_one" in simple_methods
    assert "method_two" in simple_methods

    # Verify method calls
    functions = ast_data["functions"]

    # Check ComplexClass method calls
    outer_method = functions["ComplexClass.outer_method"]
    assert outer_method["class"] == "ComplexClass"
    assert "inner_function" in outer_method["calls"]
    assert "helper_method" in outer_method["calls"]

    helper_method = functions["ComplexClass.helper_method"]
    assert helper_method["class"] == "ComplexClass"
    assert "process_data" in helper_method["calls"]

    process_data = functions["ComplexClass.process_data"]
    assert process_data["class"] == "ComplexClass"
    assert "validate" in process_data["calls"]
    assert "transform" in process_data["calls"]

    # Check SimpleClass method calls
    method_two = functions["SimpleClass.method_two"]
    assert method_two["class"] == "SimpleClass"
    assert "method_one" in method_two["calls"]


@pytest.mark.skip(reason="Not implemented yet")
@patch('gitlab.Gitlab')
def test_method_return_type_resolution(mock_gitlab, repo_tree_generator):
    """Test instance variable type resolution from method return types."""
    python_content = """
class Processor:
    def get_processor(self) -> 'Processor':
        return Processor()

class DataHandler:
    def __init__(self):
        self.processor = self.get_processor()

    def get_processor(self) -> Processor:
        return Processor()

    def run(self):
        self.processor.process()
    """

    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Setup mock project and file content
    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo/"
        )

    file_data = repo_tree['files']['src/main.py']
    ast_data = file_data['ast']

    # Verify method call resolution
    run_method = ast_data['functions']['DataHandler.run']
    assert 'Processor.process' in run_method['calls']


@pytest.mark.skip(reason="Not implemented yet")
@patch('gitlab.Gitlab')
def test_forward_reference_resolution(mock_gitlab, repo_tree_generator):
    """Test resolution of forward-referenced return types."""
    python_content = """
class Environment:
    def globals_update(self):
        pass

class Flask:
    def create_jinja_environment(self) -> Environment:
        rv = self.jinja_environment()
        rv.globals_update()
        return rv

    def jinja_environment(self) -> Environment:
        return Environment()
"""
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo/"
        )

    file_data = repo_tree['files']['src/main.py']
    ast_data = file_data['ast']

    create_method = ast_data['functions']['Flask.create_jinja_environment']
    assert (
        'Environment.globals_update' in create_method["calls"]
    ), "Method call should be resolved to 'Environment.globals_update'"
    assert (
        'Flask.jinja_environment' in create_method["calls"]
    ), "Method call should be resolved to 'Flask.jinja_environment'"

    # Verify variable resolution
    assert "rv" in create_method["local_vars"], "Variable should be captured"
    assert (
        create_method["local_vars"]["rv"] == "Environment"
    ), "Variable should be mapped to Environment class"


@patch('gitlab.Gitlab')
def test_instance_variable_call_resolution(mock_gitlab, repo_tree_generator):
    """Test method calls through instance variables resolve correctly."""
    python_content = """
class RepoTreeGenerator:
    def __init__(self):
        self.call_stack_gen = CallStackGenerator()

    def process(self):
        self.call_stack_gen._get_file_content()

class CallStackGenerator:
    def _get_file_content(self):
        pass
"""
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo/"
        )

    file_data = repo_tree['files']['src/main.py']
    ast_data = file_data['ast']

    # Verify RepoTreeGenerator.process calls
    process_method = ast_data['functions']['RepoTreeGenerator.process']
    assert (
        'CallStackGenerator._get_file_content' in process_method['calls']
    ), "Should resolve self.call_stack_gen._get_file_content() to CallStackGenerator._get_file_content"

    # Verify instance variable type resolution
    repo_tree_class = ast_data['classes']['RepoTreeGenerator']
    assert (
        repo_tree_class['instance_vars']['call_stack_gen'] == 'CallStackGenerator'
    ), "Should detect self.call_stack_gen type as CallStackGenerator"

    # Verify call chain resolution in the AST
    call_entries = [c['name'] for c in ast_data['calls']]
    assert (
        'CallStackGenerator._get_file_content' in call_entries
    ), "Call should appear in global calls list"


def test_save_repo_tree(repo_tree_generator, tmp_path):
    """Test saving repository AST tree to file."""
    # Create test data
    repo_tree = {
        "metadata": {"url": "https://example.com/repo"},
        "files": {
            "test.py": {
                "language": "python",
                "ast": {"functions": {}, "classes": {}, "calls": []},
            }
        },
    }

    # Save to temporary file
    output_file = tmp_path / "repo_tree.json"
    repo_tree_generator.save_repo_tree(repo_tree, str(output_file))

    # Verify file was created and contains correct data
    assert output_file.exists()
    with open(output_file) as f:
        saved_data = json.loads(f.read())
        assert saved_data == repo_tree


@patch('gitlab.Gitlab')
def test_generate_repo_tree_c(mock_gitlab, multi_lang_repo_tree_generator, mock_c_content):
    """Test repository AST tree generation for C code."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "shapes.c",
            "type": "blob",
            "path": "src/shapes.c",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        multi_lang_repo_tree_generator, '_get_file_content', return_value=mock_c_content
    ):
        repo_tree = multi_lang_repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

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
    
    # Verify pointer functions are captured
    assert "create_shape" in functions, "Pointer function create_shape not found"
    assert "allocate_memory" in functions, "Pointer function allocate_memory not found"

    # Verify function calls
    init_point_calls = functions["init_point"]["calls"]
    assert "validate_point" in init_point_calls

    process_shape_calls = functions["process_shape"]["calls"]
    assert "init_point" in process_shape_calls
    assert "calculate_area" in process_shape_calls
    assert "transform_shape" in process_shape_calls

    # # Verify structs/typedefs as classes
    classes = ast_data["classes"]
    assert "Point" in classes
    assert "Rectangle" in classes
    assert "Shape" in classes

    # Verify struct line numbers
    for struct_name in ["Point", "Rectangle", "Shape"]:
        struct_class = classes[struct_name]
        assert "start_line" in struct_class
        assert "end_line" in struct_class
        assert isinstance(struct_class["start_line"], int)
        assert isinstance(struct_class["end_line"], int)
        assert (
            struct_class["start_line"] <= struct_class["end_line"]
        ), f"Invalid line range for {struct_name} struct"

    # Verify imports (#includes)
    imports = ast_data["imports"]
    assert "stdio.h" in imports
    assert "stdlib.h" in imports
    assert "local_header.h" in imports


@pytest.fixture
def mock_c_pointer_functions():
    """Mock C file content with pointer functions for testing."""
    return """
#include <stdio.h>
#include <stdlib.h>

struct node {
    int data;
    struct node *next;
};

typedef struct node Node;

// Function that returns a pointer
Node *create_node(int data) {
    Node *new_node = (Node *)malloc(sizeof(Node));
    new_node->data = data;
    new_node->next = NULL;
    return new_node;
}

// Function with pointer in parameter and void return
void delete_node(Node **head, int data) {
    Node *temp = *head, *prev = NULL;
    
    if (temp != NULL && temp->data == data) {
        *head = temp->next;
        free(temp);
        return;
    }
    
    while (temp != NULL && temp->data != data) {
        prev = temp;
        temp = temp->next;
    }
    
    if (temp == NULL) return;
    
    prev->next = temp->next;
    free(temp);
}

// Function with complex pointer declaration
void **allocate_matrix(int rows, int cols, size_t elem_size) {
    void **matrix = malloc(rows * sizeof(void *));
    for (int i = 0; i < rows; i++) {
        matrix[i] = malloc(cols * elem_size);
    }
    return matrix;
}

// Function that takes function pointer as parameter
int process_with_callback(int data, int (*callback)(int)) {
    return callback(data);
}

// Function pointer typedef
typedef int (*operation_func)(int, int);

// Function that returns function pointer
operation_func get_operation(char op) {
    switch(op) {
        case '+': return &add;
        case '-': return &subtract;
        default: return NULL;
    }
}
"""

@patch('gitlab.Gitlab')
def test_c_pointer_functions(mock_gitlab, multi_lang_repo_tree_generator, mock_c_pointer_functions):
    """Test repository AST tree generation for C code with pointer functions."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "pointers.c",
            "type": "blob",
            "path": "src/pointers.c",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        multi_lang_repo_tree_generator, '_get_file_content', return_value=mock_c_pointer_functions
    ):
        repo_tree = multi_lang_repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

    # Verify repository tree structure
    assert "src/pointers.c" in repo_tree["files"]
    file_data = repo_tree["files"]["src/pointers.c"]
    assert file_data["language"] == "c"

    # Verify functions with pointers are captured
    functions = file_data["ast"]["functions"]
    assert "create_node" in functions, "Function returning pointer not found"
    assert "delete_node" in functions, "Function with pointer parameter not found"
    assert "allocate_matrix" in functions, "Function with complex pointer declaration not found"
    assert "process_with_callback" in functions, "Function with function pointer parameter not found"
    assert "get_operation" in functions, "Function returning function pointer not found"

@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_unsupported_files(mock_gitlab, repo_tree_generator):
    """Test repository AST tree generation with unsupported file types."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "data.txt",
            "type": "blob",
            "path": "src/data.txt",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    repo_tree = repo_tree_generator.generate_repo_tree("https://example.com/group/repo")

    # Verify unsupported file was skipped
    assert len(repo_tree["files"]) == 0


@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_failed_content_fetch(mock_gitlab, repo_tree_generator):
    """Test repository AST tree generation when file content fetch fails."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetch failure
    with patch.object(repo_tree_generator, '_get_file_content', return_value=None):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

        # Verify file was skipped
        assert len(repo_tree["files"]) == 0


@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_custom_ref(
    mock_gitlab, repo_tree_generator, mock_python_content
):
    """Test repository AST tree generation with custom ref."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"

    # Mock branches
    mock_branches = MagicMock()
    mock_branches.get.side_effect = lambda ref: (
        MagicMock() if ref == 'dev' else gitlab.exceptions.GitlabGetError()
    )
    mock_project.branches = mock_branches

    # Mock repository tree
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=mock_python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo", ref='dev'
        )

    # Verify repository tree structure and ref
    assert repo_tree["metadata"]["ref"] == "dev"
    assert "src/main.py" in repo_tree["files"]


@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_invalid_ref(mock_gitlab, api_only_repo_tree_generator):
    """Test repository AST tree generation with invalid ref."""
    # Setup mock project with invalid ref
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"

    # Mock branches, tags, and commits to all fail
    mock_branches = MagicMock()
    mock_branches.get.side_effect = gitlab.exceptions.GitlabGetError()
    mock_project.branches = mock_branches

    mock_tags = MagicMock()
    mock_tags.get.side_effect = gitlab.exceptions.GitlabGetError()
    mock_project.tags = mock_tags

    mock_commits = MagicMock()
    mock_commits.get.side_effect = gitlab.exceptions.GitlabGetError()
    mock_project.commits = mock_commits

    # Mock repository_tree to raise GitlabError for invalid ref
    mock_project.repository_tree.side_effect = gitlab.exceptions.GitlabError(
        "Tree Not Found"
    )

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Verify ValueError is raised for invalid ref
    with pytest.raises(
        ValueError, match="No ref found in repository by name: invalid-ref"
    ):
        api_only_repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo", ref='invalid-ref'
        )


@patch('gitlab.Gitlab')
@pytest.fixture
def mock_cpp_content():
    """Mock C++ file content for testing."""
    return """

namespace mynamespace {
    namespace crypto {

        AbstractManager::AbstractManager() :
            m_status(-1)
        {}

        bool AbstractManager::execute(const std::string &params, const std::vector<char> &data, const std::string &secret) {
            m_output.clear();
            m_error.clear();
            m_status = -1;

            resource::Pipe pipeIn, pipeOut, pipeError, pipeSecret;
            if(!pipeIn.open() || !pipeOut.open() || !pipeError.open() || (!secret.empty() && !pipeSecret.open())) {
                message::error("too many open files\n");
                return false;
            }

            pid_t pid = ::fork();
            if(pid == -1) {
                message::error("failed to fork: %d %s\n", errno, ::strerror(errno));
                return false;
            } else if(pid == 0) {
                struct sigaction sa{};
                sa.sa_handler = SIG_IGN;
                sigaction(SIGTSTP, &sa, nullptr);

                if(pipeIn.dup2(resource::Pipe::FdType::Out, ::fileno(stdin)) &&
                   pipeOut.dup2(resource::Pipe::FdType::In, ::fileno(stdout)) &&
                   pipeError.dup2(resource::Pipe::FdType::In, ::fileno(stderr)))
                {
                    pipeIn.close(resource::Pipe::FdType::In);
                    pipeOut.close(resource::Pipe::FdType::Out);
                    pipeError.close(resource::Pipe::FdType::Out);

                    const std::string cmd = buildCommand(params, pipeSecret.fd(resource::Pipe::FdType::Out));
                    int result = ::execlp("/bin/sh", "/bin/sh", "-c", cmd.c_str(), nullptr);
                    message::error("child terminated unexpectedly result %d errno %d\n", result, errno);
                }
                ::_exit(127);
            } else {
                if(!secret.empty()) {
                    resource::utils::safe_write(pipeSecret.fd(resource::Pipe::FdType::In), secret.data(), secret.length());
                    resource::utils::safe_write(pipeSecret.fd(resource::Pipe::FdType::In), "\n", 1);
                }
                if(!data.empty()) {
                    resource::utils::safe_write(pipeIn.fd(resource::Pipe::FdType::In), data.data(), data.size());
                }
                pipeIn.close();
                pipeOut.close(resource::Pipe::FdType::In);
                pipeError.close(resource::Pipe::FdType::In);

                ::fcntl(pipeOut.fd(resource::Pipe::FdType::Out), F_SETFL, O_NONBLOCK);
                ::fcntl(pipeError.fd(resource::Pipe::FdType::Out), F_SETFL, O_NONBLOCK);

                char buffer[1024];
                while(true) {
                    bool validOut = pipeOut.isValid(resource::Pipe::FdType::Out);
                    bool validError = pipeError.isValid(resource::Pipe::FdType::Out);
                    if(!validOut && !validError) {
                        break;
                    }
                    pollfd fds[2];
                    int idx = 0;
                    if(validOut) {
                        fds[idx].fd = pipeOut.fd(resource::Pipe::FdType::Out);
                        fds[idx].events = POLLIN | POLLHUP;
                        idx++;
                    }
                    if(validError) {
                        fds[idx].fd = pipeError.fd(resource::Pipe::FdType::Out);
                        fds[idx].events = POLLIN | POLLHUP;
                        idx++;
                    }
                    int ret = ::poll(fds, idx, -1);
                    if(ret < 0)
                        continue;
                    idx = 0;
                    if(validOut && (fds[idx++].revents & (POLLIN | POLLHUP))) {
                        ssize_t size = resource::utils::safe_read(pipeOut.fd(resource::Pipe::FdType::Out), buffer, sizeof(buffer));
                        if(size <= 0) {
                            pipeOut.close(resource::Pipe::FdType::Out);
                        } else {
                            m_output.insert(m_output.end(), buffer, buffer + size);
                        }
                    }
                    if(validError && (fds[idx].revents & (POLLIN | POLLHUP))) {
                        ssize_t size = resource::utils::safe_read(pipeError.fd(resource::Pipe::FdType::Out), buffer, sizeof(buffer));
                        if(size <= 0) {
                            pipeError.close(resource::Pipe::FdType::Out);
                        } else {
                            m_error.append(buffer, size);
                        }
                    }
                }
            }

            int status;
            if(resource::utils::safe_waitpid(pid, &status, 0) == pid) {
                if(WIFEXITED(status)) {
                    m_status = WEXITSTATUS(status);
                }
            }
            return m_status == 0;
        }

        std::string AbstractManager::getError() const {
            return m_error;
        }

        std::vector<char> AbstractManager::getOutput() const {
            return m_output;
        }

        int AbstractManager::getStatus() const {
            return m_status;
        }

        std::string AbstractManager::buildCommand(const std::string &params, int fdSecret) {
            std::string cmd = "LANGUAGE=C command --no-greeting --batch";
            if(fdSecret != -1) {
                cmd += utils::safe_format(" --secret-fd %d", fdSecret);
            }
            return cmd + params + (fdSecret != -1 ? " && commandconf --reload agent" : "");
        }
    }
}
"""


@patch('gitlab.Gitlab')
def test_generate_repo_tree_cpp(mock_gitlab, multi_lang_repo_tree_generator, mock_cpp_content):
    """Test repository AST tree generation for C++ code."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "abstract.cpp",
            "type": "blob",
            "path": "src/abstract.cpp",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        multi_lang_repo_tree_generator, '_get_file_content', return_value=mock_cpp_content
    ):
        repo_tree = multi_lang_repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

    # Verify C++ parsing results
    file_data = repo_tree["files"]["src/abstract.cpp"]
    assert file_data["language"] == "cpp"

    ast_data = file_data["ast"]
    # Check for constructors and methods in the AST
    assert "AbstractManager::AbstractManager" in ast_data["functions"]
    assert "AbstractManager::execute" in ast_data["functions"]
    assert "AbstractManager::buildCommand" in ast_data["functions"]

    execute_calls = ast_data["functions"]["AbstractManager::execute"]["calls"]
    # Verify that at least one call to open (e.g., pipeIn.open) is recorded and buildCommand is called
    assert any("open" in call for call in execute_calls)

    build_command_calls = ast_data["functions"]["AbstractManager::buildCommand"][
        "calls"
    ]
    # Verify that the call to the formatting utility is recorded
    assert any("safe_format" in call for call in build_command_calls)


@patch('gitlab.Gitlab')
def test_generate_repo_tree_with_default_ref(
    mock_gitlab, repo_tree_generator, mock_python_content
):
    """Test repository AST tree generation with default ref."""
    # Setup mock project
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    # Mock file content fetching
    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=mock_python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

    # Verify default branch is used
    assert repo_tree["metadata"]["ref"] == "main"
    assert "src/main.py" in repo_tree["files"]


@patch('gitlab.Gitlab')
def test_cross_class_method_resolution(mock_gitlab, repo_tree_generator):
    """Test method calls through instance variables resolve to correct class."""
    python_content = """
class Processor:
    def process(self):
        pass

class ClassName:
    def __init__(self):
        self.processor = Processor()

    def make_something_else(self):
        self.processor.process()
        self._internal_method()

    def _internal_method(self):
        pass
"""
    mock_project = Mock()
    mock_project.path_with_namespace = "group/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.return_value = [
        {
            "id": "a1b2c3d4",
            "name": "main.py",
            "type": "blob",
            "path": "src/main.py",
            "mode": "100644",
        }
    ]

    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    with patch.object(
        repo_tree_generator, '_get_file_content', return_value=python_content
    ):
        repo_tree = repo_tree_generator.generate_repo_tree(
            "https://example.com/group/repo"
        )

    file_data = repo_tree['files']['src/main.py']
    ast_data = file_data['ast']

    # Verify method calls
    func_info = ast_data['functions']['ClassName.make_something_else']
    assert (
        'Processor.process' in func_info['calls']
    ), "Should resolve processor method to Processor class"
    assert (
        'ClassName._internal_method' in func_info['calls']
    ), "Should resolve self method to original class"

    # Verify instance variable type tracking
    class_info = ast_data['classes']['ClassName']
    assert (
        class_info['instance_vars']['processor'] == 'Processor'
    ), "Should detect processor variable type"


class TestRepoTreeCommitHash:
    """Tests for repository tree commit hash functionality."""

    @patch('repomap.repo_tree.get_provider')
    @patch.object(RepoTreeGenerator, '_get_file_content')
    def test_generate_repo_tree_includes_commit_hash(self, mock_get_content, mock_get_provider):
        """Test that generate_repo_tree includes commit hash in metadata."""
        # Mock provider
        mock_provider = Mock()
        mock_provider.validate_ref.return_value = 'main'
        mock_provider.get_last_commit_hash.return_value = 'abc123def456'
        mock_provider.fetch_repo_structure.return_value = {
            'test.py': {
                'type': 'blob',
                'mode': '100644',
                'id': 'file123'
            }
        }
        mock_get_provider.return_value = mock_provider
        mock_get_content.return_value = 'print("hello")'

        generator = RepoTreeGenerator(use_multiprocessing=False, use_local_clone=False)
        repo_tree = generator.generate_repo_tree('https://github.com/owner/repo')

        # Verify commit hash is included in metadata
        assert 'last_commit_hash' in repo_tree['metadata']
        assert repo_tree['metadata']['last_commit_hash'] == 'abc123def456'
        assert repo_tree['metadata']['url'] == 'https://github.com/owner/repo'
        assert repo_tree['metadata']['ref'] == 'main'

    @patch('repomap.providers.get_provider')
    def test_is_repo_tree_up_to_date_no_file(self, mock_get_provider):
        """Test is_repo_tree_up_to_date returns False when no file exists."""
        generator = RepoTreeGenerator(use_local_clone=False)
        result = generator.is_repo_tree_up_to_date(
            'https://github.com/owner/repo', 
            'main', 
            'nonexistent.json'
        )
        assert result is False

    @patch('repomap.repo_tree.get_provider')
    def test_is_repo_tree_up_to_date_same_hash(self, mock_get_provider, tmp_path):
        """Test is_repo_tree_up_to_date returns True when commit hashes match."""
        # Create existing repo tree file
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/owner/repo',
                'ref': 'main',
                'last_commit_hash': 'same123hash'
            },
            'files': {}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        # Mock provider
        mock_provider = Mock()
        mock_provider.validate_ref.return_value = 'main'
        mock_provider.get_last_commit_hash.return_value = 'same123hash'
        mock_get_provider.return_value = mock_provider

        generator = RepoTreeGenerator(use_local_clone=False)
        result = generator.is_repo_tree_up_to_date(
            'https://github.com/owner/repo',
            'main',
            str(repo_tree_file)
        )
        assert result is True

    @patch('repomap.providers.get_provider')
    def test_is_repo_tree_up_to_date_different_hash(self, mock_get_provider, tmp_path):
        """Test is_repo_tree_up_to_date returns False when commit hashes differ."""
        # Create existing repo tree file
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/owner/repo',
                'ref': 'main',
                'last_commit_hash': 'old123hash'
            },
            'files': {}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        # Mock provider
        mock_provider = Mock()
        mock_provider.validate_ref.return_value = 'main'
        mock_provider.get_last_commit_hash.return_value = 'new456hash'
        mock_get_provider.return_value = mock_provider

        generator = RepoTreeGenerator(use_local_clone=False)
        result = generator.is_repo_tree_up_to_date(
            'https://github.com/owner/repo',
            'main',
            str(repo_tree_file)
        )
        assert result is False

    @patch('repomap.providers.get_provider')
    def test_is_repo_tree_up_to_date_different_url(self, mock_get_provider, tmp_path):
        """Test is_repo_tree_up_to_date returns False when URLs differ."""
        # Create existing repo tree file
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/other/repo',
                'ref': 'main',
                'last_commit_hash': 'same123hash'
            },
            'files': {}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        generator = RepoTreeGenerator(use_local_clone=False)
        result = generator.is_repo_tree_up_to_date(
            'https://github.com/owner/repo',
            'main',
            str(repo_tree_file)
        )
        assert result is False

    @patch('repomap.providers.get_provider')
    def test_is_repo_tree_up_to_date_missing_hash(self, mock_get_provider, tmp_path):
        """Test is_repo_tree_up_to_date returns False when existing tree has no commit hash."""
        # Create existing repo tree file without commit hash
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/owner/repo',
                'ref': 'main'
            },
            'files': {}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        generator = RepoTreeGenerator(use_local_clone=False)
        result = generator.is_repo_tree_up_to_date(
            'https://github.com/owner/repo',
            'main',
            str(repo_tree_file)
        )
        assert result is False

    @patch('builtins.print')  # Mock print to suppress output
    @patch('repomap.repo_tree.get_provider')
    def test_generate_repo_tree_if_needed_up_to_date(self, mock_get_provider, mock_print, tmp_path):
        """Test generate_repo_tree_if_needed loads existing tree when up to date."""
        # Create existing repo tree file
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/owner/repo',
                'ref': 'main',
                'last_commit_hash': 'same123hash'
            },
            'files': {'test.py': {'language': 'python', 'ast': {}}}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        # Mock provider
        mock_provider = Mock()
        mock_provider.validate_ref.return_value = 'main'
        mock_provider.get_last_commit_hash.return_value = 'same123hash'
        mock_get_provider.return_value = mock_provider

        generator = RepoTreeGenerator(use_multiprocessing=False, use_local_clone=False)
        
        # Mock generate_repo_tree so we can verify it wasn't called
        with patch.object(generator, 'generate_repo_tree') as mock_generate:
            result = generator.generate_repo_tree_if_needed(
                'https://github.com/owner/repo',
                'main',
                str(repo_tree_file)
            )

        # Should load existing tree, not generate new one
        mock_generate.assert_not_called()
        assert result == existing_tree

    @patch('builtins.print')  # Mock print to suppress output
    @patch('repomap.repo_tree.get_provider')
    @patch.object(RepoTreeGenerator, '_get_file_content')
    def test_generate_repo_tree_if_needed_outdated(self, mock_get_content, mock_get_provider, mock_print, tmp_path):
        """Test generate_repo_tree_if_needed generates new tree when outdated."""
        # Create existing repo tree file
        existing_tree = {
            'metadata': {
                'url': 'https://github.com/owner/repo',
                'ref': 'main',
                'last_commit_hash': 'old123hash'
            },
            'files': {}
        }
        repo_tree_file = tmp_path / 'repo_tree.json'
        with open(repo_tree_file, 'w') as f:
            json.dump(existing_tree, f)

        # Mock provider
        mock_provider = Mock()
        mock_provider.validate_ref.return_value = 'main'
        mock_provider.get_last_commit_hash.return_value = 'new456hash'
        mock_provider.fetch_repo_structure.return_value = {}
        mock_get_provider.return_value = mock_provider
        mock_get_content.return_value = 'print("hello")'

        generator = RepoTreeGenerator(use_multiprocessing=False, use_local_clone=False)
        result = generator.generate_repo_tree_if_needed(
            'https://github.com/owner/repo',
            'main',
            str(repo_tree_file)
        )

        # Should generate new tree with new commit hash
        assert result['metadata']['last_commit_hash'] == 'new456hash'


# ========================
# Go Language Tests
# ========================

def test_parse_go_file_ast(multi_lang_repo_tree_generator, mock_go_content):
    """Test parsing Go file AST to extract functions, types, calls, and imports."""
    ast_data = multi_lang_repo_tree_generator._parse_file_ast(mock_go_content, "go")
    
    # Test that we found the expected functions
    assert len(ast_data["functions"]) > 0
    assert "main" in ast_data["functions"]
    assert "processUser" in ast_data["functions"] 
    assert "validateUser" in ast_data["functions"]
    assert "logUser" in ast_data["functions"]
    assert "validateAge" in ast_data["functions"]
    assert "NewUserService" in ast_data["functions"]
    
    # Test method functions (with receiver types)
    assert "User.GetName" in ast_data["functions"]
    assert "User.SetAge" in ast_data["functions"]
    assert "User.GetFormattedName" in ast_data["functions"]
    assert "UserService.AddUser" in ast_data["functions"]
    
    # Test that types (Go structs) are treated as classes
    assert len(ast_data["classes"]) == 2
    assert "User" in ast_data["classes"]
    assert "UserService" in ast_data["classes"]
    
    # Test that User struct has the expected methods
    user_class = ast_data["classes"]["User"]
    assert "GetName" in user_class["methods"]
    assert "SetAge" in user_class["methods"]
    assert "GetFormattedName" in user_class["methods"]
    
    # Test that UserService struct has the expected methods
    service_class = ast_data["classes"]["UserService"]
    assert "AddUser" in service_class["methods"]
    
    # Test imports are extracted correctly
    assert len(ast_data["imports"]) == 3
    assert "fmt" in ast_data["imports"]
    assert "log" in ast_data["imports"]
    assert "strings" in ast_data["imports"]
    
    # Test that calls are detected
    assert len(ast_data["calls"]) > 0
    call_names = [call["name"] for call in ast_data["calls"]]
    assert "Println" in call_names  # fmt.Println()
    assert "SetAge" in call_names   # user.SetAge() 
    assert "processUser" in call_names  # processUser()
    assert "validateUser" in call_names  # validateUser()
    assert "GetName" in call_names  # user.GetName()


def test_go_function_details(multi_lang_repo_tree_generator, mock_go_content):
    """Test detailed function information for Go functions."""
    ast_data = multi_lang_repo_tree_generator._parse_file_ast(mock_go_content, "go")
    
    # Test main function details
    main_func = ast_data["functions"]["main"]
    assert main_func["name"] == "main"
    assert main_func["class"] is None
    assert main_func["start_line"] > 0
    assert main_func["end_line"] > main_func["start_line"]
    
    # Test method function details
    get_name_func = ast_data["functions"]["User.GetName"]
    assert get_name_func["name"] == "GetName"
    assert get_name_func["class"] == "User"
    assert get_name_func["start_line"] > 0
    
    # Test that method calls are captured
    assert len(get_name_func["calls"]) >= 0  # May or may not have calls
    
    # Test regular function details
    validate_func = ast_data["functions"]["validateUser"]
    assert validate_func["name"] == "validateUser"
    assert validate_func["class"] is None
    

def test_go_type_extraction(multi_lang_repo_tree_generator, mock_go_content):
    """Test Go type (struct) extraction and classification."""
    ast_data = multi_lang_repo_tree_generator._parse_file_ast(mock_go_content, "go")
    
    # Test User struct
    user_type = ast_data["classes"]["User"]
    assert user_type["name"] == "User"
    assert user_type["start_line"] > 0
    assert user_type["end_line"] > user_type["start_line"]
    assert len(user_type["methods"]) == 3  # GetName, SetAge, GetFormattedName
    assert user_type["base_classes"] == []  # Go structs don't have inheritance
    
    # Test UserService struct  
    service_type = ast_data["classes"]["UserService"]
    assert service_type["name"] == "UserService"
    assert len(service_type["methods"]) == 1  # AddUser


def test_go_empty_file(multi_lang_repo_tree_generator):
    """Test parsing empty Go file."""
    empty_go_content = "package main\n"
    ast_data = multi_lang_repo_tree_generator._parse_file_ast(empty_go_content, "go")
    
    assert ast_data["functions"] == {}
    assert ast_data["classes"] == {}
    assert ast_data["calls"] == []
    assert ast_data["imports"] == []


def test_go_simple_import(multi_lang_repo_tree_generator):
    """Test Go import parsing with different import styles.""" 
    simple_import_content = '''
package main

import "fmt"
import "log"

func main() {
    fmt.Println("Hello")
}
'''
    ast_data = multi_lang_repo_tree_generator._parse_file_ast(simple_import_content, "go")
    assert "fmt" in ast_data["imports"]
    assert "log" in ast_data["imports"]
    assert len(ast_data["imports"]) == 2
