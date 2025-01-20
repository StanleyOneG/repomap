"""Core functionality for repository map generation."""

import logging
from typing import Dict, Optional

from .providers import get_provider

logger = logging.getLogger(__name__)


def fetch_repo_structure(repo_url: str, token: Optional[str] = None) -> Dict:
    """Fetch repository structure.

    Args:
        repo_url: URL to the repository
        token: Optional access token for authentication

    Returns:
        Dict: Repository structure
    """
    provider = get_provider(repo_url, token)
    return provider.fetch_repo_structure(repo_url)
