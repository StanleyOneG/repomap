"""Module for generating repository AST tree."""

import os
import logging
from typing import Dict, Optional, Any, List
import json
import gitlab
from tree_sitter import Node
from .config import settings
from .core import fetch_repo_structure, GitLabFetcher
from .callstack import CallStackGenerator

logger = logging.getLogger(__name__)

class RepoTreeGenerator:
    """Class for generating repository AST tree."""

    def __init__(self, token: Optional[str] = None):
        """Initialize the repository tree generator.

        Args:
            token: Optional GitLab access token for authentication
        """
        self.token = token or (
            settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else None
        )
        self.call_stack_gen = CallStackGenerator(token=self.token)
        self.parsers = self.call_stack_gen.parsers
        self.queries = self.call_stack_gen.queries
        self.gl = gitlab.Gitlab(settings.GITLAB_BASE_URL, private_token=self.token)

    def _get_file_content(self, file_url: str) -> Optional[str]:
        """Fetch file content from URL using CallStackGenerator's implementation.

        Args:
            file_url: URL to the file

        Returns:
            str: File content or None if failed
        """
        return self.call_stack_gen._get_file_content(file_url)

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension using CallStackGenerator's implementation.

        Args:
            file_path: Path to the file

        Returns:
            str: Language identifier or None if unsupported
        """
        return self.call_stack_gen._detect_language(file_path)

    def _find_functions(  # noqa: C901
        self,
        node: Node,
        functions: Dict[str, Any],
        current_class: Optional[str] = None,
        lang: str = 'python',
    ) -> None:
        """Recursively find all function definitions in the AST.

        Args:
            node: Current AST node
            functions: Dictionary to store function data
            current_class: Name of the current class if inside one
            lang: Programming language being parsed
        """
        # Process function definitions
        if node.type in ('function_definition', 'method_definition') or (
            lang in ('c', 'cpp') and node.type == 'declaration'
        ):
            name_node = None

            if lang in ('c', 'cpp') and node.type == 'declaration':
                # Handle C/C++ function declarations
                for child in node.children:
                    if child.type == 'function_declarator':
                        for subchild in child.children:
                            if subchild.type == 'identifier':
                                name_node = subchild
                                break
                        break
            else:
                # Handle Python-style function definitions
                for child in node.children:
                    if child.type == 'identifier':
                        name_node = child
                        break
                    elif child.type == 'function_declarator':
                        for subchild in child.children:
                            if subchild.type == 'identifier':
                                name_node = subchild
                                break

            if name_node:
                func_name = name_node.text.decode('utf8')
                # Find the function body
                body_node = None
                for child in node.children:
                    if child.type in ('block', 'compound_statement'):
                        body_node = child
                        break

                if body_node or lang in (
                    'c',
                    'cpp',
                ):  # C/C++ might have declarations without bodies
                    # Process the function body for calls if it exists
                    calls = []
                    if body_node:
                        calls = self._find_function_calls(body_node, lang)
                        # Also process the function node itself for decorators and defaults
                        calls.extend(self._find_function_calls(node, lang))

                    functions[func_name] = {
                        "name": func_name,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0],
                        "class": current_class,
                        "calls": list(set(calls)),  # Remove duplicates
                    }

        # Process class/struct definitions
        elif node.type == 'class_definition' or (
            lang in ('c', 'cpp')
            and node.type in ('struct_specifier', 'type_definition')
        ):
            class_name = None

            if lang in ('c', 'cpp') and node.type == 'type_definition':
                # Handle typedef struct cases
                for child in node.children:
                    if child.type == 'type_identifier':
                        class_name = child.text.decode('utf8')
                        break
                    elif child.type == 'struct_specifier':
                        for subchild in child.children:
                            if subchild.type == 'type_identifier':
                                class_name = subchild.text.decode('utf8')
                                break
            elif lang in ('c', 'cpp') and node.type == 'struct_specifier':
                # Handle direct struct definitions
                for child in node.children:
                    if child.type == 'type_identifier':
                        class_name = child.text.decode('utf8')
                        break
            else:
                # Handle Python-style class definitions
                for child in node.children:
                    if child.type == 'identifier':
                        class_name = child.text.decode('utf8')
                        break

            if class_name:
                # Find the class/struct body
                body_node = None
                for child in node.children:
                    if child.type in ('block', 'field_declaration_list'):
                        body_node = child
                        break

                if body_node:
                    # Process class body with updated current_class
                    for child in body_node.children:
                        self._find_functions(child, functions, class_name, lang)

        # Continue traversing
        for child in node.children:
            if child.type not in (
                'block',
                'suite',
                'compound_statement',
            ):  # Skip blocks we've already processed
                self._find_functions(child, functions, current_class, lang)

    def _find_function_calls(  # noqa: C901
        self, node: Node, lang: str = 'python'
    ) -> List[str]:
        """Find all function calls within a node.

        Args:
            node: AST node to search
            lang: Programming language being parsed

        Returns:
            List[str]: List of function names that are called
        """
        calls = []

        def get_call_name(node: Node) -> Optional[str]:
            """Extract the full name of a function call."""
            if node.type == 'identifier':
                return node.text.decode('utf8')
            elif node.type == 'field_identifier':  # For C/C++ struct field access
                return node.text.decode('utf8')
            elif node.type == 'attribute':
                parts = []
                current = node
                while current:
                    if current.type == 'identifier':
                        parts.insert(0, current.text.decode('utf8'))
                        break
                    elif current.type == 'attribute':
                        # Get the rightmost identifier
                        for child in reversed(current.children):
                            if child.type == 'identifier':
                                parts.insert(0, child.text.decode('utf8'))
                                break
                        # Move to the left part
                        current = current.children[0]
                    else:
                        break
                return '.'.join(parts) if parts else None
            return None

        def visit(node: Node):
            """Visit each node in the AST."""
            # Handle function calls
            if node.type == 'call' or (
                lang in ('c', 'cpp') and node.type == 'call_expression'
            ):
                # Get the function being called
                func_node = None
                for child in node.children:
                    if child.type in ('identifier', 'attribute', 'field_identifier'):
                        func_node = child
                        break

                if func_node:
                    name = get_call_name(func_node)
                    if name:
                        calls.append(name)
                        # For method calls, also add the base name
                        if '.' in name:
                            calls.append(name.split('.')[-1])

            # Visit all children
            for child in node.children:
                # Skip certain node types that won't contain calls
                if child.type not in (
                    'string',
                    'integer',
                    'float',
                    'comment',
                    'parameters',
                    'keyword',
                    'string_literal',
                    'number_literal',
                ):
                    visit(child)

        # Start from the function body
        for child in node.children:
            if child.type in ('block', 'compound_statement'):
                visit(child)
                break

        # Also visit the function node itself for decorators and defaults
        visit(node)

        return list(set(calls))  # Remove duplicates

    def _parse_file_ast(self, content: str, lang: str) -> Dict[str, Any]:  # noqa: C901
        """Parse file content into AST data.

        Args:
            content: File content
            lang: Programming language identifier

        Returns:
            Dict[str, Any]: AST data including functions, classes, and their relationships
        """
        parser = self.parsers[lang]
        tree = parser.parse(bytes(content, 'utf8'))

        ast_data = {"functions": {}, "classes": {}, "calls": [], "imports": []}

        # Find all functions and their calls
        self._find_functions(tree.root_node, ast_data["functions"], lang=lang)

        # Extract class/struct information
        def find_classes(node: Node):
            if node.type == 'class_definition' or (
                lang in ('c', 'cpp')
                and node.type in ('struct_specifier', 'type_definition')
            ):
                class_name = None

                if lang in ('c', 'cpp') and node.type == 'type_definition':
                    # Handle typedef struct cases
                    for child in node.children:
                        if child.type == 'type_identifier':
                            class_name = child.text.decode('utf8')
                            break
                        elif child.type == 'struct_specifier':
                            for subchild in child.children:
                                if subchild.type == 'type_identifier':
                                    class_name = subchild.text.decode('utf8')
                                    break
                elif lang in ('c', 'cpp') and node.type == 'struct_specifier':
                    # Handle direct struct definitions
                    for child in node.children:
                        if child.type == 'type_identifier':
                            class_name = child.text.decode('utf8')
                            break
                else:
                    # Handle Python-style class definitions
                    for child in node.children:
                        if child.type == 'identifier':
                            class_name = child.text.decode('utf8')
                            break

                if class_name:
                    ast_data["classes"][class_name] = {
                        "name": class_name,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0],
                        "methods": [
                            func_name
                            for func_name, func_data in ast_data["functions"].items()
                            if func_data["class"] == class_name
                        ],
                    }

            for child in node.children:
                find_classes(child)

        find_classes(tree.root_node)

        # Extract all calls for easier querying
        for func_name, func_data in ast_data["functions"].items():
            for call in func_data["calls"]:
                ast_data["calls"].append(
                    {
                        "name": call,
                        "line": func_data["start_line"],  # Approximate line number
                        "caller": func_name,
                        "class": func_data["class"],
                    }
                )

        # Extract imports
        def find_imports(node: Node):
            if node.type == 'import_statement':
                for child in node.children:
                    if child.type == 'dotted_name':
                        ast_data["imports"].append(child.text.decode('utf8'))
            elif lang in ('c', 'cpp') and node.type == 'preproc_include':
                # Handle C/C++ #include statements
                for child in node.children:
                    if child.type in ('string_literal', 'system_lib_string'):
                        include_path = child.text.decode('utf8').strip('"<>')
                        ast_data["imports"].append(include_path)

            for child in node.children:
                find_imports(child)

        find_imports(tree.root_node)

        return ast_data

    def generate_repo_tree(self, repo_url: str) -> Dict[str, Any]:  # noqa: C901
        """Generate repository AST tree.

        Args:
            repo_url: URL to the repository

        Returns:
            Dict[str, Any]: Repository AST tree data
        """
        # Get repository structure using GitLabFetcher
        fetcher = GitLabFetcher(token=self.token)
        
        # Get project's default branch
        try:
            group_path, project_name = fetcher._get_project_parts(repo_url)
            project_path = f"{group_path}/{project_name}"
            project = self.gl.projects.get(project_path)
            ref = project.default_branch
        except Exception as e:
            logger.warning(f"Failed to get default branch: {e}")
            ref = 'master'

        # Fetch repository structure
        repo_structure = fetcher.fetch_repo_structure(repo_url)

        repo_tree = {
            "metadata": {
                "url": repo_url,
                "ref": ref
            },
            "files": {}
        }

        def process_files(structure: Dict[str, Any], current_path: str = ""):
            """Recursively process files in repository structure."""
            if not isinstance(structure, dict):
                return

            for name, item in structure.items():
                path = os.path.join(current_path, name)

                if isinstance(item, dict):
                    if "type" in item and item["type"] == "blob":
                        try:
                            # Only process supported file types
                            lang = self._detect_language(path)
                            if lang:
                                # Get file content using the correct ref
                                content = self._get_file_content(
                                    f"{repo_url}/-/blob/{ref}/{path}"
                                )
                                if content:
                                    ast_data = self._parse_file_ast(content, lang)
                                    repo_tree["files"][path] = {
                                        "language": lang,
                                        "ast": ast_data,
                                    }
                        except Exception as e:
                            print(f"Failed to process {path}: {e}")
                    else:
                        # This is a directory
                        process_files(item, path)

        process_files(repo_structure)
        return repo_tree

    def save_repo_tree(self, repo_tree: Dict[str, Any], output_path: str):
        """Save repository AST tree to a file.

        Args:
            repo_tree: Repository AST tree data
            output_path: Path to output file
        """
        with open(output_path, 'w') as f:
            json.dump(repo_tree, f, indent=2)
