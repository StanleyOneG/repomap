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
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


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
        self.method_return_types = {}  # Track method return types for variable resolution

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
                        self._find_function_calls(current_node, lang, current_class)
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
                        "local_vars": {},  # Initialize local_vars
                    }

                    # Extract return type for Python
                    if lang == 'python' and current_class:
                        return_type = None
                        return_type_node = next(
                            (c for c in current_node.children if c.type == 'return_type'),
                            None
                        )
                        if return_type_node:
                            # Get first meaningful type node (supports identifiers, subscriptions, etc.)
                            type_node = next(
                                (c for c in return_type_node.children 
                                 if c.type in ('identifier', 'subscript', 'attribute', 'type', 'string')),
                                None
                            )
                            if type_node:
                                return_type = type_node.text.decode('utf8')
                                # Strip quotes from string-based forward references
                                if type_node.type == 'string':
                                    return_type = return_type.strip("'\"")
                        if return_type:
                            self.method_return_types.setdefault(current_class, {})[func_name] = return_type

                    # Process __init__ for instance variables
                    if current_class and func_name == "__init__" and body_node:
                        instance_vars = self._find_instance_vars(body_node, current_class)
                        self._current_classes.setdefault(
                            current_class, {"instance_vars": {}}
                        )
                        self._current_classes[current_class]["instance_vars"].update(
                            instance_vars
                        )

                    # Capture local variable types for the function
                    if body_node:
                        local_vars = self._find_instance_vars(body_node, current_class)
                        functions[func_key]["local_vars"] = local_vars

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

    def _find_function_calls(  
        self,  
        node: Node,  
        lang: str,  
        current_class: Optional[str] = None,  
        local_vars: Dict[str, str] = {},  
    ) -> List[str]:  
        if lang not in self.queries:  
            return []  
        
        calls = []  
        query = self.queries[lang]  
        captures = query.captures(node)  
        
        for n, tag in captures:  
            if tag == 'name.reference.call':  
                call_parts = []  
                current_node = n  
                skip_self = False  
                
                if current_node.type == 'attribute':  
                    parts = []  
                    current = current_node  
                    while current.type == 'attribute':  
                        if len(current.children) >= 3:  
                            parts.insert(0, current.children[2].text.decode('utf8'))  
                        current = current.children[0]  
                    if current.type == 'identifier':  
                        parts.insert(0, current.text.decode('utf8'))  
                    call_parts = parts  
                else:  
                    call_parts = [current_node.text.decode('utf8')]  
    
                if call_parts and call_parts[0] == 'self':  
                    call_parts = call_parts[1:]  
                    skip_self = True  
    
                resolved = []  
                if current_class and call_parts:  
                    class_info = self._current_classes.get(current_class, {})  
                    instance_vars = class_info.get("instance_vars", {})  
                    class_methods = class_info.get("methods", [])  
                    found_var = False  
                    
                    for part in call_parts:  
                        if part in local_vars and not found_var:  
                            resolved.extend(local_vars[part].split('.'))  
                            found_var = True  
                            logger.debug(f"Resolved variable '{part}' to '{local_vars[part]}'")  
                        elif part in instance_vars and not found_var:  
                            resolved.extend(instance_vars[part].split('.'))  
                            found_var = True  
                            logger.debug(f"Resolved instance variable '{part}' to '{instance_vars[part]}'")  
                        else:  
                            resolved.append(part)  
                    
                    if skip_self and not found_var:  
                        if call_parts[0] in class_methods:  
                            resolved.insert(0, current_class)  
                            found_var = True  
                            logger.debug(f"Resolved method call on self: '{current_class}.{call_parts[0]}'")  
                        else:  
                            resolved.insert(0, current_class)  
                            logger.debug(f"Resolved call on self to class: '{current_class}'")  
    
                if resolved:  
                    final_call = '.'.join(resolved)  
                    if final_call != '__init__':  
                        calls.append(final_call)  
                        logger.debug(f"Added resolved call: {final_call}")  
                elif not resolved and call_parts:  
                    final_call = '.'.join(call_parts)  
                    if final_call != '__init__':  
                        calls.append(final_call)  
                        logger.debug(f"Added unresolved call: {final_call}")  
    
        return list(set(calls))  

    def find_node_by_range(self, node: Node, start_line: int, end_line: int) -> Optional[Node]:
        """Recursively find a node by its start and end lines.
        
        Args:
            node (Node): Current AST node.
            start_line (int): Starting line number.
            end_line (int): Ending line number.
        
        Returns:
            Optional[Node]: The node matching the specified line range or None.
        """
        if node.start_point[0] == start_line and node.end_point[0] == end_line:
            return node
        for child in node.children:
            result = self.find_node_by_range(child, start_line, end_line)
            if result:
                return result
        return None

    def _find_instance_vars(self, node: Node, current_class: str) -> Dict[str, str]:
        """Track instance variables and local variables within a class.
        
        Args:
            node (Node): The AST node to process.
            current_class (str): The name of the current class.

        Returns:
            Dict[str, str]: A mapping of variable names to their resolved class types.
        """
        instance_vars = {}
        stack = [node]

        while stack:
            current_node = stack.pop()

            # Handle assignments
            if current_node.type in ['assignment', 'augmented_assignment']:
                target = current_node.children[0]
                value = current_node.children[-1]

                # Handle instance variable assignments (self.var = ClassName() or self.var = self.method())
                if target.type == 'attribute':
                    attr_parts = []
                    current = target
                    while current.type == 'attribute':
                        attr_parts.insert(0, current.children[2].text.decode())
                        current = current.children[0]
                    if current.type == 'identifier' and current.text.decode() == 'self':
                        attr = '.'.join(attr_parts)

                        # Get class name from RHS
                        class_name = None
                        if value.type == 'call':
                            fn_node = value.children[0]

                            if fn_node.type == 'attribute':
                                # Extract the method name from attribute (e.g., self.jinja_environment)
                                method_name = fn_node.children[-1].text.decode('utf8')
                                class_name = self.method_return_types.get(current_class, {}).get(method_name)
                            elif fn_node.type == 'identifier':
                                # Direct constructor call (e.g., self.var = ClassName())
                                method_name = fn_node.text.decode('utf8')
                                if method_name[0].isupper():  # Heuristic for class constructors
                                    class_name = method_name

                        # Handle direct constructor calls as fallback
                        if not class_name and value.type == 'call':
                            first_child = value.children[0]
                            if first_child.type == 'identifier':
                                method_name = first_child.text.decode()
                                if method_name[0].isupper():  # Heuristic for class constructors
                                    class_name = method_name

                        if class_name:
                            instance_vars[attr] = class_name
                            logger.debug(f"Captured instance variable: {attr} = {class_name}")

                # Handle local variable assignments (var = ClassName() or var = self.method())
                elif target.type == 'identifier':
                    var_name = target.text.decode()
                    if value.type == 'call':
                        fn_node = value.children[0]
                        method_name = ""
                        if fn_node.type == 'identifier':
                            method_name = fn_node.text.decode()
                        elif fn_node.type == 'attribute':
                            # Extract the method name from attribute (e.g., self.method -> method)
                            if len(fn_node.children) >= 3:
                                method_name = fn_node.children[2].text.decode()

                        if method_name:
                            class_name = self.method_return_types.get(current_class, {}).get(method_name)
                            if class_name:
                                instance_vars[var_name] = class_name
                                logger.debug(f"Captured local variable: {var_name} = {class_name}")
                            elif method_name[0].isupper():  # Heuristic for class constructors
                                instance_vars[var_name] = method_name
                                logger.debug(f"Captured local variable (constructor heuristic): {var_name} = {method_name}")

            stack.extend(reversed(current_node.children))

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

        # Second pass to resolve calls with class context
        for func_key, func_data in ast_data["functions"].items():
            current_class = func_data["class"]
            class_vars = self._current_classes.get(current_class, {}).get("instance_vars", {}) if current_class else {}
            
            # Use the recursive finder to locate the function node
            func_node = self.find_node_by_range(
                tree.root_node,
                func_data["start_line"],
                func_data["end_line"]
            )
        
            if func_node:
                local_vars = func_data.get("local_vars", {})
                resolved_calls = self._find_function_calls(func_node, lang, current_class, local_vars)
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
