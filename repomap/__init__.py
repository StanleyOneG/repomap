"""Repository Map Generator for GitLab and GitHub repositories.

This library provides functionality to generate AST trees from Git repositories,
analyze code structure, and track function calls across the codebase.

Example:
    >>> from repomap import RepoTreeGenerator
    >>> generator = RepoTreeGenerator(token="your_token")
    >>> tree = generator.generate_repo_tree("https://github.com/user/repo")
    >>> generator.save_repo_tree(tree, "output.json")

    # Or use the lower-level API
    >>> from repomap import fetch_repo_structure
    >>> structure = fetch_repo_structure("https://github.com/user/repo", token="your_token")
"""

from .callstack import CallStackGenerator
from .core import fetch_repo_structure
from .repo_tree import RepoTreeGenerator

__version__ = "0.1.0"

__all__ = ["RepoTreeGenerator", "fetch_repo_structure", "CallStackGenerator"]
