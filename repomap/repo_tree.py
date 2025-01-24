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

# Set up debug logging
# logging.basicConfig(level=logging.DEBUG)


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
        self.provider = None  # Will be initialized when needed based on repo URL

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

                    # Log function discovery
                    logger.debug(
                        f"Found function: {func_name} in class: {current_class} "
                        f"at lines {node.start_point[0]}-{node.end_point[0]}"
                    )

                    # Create a unique key for the function that includes class context
                    func_key = (
                        f"{current_class}.{func_name}" if current_class else func_name
                    )
                    functions[func_key] = {
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
                    # Process all nodes within the class body recursively
                    for child in body_node.children:
                        self._find_functions(child, functions, class_name, lang)

        # Continue traversing if not in a class body
        if not current_class:
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
                    # Log class discovery
                    logger.debug(f"Found class: {class_name}")

                    # Check for inheritance
                    base_classes = []
                    for child in node.children:
                        if child.type == 'argument_list':
                            for arg in child.children:
                                if arg.type == 'identifier':
                                    base_name = arg.text.decode('utf8')
                                    base_classes.append(base_name)
                                    logger.debug(
                                        f"Found base class: {base_name} for {class_name}"
                                    )
                                elif arg.type == 'attribute':
                                    # Handle module.class style base classes
                                    parts = []
                                    current = arg
                                    while current:
                                        if current.type == 'identifier':
                                            parts.insert(0, current.text.decode('utf8'))
                                            break
                                        elif current.type == 'attribute':
                                            for subchild in reversed(current.children):
                                                if subchild.type == 'identifier':
                                                    parts.insert(
                                                        0, subchild.text.decode('utf8')
                                                    )
                                                    break
                                            current = current.children[0]
                                        else:
                                            break
                                    if parts:
                                        base_name = '.'.join(parts)
                                        base_classes.append(base_name)
                                        logger.debug(
                                            f"Found qualified base class: {base_name} for {class_name}"
                                        )

                    # Get all methods for this class by filtering functions with this class
                    methods = [
                        func_data["name"]
                        for func_key, func_data in ast_data["functions"].items()
                        if func_data["class"] == class_name
                    ]
                    logger.debug(f"Methods found for {class_name}: {methods}")

                    ast_data["classes"][class_name] = {
                        "name": class_name,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0],
                        "base_classes": base_classes,
                        "methods": methods,
                    }

            for child in node.children:
                find_classes(child)

        find_classes(tree.root_node)

        # Process __init__ methods to find instance variables
        for class_name, class_data in ast_data["classes"].items():
            if '__init__' in class_data["methods"]:
                func_key = f"{class_name}.__init__"
                if func_key in ast_data["functions"]:
                    # Re-parse the function body to find instance variables
                    init_content = content.split('\n')[ast_data["functions"][func_key]["start_line"]:ast_data["functions"][func_key]["end_line"]+1]
                    init_node = parser.parse(bytes('\n'.join(init_content), 'utf8')).root_node
                    class_data["instance_vars"] = self._find_instance_vars(init_node, lang)

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

        # Resolve method calls using instance variables
        for func_key, func_data in ast_data["functions"].items():
            if func_data["class"]:
                class_name = func_data["class"]
                if class_name in ast_data["classes"]:
                    instance_vars = ast_data["classes"][class_name].get("instance_vars", {})
                    resolved_calls = []
                    for call in func_data["calls"]:
                        parts = call.split('.')
                        if len(parts) >= 2 and parts[0] == 'self' and parts[1] in instance_vars:
                            # Replace self.attr with the class name
                            new_parts = [instance_vars[parts[1]]] + parts[2:]
                            resolved_call = '.'.join(new_parts)
                            resolved_calls.append(resolved_call)
                        else:
                            resolved_calls.append(call)
                    # Update the calls list, removing duplicates
                    func_data["calls"] = list(set(resolved_calls))

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

    def _find_instance_vars(self, node: Node, lang: str) -> Dict[str, str]:
        """Find instance variables initialized with class instances in __init__ method."""
        instance_vars = {}
        def visit(n: Node):
            if lang == 'python' and n.type == 'assignment':
                target = None
                value = None
                # Extract target and value from assignment
                for child in n.children:
                    if child.type == 'attribute':
                        target = child
                    elif child.type == 'call':
                        value = child
                    elif child.type == '=' and len(n.children) >= 3:
                        target = n.children[0]
                        value = n.children[2]
                if target and value and target.type == 'attribute' and value.type == 'call':
                    # Check if target is self.attribute
                    obj = target.children[0]
                    if obj.type == 'identifier' and obj.text.decode('utf8') == 'self':
                        attr = target.children[1].text.decode('utf8')
                        # Check if value is a class constructor call
                        func = value.children[0]
                        if func.type == 'identifier':
                            class_name = func.text.decode('utf8')
                            instance_vars[attr] = class_name
                        elif func.type == 'attribute':
                            # Handle cases like module.ClassName()
                            class_name = func.children[-1].text.decode('utf8')
                            instance_vars[attr] = class_name
            for child in n.children:
                visit(child)
        visit(node)
        return instance_vars

    @staticmethod
    def _process_file_worker(
        file_info: Tuple[str, Dict[str, Any], str, str, Optional[str]]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process a single file and return its AST data.

        Args:
            file_info: Tuple containing (path, item, repo_url, ref, token)

        Returns:
            Tuple[str, Optional[Dict[str, Any]]]: File path and its AST data if successful
        """
        path, item, repo_url, ref, token = file_info

        # Create a new instance for this process
        processor = RepoTreeGenerator(token=token)
        try:
            # Only process supported file types
            lang = processor._detect_language(path)
            if lang:
                # Get file content using the correct ref
                content = processor._get_file_content(f"{repo_url}/-/blob/{ref}/{path}")
                if content:
                    ast_data = processor._parse_file_ast(content, lang)
                    return path, {
                        "language": lang,
                        "ast": ast_data,
                    }
        except Exception as e:
            print(f"Failed to process {path}: {e}")
        return path, None

    def generate_repo_tree(  # noqa: C901
        self, repo_url: str, ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate repository AST tree.

        Args:
            repo_url: URL to the repository
            ref: Optional git reference (branch, tag, commit). If not provided, uses default branch.

        Returns:
            Dict[str, Any]: Repository AST tree data

        Raises:
            ValueError: If provided ref does not exist in the repository
        """
        # Initialize provider if needed
        if not self.provider:
            self.provider = get_provider(repo_url, self.token)

        # Validate ref and get default if not provided
        try:
            ref = self.provider.validate_ref(repo_url, ref)
        except ValueError as e:
            raise e
        except Exception as e:
            logger.warning(f"Failed to get default branch: {e}")
            ref = 'main'

        # Fetch repository structure
        try:
            repo_structure = self.provider.fetch_repo_structure(repo_url, ref=ref)
        except Exception as e:
            if "not found or is empty" in str(e):
                raise ValueError(f"No ref found in repository by name: {ref}")
            raise

        repo_tree = {"metadata": {"url": repo_url, "ref": ref}, "files": {}}

        # Collect all files to process
        files_to_process = []

        def collect_files(structure: Dict[str, Any], current_path: str = ""):
            """Recursively collect files from repository structure."""
            if not isinstance(structure, dict):
                return

            for name, item in structure.items():
                path = os.path.join(current_path, name)

                if isinstance(item, dict):
                    if "type" in item and item["type"] == "blob":
                        files_to_process.append((path, item, repo_url, ref))
                    else:
                        # This is a directory
                        collect_files(item, path)

        collect_files(repo_structure)

        # Process files
        if self.use_multiprocessing and len(files_to_process) > 0:
            # Process in parallel
            num_processes = min(multiprocessing.cpu_count(), len(files_to_process))
            # Add token to file_info for worker processes
            files_to_process_mp = [
                (path, item, repo_url, ref, self.token)
                for path, item, repo_url, ref in files_to_process
            ]

            with multiprocessing.Pool(processes=num_processes) as pool:
                results = pool.map(
                    RepoTreeGenerator._process_file_worker, files_to_process_mp
                )

                # Add successful results to repo_tree
                for path, data in results:
                    if data is not None:
                        repo_tree["files"][path] = data
        else:
            # Process sequentially (for testing or small number of files)
            for path, item, repo_url, ref in files_to_process:
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
        return repo_tree

    def save_repo_tree(self, repo_tree: Dict[str, Any], output_path: str):
        """Save repository AST tree to a file.

        Args:
            repo_tree: Repository AST tree data
            output_path: Path to output file
        """
        with open(output_path, 'w') as f:
            json.dump(repo_tree, f, indent=2)