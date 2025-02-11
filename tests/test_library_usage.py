"""Tests for library usage functionality."""

from unittest.mock import Mock, patch

from repomap import RepoTreeGenerator, fetch_repo_structure


def test_repo_tree_generator_import():
    """Test that RepoTreeGenerator can be imported and instantiated."""
    generator = RepoTreeGenerator(token="test_token")
    assert generator is not None
    assert generator.token == "test_token"


@patch('repomap.core.get_provider')
def test_fetch_repo_structure_import(mock_get_provider):
    """Test that fetch_repo_structure can be imported and called."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.fetch_repo_structure.return_value = {"test": "data"}
    mock_get_provider.return_value = mock_provider

    # Test the function
    result = fetch_repo_structure("https://github.com/user/repo", token="test_token")

    assert result == {"test": "data"}
    mock_get_provider.assert_called_once_with(
        "https://github.com/user/repo", "test_token"
    )
    mock_provider.fetch_repo_structure.assert_called_once_with(
        "https://github.com/user/repo"
    )


@patch('repomap.repo_tree.get_provider')
def test_repo_tree_generator_basic_usage(mock_get_provider):
    """Test basic usage of RepoTreeGenerator as a library."""
    # Mock the provider
    mock_provider = Mock()
    mock_provider.validate_ref.return_value = "main"
    mock_provider.fetch_repo_structure.return_value = {
        "test.py": {"type": "blob", "content": "def test(): pass"}
    }
    mock_get_provider.return_value = mock_provider

    # Create generator instance
    generator = RepoTreeGenerator(token="test_token", use_multiprocessing=False)

    # Test generate_repo_tree
    tree = generator.generate_repo_tree("https://github.com/user/repo")

    assert "metadata" in tree
    assert tree["metadata"]["url"] == "https://github.com/user/repo"
    assert tree["metadata"]["ref"] == "main"

    # Verify provider interactions
    mock_get_provider.assert_called_once_with(
        "https://github.com/user/repo", "test_token"
    )
    mock_provider.validate_ref.assert_called_once()
    mock_provider.fetch_repo_structure.assert_called_once()
