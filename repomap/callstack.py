"""Module for generating call stacks using tree-sitter."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
import gitlab
from tree_sitter_languages import get_language, get_parser
from .config import settings


class CallStackGenerator:
    """Class for generating call stacks from source code using tree-sitter."""

    SUPPORTED_LANGUAGES = {
        '.c': 'c',
        '.cpp': 'cpp',
        '.py': 'python',
        '.php': 'php',
        '.go': 'go',
        '.cs': 'c_sharp',
        '.java': 'java',
        '.js': 'javascript',
    }

    def __init__(
        self, structure_file: Optional[str] = None, token: Optional[str] = None
    ):
        """Initialize the call stack generator.

        Args:
            structure_file: Optional path to the JSON file containing repository structure
            token: Optional GitLab access token for authentication
        """
        self.repo_structure = (
            self._load_structure(structure_file) if structure_file else {}
        )
        self.parsers = {}
        self.queries = {}
        self.token = token or (
            settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else None
        )
        self._init_parsers()

    def _load_structure(self, structure_file: Optional[str]) -> dict:
        """Load repository structure from JSON file.

        Args:
            structure_file: Optional path to the JSON file

        Returns:
            dict: Repository structure
        """
        if not structure_file:
            return {}
        with open(structure_file) as f:
            return json.load(f)

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

    def _get_gitlab_content(self, file_url: str) -> Optional[str]:
        """Fetch content from GitLab URL.

        Args:
            file_url: GitLab URL to the file

        Returns:
            str: File content or None if failed
        """
        try:
            # Remove the base URL to get the project path and file info
            if not file_url.startswith(settings.GITLAB_BASE_URL):
                return None

            remaining_path = file_url[len(settings.GITLAB_BASE_URL) :].strip('/')

            # Split into project path and file info
            parts = remaining_path.split('/-/')
            if len(parts) != 2:
                return None

            project_path = parts[0].strip('/')  # e.g., "astra/acl"
            file_info = parts[1].strip('/')  # e.g., "blob/1.7.0/libacl/acl_add_perm.c"

            # Parse file info to get ref and file path
            file_parts = file_info.split('/')
            if len(file_parts) < 3 or file_parts[0] != 'blob':
                return None

            ref = file_parts[1]  # e.g., "1.7.0"
            file_path = '/'.join(file_parts[2:])  # e.g., "libacl/acl_add_perm.c"

            print("Parsed URL components:")
            print(f"  Project path: {project_path}")
            print(f"  Ref: {ref}")
            print(f"  File path: {file_path}")

            # Initialize GitLab client
            gl = gitlab.Gitlab(settings.GITLAB_BASE_URL, private_token=self.token)

            try:
                project = gl.projects.get(project_path)
            except gitlab.exceptions.GitlabGetError:
                # If direct path fails, try with URL encoding
                from urllib.parse import quote

                encoded_path = quote(project_path, safe='')
                project = gl.projects.get(encoded_path)

            # Get file content
            f = project.files.get(file_path=file_path, ref=ref)
            return f.decode().decode('utf-8')
        except Exception as e:
            print(f"Failed to fetch GitLab content: {e}")
            return None

    def _get_file_content(self, file_url: str) -> Optional[str]:
        """Fetch file content from URL.

        Args:
            file_url: URL to the file

        Returns:
            str: File content or None if failed
        """
        try:
            # First try GitLab-specific handling
            content = self._get_gitlab_content(file_url)
            # if content is not None:
            return content

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
                    # For C functions, we need to handle the function_declarator
                    for child in cursor.node.children:
                        if child.type == 'function_declarator':
                            for subchild in child.children:
                                if subchild.type == 'identifier':
                                    return (
                                        subchild.text.decode('utf8'),
                                        start_line,
                                        end_line,
                                    )
                        elif child.type == 'identifier':
                            return (child.text.decode('utf8'), start_line, end_line)

            # Continue traversing
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

    def get_function_content_by_name(self, repo_tree_path: str, function_name: str) -> str:
        """Get the content of a function by its name using the repository tree.

        Args:
            repo_tree_path: Path to the repository tree JSON file
            function_name: Name of the function to find

        Returns:
            str: Content of the function

        Raises:
            ValueError: If no function is found with the given name
        """
        # Load repo tree
        with open(repo_tree_path) as f:
            repo_tree = json.load(f)

        # Get repository URL from metadata
        if 'metadata' not in repo_tree or 'url' not in repo_tree['metadata']:
            raise ValueError("Invalid repository tree file: missing metadata.url")

        # Search for function in all files
        for file_path, file_data in repo_tree['files'].items():
            if 'ast' not in file_data or 'functions' not in file_data['ast']:
                continue

            functions = file_data['ast']['functions']
            if function_name in functions:
                function_info = functions[function_name]
                # Get ref from metadata
                if 'ref' not in repo_tree['metadata']:
                    raise ValueError("Repository tree is missing ref in metadata")
                ref = repo_tree['metadata']['ref']
                file_url = f"{repo_tree['metadata']['url']}/-/blob/{ref}/{file_path}"
                lang = file_data['language']
                return self._get_function_content(
                    file_url, lang, start_line=function_info['start_line']
                )

        raise ValueError(f"No function found with name: {function_name}")

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
