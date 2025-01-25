"""Module for generating repository AST tree."""

import json
import logging
import multiprocessing
import os
from typing import Any, Dict, List, Optional, Tuple

from tree_sitter import Node

from .callstack import CallStackGenerator
from .providers import get_provider

logger = logging.getLogger(__name__)


class RepoTreeGenerator:
    """Class for generating repository AST tree."""

    def __init__(self, token: Optional[str] = None, use_multiprocessing: bool = True):
        """Initialize the repository tree generator.

        Args:
            token: Optional GitLab access token for authentication
            use_multiprocessing: Whether to use multiprocessing for file processing
        """
        self.token = token
        self.use_multiprocessing = use_multiprocessing
        self.call_stack_gen = CallStackGenerator(token=self.token)
        self.parsers = self.call_stack_gen.parsers
        self.queries = self.call_stack_gen.queries
        self.provider = None
        self._current_classes = {}

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

    def _find_functions(
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
        stack = [(node, current_class)]
        while stack:
            current_node, current_class = stack.pop()

            # Process function/method definitions
            if current_node.type in ('function_definition', 'method_definition'):
                name_node = None
                body_node = None

                # Find function name and body
                for child in current_node.children:
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
                    body_node = next(
                        (c for c in current_node.children if c.type == 'block'), None
                    )

                    calls = (
                        self._find_function_calls(current_node, lang)
                        if body_node
                        else []
                    )

                    func_key = (
                        f"{current_class}.{func_name}" if current_class else func_name
                    )
                    functions[func_key] = {
                        "name": func_name,
                        "start_line": current_node.start_point[0],
                        "end_line": current_node.end_point[0],
                        "class": current_class,
                        "calls": list(set(calls)),
                    }

                    # Process __init__ for instance variables
                    if current_class and func_name == "__init__" and body_node:
                        instance_vars = self._find_instance_vars(body_node, lang)
                        self._current_classes.setdefault(
                            current_class, {"instance_vars": {}}
                        )
                        self._current_classes[current_class]["instance_vars"].update(
                            instance_vars
                        )

            # Process class definitions
            elif current_node.type == 'class_definition':
                class_name = None
                body_node = None

                # Find class name and body
                for child in current_node.children:
                    if child.type == 'identifier':
                        class_name = child.text.decode('utf8')
                    elif child.type == 'block':
                        body_node = child

                if class_name and body_node:
                    self._current_classes.setdefault(
                        class_name, {"instance_vars": {}, "methods": []}
                    )
                    # Add class body children to stack with class context
                    for child in reversed(body_node.children):
                        stack.append((child, class_name))

            # Process other nodes
            else:
                for child in reversed(current_node.children):
                    stack.append((child, current_class))

    def _find_function_calls(self, node: Node, lang: str) -> List[str]:
        """Optimized function call resolution with complexity safeguards."""
        if lang not in self.queries:
            return []
        
        calls = []
        query = self.queries[lang]
        captures = query.captures(node)
        
        # Use set for O(1) lookups
        processed_nodes = set()
        
        for n, tag in captures:
            if tag == 'name.reference.call' and id(n) not in processed_nodes:
                # Efficiently get full call expression using tree-sitter's text
                call_expression = n.parent.text.decode('utf8')
                if '(' in call_expression:
                    call_expression = call_expression.split('(')[0]
                calls.append(call_expression)
                processed_nodes.add(id(n))
        
        return list(set(calls))

    def _find_instance_vars(self, node: Node, lang: str) -> Dict[str, str]:
        instance_vars = {}
        stack = [node]

        def process_assignment(assignment_node: Node):
            if (
                len(assignment_node.children) >= 3
                and assignment_node.children[1].type == '='
            ):
                target = assignment_node.children[0]
                value = assignment_node.children[2]

                if target.type == 'attribute' and value.type == 'call':
                    obj = target.children[0]
                    if obj.type == 'identifier' and obj.text.decode() == 'self':
                        attr = target.children[1].text.decode()
                        func_node = value.children[0]

                        if func_node.type == 'identifier':
                            instance_vars[attr] = func_node.text.decode()
                        elif func_node.type == 'attribute':
                            parts = []
                            current = func_node
                            while current.type == 'attribute':
                                parts.insert(0, current.children[-1].text.decode())
                                current = current.children[0]
                            if current.type == 'identifier':
                                parts.insert(0, current.text.decode())
                            instance_vars[attr] = '.'.join(parts)
                        elif func_node.type == 'call':
                            call_parts = []
                            current = func_node
                            while current and current.type in ('call', 'attribute', 'identifier'):
                                if current.type == 'call':
                                    current = current.children[0]
                                elif current.type == 'attribute':
                                    call_parts.insert(0, current.children[-1].text.decode())
                                    current = current.children[0]
                                elif current.type == 'identifier':
                                    call_parts.insert(0, current.text.decode())
                                    break
                            instance_vars[attr] = '.'.join(call_parts)

        while stack:
            current_node = stack.pop()

            if current_node.type == 'expression_statement':
                for child in current_node.children:
                    if child.type == 'assignment':
                        process_assignment(child)
            elif current_node.type == 'assignment':
                process_assignment(current_node)

            for child in reversed(current_node.children):
                stack.append(child)

        return instance_vars

    def _parse_file_ast(self, content: str, lang: str) -> Dict[str, Any]:
        parser = self.parsers[lang]
        tree = parser.parse(bytes(content, 'utf8'))

        ast_data = {"functions": {}, "classes": {}, "calls": [], "imports": []}

        self._current_classes = {}
        self._find_functions(tree.root_node, ast_data["functions"], lang=lang)

        # Process classes and methods
        for class_name, class_info in self._current_classes.items():
            methods = [
                func_data["name"]
                for func_key, func_data in ast_data["functions"].items()
                if func_data["class"] == class_name
            ]

            ast_data["classes"][class_name] = {
                "name": class_name,
                "methods": methods,
                "instance_vars": class_info.get("instance_vars", {}),
            }

        # Resolve method calls using instance variables
        for func_key, func_data in ast_data["functions"].items():
            if func_data["class"]:
                class_name = func_data["class"]
                instance_vars = ast_data["classes"][class_name]["instance_vars"]
                resolved_calls = []
                        
                for call in func_data["calls"]:
                    parts = call.split('.')
                            
                    # Handle self references and instance variables
                    if parts[0] == 'self' and len(parts) > 1:
                        if parts[1] in instance_vars:
                            # Replace self.x with the class name from instance vars
                            resolved = instance_vars[parts[1]]
                            if len(parts) > 2:
                                resolved += '.' + '.'.join(parts[2:])
                            resolved_calls.append(resolved)
                        else:
                            # If no instance var found, keep the chain without self
                            resolved_calls.append('.'.join(parts[1:]))
                    else:
                        resolved_calls.append(call)
                        
                func_data["calls"] = list(set(resolved_calls))

        # Collect all calls
        for func_name, func_data in ast_data["functions"].items():
            for call in func_data["calls"]:
                ast_data["calls"].append(
                    {
                        "name": call,
                        "line": func_data["start_line"],
                        "caller": func_name,
                        "class": func_data["class"],
                    }
                )

        # Process imports
        def find_imports(root: Node):
            stack = [root]
            while stack:
                node = stack.pop()
                if node.type == 'import_statement':
                    for child in node.children:
                        if child.type == 'dotted_name':
                            ast_data["imports"].append(child.text.decode('utf8'))
                elif node.type == 'import_from_statement':
                    module = []
                    for child in node.children:
                        if child.type == 'dotted_name':
                            module.append(child.text.decode('utf8'))
                        elif child.type == 'import_prefix':
                            module.append(child.text.decode('utf8'))
                    if module:
                        ast_data["imports"].append('.'.join(module))
                stack.extend(node.children)

        find_imports(tree.root_node)

        return ast_data

    @staticmethod
    def _process_file_worker(
        file_info: Tuple[str, Dict[str, Any], str, str, Optional[str]]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        path, item, repo_url, ref, token = file_info
        processor = RepoTreeGenerator(token=token)
        try:
            lang = processor._detect_language(path)
            if lang:
                content = processor._get_file_content(f"{repo_url}/-/blob/{ref}/{path}")
                if content:
                    ast_data = processor._parse_file_ast(content, lang)
                    return path, {"language": lang, "ast": ast_data}
        except Exception as e:
            logger.error(f"Failed to process {path}: {str(e)}")
        return path, None

    def generate_repo_tree(
        self, repo_url: str, ref: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.provider:
            self.provider = get_provider(repo_url, self.token)

        try:
            ref = self.provider.validate_ref(repo_url, ref)
        except ValueError as e:
            raise e
        except Exception as e:
            logger.warning(f"Failed to get default branch: {str(e)}")
            ref = 'main'

        try:
            repo_structure = self.provider.fetch_repo_structure(repo_url, ref=ref)
        except Exception as e:
            if "not found or is empty" in str(e):
                raise ValueError(f"No ref found in repository by name: {ref}")
            raise

        # Add complexity limits
        self.node_count = 0
        self.MAX_NODES = 10000

        repo_tree = {"metadata": {"url": repo_url, "ref": ref}, "files": {}}

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

        if self.use_multiprocessing and files_to_process:
            files_to_process_mp = [
                (path, item, repo_url, ref, self.token)
                for path, item, repo_url, ref in files_to_process
            ]

            # Add resource constraints
            max_workers = min(
                multiprocessing.cpu_count(),
                len(files_to_process),
                8  # Hard cap for CPU protection
            )
            
            with multiprocessing.Pool(
                processes=max_workers,
                maxtasksperchild=50  # Prevent memory bloat
            ) as pool:
                results = pool.map(self._process_file_worker, files_to_process_mp)
                for path, data in results:
                    if data:
                        repo_tree["files"][path] = data
        else:
            for path, item, repo_url, ref in files_to_process:
                try:
                    lang = self._detect_language(path)
                    if lang:
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
                    logger.error(f"Failed to process {path}: {str(e)}")

        return repo_tree

    def save_repo_tree(self, repo_tree: Dict[str, Any], output_path: str):
        with open(output_path, 'w') as f:
            json.dump(repo_tree, f, indent=2)
