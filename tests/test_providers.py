"""Tests for repository providers."""

from unittest.mock import MagicMock, patch

import gitlab
import pytest

from repomap.providers import GitHubProvider, GitLabProvider, LocalRepoProvider, get_provider


def test_get_provider_github():
    """Test get_provider returns LocalRepoProvider by default for GitHub URLs."""
    provider = get_provider('https://github.com/owner/repo')
    assert isinstance(provider, LocalRepoProvider)


def test_get_provider_gitlab():
    """Test get_provider returns LocalRepoProvider by default for GitLab URLs."""
    provider = get_provider('https://gitlab.com/owner/repo')
    assert isinstance(provider, LocalRepoProvider)


def test_get_provider_github_no_local_clone():
    """Test get_provider returns GitHubProvider when local clone is disabled for GitHub URLs."""
    provider = get_provider('https://github.com/owner/repo', use_local_clone=False)
    assert isinstance(provider, GitHubProvider)


def test_get_provider_gitlab_no_local_clone():
    """Test get_provider returns GitLabProvider when local clone is disabled for GitLab URLs."""
    provider = get_provider('https://gitlab.com/owner/repo', use_local_clone=False)
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


class TestLocalRepoProvider:
    """Tests for LocalRepoProvider."""

    def test_init_with_local_clone_enabled(self):
        """Test LocalRepoProvider initialization with local clone enabled."""
        provider = LocalRepoProvider(use_local_clone=True)
        assert provider.use_local_clone is True
        assert provider._temp_dirs == []
        assert provider._cloned_repos == {}

    def test_init_with_local_clone_disabled(self):
        """Test LocalRepoProvider initialization with local clone disabled."""
        provider = LocalRepoProvider(use_local_clone=False)
        assert provider.use_local_clone is False

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    def test_clone_repo_success(self, mock_clone, mock_tempdir):
        """Test successful repository cloning."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider._clone_repo('https://github.com/owner/repo')

        assert str(result) == '/tmp/test_dir/repo'
        mock_clone.assert_called_once()

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    def test_clone_repo_with_token(self, mock_clone, mock_tempdir):
        """Test repository cloning with authentication token."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo

        provider = LocalRepoProvider(token='test_token')
        provider._clone_repo('https://github.com/owner/repo')

        # Verify that the clone URL was modified to include the token
        args, kwargs = mock_clone.call_args
        assert 'test_token@github.com' in args[0]

    @patch('shutil.rmtree')
    def test_cleanup(self, mock_rmtree):
        """Test cleanup of temporary directories."""
        provider = LocalRepoProvider()
        provider._temp_dirs = ['/tmp/dir1', '/tmp/dir2']
        provider._cloned_repos = {'key': 'path'}
        
        with patch('os.path.exists', return_value=True):
            provider.cleanup()

        assert provider._temp_dirs == []
        assert provider._cloned_repos == {}
        assert mock_rmtree.call_count == 2

    def test_get_file_content_no_local_clone(self):
        """Test get_file_content falls back to API when local clone is disabled."""
        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.get_file_content.return_value = 'file content'
            mock_get_provider.return_value = mock_api_provider

            provider = LocalRepoProvider(use_local_clone=False)
            content = provider.get_file_content('https://github.com/owner/repo/blob/main/file.py')

            assert content == 'file content'
            mock_get_provider.assert_called_once()

    def test_fetch_repo_structure_no_local_clone(self):
        """Test fetch_repo_structure falls back to API when local clone is disabled."""
        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.fetch_repo_structure.return_value = {'file.py': {'type': 'blob'}}
            mock_get_provider.return_value = mock_api_provider

            provider = LocalRepoProvider(use_local_clone=False)
            structure = provider.fetch_repo_structure('https://github.com/owner/repo')

            assert structure == {'file.py': {'type': 'blob'}}
            mock_get_provider.assert_called_once()

    @patch('pathlib.Path.iterdir')
    def test_build_structure_from_path(self, mock_iterdir):
        """Test building repository structure from local filesystem."""
        from pathlib import Path
        
        # Mock file and directory items
        mock_file = MagicMock(spec=Path)
        mock_file.name = 'test.py'
        mock_file.is_file.return_value = True
        mock_file.is_dir.return_value = False
        
        mock_dir = MagicMock(spec=Path)
        mock_dir.name = 'src'
        mock_dir.is_file.return_value = False
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = []
        
        mock_iterdir.return_value = [mock_file, mock_dir]
        
        provider = LocalRepoProvider()
        structure = provider._build_structure_from_path(Path('/fake/path'))
        
        assert 'test.py' in structure
        assert structure['test.py']['type'] == 'blob'
        assert 'src' in structure
        assert isinstance(structure['src'], dict)
