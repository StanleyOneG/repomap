"""Tests for call stack generation functionality."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from repomap.callstack import CallStackGenerator
from repomap.config import settings

# Mock settings for tests
settings.GITLAB_BASE_URL = "https://example.com"

# Sample repository structure for testing
SAMPLE_STRUCTURE = {
    "metadata": {"url": "https://example.com/repo", "version": "0.1.0"},
    "structure": {"src": {"main.py": {"type": "blob", "path": "src/main.py"}}},
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

# Sample C file content for testing
SAMPLE_C_CONTENT = '''
static int try_open(snd_mixer_class_t *class, const char *lib)
{
    class_priv_t *priv = snd_mixer_class_get_private(class);
    snd_mixer_event_t event_func;
    snd_mixer_sbasic_init_t init_func = NULL;
    char *xlib, *path, errbuf[256];
    void *h;
    int err = 0;

    if (!lib)
        return -ENXIO;
    path = getenv("ALSA_MIXER_SIMPLE_MODULES");
    if (!path)
        path = SO_PATH;
    xlib = malloc(strlen(lib) + strlen(path) + 1 + 1);
    if (xlib == NULL)
        return -ENOMEM;
    strcpy(xlib, path);
    strcat(xlib, "/");
    strcat(xlib, lib);
    h = INTERNAL(snd_dlopen)(xlib, RTLD_NOW, errbuf, sizeof(errbuf));
    if (h == NULL) {
        SNDERR("Unable to open library '%s' (%s)", xlib, errbuf);
        free(xlib);
        return -ENXIO;
    }
    priv->dlhandle = h;
    event_func = snd_dlsym(h, "alsa_mixer_simple_event", NULL);
    if (event_func == NULL) {
        SNDERR("Symbol 'alsa_mixer_simple_event' was not found in '%s'", xlib);
        err = -ENXIO;
    }
    if (err == 0) {
        init_func = snd_dlsym(h, "alsa_mixer_simple_init", NULL);
        if (init_func == NULL) {
            SNDERR("Symbol 'alsa_mixer_simple_init' was not found in '%s'", xlib);
            err = -ENXIO;
        }
    }
    free(xlib);
    err = err == 0 ? init_func(class) : err;
    if (err < 0)
        return err;
    snd_mixer_class_set_event(class, event_func);
    return 1;
}

static int match(snd_mixer_class_t *class, const char *lib, const char *searchl)
{
    class_priv_t *priv = snd_mixer_class_get_private(class);
    const char *components;

    if (searchl == NULL)
        return try_open(class, lib);
    components = snd_ctl_card_info_get_components(priv->info);
    while (*components != '\\0') {
        if (!strncmp(components, searchl, strlen(searchl)))
            return try_open(class, lib);
        while (*components != ' ' && *components != '\\0')
            components++;
        while (*components == ' ' && *components != '\\0')
            components++;
    }
    return 0;
}
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
    url = "https://example.com/group/project/-/blob/main/src/file.py"
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

    url = "https://example.com/group/project/-/blob/main/src/file.py"
    call_stack = generator.generate_call_stack(url, 7)

    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'main'
    assert call_stack[0]['file'] == url
    assert call_stack[0]['line'] == 7
    assert 'helper' in call_stack[0]['calls']


@patch('gitlab.Gitlab')
def test_generate_call_stack_c(mock_gitlab, generator):
    """Test generating call stack from C code."""
    # Setup mock GitLab instance and project
    mock_gitlab_instance = Mock()
    mock_project = Mock()
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = SAMPLE_C_CONTENT

    mock_project.files.get.return_value = mock_file
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance

    url = "https://example.com/group/project/-/blob/main/src/file.c"
    # Test line inside match function
    call_stack = generator.generate_call_stack(
        url, 57
    )  # Line with the match function definition

    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'match'
    assert call_stack[0]['file'] == url
    assert call_stack[0]['line'] == 57
    # Check for function calls inside match
    assert 'try_open' in call_stack[0]['calls']
    assert 'snd_mixer_class_get_private' in call_stack[0]['calls']
    assert 'snd_ctl_card_info_get_components' in call_stack[0]['calls']
    assert 'strncmp' in call_stack[0]['calls']
    assert 'strlen' in call_stack[0]['calls']


def test_save_call_stack(generator, tmp_path):
    """Test saving call stack to file."""
    output_file = tmp_path / "call_stack.json"
    call_stack = [
        {'function': 'main', 'file': 'test.py', 'line': 10, 'calls': ['helper']}
    ]

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
    url = "https://example.com/group/project/-/blob/main/src/file.py"
    call_stack = generator.generate_call_stack(url, 7)

    assert len(call_stack) == 1
    assert call_stack[0]['function'] == 'main'
    assert call_stack[0]['file'] == url
    assert call_stack[0]['line'] == 7
    assert 'helper' in call_stack[0]['calls']


def test_unsupported_language(generator):
    """Test handling of unsupported file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        url = "https://example.com/group/project/-/blob/main/test.unsupported"
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
        url = "https://example.com/group/project/-/blob/main/src/file.py"
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
    url = "https://example.com/group/project/-/blob/main/src/file.py"

    # Test getting main function content
    content = generator.get_function_content_by_line(url, 7)  # Line inside main()
    assert "def main():" in content
    assert "x = helper()" in content
    assert "return x" in content

    # Test getting helper function content
    content = generator.get_function_content_by_line(url, 2)  # Line inside helper()
    assert "def helper():" in content
    assert 'print("Helper function")' in content
    assert "return 42" in content

    # Test invalid line number
    with pytest.raises(ValueError, match="No function found at line"):
        generator.get_function_content_by_line(url, 10)  # Line outside any function

    # Test unsupported file type
    with pytest.raises(ValueError, match="Unsupported file type"):
        generator.get_function_content_by_line("test.unsupported", 1)


# Mock data for testing
MOCK_REPO_TREE = {
    "metadata": {"url": "https://example.com/group/repo", "ref": "main"},
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
                        "calls": [],
                    }
                }
            },
        }
    },
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
    content = mock_generator.get_function_content_by_name(
        mock_repo_tree_file, "interpret_filename"
    )
    assert "int interpret_filename(const char *filename)" in content
    assert "return err;" in content


def test_get_function_content_by_name_not_found(mock_repo_tree_file, mock_generator):
    """Test error when function name is not found."""
    with pytest.raises(
        ValueError, match="No function found with name: nonexistent_function"
    ):
        mock_generator.get_function_content_by_name(
            mock_repo_tree_file, "nonexistent_function"
        )


def test_get_function_content_by_name_invalid_tree(tmp_path):
    """Test error with invalid repo tree file."""
    # Create invalid repo tree file
    file_path = tmp_path / "invalid_tree.json"
    with open(file_path, "w") as f:
        json.dump({}, f)

    generator = CallStackGenerator()
    with pytest.raises(
        ValueError, match="Invalid repository tree file: missing metadata.url"
    ):
        generator.get_function_content_by_name(str(file_path), "any_function")
