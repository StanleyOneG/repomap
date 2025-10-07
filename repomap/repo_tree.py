"""Module for generating repository AST tree using ast-grep."""

import json
import logging
import multiprocessing
import os
import signal
import time
from typing import Any, Dict, List, Optional, Tuple

from .ast_grep_utils import AstGrepParser
from .providers import get_provider

logger = logging.getLogger(__name__)

# Global parser instance for worker processes (initialized once per worker)
_worker_parser = None


def _get_worker_parser():
    """Get or create the parser instance for this worker process."""
    global _worker_parser
    if _worker_parser is None:
        _worker_parser = AstGrepParser()
    return _worker_parser


class TimeoutError(Exception):
    """Raised when AST parsing exceeds the timeout."""

    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("AST parsing timed out")


def with_timeout(timeout_seconds: int):
    """Decorator to add timeout to function execution."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Set up the signal alarm
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Clean up the alarm
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


class RepoTreeGenerator:
    """Class for generating repository AST tree using ast-grep."""

    def __init__(
        self,
        token: Optional[str] = None,
        use_multiprocessing: bool = True,
        use_local_clone: bool = True,
    ):
        """Initialize the repository tree generator.

        Args:
            token: Optional GitLab access token for authentication
            use_multiprocessing: Whether to use multiprocessing for file processing
            use_local_clone: Whether to use local cloning for improved performance (default: True)
        """
        self.token = token
        self.use_multiprocessing = use_multiprocessing
        self.use_local_clone = use_local_clone
        self.ast_grep = AstGrepParser()
        self.provider = None
        self._local_clone_path = None

    def _get_file_content(self, file_url: str) -> Optional[str]:
        """Fetch file content from URL.

        Args:
            file_url: URL to the file

        Returns:
            str: File content or None if failed
        """
        try:
            if not self.provider:
                self.provider = get_provider(file_url, self.token, self.use_local_clone)
            return self.provider.get_file_content(file_url)
        except Exception as e:
            logger.debug(f"Failed to fetch file content from {file_url}: {e}")
            return None

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            str: Language identifier or None if unsupported
        """
        return self.ast_grep.detect_language(file_path)

    @with_timeout(30)  # 30 second timeout for AST parsing
    def _parse_file_ast(self, content: str, lang: str) -> Dict[str, Any]:
        """Parse file AST using ast-grep.

        Args:
            content: Source code content
            lang: Programming language

        Returns:
            Dictionary with AST data
        """
        return self.ast_grep.extract_comprehensive_ast_data(content, lang)

    @staticmethod
    def _process_file_worker(
        file_info: Tuple[
            str, Dict[str, Any], str, str, Optional[str], bool, Optional[str]
        ]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Worker function for multiprocessing file parsing.

        Args:
            file_info: Tuple containing file processing information

        Returns:
            Tuple of file path and parsed data
        """
        path, item, repo_url, ref, token, use_local_clone, local_clone_path = file_info

        # Use global parser instance to avoid re-initialization overhead
        parser = _get_worker_parser()

        try:
            start_time = time.time()
            lang = parser.detect_language(path)
            if not lang:
                return path, None

            content = None
            if use_local_clone and local_clone_path:
                # Read from local filesystem (pre-cloned by main process)
                from pathlib import Path

                file_path = Path(local_clone_path) / path
                if not file_path.exists() or not file_path.is_file():
                    return path, None

                # Read file regardless of size - we want complete processing
                try:
                    # Read entire file content without size limits
                    with open(file_path, 'rb') as f:
                        content_bytes = f.read()  # Read entire file
                    content = content_bytes.decode('utf-8', errors='ignore')
                except (OSError, UnicodeDecodeError):
                    return path, None
            else:
                # Use API method - this should be rare with local clone enabled
                content = processor._get_file_content(f"{repo_url}/-/blob/{ref}/{path}")
                if not content:
                    return path, None

            # Only skip truly empty files - process everything else
            if not content:
                return path, None

            # More permissive binary file check - only skip obvious binary files
            null_count = content[:5000].count('\0')  # Check first 5KB
            if null_count > 10:  # Allow some null bytes but skip obviously binary files
                return path, None

            try:
                # Use parser directly instead of creating a new RepoTreeGenerator
                ast_data = parser.extract_comprehensive_ast_data(content, lang)
                elapsed = time.time() - start_time
                if elapsed > 1:  # Log files taking more than 1 second
                    logger.info(f"Parsed {path} ({lang}) in {elapsed:.2f}s")
                return path, {"language": lang, "ast": ast_data}
            except Exception as e:
                logger.debug(f"Error parsing {path} ({lang}): {e}")
                return path, None
        except Exception:
            pass

        return path, None

    def generate_repo_tree(  # noqa: C901
        self,
        repo_url: str,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate repository AST tree.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)

        Returns:
            Dictionary containing repository AST tree
        """
        if not self.provider:
            self.provider = get_provider(repo_url, self.token, self.use_local_clone)

        # Store original ref for cache key consistency
        original_ref = ref

        # Fetch repo structure first (this handles ref validation and cloning)
        try:
            repo_structure = self.provider.fetch_repo_structure(repo_url, ref=ref)
        except Exception as e:
            # Handle various error messages that indicate invalid ref specifically
            error_str = str(e).lower()
            # Only catch ref-specific errors, not general repository not found errors
            if ref and any(
                msg in error_str
                for msg in ["tree not found", "is empty", "invalid reference"]
            ):
                raise ValueError(f"No ref found in repository by name: {ref}")
            raise

        # Get the actual ref that was used (in case ref was None)
        if not ref:
            # If no ref was provided, get the default branch
            ref = self.provider.validate_ref(repo_url, None)

        # Get commit hash (API-first for speed, with clone fallback)
        last_commit_hash = self.provider.get_last_commit_hash(repo_url, ref)

        repo_tree = {
            "metadata": {
                "url": repo_url,
                "ref": ref,
                "last_commit_hash": last_commit_hash,
            },
            "files": {},
        }

        files_to_process = []

        def collect_files(structure: Dict[str, Any], current_path: str = ""):
            for name, item in structure.items():
                path = os.path.join(current_path, name)
                if isinstance(item, dict):
                    if "type" in item and item["type"] == "blob":
                        files_to_process.append((path, item, repo_url, ref))
                    else:
                        collect_files(item, path)

        collect_files(repo_structure)

        # Get local clone path if using local clone
        local_clone_path = None
        if self.use_local_clone and hasattr(self.provider, '_cloned_repos'):
            # Use original ref for cache key consistency with cloning
            cache_key = f"{repo_url}#{original_ref or 'default'}"
            local_clone_path = str(self.provider._cloned_repos.get(cache_key, ''))

        if self.use_multiprocessing and files_to_process:
            files_to_process_mp = [
                (
                    path,
                    item,
                    repo_url,
                    ref,
                    self.token,
                    self.use_local_clone,
                    local_clone_path,
                )
                for path, item, repo_url, ref in files_to_process
            ]

            # Optimized resource constraints
            cpu_count = multiprocessing.cpu_count()
            max_workers = min(
                len(files_to_process),
                max(1, cpu_count - 1),  # Use cpu_count - 1, but at least 1
            )
            logger.info(f"Processing {len(files_to_process)} files with {max_workers} workers")

            with multiprocessing.Pool(
                processes=max_workers,
                maxtasksperchild=100,  # Increased batch size for better efficiency
            ) as pool:
                # Use imap_unordered for progress tracking
                results_iter = pool.imap_unordered(self._process_file_worker, files_to_process_mp, chunksize=10)
                processed = 0
                parsed_count = 0
                for path, data in results_iter:
                    if data:
                        repo_tree["files"][path] = data
                        parsed_count += 1
                    processed += 1
                    if processed % 100 == 0:
                        logger.info(f"Processed {processed}/{len(files_to_process)} files ({parsed_count} parsed)")
                logger.info(f"Completed: {parsed_count}/{len(files_to_process)} files successfully parsed")
        else:
            for path, item, repo_url, ref in files_to_process:
                try:
                    start_time = time.time()
                    lang = self._detect_language(path)
                    if lang:
                        if self.use_local_clone and local_clone_path:
                            # Read from local filesystem
                            from pathlib import Path

                            file_path = Path(local_clone_path) / path
                            if file_path.exists() and file_path.is_file():
                                content = file_path.read_text(
                                    encoding='utf-8', errors='ignore'
                                )
                            else:
                                continue
                        else:
                            # Use API method
                            content = self._get_file_content(
                                f"{repo_url}/-/blob/{ref}/{path}"
                            )

                        if content:
                            try:
                                ast_data = self._parse_file_ast(content, lang)
                                elapsed = time.time() - start_time
                                if elapsed > 10:  # Log slow files
                                    logger.warning(
                                        f"Slow AST parsing for {path} ({lang}): {elapsed:.2f}s"
                                    )
                                repo_tree["files"][path] = {
                                    "language": lang,
                                    "ast": ast_data,
                                }
                            except TimeoutError:
                                logger.error(
                                    f"AST parsing timeout for {path} ({lang}) after 30s"
                                )
                                continue
                            except Exception as e:
                                logger.error(
                                    f"AST parsing error for {path} ({lang}): {e}"
                                )
                                continue
                except Exception as e:
                    logger.error(f"Error processing {path}: {e}")
                    continue

        # Cleanup temporary clones if using LocalRepoProvider
        if hasattr(self.provider, 'cleanup'):
            self.provider.cleanup()

        return repo_tree

    def is_repo_tree_up_to_date(
        self,
        repo_url: str,
        ref: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> bool:
        """Check if repo-tree is up to date by comparing commit hashes.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)
            output_path: Path to existing repo-tree file to check

        Returns:
            bool: True if repo-tree is up to date, False if needs regeneration
        """
        # Quick check - if file doesn't exist, no need to do expensive operations
        if not output_path or not os.path.exists(output_path):
            return False

        try:
            # Load existing repo-tree
            with open(output_path, 'r') as f:
                existing_repo_tree = json.load(f)

            existing_metadata = existing_repo_tree.get('metadata', {})
            existing_url = existing_metadata.get('url')
            existing_ref = existing_metadata.get('ref')
            existing_hash = existing_metadata.get('last_commit_hash')

            # Quick checks first - avoid expensive operations
            if existing_url != repo_url:
                return False

            # Check if existing repo-tree has commit hash
            if not existing_hash:
                return False

            if not self.provider:
                self.provider = get_provider(repo_url, self.token, self.use_local_clone)

            # Only validate ref if we need to (when ref is provided and different from stored)
            current_ref = ref
            if not ref:
                # If no ref provided, we need to get the default
                current_ref = self.provider.validate_ref(repo_url, ref)
            elif ref != existing_ref:
                # Only validate if the refs are different
                current_ref = self.provider.validate_ref(repo_url, ref)
                if existing_ref != current_ref:
                    return False
            else:
                # Use the existing ref if it matches what we're asking for
                current_ref = existing_ref

            # Get current commit hash
            current_hash = self.provider.get_last_commit_hash(repo_url, current_ref)
            if not current_hash:
                return False

            # Compare hashes
            return existing_hash == current_hash

        except Exception as e:
            print(f"Error checking repo-tree status: {e}")
            return False

    def generate_repo_tree_if_needed(
        self,
        repo_url: str,
        ref: Optional[str] = None,
        output_path: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Generate repo-tree only if needed (commit hash has changed) or force is True.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit)
            output_path: Path to save/check existing repo-tree file
            force: Force regeneration even if up to date

        Returns:
            Dict[str, Any]: Repository tree data
        """
        # Check if regeneration is needed
        if (
            not force
            and output_path
            and self.is_repo_tree_up_to_date(repo_url, ref, output_path)
        ):
            print(
                f"Repository AST tree is up to date (no changes in commit hash). Loading existing tree."
            )
            with open(output_path, 'r') as f:
                return json.load(f)

        print("Repository has changes, generating new AST tree...")
        repo_tree = self.generate_repo_tree(repo_url, ref)

        if output_path:
            self.save_repo_tree(repo_tree, output_path)
            print(f"Repository AST tree saved to {output_path}")

        return repo_tree

    def save_repo_tree(self, repo_tree: Dict[str, Any], output_path: str):
        """Save repository tree to a file.

        Args:
            repo_tree: Repository tree data
            output_path: Path to output file
        """
        with open(output_path, 'w') as f:
            json.dump(repo_tree, f, indent=2)
