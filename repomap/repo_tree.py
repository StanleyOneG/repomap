"""Module for generating repository AST tree."""

import json
import logging
import multiprocessing
import os
import signal
import time
from typing import Any, Dict, List, Optional, Tuple

from tree_sitter import Node

from .callstack import CallStackGenerator
from .providers import get_provider

logger = logging.getLogger(__name__)

# Remove old logging setup as we now use proper logger above

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
    """Class for generating repository AST tree."""

    def __init__(self, token: Optional[str] = None, use_multiprocessing: bool = True, use_local_clone: bool = True):
        """Initialize the repository tree generator.

        Args:
            token: Optional GitLab access token for authentication
            use_multiprocessing: Whether to use multiprocessing for file processing
            use_local_clone: Whether to use local cloning for improved performance (default: True)
        """
        self.token = token
        self.use_multiprocessing = use_multiprocessing
        self.use_local_clone = use_local_clone
        self.call_stack_gen = CallStackGenerator(token=self.token)
        self.parsers = self.call_stack_gen.parsers
        self.queries = self.call_stack_gen.queries
        self.provider = None
        self._current_classes = {}
        self.method_return_types = {}
        self._local_clone_path = None

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
        stack = [(node, current_class)]
        iteration_count = 0
        MAX_ITERATIONS = 50000  # Prevent infinite loops
        
        while stack and iteration_count < MAX_ITERATIONS:
            iteration_count += 1
            current_node, current_class = stack.pop()

            # Process C structs and typedefs
            if lang == 'c':
                # Handle typedef struct
                if current_node.type == 'type_definition':
                    struct_node = None
                    name_node = None

                    for child in current_node.children:
                        if child.type == 'struct_specifier':
                            struct_node = child
                            # Get name from struct specifier if it exists
                            struct_name_node = next(
                                (
                                    c
                                    for c in child.children
                                    if c.type == 'type_identifier'
                                ),
                                None,
                            )
                            if struct_name_node:
                                name_node = struct_name_node
                        elif child.type == 'type_identifier':
                            name_node = child

                    if name_node and struct_node:
                        struct_name = name_node.text.decode('utf8')
                        self._current_classes[struct_name] = {
                            "instance_vars": {},
                            "methods": [],
                            "base_classes": [],
                            "start_line": struct_node.start_point[0],
                            "end_line": current_node.end_point[0],
                        }

                # Handle regular struct definitions
                elif current_node.type == 'struct_specifier':
                    name_node = next(
                        (
                            c
                            for c in current_node.children
                            if c.type == 'type_identifier'
                        ),
                        None,
                    )
                    if name_node:
                        struct_name = name_node.text.decode('utf8')
                        self._current_classes[struct_name] = {
                            "instance_vars": {},
                            "methods": [],
                            "base_classes": [],
                            "start_line": current_node.start_point[0],
                            "end_line": current_node.end_point[0],
                        }

            # Process C++ class definitions
            if lang == 'cpp' and current_node.type == 'class_specifier':
                class_name_node = next(
                    (c for c in current_node.children if c.type == 'type_identifier'),
                    None,
                )
                if class_name_node:
                    current_class = class_name_node.text.decode('utf8')
                    self._current_classes[current_class] = {
                        "instance_vars": {},
                        "methods": [],
                        "base_classes": [],
                        "start_line": current_node.start_point[0],
                        "end_line": current_node.end_point[0],
                    }
                    # Process class body children with class context
                    for child in reversed(current_node.children):
                        if child.type == 'field_declaration_list':
                            for grandchild in reversed(child.children):
                                stack.append((grandchild, current_class))
                        elif child.type == 'declaration_list':
                            for grandchild in reversed(child.children):
                                stack.append((grandchild, current_class))
                    continue

            # Process Go type definitions (structs/interfaces)
            if lang == 'go' and current_node.type == 'type_declaration':
                try:
                    # Handle Go type declarations (struct, interface, etc.)
                    for child in current_node.children[:10]:  # Limit children to prevent excessive iteration
                        if child.type == 'type_spec':
                            type_name_node = None
                            for spec_child in child.children[:5]:  # Limit nested children
                                if spec_child.type == 'type_identifier':
                                    type_name_node = spec_child
                                    break
                            
                            if type_name_node:
                                type_name = type_name_node.text.decode('utf8')
                                self._current_classes[type_name] = {
                                    "instance_vars": {},
                                    "methods": [],
                                    "base_classes": [],
                                    "start_line": current_node.start_point[0],
                                    "end_line": current_node.end_point[0],
                                }
                except Exception as e:
                    logger.warning(f"Error processing Go type declaration: {e}")
                    continue

            # Process function/method definitions
            if current_node.type in ('function_definition', 'method_definition', 'function_declaration', 'method_declaration'):
                name_node = None
                body_node = None

                # Find function name and body
                if lang == 'go':
                    try:
                        # Handle Go function and method declarations with bounds checking
                        if current_node.type == 'function_declaration':
                            # For regular functions: func main() { ... }
                            for child in current_node.children[:10]:  # Limit children iteration
                                if child.type == 'identifier':
                                    name_node = child
                                    break
                        elif current_node.type == 'method_declaration':
                            # For methods: func (u *User) GetName() { ... }
                            # Find the method name (field_identifier)
                            for child in current_node.children[:15]:  # Limit children iteration
                                if child.type == 'field_identifier':
                                    name_node = child
                                    break
                            # Also extract the receiver type for context
                            receiver_type = None
                            for child in current_node.children[:10]:  # Limit iteration
                                if child.type == 'parameter_list':
                                    # This is the receiver parameter list
                                    for param_child in child.children[:5]:  # Limit nested iteration
                                        if param_child.type == 'parameter_declaration':
                                            for param_subchild in param_child.children[:5]:  # Limit nested iteration
                                                if param_subchild.type == 'pointer_type':
                                                    for ptr_child in param_subchild.children[:3]:  # Limit deeply nested iteration
                                                        if ptr_child.type == 'type_identifier':
                                                            receiver_type = ptr_child.text.decode('utf8')
                                                            break
                                                elif param_subchild.type == 'type_identifier':
                                                    receiver_type = param_subchild.text.decode('utf8')
                                            break
                                    break
                            if receiver_type:
                                current_class = receiver_type
                        
                        # Find body node for Go
                        body_node = next(
                            (c for c in current_node.children[:15] if c.type == 'block'), None  # Limit search
                        )
                    except Exception as e:
                        logger.warning(f"Error processing Go function/method declaration: {e}")
                        continue
                elif lang == 'cpp':
                    declarator = next(
                        (
                            c
                            for c in current_node.children
                            if c.type == 'function_declarator'
                        ),
                        None,
                    )
                    if declarator:
                        name_node = next(
                            (
                                c
                                for c in declarator.children
                                if c.type in ('identifier', 'qualified_identifier')
                            ),
                            None,
                        )
                else:
                    # First try to find the function name directly
                    for child in current_node.children:
                        if child.type == 'identifier':
                            name_node = child
                            break
                        elif child.type == 'function_declarator':
                            for subchild in child.children:
                                if subchild.type == 'identifier':
                                    name_node = subchild
                                    break
                    
                    # If name_node is still not found, handle C functions with pointer return types
                    if not name_node and lang == 'c':
                        # Get the full text of the function definition for C functions with pointers
                        full_func_text = current_node.text.decode('utf8')
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
                                            name_node = type('DummyNode', (), {'text': func_name.encode('utf8')})
                                            break
                                else:
                                    # For regular functions, the name is the last part
                                    parts = before_paren.split()
                                    if parts:
                                        func_name = parts[-1]
                                        name_node = type('DummyNode', (), {'text': func_name.encode('utf8')})

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
                        "local_vars": {},
                    }

                    # Extract return type for Python
                    if lang == 'python' and current_class:
                        return_type = None
                        return_type_node = next(
                            (
                                c
                                for c in current_node.children
                                if c.type == 'return_type'
                            ),
                            None,
                        )
                        if return_type_node:
                            # Get first meaningful type node (supports identifiers, subscriptions, etc.)
                            type_node = next(
                                (
                                    c
                                    for c in return_type_node.children
                                    if c.type
                                    in (
                                        'identifier',
                                        'subscript',
                                        'attribute',
                                        'type',
                                        'string',
                                    )
                                ),
                                None,
                            )
                            if type_node:
                                return_type = type_node.text.decode('utf8')
                                # Strip quotes from string-based forward references
                                if type_node.type == 'string':
                                    return_type = return_type.strip("'\"")
                        if return_type:
                            self.method_return_types.setdefault(current_class, {})[
                                func_name
                            ] = return_type

                    # Process __init__ for instance variables
                    if current_class and func_name == "__init__" and body_node:
                        instance_vars = self._find_instance_vars(
                            body_node, current_class
                        )
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
                base_classes = []
                body_node = None

                # Extract class name and base classes
                for child in current_node.children:
                    if child.type == 'identifier':
                        class_name = child.text.decode('utf8')
                    elif child.type == 'block':
                        body_node = child
                    elif child.type == 'argument_list':
                        # Get base classes for Python
                        base_class_nodes = [
                            n for n in child.children if n.type not in (',', '(', ')')
                        ]
                        base_classes = [n.text.decode('utf8') for n in base_class_nodes]

                if class_name and body_node:
                    self._current_classes.setdefault(
                        class_name,
                        {
                            "instance_vars": {},
                            "methods": [],
                            "base_classes": base_classes,
                            "start_line": current_node.start_point[0],
                            "end_line": current_node.end_point[0],
                        },
                    )
                    # Add class body children to stack with class context
                    for child in reversed(body_node.children):
                        stack.append((child, class_name))

            # Process other nodes
            else:
                for child in reversed(current_node.children):
                    stack.append((child, current_class))
        
        # Warn if we hit iteration limit
        if iteration_count >= MAX_ITERATIONS:
            logger.warning(f"Hit iteration limit ({MAX_ITERATIONS}) in _find_functions for language: {lang}")

    def _find_function_calls(  # noqa: C901
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
                current_node = n
                parts = []
                current_context = current_class

                # Handle C++ qualified identifiers and field expressions
                if lang == 'cpp':
                    if current_node.type == 'qualified_identifier':
                        parts = [
                            c.text.decode('utf8')
                            for c in current_node.children
                            if c.type == 'identifier'
                        ]
                        if parts:
                            calls.append('::'.join(parts))
                        continue
                    elif current_node.type == 'field_identifier':
                        method_name = current_node.text.decode('utf8')
                        if current_class:
                            calls.append(f"{current_class}::{method_name}")
                        else:
                            calls.append(method_name)
                        continue
                    elif current_node.type == 'identifier':
                        func_name = current_node.text.decode('utf8')
                        if current_class:
                            # Check if it's a method call within the class
                            if any(
                                func_name == m
                                for m in self._current_classes.get(
                                    current_class, {}
                                ).get("methods", [])
                            ):
                                calls.append(f"{current_class}::{func_name}")
                            else:
                                calls.append(func_name)
                        else:
                            calls.append(func_name)
                        continue

                # Handle Go function calls 
                if lang == 'go':
                    if current_node.type == 'field_identifier':
                        # This is a method call like user.GetName() or fmt.Println()
                        method_name = current_node.text.decode('utf8')
                        calls.append(method_name)
                        continue
                    elif current_node.type == 'identifier':
                        # This is a regular function call
                        func_name = current_node.text.decode('utf8')
                        calls.append(func_name)
                        continue

                # Decompose attribute chain into ordered parts
                while current_node and current_node.type in (
                    'attribute',
                    'qualified_identifier',
                    'field_expression',
                ):
                    if current_node.type == 'qualified_identifier':
                        parts.extend(
                            reversed(
                                [
                                    c.text.decode('utf8')
                                    for c in current_node.children
                                    if c.type == 'identifier'
                                ]
                            )
                        )
                        break
                    elif current_node.type == 'attribute':
                        if len(current_node.children) >= 3:
                            attr_name = current_node.children[2].text.decode('utf8')
                            parts.append(attr_name)
                    current_node = current_node.children[0]

                if current_node and current_node.type == 'identifier':
                    parts.append(current_node.text.decode('utf8'))

                parts = parts[::-1]  # Reverse to get left-to-right order

                if not parts:
                    continue

                method_name = parts[-1]
                object_parts = parts[:-1]

                # Resolve context through object parts
                for part in object_parts:
                    if part == 'self':
                        continue

                    # Check class instance variables
                    if current_context:
                        class_vars = self._current_classes.get(current_context, {}).get(
                            'instance_vars', {}
                        )
                        if part in class_vars:
                            current_context = class_vars[part]
                            continue

                    # Check local variables
                    if part in local_vars:
                        current_context = local_vars[part]
                        continue

                    current_context = None
                    break

                # Build final call
                if current_context:
                    resolved_call = f"{current_context}.{method_name}"
                else:
                    resolved_call = '.'.join(parts)

                if resolved_call and not resolved_call.startswith('__init__'):
                    calls.append(resolved_call)

        return list(set(calls))

    def find_node_by_range(
        self, node: Node, start_line: int, end_line: int
    ) -> Optional[Node]:
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

    def _find_instance_vars(  # noqa: C901
        self,
        node: Node,
        current_class: str,
    ) -> Dict[str, str]:  # noqa: C901
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

                        class_name = self._get_rhs_type(value, current_class)

                        if class_name:
                            instance_vars[attr] = class_name

                # Handle local variable assignments (var = ClassName() or var = self.method())
                elif target.type == 'identifier':
                    var_name = target.text.decode()
                    class_name = self._get_rhs_type(value, current_class)
                    if class_name:
                        instance_vars[var_name] = class_name

            stack.extend(reversed(current_node.children))

        return instance_vars

    def _get_rhs_type(self, value_node: Node, current_class: str) -> Optional[str]:
        """Determine the type of the right-hand side of an assignment."""
        # Handle constructor calls (ClassName())
        if value_node.type == 'call' and value_node.children[0].type == 'identifier':
            class_name = value_node.children[0].text.decode()
            if class_name[0].isupper():
                return class_name

        # Handle method calls (self.method())
        if value_node.type == 'call' and value_node.children[0].type == 'attribute':
            method_name = value_node.children[0].children[-1].text.decode()
            return self.method_return_types.get(current_class, {}).get(method_name)

        # Handle attribute access (self.some_attribute)
        if value_node.type == 'attribute':
            attr_parts = []
            current = value_node
            while current.type == 'attribute':
                attr_parts.insert(0, current.children[2].text.decode())
                current = current.children[0]
            if current.text.decode() == 'self':
                attr = '.'.join(attr_parts)
                return (
                    self._current_classes.get(current_class, {})
                    .get('instance_vars', {})
                    .get(attr)
                )

        return None

    @with_timeout(30)  # 30 second timeout for AST parsing
    def _parse_file_ast(self, content: str, lang: str) -> Dict[str, Any]:  # noqa: C901
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
                "base_classes": class_info.get("base_classes", []),
                "start_line": class_info.get("start_line"),
                "end_line": class_info.get("end_line"),
            }

        # Second pass to resolve calls with class context
        for func_key, func_data in ast_data["functions"].items():
            current_class = func_data["class"]
            class_vars = (  # noqa: F841
                self._current_classes.get(current_class, {}).get("instance_vars", {})
                if current_class
                else {}
            )

            # Use the recursive finder to locate the function node
            func_node = self.find_node_by_range(
                tree.root_node, func_data["start_line"], func_data["end_line"]
            )

            if func_node:
                local_vars = func_data.get("local_vars", {})
                resolved_calls = self._find_function_calls(
                    func_node, lang, current_class, local_vars
                )
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
                elif node.type == 'preproc_include':
                    # Handle C-style #include statements
                    for child in node.children:
                        if child.type == 'string_literal':
                            # Remove quotes from "header.h"
                            header = child.text.decode('utf8').strip('"')
                            ast_data["imports"].append(header)
                        elif child.type == 'system_lib_string':
                            # Remove <> from <header.h>
                            header = child.text.decode('utf8').strip('<>')
                            ast_data["imports"].append(header)
                elif node.type == 'import_declaration':
                    # Handle Go imports: import "fmt" or import ( "fmt"; "os" )
                    for child in node.children:
                        if child.type == 'import_spec':
                            # Single import spec
                            for spec_child in child.children:
                                if spec_child.type == 'interpreted_string_literal':
                                    # Remove quotes from import path
                                    import_path = spec_child.text.decode('utf8').strip('"')
                                    ast_data["imports"].append(import_path)
                        elif child.type == 'import_spec_list':
                            # Multiple imports in parentheses
                            for spec_list_child in child.children:
                                if spec_list_child.type == 'import_spec':
                                    for spec_child in spec_list_child.children:
                                        if spec_child.type == 'interpreted_string_literal':
                                            import_path = spec_child.text.decode('utf8').strip('"')
                                            ast_data["imports"].append(import_path)
                        elif child.type == 'interpreted_string_literal':
                            # Direct string import: import "fmt"
                            import_path = child.text.decode('utf8').strip('"')
                            ast_data["imports"].append(import_path)
                stack.extend(node.children)

        find_imports(tree.root_node)

        return ast_data

    @staticmethod
    def _process_file_worker(
        file_info: Tuple[str, Dict[str, Any], str, str, Optional[str], bool, Optional[str]]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        path, item, repo_url, ref, token, use_local_clone, local_clone_path = file_info
        # Create processor with local cloning disabled to avoid worker processes trying to clone
        processor = RepoTreeGenerator(token=token, use_local_clone=False)
        
        try:
            start_time = time.time()
            lang = processor._detect_language(path)
            if not lang:
                logger.debug(f"SKIP: No language detected for {path}")
                return path, None
            
            content = None
            if use_local_clone and local_clone_path:
                # Read from local filesystem (pre-cloned by main process)
                from pathlib import Path
                file_path = Path(local_clone_path) / path
                if not file_path.exists() or not file_path.is_file():
                    logger.debug(f"SKIP: File not found: {path}")
                    return path, None
                
                # Read file regardless of size - we want complete processing
                try:
                    # Read entire file content without size limits
                    with open(file_path, 'rb') as f:
                        content_bytes = f.read()  # Read entire file
                    content = content_bytes.decode('utf-8', errors='ignore')
                except (OSError, UnicodeDecodeError) as e:
                    logger.debug(f"SKIP: Failed to read {path}: {e}")
                    return path, None
            else:
                # Use API method - this should be rare with local clone enabled
                content = processor._get_file_content(f"{repo_url}/-/blob/{ref}/{path}")
                if not content:
                    logger.debug(f"SKIP: No content from API for {path}")
                    return path, None
            
            # Only skip truly empty files - process everything else
            if not content:
                logger.debug(f"SKIP: Empty content for {path}")
                return path, None
            
            # More permissive binary file check - only skip obvious binary files
            null_count = content[:5000].count('\0')  # Check first 5KB
            if null_count > 10:  # Allow some null bytes but skip obviously binary files
                logger.debug(f"SKIP: Binary file {path} (null bytes: {null_count})")
                return path, None
            
            try:
                ast_data = processor._parse_file_ast(content, lang)
                elapsed = time.time() - start_time
                if elapsed > 5:  # Reduced threshold from 10s to 5s
                    logger.warning(f"Slow AST parsing for {path} ({lang}): {elapsed:.2f}s")
                return path, {"language": lang, "ast": ast_data}
            except TimeoutError:
                logger.warning(f"AST parsing timeout for {path} ({lang}) after 60s - file too complex")
                return path, None
            except Exception as e:
                logger.debug(f"SKIP: AST parsing error for {path} ({lang}): {e}")
                return path, None
        except Exception as e:
            logger.debug(f"SKIP: Worker error processing {path}: {e}")
            
        return path, None

    def generate_repo_tree(  # noqa: C901
        self,
        repo_url: str,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            if ref and any(msg in error_str for msg in ["tree not found", "is empty", "invalid reference"]):
                raise ValueError(f"No ref found in repository by name: {ref}")
            raise

        # Get the actual ref that was used (in case ref was None)
        if not ref:
            # If no ref was provided, get the default branch
            ref = self.provider.validate_ref(repo_url, None)

        # Get commit hash (API-first for speed, with clone fallback)
        last_commit_hash = self.provider.get_last_commit_hash(repo_url, ref)

        self.node_count = 0
        self.MAX_NODES = 10000

        repo_tree = {"metadata": {"url": repo_url, "ref": ref, "last_commit_hash": last_commit_hash}, "files": {}}

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
                (path, item, repo_url, ref, self.token, self.use_local_clone, local_clone_path)
                for path, item, repo_url, ref in files_to_process
            ]

            # Optimized resource constraints
            cpu_count = multiprocessing.cpu_count()
            max_workers = min(
                cpu_count,
                len(files_to_process),
                cpu_count,  # Use all available cores for CPU-intensive AST parsing
            )

            with multiprocessing.Pool(
                processes=max_workers, 
                maxtasksperchild=100  # Increased batch size for better efficiency
            ) as pool:
                results = pool.map(self._process_file_worker, files_to_process_mp)
                for path, data in results:
                    if data:
                        repo_tree["files"][path] = data
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
                                content = file_path.read_text(encoding='utf-8', errors='ignore')
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
                                    logger.warning(f"Slow AST parsing for {path} ({lang}): {elapsed:.2f}s")
                                repo_tree["files"][path] = {
                                    "language": lang,
                                    "ast": ast_data,
                                }
                            except TimeoutError:
                                logger.error(f"AST parsing timeout for {path} ({lang}) after 30s")
                                continue
                            except Exception as e:
                                logger.error(f"AST parsing error for {path} ({lang}): {e}")
                                continue
                except Exception as e:
                    logger.error(f"Error processing {path}: {e}")
                    continue

        # Cleanup temporary clones if using LocalRepoProvider
        if hasattr(self.provider, 'cleanup'):
            self.provider.cleanup()

        return repo_tree

    def is_repo_tree_up_to_date(self, repo_url: str, ref: Optional[str] = None, output_path: Optional[str] = None) -> bool:
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
        force: bool = False
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
        if not force and output_path and self.is_repo_tree_up_to_date(repo_url, ref, output_path):
            print(f"Repository AST tree is up to date (no changes in commit hash). Loading existing tree.")
            with open(output_path, 'r') as f:
                return json.load(f)

        print("Repository has changes, generating new AST tree...")
        repo_tree = self.generate_repo_tree(repo_url, ref)
        
        if output_path:
            self.save_repo_tree(repo_tree, output_path)
            print(f"Repository AST tree saved to {output_path}")
        
        return repo_tree

    def save_repo_tree(self, repo_tree: Dict[str, Any], output_path: str):
        with open(output_path, 'w') as f:
            json.dump(repo_tree, f, indent=2)
