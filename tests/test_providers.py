"""Tests for repository providers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import git
import gitlab
import pytest

from repomap.providers import (
    GitHubProvider,
    GitLabProvider,
    LocalRepoProvider,
    get_provider,
)


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
    @patch('git.Repo')
    def test_clone_repo_success(self, mock_git_repo, mock_clone, mock_tempdir):
        """Test successful repository cloning."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider._clone_repo('https://github.com/owner/repo')

        assert str(result) == '/tmp/test_dir/repo'
        mock_clone.assert_called_once()

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_with_token(self, mock_git_repo, mock_clone, mock_tempdir):
        """Test repository cloning with authentication token."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

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

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_with_branch_ref(self, mock_git_repo, mock_clone, mock_tempdir):
        """Test repository cloning with specific branch reference."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider._clone_repo('https://github.com/owner/repo', 'develop')

        assert str(result) == '/tmp/test_dir/repo'
        # Should try to clone the specific branch first
        mock_clone.assert_called_once()
        args, kwargs = mock_clone.call_args
        assert kwargs.get('branch') == 'develop'

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_with_tag_ref_fallback(
        self, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test repository cloning with tag reference requiring fallback."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'

        # First call (specific ref) fails, second call (default) succeeds
        mock_clone.side_effect = [
            git.exc.GitCommandError("Branch not found"),
            mock_repo,
        ]
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider._clone_repo('https://github.com/owner/repo', 'v2.0.0')

        assert str(result) == '/tmp/test_dir/repo'
        # Should be called twice - once for specific ref, once for default
        assert mock_clone.call_count == 2

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_with_invalid_ref(self, mock_git_repo, mock_clone, mock_tempdir):
        """Test repository cloning with invalid reference raises ValueError."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_repo.git.checkout.side_effect = git.exc.GitCommandError("Ref not found")
        mock_repo.git.fetch.side_effect = git.exc.GitCommandError("Ref not found")

        # First call (specific ref) fails, second call (default) succeeds but checkout fails
        mock_clone.side_effect = [
            git.exc.GitCommandError("Branch not found"),
            mock_repo,
        ]
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()

        with pytest.raises(
            ValueError, match="No ref found in repository by name: nonexistent-ref"
        ):
            provider._clone_repo('https://github.com/owner/repo', 'nonexistent-ref')

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    @patch('shutil.rmtree')
    def test_validate_ref_with_branch(
        self, mock_rmtree, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test validate_ref with valid branch reference."""
        mock_tempdir.return_value = '/tmp/validate_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider.validate_ref('https://github.com/owner/repo', 'develop')

        assert result == 'develop'
        mock_repo.git.checkout.assert_called_once_with('develop')

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    @patch('shutil.rmtree')
    def test_validate_ref_with_tag_fallback(
        self, mock_rmtree, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test validate_ref with tag requiring fallback fetch."""
        mock_tempdir.return_value = '/tmp/validate_dir'
        mock_repo = MagicMock()
        mock_repo.active_branch.name = 'main'

        # Checkout fails first, then fetch and checkout succeed
        mock_repo.git.checkout.side_effect = [
            git.exc.GitCommandError("Not found"),
            None,
        ]
        mock_repo.git.fetch.return_value = None
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        result = provider.validate_ref('https://github.com/owner/repo', 'v1.0.0')

        assert result == 'v1.0.0'
        # Should try multiple fetch strategies
        assert mock_repo.git.fetch.call_count >= 1

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    @patch('shutil.rmtree')
    def test_validate_ref_invalid(
        self, mock_rmtree, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test validate_ref with invalid reference raises ValueError."""
        mock_tempdir.return_value = '/tmp/validate_dir'
        mock_repo = MagicMock()
        mock_repo.git.checkout.side_effect = git.exc.GitCommandError("Not found")
        mock_repo.git.fetch.side_effect = git.exc.GitCommandError("Not found")
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()

        with pytest.raises(
            ValueError, match="No ref found in repository by name: invalid-ref"
        ):
            provider.validate_ref('https://github.com/owner/repo', 'invalid-ref')

    def test_get_file_content_no_local_clone(self):
        """Test get_file_content falls back to API when local clone is disabled."""
        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.get_file_content.return_value = 'file content'
            mock_get_provider.return_value = mock_api_provider

            provider = LocalRepoProvider(use_local_clone=False)
            content = provider.get_file_content(
                'https://github.com/owner/repo/blob/main/file.py'
            )

            assert content == 'file content'
            mock_get_provider.assert_called_once()

    def test_fetch_repo_structure_no_local_clone(self):
        """Test fetch_repo_structure falls back to API when local clone is disabled."""
        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.fetch_repo_structure.return_value = {
                'file.py': {'type': 'blob'}
            }
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


def test_github_provider_get_last_commit_hash(mock_github):
    """Test GitHub provider get_last_commit_hash method."""
    mock_branch = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = 'abc123def456'
    mock_branch.commit = mock_commit
    mock_github.get_repo.return_value.get_branch.return_value = mock_branch

    provider = GitHubProvider()
    commit_hash = provider.get_last_commit_hash('https://github.com/owner/repo', 'main')

    assert commit_hash == 'abc123def456'


def test_github_provider_get_last_commit_hash_default_branch(mock_github):
    """Test GitHub provider get_last_commit_hash with default branch."""
    mock_branch = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = 'xyz789'
    mock_branch.commit = mock_commit
    mock_github.get_repo.return_value.default_branch = 'main'
    mock_github.get_repo.return_value.get_branch.return_value = mock_branch

    provider = GitHubProvider()
    commit_hash = provider.get_last_commit_hash('https://github.com/owner/repo')

    assert commit_hash == 'xyz789'


def test_github_provider_get_last_commit_hash_tag(mock_github):
    """Test GitHub provider get_last_commit_hash with tag reference."""
    mock_tag = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = 'tag123hash'
    mock_tag.commit = mock_commit

    # Branch fails, tag succeeds
    mock_github.get_repo.return_value.get_branch.side_effect = Exception()
    mock_github.get_repo.return_value.get_tag.return_value = mock_tag

    provider = GitHubProvider()
    commit_hash = provider.get_last_commit_hash(
        'https://github.com/owner/repo', 'v1.0.0'
    )

    assert commit_hash == 'tag123hash'


def test_gitlab_provider_get_last_commit_hash(mock_gitlab):
    """Test GitLab provider get_last_commit_hash method."""
    mock_commit = MagicMock()
    mock_commit.id = 'gitlab123hash'
    mock_gitlab.projects.get.return_value.commits.list.return_value = [mock_commit]

    provider = GitLabProvider()
    commit_hash = provider.get_last_commit_hash('https://gitlab.com/owner/repo', 'main')

    assert commit_hash == 'gitlab123hash'


def test_gitlab_provider_get_last_commit_hash_default_branch(mock_gitlab):
    """Test GitLab provider get_last_commit_hash with default branch."""
    mock_commit = MagicMock()
    mock_commit.id = 'gitlab456hash'
    mock_gitlab.projects.get.return_value.commits.list.return_value = [mock_commit]
    mock_gitlab.projects.get.return_value.default_branch = 'develop'

    provider = GitLabProvider()
    commit_hash = provider.get_last_commit_hash('https://gitlab.com/owner/repo')

    assert commit_hash == 'gitlab456hash'


def test_gitlab_provider_get_last_commit_hash_pagination_parameter(mock_gitlab):
    """Test GitLab provider get_last_commit_hash passes get_all=False to suppress pagination warning."""
    mock_commit = MagicMock()
    mock_commit.id = 'testcommithash'
    mock_gitlab.projects.get.return_value.commits.list.return_value = [mock_commit]

    provider = GitLabProvider()
    commit_hash = provider.get_last_commit_hash('https://gitlab.com/owner/repo', 'main')

    # Verify that commits.list was called with get_all=False
    mock_gitlab.projects.get.return_value.commits.list.assert_called_with(
        ref_name='main', per_page=1, get_all=False
    )
    assert commit_hash == 'testcommithash'


class TestLocalRepoProviderCommitHash:
    """Tests for LocalRepoProvider get_last_commit_hash functionality."""

    @patch('repomap.providers.LocalRepoProvider._clone_repo')
    @patch('git.Repo')
    def test_get_last_commit_hash_success(self, mock_git_repo, mock_clone):
        """Test successful commit hash retrieval from local clone."""
        from pathlib import Path

        mock_clone.return_value = Path('/tmp/test_repo')
        mock_repo = MagicMock()
        mock_commit = MagicMock()
        mock_commit.hexsha = 'local123hash'
        mock_repo.head.commit = mock_commit
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider()
        commit_hash = provider.get_last_commit_hash(
            'https://github.com/owner/repo', 'main'
        )

        assert commit_hash == 'local123hash'
        mock_clone.assert_called_once_with('https://github.com/owner/repo', 'main')
        # git.Repo is called with the Path object returned by _clone_repo
        mock_git_repo.assert_called_once_with(Path('/tmp/test_repo'))

    def test_get_last_commit_hash_no_local_clone(self):
        """Test get_last_commit_hash falls back to API when local clone is disabled."""
        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.get_last_commit_hash.return_value = 'api123hash'
            mock_get_provider.return_value = mock_api_provider

            provider = LocalRepoProvider(use_local_clone=False)
            commit_hash = provider.get_last_commit_hash(
                'https://github.com/owner/repo', 'main'
            )

            assert commit_hash == 'api123hash'
            mock_get_provider.assert_called_once()

    @patch('repomap.providers.LocalRepoProvider._clone_repo')
    @patch('git.Repo')
    def test_get_last_commit_hash_with_fallback(self, mock_git_repo, mock_clone):
        """Test commit hash retrieval with fallback to API on local failure."""
        mock_clone.side_effect = Exception("Clone failed")

        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            # Make API fail first, then return fallback API provider
            mock_api_provider = MagicMock()
            mock_api_provider.get_last_commit_hash.return_value = 'fallback123hash'
            mock_get_provider.side_effect = [Exception("API failed"), mock_api_provider]

            provider = LocalRepoProvider(
                use_local_clone=True
            )  # Ensure local clone is enabled
            commit_hash = provider.get_last_commit_hash(
                'https://github.com/owner/repo', 'main'
            )

            assert (
                commit_hash is None
            )  # Should return None when both API and local clone fail
            mock_clone.assert_called_once_with('https://github.com/owner/repo', 'main')
            assert mock_get_provider.call_count == 1  # API should be tried once


class TestLocalRepoProviderDockerAuth:
    """Tests for LocalRepoProvider Docker authentication fixes."""

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    def test_clone_repo_docker_auth_failure_fallback(self, mock_clone, mock_tempdir):
        """Test that Docker authentication failures trigger proper fallback."""
        mock_tempdir.return_value = '/tmp/test_dir'

        # Simulate Docker authentication error
        auth_error = git.exc.GitCommandError(
            command='git clone',
            status=128,
            stderr='fatal: could not read Username for \'https://git-testing.example.com\': No such device or address',
        )
        mock_clone.side_effect = auth_error

        provider = LocalRepoProvider(token='test_token')

        with pytest.raises(git.exc.GitCommandError) as exc_info:
            provider._clone_repo('https://git-testing.example.com/owner/repo')

        # Verify the error message indicates authentication failure
        assert 'Authentication failed for repository' in str(exc_info.value.stderr)

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_git_env_configuration(
        self, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test that git environment variables are properly configured for Docker."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider(token='test_token')
        provider._clone_repo('https://github.com/owner/repo')

        # Verify clone_from was called with proper environment variables
        mock_clone.assert_called_once()
        args, kwargs = mock_clone.call_args

        # Check that env parameter was passed
        assert 'env' in kwargs
        git_env = kwargs['env']
        assert git_env.get('GIT_TERMINAL_PROMPT') == '0'
        assert git_env.get('GIT_ASKPASS') == 'echo'
        assert 'BatchMode=yes' in git_env.get('GIT_SSH_COMMAND', '')

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    def test_clone_repo_gitlab_private_instance_auth(
        self, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test authentication URL construction for private GitLab instances."""
        mock_tempdir.return_value = '/tmp/test_dir'
        mock_repo = MagicMock()
        mock_clone.return_value = mock_repo
        mock_git_repo.return_value = mock_repo

        provider = LocalRepoProvider(token='private_token')
        provider._clone_repo(
            'https://git-testing.devsec.astralinux.ru/astra/containerd'
        )

        # Verify that the clone URL was constructed with OAuth2 token
        args, kwargs = mock_clone.call_args
        clone_url = args[0]
        assert 'oauth2:private_token@git-testing.devsec.astralinux.ru' in clone_url

    @patch('git.Repo')
    def test_get_file_content_auth_fallback(self, mock_git_repo):
        """Test get_file_content falls back to API on authentication errors."""
        with patch('repomap.providers.LocalRepoProvider._clone_repo') as mock_clone:
            auth_error = git.exc.GitCommandError(
                command='git clone',
                status=128,
                stderr='fatal: could not read Username for \'https://private.gitlab.com\': No such device or address',
            )
            mock_clone.side_effect = auth_error

            with patch('repomap.providers._get_api_provider') as mock_get_provider:
                mock_api_provider = MagicMock()
                mock_api_provider.get_file_content.return_value = (
                    'file content from API'
                )
                mock_get_provider.return_value = mock_api_provider

                provider = LocalRepoProvider()
                content = provider.get_file_content(
                    'https://private.gitlab.com/owner/repo/-/blob/main/file.py'
                )

                assert content == 'file content from API'
                mock_get_provider.assert_called_once()

    @patch('git.Repo')
    def test_fetch_repo_structure_auth_fallback(self, mock_git_repo):
        """Test fetch_repo_structure falls back to API on authentication errors."""
        with patch('repomap.providers.LocalRepoProvider._clone_repo') as mock_clone:
            auth_error = git.exc.GitCommandError(
                command='git clone',
                status=128,
                stderr='fatal: could not read Username for \'https://private.gitlab.com\': No such device or address',
            )
            mock_clone.side_effect = auth_error

            with patch('repomap.providers._get_api_provider') as mock_get_provider:
                mock_api_provider = MagicMock()
                mock_api_provider.fetch_repo_structure.return_value = {
                    'file.py': {'type': 'blob'}
                }
                mock_get_provider.return_value = mock_api_provider

                provider = LocalRepoProvider()
                structure = provider.fetch_repo_structure(
                    'https://private.gitlab.com/owner/repo'
                )

                assert structure == {'file.py': {'type': 'blob'}}
                mock_get_provider.assert_called_once()

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    @patch('git.Repo')
    @patch('shutil.rmtree')
    def test_validate_ref_auth_fallback(
        self, mock_rmtree, mock_git_repo, mock_clone, mock_tempdir
    ):
        """Test validate_ref falls back to API on authentication errors."""
        mock_tempdir.return_value = '/tmp/validate_dir'
        auth_error = git.exc.GitCommandError(
            command='git clone',
            status=128,
            stderr='fatal: could not read Username for \'https://private.gitlab.com\': No such device or address',
        )
        mock_clone.side_effect = auth_error

        with patch('repomap.providers._get_api_provider') as mock_get_provider:
            mock_api_provider = MagicMock()
            mock_api_provider.validate_ref.return_value = 'main'
            mock_get_provider.return_value = mock_api_provider

            provider = LocalRepoProvider()
            result = provider.validate_ref(
                'https://private.gitlab.com/owner/repo', 'main'
            )

            assert result == 'main'
            mock_get_provider.assert_called_once()

    @patch('tempfile.mkdtemp')
    @patch('git.Repo.clone_from')
    def test_clone_repo_non_auth_git_error(self, mock_clone, mock_tempdir):
        """Test that non-authentication git errors are handled differently."""
        mock_tempdir.return_value = '/tmp/test_dir'

        # Simulate non-authentication git error
        git_error = git.exc.GitCommandError(
            command='git clone', status=128, stderr='fatal: repository not found'
        )
        mock_clone.side_effect = git_error

        provider = LocalRepoProvider()

        with pytest.raises(RuntimeError) as exc_info:
            provider._clone_repo('https://github.com/owner/nonexistent-repo')

        # Verify it's a RuntimeError, not a GitCommandError
        assert 'Failed to clone repository' in str(exc_info.value)
