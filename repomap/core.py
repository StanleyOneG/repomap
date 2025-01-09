"""Core functionality for fetching and processing GitLab repositories."""

from typing import Dict, List, Optional
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class GitLabFetcher:
    """Class for fetching repository data from GitLab."""

    def __init__(self, base_url: str = "https://gitlab.com", token: Optional[str] = None):
        """Initialize GitLab fetcher.
        
        Args:
            base_url (str): Base URL for GitLab instance
            token (Optional[str]): GitLab access token for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({'PRIVATE-TOKEN': token})

    def _get_project_id(self, repo_url: str) -> str:
        """Extract project ID from repository URL.
        
        Args:
            repo_url (str): GitLab repository URL
            
        Returns:
            str: Project ID or path
            
        Raises:
            ValueError: If URL is invalid or not a repository URL
        """
        try:
            parsed = urlparse(repo_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
                
            path = parsed.path.strip('/')
            path_parts = path.split('/')
            
            # GitLab repository URLs must have at least user/repo format
            if len(path_parts) < 2:
                raise ValueError("Invalid repository URL: must be in format 'user/repo' or 'group/subgroup/repo'")
                
            # Return the path as-is, URL encoding will be handled by requests
            return path
            
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
            requests.exceptions.RequestException: If API request fails
            ValueError: If repository URL is invalid
        """
        project_id = self._get_project_id(repo_url)
        
        try:
            # Get repository tree recursively
            # URL encode the project ID for the API request
            from urllib.parse import quote
            encoded_project_id = quote(project_id, safe='')
            url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/repository/tree"
            items = []
            page = 1
            
            while True:
                params = {
                    'ref': ref,
                    'recursive': True,
                    'per_page': 100,
                    'page': page
                }
                
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                batch = response.json()
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

        except requests.exceptions.RequestException as e:
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
