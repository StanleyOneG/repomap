"""Module for repository provider abstractions and implementations."""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import git
import gitlab
from github import Github
from github.Repository import Repository

from .config import settings

logger = logging.getLogger(__name__)


class RepoProvider(ABC):
    """Abstract base class for repository providers."""

    @abstractmethod
    def get_file_content(self, file_url: str) -> Optional[str]:
        """Get content of a file from the repository.

        Args:
            file_url: URL to the file

        Returns:
            Optional[str]: File content or None if failed
        """
        pass

    @abstractmethod
    def fetch_repo_structure(self, repo_url: str, ref: Optional[str] = None) -> Dict:
        """Fetch repository structure.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Dict: Repository structure
        """
        pass

    @abstractmethod
    def validate_ref(self, repo_url: str, ref: Optional[str] = None) -> str:
        """Validate git reference and return default if not provided.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            str: Validated reference or default branch

        Raises:
            ValueError: If provided ref does not exist
        """
        pass

    @abstractmethod
    def get_last_commit_hash(self, repo_url: str, ref: Optional[str] = None) -> Optional[str]:
        """Get the last commit hash for the given repository and reference.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Optional[str]: Last commit hash or None if failed
        """
        pass


class GitLabProvider(RepoProvider):
    """GitLab repository provider implementation."""

    def __init__(self, token: Optional[str] = None):
        """Initialize GitLab provider.

        Args:
            token: Optional GitLab access token
        """
        self.token = token or (
            settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else None
        )
        self.gl = None
        self.base_url = None

    def _ensure_gitlab_client(self, repo_url: str):
        """Ensure GitLab client is initialized with correct base URL.

        Args:
            repo_url: Repository URL to extract base URL from
        """
        if not self.gl:
            parsed = urlparse(repo_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid repository URL: {repo_url}")
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
            self.gl = gitlab.Gitlab(self.base_url, private_token=self.token)

    def _get_project_parts(self, repo_url: str) -> tuple[str, str]:
        """Extract group path and project name from repository URL.

        Args:
            repo_url: Repository URL

        Returns:
            tuple[str, str]: Group path and project name
        """
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) < 2:
            raise ValueError(f"Invalid repository URL format: {repo_url}")
        project_name = path_parts[-1]
        group_path = '/'.join(path_parts[:-1])
        return group_path, project_name

    def get_file_content(self, file_url: str) -> Optional[str]:
        """Get content of a file from GitLab.

        Args:
            file_url: URL to the file

        Returns:
            Optional[str]: File content or None if failed
        """
        try:
            parsed = urlparse(file_url)
            if not parsed.scheme or not parsed.netloc:
                return None

            base_url = f"{parsed.scheme}://{parsed.netloc}"
            remaining_path = file_url[len(base_url) :].strip('/')

            parts = remaining_path.split('/-/')
            if len(parts) != 2:
                return None

            project_path = parts[0].strip('/')
            file_info = parts[1].strip('/')

            file_parts = file_info.split('/')
            if len(file_parts) < 3 or file_parts[0] != 'blob':
                return None

            ref = file_parts[1]
            file_path = '/'.join(file_parts[2:])

            gl = gitlab.Gitlab(base_url, private_token=self.token)

            try:
                project = gl.projects.get(project_path)
            except gitlab.exceptions.GitlabGetError:
                from urllib.parse import quote

                encoded_path = quote(project_path, safe='')
                project = gl.projects.get(encoded_path)

            f = project.files.get(file_path=file_path, ref=ref)
            return f.decode().decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to fetch GitLab content: {e}")
            return None

    def fetch_repo_structure(self, repo_url: str, ref: Optional[str] = None) -> Dict:
        """Fetch repository structure from GitLab.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Dict: Repository structure
        """
        self._ensure_gitlab_client(repo_url)
        group_path, project_name = self._get_project_parts(repo_url)
        project_path = f"{group_path}/{project_name}"

        try:
            project = self.gl.projects.get(project_path)
        except gitlab.exceptions.GitlabGetError:
            from urllib.parse import quote

            encoded_path = quote(project_path, safe='')
            project = self.gl.projects.get(encoded_path)

        if not ref:
            ref = project.default_branch

        items = project.repository_tree(ref=ref, recursive=True, all=True)
        structure = {}

        for item in items:
            path = item['path']
            parts = path.split('/')
            current = structure

            # Build tree structure
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # File
                    current[part] = {
                        'type': item['type'],
                        'mode': item.get('mode', '100644'),
                        'id': item['id'],
                    }
                else:
                    # Directory
                    if part not in current:
                        current[part] = {}
                    current = current[part]

        return structure

    def validate_ref(self, repo_url: str, ref: Optional[str] = None) -> str:
        """Validate git reference and return default if not provided.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            str: Validated reference or default branch

        Raises:
            ValueError: If provided ref does not exist
        """
        self._ensure_gitlab_client(repo_url)
        group_path, project_name = self._get_project_parts(repo_url)
        project_path = f"{group_path}/{project_name}"
        project = self.gl.projects.get(project_path)

        if ref:
            try:
                project.branches.get(ref)
                return ref
            except gitlab.exceptions.GitlabGetError:
                try:
                    project.tags.get(ref)
                    return ref
                except gitlab.exceptions.GitlabGetError:
                    try:
                        project.commits.get(ref)
                        return ref
                    except gitlab.exceptions.GitlabGetError:
                        raise ValueError(f"No ref found in repository by name: {ref}")
        return project.default_branch

    def get_last_commit_hash(self, repo_url: str, ref: Optional[str] = None) -> Optional[str]:
        """Get the last commit hash for the given repository and reference.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Optional[str]: Last commit hash or None if failed
        """
        try:
            self._ensure_gitlab_client(repo_url)
            group_path, project_name = self._get_project_parts(repo_url)
            project_path = f"{group_path}/{project_name}"
            project = self.gl.projects.get(project_path)
            
            if not ref:
                ref = project.default_branch
            
            # Get the latest commit for the reference
            commits = project.commits.list(ref_name=ref, per_page=1, get_all=False)
            if commits:
                return commits[0].id
        except Exception as e:
            logger.warning(f"Failed to get last commit hash from GitLab: {e}")
        return None


