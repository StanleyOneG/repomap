"""Module for repository provider abstractions and implementations."""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from urllib.parse import urlparse

import gitlab
from github import Github
from github.Repository import Repository

from .config import settings


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
            print(f"Failed to fetch GitLab content: {e}")
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
            print(f"Failed to fetch GitHub content: {e}")
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
                print(f"Error fetching contents for path {path}: {e}")
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


def get_provider(repo_url: str, token: Optional[str] = None) -> RepoProvider:
    """Get appropriate repository provider based on URL.

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
