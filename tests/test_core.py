"""Tests for core functionality."""

import pytest
import unittest
from unittest.mock import Mock, patch
import gitlab

from repomap.core import GitLabFetcher, fetch_repo_structure

def test_gitlab_fetcher_init():
    """Test GitLabFetcher initialization."""
    # Test with default values
    fetcher = GitLabFetcher()
    assert fetcher.base_url == "https://git-testing.devsec.astralinux.ru"
    
    # Test with custom values
    fetcher = GitLabFetcher("https://custom.gitlab.com", "test-token")
    assert fetcher.base_url == "https://custom.gitlab.com"
    assert fetcher.token == "test-token"
    
    # Test URL normalization
    fetcher = GitLabFetcher("https://custom.gitlab.com/")
    assert fetcher.base_url == "https://custom.gitlab.com"

def test_get_project_parts():
    """Test project parts extraction from URL."""
    fetcher = GitLabFetcher()
    
    # Test valid URLs
    group, project = fetcher._get_project_parts("https://git-testing.devsec.astralinux.ru/user/repo")
    assert group == "user"
    assert project == "repo"
    
    group, project = fetcher._get_project_parts("https://git-testing.devsec.astralinux.ru/group/subgroup/repo")
    assert group == "group/subgroup"
    assert project == "repo"
    
    # Test invalid URLs
    with pytest.raises(ValueError):
        fetcher._get_project_parts("https://git-testing.devsec.astralinux.ru")
    with pytest.raises(ValueError):
        fetcher._get_project_parts("invalid-url")

@patch('gitlab.Gitlab')
def test_fetch_repo_structure(mock_gitlab):
    """Test repository structure fetching."""
    # Setup mock project with path_with_namespace and default branch
    mock_project = Mock()
    mock_project.path_with_namespace = "user/repo"
    mock_project.default_branch = "main"
    mock_project.repository_tree.side_effect = [
        [
            {
                "id": "a1b2c3d4",
                "name": "file.py",
                "type": "blob",
                "path": "src/file.py",
                "mode": "100644"
            },
            {
                "id": "e5f6g7h8",
                "name": "README.md",
                "type": "blob",
                "path": "README.md",
                "mode": "100644"
            }
        ],
        []  # Second page returns empty list to end pagination
    ]
    
    # Setup mock GitLab instance
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.return_value = mock_project
    mock_gitlab.return_value = mock_gitlab_instance
    
    # Test successful fetch
    fetcher = GitLabFetcher(token="test-token")
    result = fetcher.fetch_repo_structure("https://git-testing.devsec.astralinux.ru/user/repo")
    
    assert isinstance(result, dict)
    assert "src" in result
    assert "file.py" in result["src"]
    assert "README.md" in result
    
    # Verify API calls - should try unencoded path first
    mock_gitlab_instance.projects.get.assert_called_with("user/repo")
    expected_calls = [
        unittest.mock.call(
            ref='main',
            recursive=True,
            per_page=100,
            page=1
        )
    ]
    mock_project.repository_tree.assert_has_calls(expected_calls)

@patch('gitlab.Gitlab')
def test_fetch_repo_structure_error_handling(mock_gitlab):
    """Test error handling in fetch_repo_structure."""
    # Mock GitLab error - both unencoded and encoded paths fail
    mock_gitlab_instance = Mock()
    mock_gitlab_instance.projects.get.side_effect = [
        gitlab.exceptions.GitlabGetError("Not found"),  # First try with unencoded path
        gitlab.exceptions.GitlabGetError("Not found")   # Second try with encoded path
    ]
    mock_gitlab.return_value = mock_gitlab_instance
    
    fetcher = GitLabFetcher()
    
    with pytest.raises(gitlab.exceptions.GitlabGetError) as exc_info:
        fetcher.fetch_repo_structure("https://git-testing.devsec.astralinux.ru/user/repo")
    assert "Project not found: user/repo" in str(exc_info.value)
    
    # Verify both attempts were made
    assert mock_gitlab_instance.projects.get.call_count == 2
    mock_gitlab_instance.projects.get.assert_has_calls([
        unittest.mock.call("user/repo"),           # First try with unencoded path
        unittest.mock.call("user%2Frepo")          # Second try with encoded path
    ])

def test_convenience_function():
    """Test the convenience function."""
    with patch('repomap.core.GitLabFetcher') as mock_fetcher_class:
        mock_fetcher = Mock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.fetch_repo_structure.return_value = {"test": "data"}
        
        result = fetch_repo_structure("https://git-testing.devsec.astralinux.ru/user/repo", "test-token")
        
        assert result == {"test": "data"}
        mock_fetcher_class.assert_called_with(token="test-token")
        mock_fetcher.fetch_repo_structure.assert_called_with("https://git-testing.devsec.astralinux.ru/user/repo")
