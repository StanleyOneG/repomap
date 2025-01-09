"""Tests for core functionality."""

import pytest
import unittest
from unittest.mock import Mock, patch
import requests

from repomap.core import GitLabFetcher, fetch_repo_structure

def test_gitlab_fetcher_init():
    """Test GitLabFetcher initialization."""
    # Test with default values
    fetcher = GitLabFetcher()
    assert fetcher.base_url == "https://git-testing.devsec.astralinux.ru"
    assert fetcher.token is None
    
    # Test with custom values
    fetcher = GitLabFetcher("https://custom.gitlab.com", "test-token")
    assert fetcher.base_url == "https://custom.gitlab.com"
    assert fetcher.token == "test-token"
    
    # Test URL normalization
    fetcher = GitLabFetcher("https://custom.gitlab.com/")
    assert fetcher.base_url == "https://custom.gitlab.com"

def test_get_project_id():
    """Test project ID extraction from URL."""
    fetcher = GitLabFetcher()
    
    # Test valid URLs
    assert fetcher._get_project_id("https://git-testing.devsec.astralinux.ru/user/repo") == "user/repo"
    assert fetcher._get_project_id("https://git-testing.devsec.astralinux.ru/group/subgroup/repo") == "group/subgroup/repo"
    
    # Test invalid URLs
    with pytest.raises(ValueError):
        fetcher._get_project_id("https://git-testing.devsec.astralinux.ru")
    with pytest.raises(ValueError):
        fetcher._get_project_id("invalid-url")

@patch('requests.Session')
def test_fetch_repo_structure(mock_session):
    """Test repository structure fetching."""
    # Mock response data
    # Create two different responses for pagination
    first_response = Mock()
    first_response.json.return_value = [
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
    ]
    first_response.raise_for_status = Mock()
    
    empty_response = Mock()
    empty_response.json.return_value = []  # Second page returns empty list to end pagination
    empty_response.raise_for_status = Mock()
    
    # Setup mock session to return different responses for each call
    mock_session_instance = Mock()
    mock_session_instance.get.side_effect = [first_response, empty_response]
    mock_session.return_value = mock_session_instance
    
    # Test successful fetch
    fetcher = GitLabFetcher(token="test-token")
    result = fetcher.fetch_repo_structure("https://git-testing.devsec.astralinux.ru/user/repo")
    
    assert isinstance(result, dict)
    assert "src" in result
    assert "file.py" in result["src"]
    assert "README.md" in result
    
    # Verify API calls
    expected_calls = [
        unittest.mock.call(
            "https://git-testing.devsec.astralinux.ru/api/v4/projects/user%2Frepo/repository/tree",
            params={'ref': 'main', 'recursive': True, 'per_page': 100, 'page': 1}
        ),
        unittest.mock.call(
            "https://git-testing.devsec.astralinux.ru/api/v4/projects/user%2Frepo/repository/tree",
            params={'ref': 'main', 'recursive': True, 'per_page': 100, 'page': 2}
        )
    ]
    mock_session_instance.get.assert_has_calls(expected_calls)

@patch('requests.Session')
def test_fetch_repo_structure_error_handling(mock_session):
    """Test error handling in fetch_repo_structure."""
    # Mock network error
    mock_session_instance = Mock()
    mock_session_instance.get.side_effect = requests.exceptions.RequestException("Network error")
    mock_session.return_value = mock_session_instance
    
    fetcher = GitLabFetcher()
    
    with pytest.raises(requests.exceptions.RequestException):
        fetcher.fetch_repo_structure("https://git-testing.devsec.astralinux.ru/user/repo")

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
