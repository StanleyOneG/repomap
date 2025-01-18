"""Core functionality for fetching and processing GitLab repositories."""

import logging
from typing import Dict, Optional
from urllib.parse import quote, urlparse

import gitlab

from .config import settings

logger = logging.getLogger(__name__)


class GitLabFetcher:
    """Class for fetching repository data from GitLab."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        """Initialize GitLab fetcher.

        Args:
            base_url (Optional[str]): Base URL for GitLab instance.
                                      Uses config value if not provided.
            token (Optional[str]): GitLab access token for authentication.
                                   Uses config value if not provided.
        """
        # If base_url is provided, use it. Otherwise, it will be detected from the first repository URL
        self.base_url = base_url.rstrip('/') if base_url is not None else None
        self.token = token or (settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else None)
        # GitLab client will be initialized when needed since we may need to detect base_url first
        self.gl = None

    def _get_base_url_from_repo_url(self, repo_url: str) -> str:
        """Extract GitLab base URL from repository URL.

        Args:
            repo_url (str): GitLab repository URL

        Returns:
            str: Base URL for GitLab instance

        Raises:
            ValueError: If URL is invalid
        """
        try:
            parsed = urlparse(repo_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception as e:
            raise ValueError(f"Invalid repository URL: {str(e)}")

    def _ensure_gitlab_client(self, repo_url: str):
        """Ensure GitLab client is initialized with correct base URL.

        Args:
            repo_url (str): Repository URL to detect base URL from if needed
        """
        if not self.base_url:
            # If GITLAB_BASE_URL is set in settings, use it
            if settings.GITLAB_BASE_URL:
                self.base_url = settings.GITLAB_BASE_URL.rstrip('/')
            else:
                # Otherwise detect from repo URL
                self.base_url = self._get_base_url_from_repo_url(repo_url)
        
        if not self.gl:
            self.gl = gitlab.Gitlab(self.base_url, private_token=self.token)

    def _get_project_parts(self, repo_url: str) -> tuple[str, str]:
        """Extract group and project name from repository URL.

        Args:
            repo_url (str): GitLab repository URL

        Returns:
            tuple[str, str]: Group name and project name

        Raises:
            ValueError: If URL is invalid or not a repository URL
        """
        try:
            parsed = urlparse(repo_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")

            path = parsed.path.strip('/')
            path_parts = path.split('/')

            # GitLab repository URLs must have at least group/repo format
            if len(path_parts) < 2:
                raise ValueError(
                    "Invalid repository URL: must be in format 'group/repo' or 'group/subgroup/repo'"
                )

            # Last part is the project name, everything before is the group path
            project_name = path_parts[-1]
            group_path = '/'.join(path_parts[:-1])

            return group_path, project_name

        except Exception as e:
            raise ValueError(f"Invalid repository URL: {str(e)}")

    def fetch_repo_structure(  # noqa: C901
        self, repo_url: str, ref: Optional[str] = None
    ) -> Dict:
        """Fetch repository structure from GitLab.

        Args:
            repo_url (str): GitLab repository URL
            ref (str): Git reference (branch/tag/commit)

        Returns:
            Dict: Repository structure as nested dictionary

        Raises:
            gitlab.exceptions.GitlabError: If API request fails
            ValueError: If repository URL is invalid
        """
        try:
            # Initialize GitLab client if needed
            self._ensure_gitlab_client(repo_url)
            
            group_path, project_name = self._get_project_parts(repo_url)

            # Get project instance using the full path
            project_path = f"{group_path}/{project_name}"
            try:
                project = self.gl.projects.get(project_path)
            except gitlab.exceptions.GitlabGetError:
                # If direct path fails, try with URL encoding
                encoded_path = quote(project_path, safe='')
                try:
                    project = self.gl.projects.get(encoded_path)
                except gitlab.exceptions.GitlabGetError:
                    raise gitlab.exceptions.GitlabGetError(
                        f"Project not found: {project_path}"
                    )

            # Use provided ref or get default branch from project
            if not ref:
                ref = project.default_branch

            if not ref:
                raise gitlab.exceptions.GitlabError(
                    "Repository appears to be empty (no default branch)"
                )

            # Get repository tree recursively
            items = []
            page = 1
            per_page = 100
            max_pages = 100  # Safety limit

            try:
                while page <= max_pages:
                    batch = project.repository_tree(
                        ref=ref, recursive=True, per_page=per_page, page=page
                    )

                    if not batch:
                        break

                    items.extend(batch)

                    # If we got fewer items than per_page, we've hit the last page
                    if len(batch) < per_page:
                        break

                    page += 1

                if page > max_pages:
                    logger.warning(
                        f"Reached maximum page limit ({max_pages}), repository may be truncated"
                    )
            except gitlab.exceptions.GitlabError as e:
                if "Tree Not Found" in str(e):
                    raise gitlab.exceptions.GitlabError(
                        f"Repository branch '{ref}' not found or is empty"
                    )
                raise

            if not items:
                raise gitlab.exceptions.GitlabError("Repository is empty")

            # Convert flat list to nested dictionary structure
            root = {}
            for item in items:
                path = item['path']
                parts = path.split('/')
                current = root

                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                current[parts[-1]] = item

            return root

        except gitlab.exceptions.GitlabError as e:
            logger.error(f"Failed to fetch repository structure: {e}")
            raise


def fetch_repo_structure(repo_url: str, token: Optional[str] = None) -> Dict:
    """Convenience function to fetch repository structure.

    Args:
        repo_url (str): GitLab repository URL
        token (Optional[str]): GitLab access token

    Returns:
        Dict: Repository structure
    """
    fetcher = GitLabFetcher(token=token)
    return fetcher.fetch_repo_structure(repo_url)
