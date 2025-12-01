"""Module for generating call stacks using ast-grep."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .ast_grep_utils import AstGrepParser
from .providers import get_provider


class CallStackGenerator:
    """Class for generating call stacks from source code using ast-grep."""

    # For backward compatibility
    SUPPORTED_LANGUAGES = AstGrepParser.SUPPORTED_LANGUAGES

    def __init__(
        self,
        token: Optional[str] = None,
    ):
        """Initialize the call stack generator.

        Args:
            token: Optional GitLab access token for authentication
        """
        self.ast_grep = AstGrepParser()
        self.token = token
        self.provider = None  # Will be initialized when needed based on repo URL
        # For backward compatibility with tests
        self.parsers = {'python': True, 'c': True, 'cpp': True, 'go': True, 'java': True, 'php': True, 'csharp': True, 'javascript': True}
        self.queries = {'python': True, 'c': True, 'cpp': True, 'go': True, 'java': True, 'php': True, 'csharp': True, 'javascript': True}

    def _get_file_content(self, file_url: str) -> Optional[str]:
        """Fetch file content from URL.

        Args:
            file_url: URL to the file

        Returns:
            str: File content or None if failed
        """
        try:
            # Initialize provider if needed
            if not self.provider:
                self.provider = get_provider(file_url, self.token)
            return self.provider.get_file_content(file_url)
        except Exception as e:
            print(f"Failed to fetch file content from {file_url}: {e}")
            return None

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            str: Language identifier or None if unsupported
        """
        return self.ast_grep.detect_language(file_path)

    def _find_function_at_line(
        self, content: str, lang: str, line: int
    ) -> Optional[Tuple[str, int, int]]:
        """Find function definition containing the specified line.

        Args:
            content: Source code content
            lang: Programming language
            line: Line number to find

        Returns:
            Tuple[str, int, int]: Function name, start line, end line or None if not found
        """
        root = self.ast_grep.parse_code(content, lang)
        if not root:
            return None

        func_info = self.ast_grep.find_function_at_line(root, line, lang)
        if func_info:
            return (func_info['name'], func_info['start_line'], func_info['end_line'])

        return None

    def _find_function_calls(
        self, content: str, lang: str, start_line: int, end_line: int
    ) -> Set[str]:
        """Find all function calls within a line range.

        Args:
            content: Source code content
            lang: Programming language
            start_line: Start line number
            end_line: End line number

        Returns:
            Set[str]: Set of function names that are called
        """
        root = self.ast_grep.parse_code(content, lang)
        if not root:
            return set()

        return self.ast_grep.find_function_calls(root, lang, start_line, end_line)

    def generate_call_stack(self, target_file: str, line_number: int) -> List[Dict]:
        """Generate call stack from a given line in a file.

        Args:
            target_file: URL to the target file
            line_number: Line number to analyze

        Returns:
            List[Dict]: Call stack information
        """
        lang = self._detect_language(target_file)
        if not lang:
            raise ValueError(f"Unsupported file type: {target_file}")

        content = self._get_file_content(target_file)
        if not content:
            raise ValueError(f"Failed to fetch content from {target_file}")

        # Find the function containing the target line
        func_info = self._find_function_at_line(content, lang, line_number)
        if not func_info:
            raise ValueError(f"No function found at line {line_number}")

        func_name, start_line, end_line = func_info

        # Find all function calls within this function
        calls = self._find_function_calls(content, lang, start_line, end_line)

        # Build the call stack
        call_stack = [
            {
                'function': func_name,
                'file': target_file,
                'line': line_number,
                'calls': list(calls),
            }
        ]

        return call_stack

    def save_call_stack(self, call_stack: List[Dict], output_file: str):
        """Save call stack to a file.

        Args:
            call_stack: Call stack information
            output_file: Path to output file
        """
        with open(output_file, 'w') as f:
            json.dump(call_stack, f, indent=2)

    def get_function_content_by_line(self, file_url: str, line_number: int) -> str:
        """Get the content of the function containing the specified line.

        Args:
            file_url: URL to the target file
            line_number: Line number within the function

        Returns:
            str: Content of the function

        Raises:
            ValueError: If no function is found or file type is unsupported
        """
        lang = self._detect_language(file_url)
        return self._get_function_content(file_url, lang, line_number=line_number)

    def get_function_content_by_name(  # noqa: C901
        self,
        ast_tree: str | dict,
        function_name: str,
        file_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """Get the content of a function by its name using the repository tree.
        If multiple functions with the same name exist in different files or classes,
        returns content for all of them.

        Args:
            ast_tree: Path to the repository tree JSON file, Dictionary with repository tree itself
            function_name: Name of the function to find (without class prefix)
            file_path: Optional file path to search in. If provided, only searches in that
                      specific file. The path should match the key in the repo tree's files dict.

        Returns:
            Dict[str, str]: Dictionary mapping keys to function content strings.
                           Key format is "file_path:class_or_global" (e.g., "src/main.py:global"
                           or "src/utils.py:ClassName") to handle functions with the same name
                           in different files.

        Raises:
            ValueError: If no function is found with the given name
        """
        if isinstance(ast_tree, str):
            # Load repo tree
            try:
                with open(ast_tree) as f:
                    repo_tree = json.load(f)
            except FileNotFoundError:
                raise ValueError(f"Repository tree file not found: {ast_tree}")
        elif isinstance(ast_tree, dict):
            repo_tree = ast_tree
        else:
            raise ValueError("Invalid ast_tree type")

        # Get repository URL from metadata
        if 'metadata' not in repo_tree or 'url' not in repo_tree['metadata']:
            raise ValueError("Invalid repository tree file: missing metadata.url")

        # Get ref from metadata
        if 'ref' not in repo_tree['metadata']:
            raise ValueError("Repository tree is missing ref in metadata")
        ref = repo_tree['metadata']['ref']

        # Determine which files to search
        if file_path is not None:
            # Search only in the specified file
            if file_path not in repo_tree['files']:
                raise ValueError(f"File not found in repository tree: {file_path}")
            files_to_search = {file_path: repo_tree['files'][file_path]}
        else:
            # Search in all files
            files_to_search = repo_tree['files']

        # Search for function in selected files
        found_functions = {}
        for current_file_path, file_data in files_to_search.items():
            if 'ast' not in file_data or 'functions' not in file_data['ast']:
                continue

            functions = file_data['ast']['functions']
            for func_key, func_info in functions.items():
                # Check if this function matches the name we're looking for
                if func_info['name'] == function_name:
                    # Create file URL
                    file_url = (
                        f"{repo_tree['metadata']['url']}/-/blob/{ref}/{current_file_path}"
                    )
                    lang = file_data['language']

                    # Get function content
                    content = self._get_function_content(
                        file_url, lang, start_line=func_info['start_line']
                    )

                    # Use composite key: "file_path:class_or_global" for uniqueness
                    class_name = func_info['class'] if func_info['class'] else 'global'
                    key = f"{current_file_path}:{class_name}"
                    found_functions[key] = content

        if not found_functions:
            if file_path is not None:
                raise ValueError(
                    f"No function found with name: {function_name} in file: {file_path}"
                )
            raise ValueError(f"No function found with name: {function_name}")

        return found_functions

    def _get_function_content(
        self,
        file_url: str,
        lang: str,
        line_number: Optional[int] = None,
        start_line: Optional[int] = None,
    ) -> str:
        """Internal method to get function content either by line number or start line.

        Args:
            file_url: URL to the target file
            lang: Programming language
            line_number: Optional line number within function
            start_line: Optional start line of function

        Returns:
            str: Content of the function

        Raises:
            ValueError: If no function is found or file type is unsupported
        """
        if not lang:
            raise ValueError(f"Unsupported file type: {file_url}")

        content = self._get_file_content(file_url)
        if not content:
            raise ValueError(f"Failed to fetch content from {file_url}")

        # Get function start and end lines
        if line_number is not None:
            # Find the function containing the target line
            func_info = self._find_function_at_line(content, lang, line_number)
            if not func_info:
                raise ValueError(f"No function found at line {line_number}")
            func_name, start_line, end_line = func_info
        elif start_line is not None:
            # Use the provided start line and find the function there
            func_info = self._find_function_at_line(content, lang, start_line)
            if not func_info:
                raise ValueError(f"No function found at line {start_line}")
            func_name, start_line, end_line = func_info
        else:
            raise ValueError("Either line_number or start_line must be provided")

        # Get the function content by extracting the lines
        lines = content.splitlines()
        function_lines = lines[start_line : end_line + 1]
        return '\n'.join(function_lines)
