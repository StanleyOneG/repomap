"""Tests for repository providers."""

from unittest.mock import MagicMock, patch

import gitlab
import pytest

from repomap.providers import GitHubProvider, GitLabProvider, get_provider


def test_get_provider_github():
    """Test get_provider returns GitHubProvider for GitHub URLs."""
    provider = get_provider('https://github.com/owner/repo')
    assert isinstance(provider, GitHubProvider)


def test_get_provider_gitlab():
    """Test get_provider returns GitLabProvider for GitLab URLs."""
    provider = get_provider('https://gitlab.com/owner/repo')
    assert isinstance(provider, GitLabProvider)


@pytest.fixture
def mock_github():
    """Fixture for mocked GitHub client."""
    with patch('repomap.providers.Github') as mock:
        mock_repo = MagicMock()
        mock_repo.default_branch = 'main'
        file_mock = MagicMock()
        file_mock.type = 'file'
        file_mock.name = 'file1.py'
        file_mock.path = 'file1.py'
        file_mock.sha = 'abc123'

        dir_mock = MagicMock()
        dir_mock.type = 'dir'
        dir_mock.name = 'dir1'
        dir_mock.path = 'dir1'

        mock_repo.get_contents.return_value = [file_mock, dir_mock]
        mock_repo.get_branch.return_value = MagicMock()
        mock_repo.get_tag.return_value = MagicMock()
        mock_repo.get_commit.return_value = MagicMock()

        mock_instance = mock.return_value
        mock_instance.get_repo.return_value = mock_repo
        yield mock_instance


def test_github_provider_fetch_structure(mock_github):
    """Test GitHub provider fetch_repo_structure method."""
    provider = GitHubProvider()
    structure = provider.fetch_repo_structure('https://github.com/owner/repo')

    assert isinstance(structure, dict)
    assert 'file1.py' in structure
    assert structure['file1.py']['type'] == 'blob'
    assert 'dir1' in structure


def test_github_provider_validate_ref_branch(mock_github):
    """Test GitHub provider validate_ref with branch."""
    provider = GitHubProvider()
    ref = provider.validate_ref('https://github.com/owner/repo', 'develop')
    assert ref == 'develop'


def test_github_provider_validate_ref_invalid(mock_github):
    """Test GitHub provider validate_ref with invalid ref."""
    mock_github.get_repo.return_value.get_branch.side_effect = Exception()
    mock_github.get_repo.return_value.get_tag.side_effect = Exception()
    mock_github.get_repo.return_value.get_commit.side_effect = Exception()

    provider = GitHubProvider()
    with pytest.raises(ValueError, match="No ref found in repository by name"):
        provider.validate_ref('https://github.com/owner/repo', 'nonexistent')


def test_github_provider_get_file_content(mock_github):
    """Test GitHub provider get_file_content method."""
    mock_content = MagicMock()
    mock_content.decoded_content = b'file content'
    mock_github.get_repo.return_value.get_contents.return_value = mock_content

    provider = GitHubProvider()
    content = provider.get_file_content(
        'https://github.com/owner/repo/blob/main/file.py'
    )
    assert content == 'file content'


@pytest.fixture
def mock_gitlab():
    """Fixture for mocked GitLab client."""
    with patch('repomap.providers.gitlab.Gitlab') as mock:
        mock_project = MagicMock()
        mock_project.default_branch = 'main'
        mock_project.repository_tree.return_value = [
            {
                'type': 'blob',
                'path': 'file1.py',
                'mode': '100644',
                'id': 'abc123',
            },
            {
                'type': 'tree',
                'path': 'dir1',
                'mode': '040000',
                'id': 'def456',
            },
        ]
        mock_project.branches.get.return_value = MagicMock()
        mock_project.tags.get.return_value = MagicMock()
        mock_project.commits.get.return_value = MagicMock()

        mock_instance = mock.return_value
        mock_instance.projects.get.return_value = mock_project
        yield mock_instance


def test_gitlab_provider_fetch_structure(mock_gitlab):
    """Test GitLab provider fetch_repo_structure method."""
    provider = GitLabProvider()
    structure = provider.fetch_repo_structure('https://gitlab.com/owner/repo')

    assert isinstance(structure, dict)
    assert 'file1.py' in structure
    assert structure['file1.py']['type'] == 'blob'
    assert 'dir1' in structure


def test_gitlab_provider_validate_ref_branch(mock_gitlab):
    """Test GitLab provider validate_ref with branch."""
    provider = GitLabProvider()
    ref = provider.validate_ref('https://gitlab.com/owner/repo', 'develop')
    assert ref == 'develop'


def test_gitlab_provider_validate_ref_invalid(mock_gitlab):
    """Test GitLab provider validate_ref with invalid ref."""
    mock_gitlab.projects.get.return_value.branches.get.side_effect = (
        gitlab.exceptions.GitlabGetError('', '', '')
    )
    mock_gitlab.projects.get.return_value.tags.get.side_effect = (
        gitlab.exceptions.GitlabGetError('', '', '')
    )
    mock_gitlab.projects.get.return_value.commits.get.side_effect = (
        gitlab.exceptions.GitlabGetError('', '', '')
    )

    provider = GitLabProvider()
    with pytest.raises(ValueError, match="No ref found in repository by name"):
        provider.validate_ref('https://gitlab.com/owner/repo', 'nonexistent')


def test_gitlab_provider_get_file_content(mock_gitlab):
    """Test GitLab provider get_file_content method."""
    mock_file = MagicMock()
    mock_file.decode.return_value.decode.return_value = 'file content'
    mock_gitlab.projects.get.return_value.files.get.return_value = mock_file

    provider = GitLabProvider()
    content = provider.get_file_content(
        'https://gitlab.com/owner/repo/-/blob/main/file.py'
    )
    assert content == 'file content'
