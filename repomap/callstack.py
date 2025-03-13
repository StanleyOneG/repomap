"""Module for generating call stacks using tree-sitter."""

import json
import warnings

# Suppress the tree-sitter Language deprecation warning
warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tree_sitter_languages import get_language, get_parser

from .providers import get_provider


class CallStackGenerator:
    """Class for generating call stacks from source code using tree-sitter."""

    SUPPORTED_LANGUAGES = {
        '.c': 'c',
        '.cc': 'c',
        '.cpp': 'cpp',
        '.py': 'python',
        '.php': 'php',
        '.go': 'go',
        '.cs': 'c_sharp',
        '.java': 'java',
        '.js': 'javascript',
    }

    def __init__(
        self,
        token: Optional[str] = None,
    ):
        """Initialize the call stack generator.

        Args:
            token: Optional GitLab access token for authentication
        """
        self.parsers = {}
        self.queries = {}
        self.token = token
        self.provider = None  # Will be initialized when needed based on repo URL
        self._init_parsers()

    def _init_parsers(self):
        """Initialize tree-sitter parsers and queries for supported languages."""
        queries_dir = Path(__file__).parent / "queries"

        for ext, lang in self.SUPPORTED_LANGUAGES.items():
            try:
                parser = get_parser(lang)
                language = get_language(lang)
                query_file = queries_dir / f"tree-sitter-{lang}-tags.scm"

                if query_file.exists():
                    query = language.query(query_file.read_text())
                    self.parsers[lang] = parser
                    self.queries[lang] = query
            except Exception as e:
                print(f"Failed to initialize parser for {lang}: {e}")

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
        ext = os.path.splitext(file_path)[1].lower()
        return self.SUPPORTED_LANGUAGES.get(ext)

    def _find_function_at_line(  # noqa: C901
        self, tree, line: int
    ) -> Optional[Tuple[str, int, int]]:
        """Find function definition containing the specified line.

        Args:
            tree: Tree-sitter AST
            line: Line number to find

        Returns:
            Tuple[str, int, int]: Function name, start line, end line or None if not found
        """
        cursor = tree.walk()

        def visit_node():
            if cursor.node.type in (
                'function_definition',
                'method_definition',
                'function_declaration',
            ):
                start_line = cursor.node.start_point[0]
                end_line = cursor.node.end_point[0]

                if start_line <= line <= end_line:
                    # Handle different function declaration patterns
                    func_name = None

                    # For C++ methods and functions
                    if cursor.node.type == 'function_definition':
                        declarator = next(
                            (
                                c
                                for c in cursor.node.children
                                if c.type == 'function_declarator'
                            ),
                            None,
                        )
                        if declarator:
                            # Handle qualified identifiers (class methods)
                            name_node = next(
                                (
                                    c
                                    for c in declarator.children
                                    if c.type
                                    in (
                                        'identifier',
                                        'qualified_identifier',
                                        'field_identifier',
                                    )
                                ),
                                None,
                            )
                            if name_node:
                                func_name = name_node.text.decode('utf8')

                    # For C functions and other cases
                    if not func_name:
                        # Get the full text of the function definition for C functions with pointers
                        full_func_text = cursor.node.text.decode('utf8')
                        lines = full_func_text.split('\n')

                        # For C functions with pointer return types (like "*func_name")
                        if len(lines) > 0:
                            # Extract the function declaration line(s)
                            declaration = '\n'.join(
                                lines[: min(3, len(lines))]
                            )  # Take first few lines

                            # Find opening parenthesis of parameters
                            paren_pos = declaration.find('(')
                            if paren_pos > 0:
                                # Get everything before the parenthesis
                                before_paren = declaration[:paren_pos].strip()

                                # Handle pointer functions like "*func_name" or "type *func_name"
                                if '*' in before_paren:
                                    # The function name is typically the last identifier before the parenthesis
                                    # It might have a * prefix or a * might be between type and name
                                    parts = before_paren.replace('*', ' * ').split()

                                    # Find the last part that's not a pointer symbol
                                    for i in range(len(parts) - 1, -1, -1):
                                        if parts[i] != '*':
                                            func_name = parts[i]
                                            break
                                else:
                                    # For regular functions, the name is the last part
                                    parts = before_paren.split()
                                    if parts:
                                        func_name = parts[-1]

                        # Fallback to the original method if we couldn't extract the name
                        if not func_name:
                            for child in cursor.node.children:
                                if child.type == 'function_declarator':
                                    for subchild in child.children:
                                        if subchild.type == 'identifier':
                                            func_name = subchild.text.decode('utf8')
                                            break
                                elif child.type == 'identifier':
                                    func_name = child.text.decode('utf8')
                                    break

                    if func_name:
                        return (func_name, start_line, end_line)

            if cursor.goto_first_child():
                result = visit_node()
                if result:
                    return result
                cursor.goto_parent()

            if cursor.goto_next_sibling():
                result = visit_node()
                if result:
                    return result

            return None

        return visit_node()

    def _find_function_calls(
        self, tree, query, start_line: int, end_line: int
    ) -> Set[str]:
        """Find all function calls within a line range.

        Args:
            tree: Tree-sitter AST
            query: Tree-sitter query
            start_line: Start line number
            end_line: End line number

        Returns:
            Set[str]: Set of function names that are called
        """
        calls = set()
        captures = query.captures(tree.root_node)

        for node, tag in captures:
            if tag == 'name.reference.call':
                line = node.start_point[0]
                if start_line <= line <= end_line:
                    calls.add(node.text.decode('utf8'))

        return calls

    def generate_call_stack(self, target_file: str, line_number: int) -> List[Dict]:
        """Generate call stack from a given line in a file.

        Args:
            target_file: URL to the target file
            line_number: Line number to analyze

        Returns:
            List[Dict]: Call stack information
        """
        lang = self._detect_language(target_file)
        if not lang or lang not in self.parsers:
            raise ValueError(f"Unsupported file type: {target_file}")

        content = self._get_file_content(target_file)
        if not content:
            raise ValueError(f"Failed to fetch content from {target_file}")

        parser = self.parsers[lang]
        query = self.queries[lang]

        tree = parser.parse(bytes(content, 'utf8'))

        # Get function start and end lines
        if line_number is not None:
            # Find the function containing the target line
            func_info = self._find_function_at_line(tree, line_number)
            if not func_info:
                raise ValueError(f"No function found at line {line_number}")
            func_name, start_line, end_line = func_info
        elif start_line is not None:
            # Use the provided start line and find the function there
            func_info = self._find_function_at_line(tree, start_line)
            if not func_info:
                raise ValueError(f"No function found at line {start_line}")
            func_name, start_line, end_line = func_info
        else:
            raise ValueError("Either line_number or start_line must be provided")

        # Find all function calls within this function
        calls = self._find_function_calls(tree, query, start_line, end_line)

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
    ) -> Dict[str, str]:
        """Get the content of a function by its name using the repository tree.
        If multiple functions with the same name exist in different classes,
        returns content for all of them.

        Args:
            ast_tree: Path to the repository tree JSON file, Dictionary with repository tree itself
            function_name: Name of the function to find (without class prefix)

        Returns:
            Dict[str, str]: Dictionary mapping class names (or 'global' for non-class functions)
                           to function content strings

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

        # Search for function in all files
        found_functions = {}
        for file_path, file_data in repo_tree['files'].items():
            if 'ast' not in file_data or 'functions' not in file_data['ast']:
                continue

            functions = file_data['ast']['functions']
            for func_key, func_info in functions.items():
                # Check if this function matches the name we're looking for
                if func_info['name'] == function_name:
                    # Create file URL
                    file_url = (
                        f"{repo_tree['metadata']['url']}/-/blob/{ref}/{file_path}"
                    )
                    lang = file_data['language']

                    # Get function content
                    content = self._get_function_content(
                        file_url, lang, start_line=func_info['start_line']
                    )

                    # Use class name as key, or 'global' for functions not in a class
                    class_name = func_info['class'] if func_info['class'] else 'global'
                    found_functions[class_name] = content

        if not found_functions:
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
        if not lang or lang not in self.parsers:
            raise ValueError(f"Unsupported file type: {file_url}")

        content = self._get_file_content(file_url)
        if not content:
            raise ValueError(f"Failed to fetch content from {file_url}")

        parser = self.parsers[lang]
        tree = parser.parse(bytes(content, 'utf8'))

        # Get function start and end lines
        if line_number is not None:
            # Find the function containing the target line
            func_info = self._find_function_at_line(tree, line_number)
            if not func_info:
                raise ValueError(f"No function found at line {line_number}")
            func_name, start_line, end_line = func_info
        elif start_line is not None:
            # Use the provided start line and find the function there
            func_info = self._find_function_at_line(tree, start_line)
            if not func_info:
                raise ValueError(f"No function found at line {start_line}")
            func_name, start_line, end_line = func_info
        else:
            raise ValueError("Either line_number or start_line must be provided")

        # Get the function content by extracting the lines
        lines = content.splitlines()
        function_lines = lines[start_line : end_line + 1]
        return '\n'.join(function_lines)