class GitHubProvider(RepoProvider):
    """GitHub repository provider implementation."""

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub provider.

        Args:
            token: Optional GitHub access token
        """
        self.token = token or (
            settings.GITHUB_TOKEN.get_secret_value() if settings.GITHUB_TOKEN else None
        )
        self.gh = Github(self.token) if self.token else Github()

    def _get_repo_from_url(self, repo_url: str) -> Repository:
        """Get GitHub repository from URL.

        Args:
            repo_url: Repository URL

        Returns:
            Repository: GitHub repository object
        """
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) < 2:
            raise ValueError(f"Invalid repository URL format: {repo_url}")
        repo_full_name = '/'.join(path_parts[-2:])
        return self.gh.get_repo(repo_full_name)

    def get_file_content(self, file_url: str) -> Optional[str]:
        """Get content of a file from GitHub.

        Args:
            file_url: URL to the file

        Returns:
            Optional[str]: File content or None if failed
        """
        try:
            parsed = urlparse(file_url)
            path_parts = parsed.path.strip('/').split('/')

            owner = path_parts[0]
            repo_name = path_parts[1]

            if 'blob' not in path_parts:
                return None
            blob_index = path_parts.index('blob')
            ref = path_parts[blob_index + 1]
            file_path = '/'.join(path_parts[blob_index + 2 :])

            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            content = repo.get_contents(file_path, ref=ref)
            return content.decoded_content.decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub content: {e}")
            return None

    def fetch_repo_structure(  # noqa: C901
        self, repo_url: str, ref: Optional[str] = None
    ) -> Dict:
        """Fetch repository structure from GitHub.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Dict: Repository structure
        """
        repo = self._get_repo_from_url(repo_url)
        if not ref:
            ref = repo.default_branch

        def get_tree_recursive(path='', depth=0):
            if depth > 20:
                return {}

            try:
                contents = repo.get_contents(path, ref=ref)
                if not contents:
                    return {}

                # Convert to list if single item
                if not isinstance(contents, list):
                    contents = [contents]

                structure = {}
                for content in contents:
                    name = str(content.name)
                    if content.type == 'dir':
                        structure[name] = get_tree_recursive(content.path, depth + 1)
                    else:
                        structure[name] = {
                            'type': 'blob',
                            'mode': '100644',
                            'id': content.sha,
                        }
                return structure
            except Exception as e:
                logger.warning(f"Error fetching contents for path {path}: {e}")
                return {}

        return get_tree_recursive()

    def validate_ref(self, repo_url: str, ref: Optional[str] = None) -> str:
        """Validate git reference and return default if not provided.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            str: Validated reference or default branch

        Raises:
            ValueError: If provided ref does not exist
        """
        repo = self._get_repo_from_url(repo_url)

        if ref:
            try:
                repo.get_branch(ref)
                return ref
            except Exception:
                try:
                    repo.get_tag(ref)
                    return ref
                except Exception:
                    try:
                        repo.get_commit(ref)
                        return ref
                    except Exception:
                        raise ValueError(f"No ref found in repository by name: {ref}")
        return repo.default_branch

    def get_last_commit_hash(self, repo_url: str, ref: Optional[str] = None) -> Optional[str]:
        """Get the last commit hash for the given repository and reference.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Optional[str]: Last commit hash or None if failed
        """
        try:
            repo = self._get_repo_from_url(repo_url)
            
            if not ref:
                ref = repo.default_branch
            
            # Get the latest commit for the reference
            try:
                # Try to get branch first
                branch = repo.get_branch(ref)
                return branch.commit.sha
            except Exception:
                try:
                    # Try to get tag
                    tag = repo.get_tag(ref)
                    return tag.commit.sha
                except Exception:
                    try:
                        # Try to get commit directly
                        commit = repo.get_commit(ref)
                        return commit.sha
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to get last commit hash from GitHub: {e}")
        return None


class LocalRepoProvider(RepoProvider):
    """Local repository provider implementation using GitPython."""

    def __init__(self, token: Optional[str] = None, use_local_clone: bool = True):
        """Initialize Local repository provider.

        Args:
            token: Optional access token for authentication
            use_local_clone: Whether to use local cloning for performance
        """
        self.token = token
        self.use_local_clone = use_local_clone
        self._temp_dirs = []
        self._cloned_repos = {}

    def __del__(self):
        """Cleanup temporary directories."""
        self.cleanup()

    def cleanup(self):
        """Clean up temporary clone directories."""
        import shutil
        for temp_dir in self._temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
        self._temp_dirs.clear()
        self._cloned_repos.clear()

    def _clone_repo(self, repo_url: str, ref: Optional[str] = None) -> Path:
        """Clone repository locally for faster access.

        Args:
            repo_url: Repository URL
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Path: Path to local clone
        """
        cache_key = f"{repo_url}#{ref or 'default'}"
        if cache_key in self._cloned_repos:
            return self._cloned_repos[cache_key]

        temp_dir = tempfile.mkdtemp(prefix="repomap_clone_")
        self._temp_dirs.append(temp_dir)
        clone_path = Path(temp_dir) / "repo"

        try:
            # Create authenticated URL if token is provided
            clone_url = repo_url
            if self.token:
                parsed = urlparse(repo_url)
                if 'github.com' in parsed.netloc:
                    clone_url = repo_url.replace('https://github.com/', f'https://{self.token}@github.com/')
                else:
                    # Handle GitLab instances (both public and private)
                    # Use OAuth2 token format which works for most GitLab instances
                    clone_url = repo_url.replace('https://', f'https://oauth2:{self.token}@')
            
            # Configure git environment for non-interactive Docker containers
            git_env = os.environ.copy()
            git_env.update({
                'GIT_TERMINAL_PROMPT': '0',  # Never prompt for credentials
                'GIT_ASKPASS': 'echo',       # Use echo to prevent credential prompts
                'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o StrictHostKeyChecking=no'
            })

            # Clone the repository - different strategy based on whether ref is specified
            if ref:
                try:
                    # Try to clone the specific branch/tag directly first
                    repo = git.Repo.clone_from(
                        clone_url,
                        clone_path,
                        depth=1,
                        single_branch=True,
                        branch=ref,
                        env=git_env
                    )
                except git.exc.GitCommandError:
                    # If direct clone of branch fails, clone default and checkout
                    repo = git.Repo.clone_from(
                        clone_url,
                        clone_path,
                        depth=1,
                        env=git_env
                    )
                    
                    # Try to checkout the ref
                    try:
                        repo.git.checkout(ref)
                    except git.exc.GitCommandError:
                        # If checkout fails, try to fetch the ref from remote
                        try:
                            repo.git.fetch('origin', f'{ref}:{ref}')
                            repo.git.checkout(ref)
                        except git.exc.GitCommandError:
                            # Try fetching as a tag or remote branch
                            try:
                                repo.git.fetch('origin', f'+refs/heads/{ref}:refs/remotes/origin/{ref}')
                                repo.git.checkout(f'origin/{ref}')
                            except git.exc.GitCommandError:
                                # Try fetching as a tag
                                try:
                                    repo.git.fetch('origin', f'+refs/tags/{ref}:refs/tags/{ref}')
                                    repo.git.checkout(ref)
                                except git.exc.GitCommandError:
                                    raise ValueError(f"No ref found in repository by name: {ref}")
            else:
                # No specific ref, clone default branch
                repo = git.Repo.clone_from(
                    clone_url,
                    clone_path,
                    depth=1,
                    single_branch=True,
                    env=git_env
                )

            self._cloned_repos[cache_key] = clone_path
            return clone_path

        except ValueError as e:
            # Re-raise ValueError for invalid refs
            raise
        except git.exc.GitCommandError as e:
            # Check if this is an authentication error that should trigger API fallback
            error_msg = str(e).lower()
            if any(auth_error in error_msg for auth_error in [
                'could not read username', 'could not read password', 
                'authentication failed', 'access denied', 'permission denied',
                'no such device or address', 'terminal prompts disabled'
            ]):
                # Clean up failed clone attempt
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                if temp_dir in self._temp_dirs:
                    self._temp_dirs.remove(temp_dir)
                # Let this exception propagate to trigger API fallback
                raise git.exc.GitCommandError(command=e.command, status=e.status, 
                                            stderr=f"Authentication failed for repository {repo_url}: {e.stderr}")
            else:
                # Other git errors, convert to RuntimeError 
                raise RuntimeError(f"Failed to clone repository {repo_url}: {e}")
        except Exception as e:
            # Clean up on any other error
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if temp_dir in self._temp_dirs:
                self._temp_dirs.remove(temp_dir)
            raise RuntimeError(f"Failed to clone repository {repo_url}: {e}")

    def get_file_content(self, file_url: str) -> Optional[str]:
        """Get content of a file from local clone or API.

        Args:
            file_url: URL to the file or local path if already cloned

        Returns:
            Optional[str]: File content or None if failed
        """
        if not self.use_local_clone:
            # Fallback to appropriate API provider
            provider = _get_api_provider(file_url, self.token)
            return provider.get_file_content(file_url)

        try:
            # Extract repo URL and file path from file URL
            parsed = urlparse(file_url)
            if '/-/blob/' in file_url:  # GitLab format
                parts = file_url.split('/-/blob/')
                repo_url = parts[0]
                ref_and_path = parts[1].split('/', 1)
                ref = ref_and_path[0]
                file_path = ref_and_path[1] if len(ref_and_path) > 1 else ''
            elif '/blob/' in file_url:  # GitHub format
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                path_parts = parsed.path.strip('/').split('/')
                owner, repo_name = path_parts[:2]
                repo_url = f"{base_url}/{owner}/{repo_name}"
                
                blob_index = path_parts.index('blob')
                ref = path_parts[blob_index + 1]
                file_path = '/'.join(path_parts[blob_index + 2:])
            else:
                return None

            clone_path = self._clone_repo(repo_url, ref)
            full_file_path = clone_path / file_path
            
            if full_file_path.exists() and full_file_path.is_file():
                return full_file_path.read_text(encoding='utf-8', errors='ignore')
            return None

        except Exception as e:
            logger.warning(f"Failed to get file content from local clone: {e}")
            # Fallback to API
            provider = _get_api_provider(file_url, self.token)
            return provider.get_file_content(file_url)

    def fetch_repo_structure(self, repo_url: str, ref: Optional[str] = None) -> Dict:
        """Fetch repository structure from local clone or API.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Dict: Repository structure
        """
        if not self.use_local_clone:
            # Fallback to appropriate API provider
            provider = _get_api_provider(repo_url, self.token)
            return provider.fetch_repo_structure(repo_url, ref)

        try:
            clone_path = self._clone_repo(repo_url, ref)
            return self._build_structure_from_path(clone_path)

        except Exception as e:
            logger.warning(f"Failed to fetch repo structure from local clone: {e}")
            # Fallback to API
            provider = _get_api_provider(repo_url, self.token)
            return provider.fetch_repo_structure(repo_url, ref)

    def _build_structure_from_path(self, root_path: Path) -> Dict:
        """Build repository structure from local filesystem.

        Args:
            root_path: Path to repository root

        Returns:
            Dict: Repository structure
        """
        structure = {}
        
        def scan_directory(current_path: Path, current_structure: Dict):
            try:
                for item in current_path.iterdir():
                    # Skip .git directory and other hidden directories
                    if item.name.startswith('.'):
                        continue
                        
                    if item.is_file():
                        current_structure[item.name] = {
                            'type': 'blob',
                            'mode': '100644',
                            'id': '',  # We don't need git object IDs for our purposes
                        }
                    elif item.is_dir():
                        current_structure[item.name] = {}
                        scan_directory(item, current_structure[item.name])
            except PermissionError:
                # Skip directories we can't read
                pass

        scan_directory(root_path, structure)
        return structure

    def validate_ref(self, repo_url: str, ref: Optional[str] = None) -> str:
        """Validate git reference and return default if not provided.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            str: Validated reference or default branch

        Raises:
            ValueError: If provided ref does not exist
        """
        if not self.use_local_clone:
            # Fallback to appropriate API provider
            provider = _get_api_provider(repo_url, self.token)
            return provider.validate_ref(repo_url, ref)

        try:
            # For local cloning, we'll attempt the clone and let GitPython handle validation
            temp_dir = tempfile.mkdtemp(prefix="repomap_validate_")
            try:
                clone_url = repo_url
                if self.token:
                    parsed = urlparse(repo_url)
                    if 'github.com' in parsed.netloc:
                        clone_url = repo_url.replace('https://github.com/', f'https://{self.token}@github.com/')
                    else:
                        # Handle GitLab instances (both public and private)
                        # Use OAuth2 token format which works for most GitLab instances
                        clone_url = repo_url.replace('https://', f'https://oauth2:{self.token}@')

                # Configure git environment for non-interactive Docker containers
                git_env = os.environ.copy()
                git_env.update({
                    'GIT_TERMINAL_PROMPT': '0',
                    'GIT_ASKPASS': 'echo',
                    'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o StrictHostKeyChecking=no'
                })

                repo = git.Repo.clone_from(clone_url, temp_dir, depth=1, env=git_env)
                
                if not ref:
                    return repo.active_branch.name
                
                # Try to checkout the ref to validate it exists
                try:
                    repo.git.checkout(ref)
                    return ref
                except git.exc.GitCommandError:
                    # If checkout fails, try to fetch the ref from remote
                    try:
                        repo.git.fetch('origin', f'{ref}:{ref}')
                        repo.git.checkout(ref)
                        return ref
                    except git.exc.GitCommandError:
                        # Try fetching as a remote branch
                        try:
                            repo.git.fetch('origin', f'+refs/heads/{ref}:refs/remotes/origin/{ref}')
                            repo.git.checkout(f'origin/{ref}')
                            return ref
                        except git.exc.GitCommandError:
                            # Try fetching as a tag
                            try:
                                repo.git.fetch('origin', f'+refs/tags/{ref}:refs/tags/{ref}')
                                repo.git.checkout(ref)
                                return ref
                            except git.exc.GitCommandError:
                                raise ValueError(f"No ref found in repository by name: {ref}")
            finally:
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

        except ValueError as e:
            # Re-raise ValueError for invalid refs
            raise
        except git.exc.GitCommandError as e:
            # Fall back to API for any git command errors (authentication, repo not found, etc.)
            logger.warning(f"Git command failed during validation, falling back to API: {e}")
            provider = _get_api_provider(repo_url, self.token)
            return provider.validate_ref(repo_url, ref)
        except Exception as e:
            if "No ref found" in str(e):
                raise
            # Fallback to API for validation
            logger.warning(f"Failed to validate ref locally, falling back to API: {e}")
            provider = _get_api_provider(repo_url, self.token)
            return provider.validate_ref(repo_url, ref)

    def get_last_commit_hash(self, repo_url: str, ref: Optional[str] = None) -> Optional[str]:
        """Get the last commit hash for the given repository and reference.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Optional[str]: Last commit hash or None if failed
        """
        # ALWAYS try API first for speed (key optimization!)
        try:
            provider = _get_api_provider(repo_url, self.token)
            commit_hash = provider.get_last_commit_hash(repo_url, ref)
            if commit_hash:
                return commit_hash
        except Exception as e:
            logger.warning(f"Failed to get commit hash via API: {e}")

        # Only fall back to local cloning if API fails AND local cloning is enabled
        if self.use_local_clone:
            try:
                clone_path = self._clone_repo(repo_url, ref)
                repo = git.Repo(clone_path)
                
                # Get the current HEAD commit hash
                return repo.head.commit.hexsha
            except Exception as e:
                logger.warning(f"Failed to get last commit hash from local clone: {e}")
        
        return None


def _get_api_provider(repo_url: str, token: Optional[str] = None) -> RepoProvider:
    """Get appropriate API-based repository provider based on URL.

    Args:
        repo_url: Repository URL
        token: Optional access token

    Returns:
        RepoProvider: Repository provider instance
    """
    parsed = urlparse(repo_url)
    if 'github' in parsed.netloc:
        return GitHubProvider(token)
    return GitLabProvider(token)


def get_provider(repo_url: str, token: Optional[str] = None, use_local_clone: bool = True) -> RepoProvider:
    """Get appropriate repository provider based on URL and preferences.

    Args:
        repo_url: Repository URL
        token: Optional access token
        use_local_clone: Whether to use local cloning for performance (default: True)

    Returns:
        RepoProvider: Repository provider instance
    """
    if use_local_clone:
        return LocalRepoProvider(token, use_local_clone=True)
    return _get_api_provider(repo_url, token)
