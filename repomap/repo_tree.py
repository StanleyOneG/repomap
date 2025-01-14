"""Module for generating repository AST tree."""

import os
from typing import Dict, Optional, Any, List
import json
import gitlab
from tree_sitter import Node
from .config import settings
from .core import fetch_repo_structure, GitLabFetcher
from .callstack import CallStackGenerator

class RepoTreeGenerator:
    """Class for generating repository AST tree."""

    def __init__(self, token: Optional[str] = None):
        """Initialize the repository tree generator.
        
        Args:
            token: Optional GitLab access token for authentication
        """
        self.token = token or (settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else None)
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

    def _find_functions(self, node: Node, functions: Dict[str, Any], current_class: Optional[str] = None) -> None:
        """Recursively find all function definitions in the AST.
        
        Args:
            node: Current AST node
            functions: Dictionary to store function data
            current_class: Name of the current class if inside one
        """
        # Process function definitions
        if node.type in ('function_definition', 'method_definition'):
            # Find function name
            name_node = None
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
                    if child.type == 'block':
                        body_node = child
                        break
                
                if body_node:
                    # Process the function body for calls
                    calls = self._find_function_calls(body_node)
                    # Also process the function node itself for decorators and defaults
                    calls.extend(self._find_function_calls(node))
                    functions[func_name] = {
                        "name": func_name,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0],
                        "class": current_class,
                        "calls": list(set(calls))  # Remove duplicates
                    }
        
        # Process class definitions
        elif node.type == 'class_definition':
            class_name = None
            for child in node.children:
                if child.type == 'identifier':
                    class_name = child.text.decode('utf8')
                    break
            
            if class_name:
                # Find the class body
                body_node = None
                for child in node.children:
                    if child.type == 'block':
                        body_node = child
                        break
                
                if body_node:
                    # Process class body with updated current_class
                    for child in body_node.children:
                        self._find_functions(child, functions, class_name)
        
        # Continue traversing
        for child in node.children:
            if child.type not in ('block', 'suite'):  # Skip blocks we've already processed
                self._find_functions(child, functions, current_class)

    def _find_function_calls(self, node: Node) -> List[str]:
        """Find all function calls within a node.
        
        Args:
            node: AST node to search
            
        Returns:
            List[str]: List of function names that are called
        """
        calls = []
        
        def get_call_name(node: Node) -> Optional[str]:
            """Extract the full name of a function call."""
            if node.type == 'identifier':
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
            if node.type == 'call':
                # Get the function being called
                func_node = None
                for child in node.children:
                    if child.type in ('identifier', 'attribute'):
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
                if child.type not in ('string', 'integer', 'float', 'comment', 'parameters', 'keyword'):
                    visit(child)

        # Start from the function body
        for child in node.children:
            if child.type == 'block':
                visit(child)
                break
        
        # Also visit the function node itself for decorators and defaults
        visit(node)
        
        return list(set(calls))  # Remove duplicates

    def _parse_file_ast(self, content: str, lang: str) -> Dict[str, Any]:
        """Parse file content into AST data.
        
        Args:
            content: File content
            lang: Programming language identifier
            
        Returns:
            Dict[str, Any]: AST data including functions, classes, and their relationships
        """
        parser = self.parsers[lang]
        tree = parser.parse(bytes(content, 'utf8'))
        
        ast_data = {
            "functions": {},
            "classes": {},
            "calls": [],
            "imports": []
        }
        
        # Find all functions and their calls
        self._find_functions(tree.root_node, ast_data["functions"])
        
        # Extract class information
        def find_classes(node: Node):
            if node.type == 'class_definition':
                for child in node.children:
                    if child.type == 'identifier':
                        class_name = child.text.decode('utf8')
                        ast_data["classes"][class_name] = {
                            "name": class_name,
                            "start_line": node.start_point[0],
                            "end_line": node.end_point[0],
                            "methods": [
                                func_name for func_name, func_data in ast_data["functions"].items()
                                if func_data["class"] == class_name
                            ]
                        }
                        break
            for child in node.children:
                find_classes(child)
        
        find_classes(tree.root_node)
        
        # Extract all calls for easier querying
        for func_name, func_data in ast_data["functions"].items():
            for call in func_data["calls"]:
                ast_data["calls"].append({
                    "name": call,
                    "line": func_data["start_line"],  # Approximate line number
                    "caller": func_name,
                    "class": func_data["class"]
                })
        
        # Extract imports
        def find_imports(node: Node):
            if node.type == 'import_statement':
                for child in node.children:
                    if child.type == 'dotted_name':
                        ast_data["imports"].append(child.text.decode('utf8'))
            for child in node.children:
                find_imports(child)
        
        find_imports(tree.root_node)
        
        return ast_data

    def generate_repo_tree(self, repo_url: str) -> Dict[str, Any]:
        """Generate repository AST tree.
        
        Args:
            repo_url: URL to the repository
            
        Returns:
            Dict[str, Any]: Repository AST tree data
        """
        
        # Fetch repository structure
        repo_structure = fetch_repo_structure(repo_url, self.token)
        
        repo_tree = {
            "metadata": {
                "url": repo_url
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
                                # Extract project path from URL
                                fetcher = GitLabFetcher(self.token)
                                group_path, project_name = fetcher._get_project_parts(repo_url)
                                project_path = f"{group_path}/{project_name}"
                                
                                # Get project's default branch
                                project = self.gl.projects.get(project_path)
                                default_branch = project.default_branch or 'master'
                                
                                # Get file content using default branch
                                content = self._get_file_content(f"{repo_url}/-/blob/{default_branch}/{path}")
                                if content:
                                    ast_data = self._parse_file_ast(content, lang)
                                    repo_tree["files"][path] = {
                                        "language": lang,
                                        "ast": ast_data
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
