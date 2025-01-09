"""Core functionality for fetching and processing GitLab repositories."""

from typing import Dict, List, Optional
import logging
import gitlab
from urllib.parse import urlparse, quote

logger = logging.getLogger(__name__)

class GitLabFetcher:
    """Class for fetching repository data from GitLab."""

    def __init__(self, base_url: str = "https://git-testing.devsec.astralinux.ru", token: Optional[str] = None):
        """Initialize GitLab fetcher.
        
        Args:
            base_url (str): Base URL for GitLab instance
            token (Optional[str]): GitLab access token for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.gl = gitlab.Gitlab(self.base_url, private_token=token)

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
                raise ValueError("Invalid repository URL: must be in format 'group/repo' or 'group/subgroup/repo'")
            
            # Last part is the project name, everything before is the group path
            project_name = path_parts[-1]
            group_path = '/'.join(path_parts[:-1])
            
            return group_path, project_name
            
        except Exception as e:
            raise ValueError(f"Invalid repository URL: {str(e)}")

    def fetch_repo_structure(self, repo_url: str, ref: str = "main") -> Dict:
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
                    raise gitlab.exceptions.GitlabGetError(f"Project not found: {project_path}")
            
            # Get repository tree recursively
            items = []
            page = 1
            
            while True:
                batch = project.repository_tree(
                    ref=ref,
                    recursive=True,
                    all=True,
                    per_page=100,
                    page=page
                )
                
                if not batch:
                    break
                    
                items.extend(batch)
                page += 1

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
