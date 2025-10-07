"""Utility module for ast-grep integration."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ast_grep_py import SgRoot


class AstGrepParser:
    """Wrapper for ast-grep functionality."""

    SUPPORTED_LANGUAGES = {
        # C family
        '.c': 'c',
        '.h': 'c',
        '.cc': 'cpp',
        '.cpp': 'cpp',
        '.hpp': 'cpp',
        '.cxx': 'cpp',
        '.c++': 'cpp',
        '.hxx': 'cpp',
        '.hh': 'cpp',
        # Python
        '.py': 'python',
        '.pyx': 'python',
        '.pyi': 'python',
        # JavaScript/TypeScript
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'tsx',
        '.mjs': 'javascript',
        # Go
        '.go': 'go',
        # Java
        '.java': 'java',
        # PHP
        '.php': 'php',
        # C#
        '.cs': 'csharp',
    }

    # Map file extensions to ast-grep language identifiers
    AST_GREP_LANG_MAP = {
        'c': 'c',
        'cpp': 'cpp',
        'python': 'python',
        'javascript': 'javascript',
        'typescript': 'typescript',
        'tsx': 'tsx',
        'go': 'go',
        'java': 'java',
        'php': 'php',
        'csharp': 'csharp',
        'c_sharp': 'csharp',
    }

    def __init__(self):
        """Initialize the ast-grep parser."""
        self.custom_rules_dir = Path(__file__).parent.parent / "custom-rules"

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            str: Language identifier or None if unsupported
        """
        ext = os.path.splitext(file_path)[1].lower()
        return self.SUPPORTED_LANGUAGES.get(ext)

    def parse_code(self, content: str, language: str) -> Optional[SgRoot]:
        """Parse source code using ast-grep.

        Args:
            content: Source code content
            language: Programming language

        Returns:
            SgRoot: Parsed AST root or None if parsing failed
        """
        try:
            ast_grep_lang = self.AST_GREP_LANG_MAP.get(language, language)
            root = SgRoot(content, ast_grep_lang)
            return root
        except Exception as e:
            print(f"Failed to parse code with ast-grep for language {language}: {e}")
            return None

    def find_functions(
        self, root: SgRoot, language: str
    ) -> List[Dict[str, Any]]:
        """Find all function definitions in the AST.

        Args:
            root: SgRoot object
            language: Programming language

        Returns:
            List of function information dictionaries
        """
        functions = []
        try:
            node = root.root()
        except Exception:
            return functions

        try:
            if language == 'python':
                # Find all function definitions
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_info = self._extract_python_function(func_node)
                    if func_info:
                        functions.append(func_info)

            elif language == 'go':
                # Find function declarations
                func_nodes = node.find_all(kind='function_declaration')
                for func_node in func_nodes:
                    func_info = self._extract_go_function(func_node)
                    if func_info:
                        functions.append(func_info)

                # Find method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    func_info = self._extract_go_method(method_node)
                    if func_info:
                        functions.append(func_info)

            elif language in ('c', 'cpp'):
                # Find function definitions
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_info = self._extract_c_function(func_node, language)
                    if func_info:
                        functions.append(func_info)

            elif language == 'java':
                # Find method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    func_info = self._extract_java_method(method_node)
                    if func_info:
                        functions.append(func_info)

                # Find constructor declarations
                constructor_nodes = node.find_all(kind='constructor_declaration')
                for constructor_node in constructor_nodes:
                    func_info = self._extract_java_constructor(constructor_node)
                    if func_info:
                        functions.append(func_info)

            elif language == 'php':
                # Find function definitions
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_info = self._extract_php_function(func_node)
                    if func_info:
                        functions.append(func_info)

                # Find method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    func_info = self._extract_php_method(method_node)
                    if func_info:
                        functions.append(func_info)

            elif language == 'csharp':
                # Find method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    func_info = self._extract_csharp_method(method_node)
                    if func_info:
                        functions.append(func_info)

            elif language in ('javascript', 'typescript', 'tsx'):
                # Find function declarations
                func_nodes = node.find_all(kind='function_declaration')
                for func_node in func_nodes:
                    func_info = self._extract_js_function(func_node)
                    if func_info:
                        functions.append(func_info)

                # Find method definitions
                method_nodes = node.find_all(kind='method_definition')
                for method_node in method_nodes:
                    func_info = self._extract_js_method(method_node)
                    if func_info:
                        functions.append(func_info)

                # Find arrow functions assigned to variables
                arrow_nodes = node.find_all(kind='arrow_function')
                for arrow_node in arrow_nodes:
                    func_info = self._extract_js_arrow_function(arrow_node)
                    if func_info:
                        functions.append(func_info)
        except Exception:
            # If any ast-grep operation fails, return what we have so far
            pass

        return functions

    def find_classes(self, root: SgRoot, language: str) -> List[Dict[str, Any]]:
        """Find all class definitions in the AST.

        Args:
            root: SgRoot object
            language: Programming language

        Returns:
            List of class information dictionaries
        """
        classes = []
        try:
            node = root.root()
        except Exception:
            return classes

        try:
            if language == 'python':
                class_nodes = node.find_all(kind='class_definition')
                for class_node in class_nodes:
                    class_info = self._extract_python_class(class_node)
                    if class_info:
                        classes.append(class_info)

            elif language in ('cpp', 'java', 'csharp'):
                class_nodes = node.find_all(kind='class_declaration')
                for class_node in class_nodes:
                    class_info = self._extract_oop_class(class_node, language)
                    if class_info:
                        classes.append(class_info)

            elif language == 'go':
                # Go uses type declarations for structs
                type_nodes = node.find_all(kind='type_declaration')
                for type_node in type_nodes:
                    class_info = self._extract_go_type(type_node)
                    if class_info:
                        classes.append(class_info)

            elif language in ('javascript', 'typescript', 'tsx'):
                class_nodes = node.find_all(kind='class_declaration')
                for class_node in class_nodes:
                    class_info = self._extract_js_class(class_node)
                    if class_info:
                        classes.append(class_info)
        except Exception:
            # If any ast-grep operation fails, return what we have
            pass

        return classes

    def find_function_calls(
        self, root: SgRoot, language: str, start_line: int, end_line: int
    ) -> Set[str]:
        """Find all function calls within a line range.

        Args:
            root: SgRoot object
            language: Programming language
            start_line: Start line number
            end_line: End line number

        Returns:
            Set of function names that are called
        """
        calls = set()
        node = root.root()

        # Language-specific call node types
        call_kinds = {
            'python': ['call'],
            'javascript': ['call_expression'],
            'typescript': ['call_expression'],
            'tsx': ['call_expression'],
            'go': ['call_expression'],
            'c': ['call_expression'],
            'cpp': ['call_expression'],
            'java': ['method_invocation'],
            'php': ['function_call_expression'],
            'csharp': ['invocation_expression'],
        }

        # Get the appropriate call kinds for this language
        kinds = call_kinds.get(language, ['call', 'call_expression'])

        for kind in kinds:
            try:
                call_nodes = node.find_all(kind=kind)
                for call_node in call_nodes:
                    try:
                        call_range = call_node.range()
                        call_start_line = call_range.start.line

                        if start_line <= call_start_line <= end_line:
                            call_name = self._extract_call_name(call_node, language)
                            if call_name:
                                calls.add(call_name)
                    except Exception:
                        # Skip problematic nodes
                        continue
            except Exception:
                # If the kind doesn't exist for this language, skip it
                continue

        return calls

    def _extract_python_function(self, func_node) -> Optional[Dict[str, Any]]:
        """Extract function information from Python function node."""
        try:
            func_range = func_node.range()
            func_name_node = func_node.field('name')
            if not func_name_node:
                return None

            func_name = func_name_node.text()
            # Validate that the function name is not empty
            if not func_name or not func_name.strip():
                return None

            return {
                'name': func_name,
                'start_line': func_range.start.line,
                'end_line': func_range.end.line,
                'node': func_node,
            }
        except Exception:
            return None

    def _extract_go_function(self, func_node) -> Optional[Dict[str, Any]]:
        """Extract function information from Go function node."""
        try:
            func_range = func_node.range()
            func_name_node = func_node.field('name')
            if not func_name_node:
                return None

            func_name = func_name_node.text()
            # Validate that the function name is not empty
            if not func_name or not func_name.strip():
                return None

            return {
                'name': func_name,
                'start_line': func_range.start.line,
                'end_line': func_range.end.line,
                'node': func_node,
            }
        except Exception:
            return None

    def _extract_go_method(self, method_node) -> Optional[Dict[str, Any]]:
        """Extract method information from Go method node."""
        try:
            method_range = method_node.range()
            method_name_node = method_node.field('name')
            if not method_name_node:
                return None

            method_name = method_name_node.text()
            # Validate that the method name is not empty
            if not method_name or not method_name.strip():
                return None

            # Extract receiver type
            receiver_node = method_node.field('receiver')
            receiver_type = None
            if receiver_node:
                # Find type identifier in receiver
                type_children = receiver_node.children()
                for child in type_children:
                    if child.kind() in ('type_identifier', 'pointer_type'):
                        receiver_type = child.text().replace('*', '').strip()
                        break

            return {
                'name': method_name,
                'start_line': method_range.start.line,
                'end_line': method_range.end.line,
                'class': receiver_type,
                'node': method_node,
            }
        except Exception:
            return None

    def _extract_c_function(self, func_node, language: str) -> Optional[Dict[str, Any]]:
        """Extract function information from C/C++ function node."""
        try:
            func_range = func_node.range()

            # Find function declarator
            declarator = func_node.field('declarator')
            if not declarator:
                return None

            # Handle pointer and reference declarators (for functions returning pointers/references)
            # Navigate through pointer_declarator/reference_declarator to get to function_declarator
            while declarator and declarator.kind() in ('pointer_declarator', 'reference_declarator'):
                # Get the child declarator within the pointer/reference declarator
                child = declarator.field('declarator')
                if child:
                    declarator = child
                else:
                    break

            # Now declarator should be a function_declarator
            func_name = None
            if declarator.kind() == 'function_declarator':
                declarator_child = declarator.field('declarator')
                if declarator_child:
                    if declarator_child.kind() == 'identifier':
                        func_name = declarator_child.text()
                    elif declarator_child.kind() == 'qualified_identifier':
                        # For C++ qualified identifiers (Class::method)
                        func_name = declarator_child.text()
                    elif declarator_child.kind() == 'field_identifier':
                        func_name = declarator_child.text()

            # Validate that the function name is not empty
            if not func_name or not func_name.strip():
                return None

            return {
                'name': func_name,
                'start_line': func_range.start.line,
                'end_line': func_range.end.line,
                'node': func_node,
            }
        except Exception:
            return None

    def _extract_java_method(self, method_node) -> Optional[Dict[str, Any]]:
        """Extract method information from Java method node."""
        try:
            method_range = method_node.range()
            method_name_node = method_node.field('name')
            if not method_name_node:
                return None

            method_name = method_name_node.text()
            # Validate that the method name is not empty
            if not method_name or not method_name.strip():
                return None

            return {
                'name': method_name,
                'start_line': method_range.start.line,
                'end_line': method_range.end.line,
                'node': method_node,
            }
        except Exception:
            return None

    def _extract_java_constructor(self, constructor_node) -> Optional[Dict[str, Any]]:
        """Extract constructor information from Java constructor node."""
        try:
            constructor_range = constructor_node.range()
            constructor_name_node = constructor_node.field('name')
            if not constructor_name_node:
                return None

            constructor_name = constructor_name_node.text()
            # Validate that the constructor name is not empty
            if not constructor_name or not constructor_name.strip():
                return None

            return {
                'name': constructor_name,
                'start_line': constructor_range.start.line,
                'end_line': constructor_range.end.line,
                'node': constructor_node,
            }
        except Exception:
            return None

    def _extract_php_function(self, func_node) -> Optional[Dict[str, Any]]:
        """Extract function information from PHP function node."""
        try:
            func_range = func_node.range()
            func_name_node = func_node.field('name')
            if not func_name_node:
                return None

            func_name = func_name_node.text()
            # Validate that the function name is not empty
            if not func_name or not func_name.strip():
                return None

            return {
                'name': func_name,
                'start_line': func_range.start.line,
                'end_line': func_range.end.line,
                'node': func_node,
            }
        except Exception:
            return None

    def _extract_php_method(self, method_node) -> Optional[Dict[str, Any]]:
        """Extract method information from PHP method node."""
        try:
            method_range = method_node.range()
            method_name_node = method_node.field('name')
            if not method_name_node:
                return None

            method_name = method_name_node.text()
            # Validate that the method name is not empty
            if not method_name or not method_name.strip():
                return None

            return {
                'name': method_name,
                'start_line': method_range.start.line,
                'end_line': method_range.end.line,
                'node': method_node,
            }
        except Exception:
            return None

    def _extract_csharp_method(self, method_node) -> Optional[Dict[str, Any]]:
        """Extract method information from C# method node."""
        try:
            method_range = method_node.range()
            method_name_node = method_node.field('name')
            if not method_name_node:
                return None

            method_name = method_name_node.text()
            # Validate that the method name is not empty
            if not method_name or not method_name.strip():
                return None

            return {
                'name': method_name,
                'start_line': method_range.start.line,
                'end_line': method_range.end.line,
                'node': method_node,
            }
        except Exception:
            return None

    def _extract_js_function(self, func_node) -> Optional[Dict[str, Any]]:
        """Extract function information from JavaScript function node."""
        try:
            func_range = func_node.range()
            func_name_node = func_node.field('name')
            if not func_name_node:
                return None

            func_name = func_name_node.text()
            # Validate that the function name is not empty
            if not func_name or not func_name.strip():
                return None

            return {
                'name': func_name,
                'start_line': func_range.start.line,
                'end_line': func_range.end.line,
                'node': func_node,
            }
        except Exception:
            return None

    def _extract_js_method(self, method_node) -> Optional[Dict[str, Any]]:
        """Extract method information from JavaScript method node."""
        try:
            method_range = method_node.range()
            method_name_node = method_node.field('name')
            if not method_name_node:
                return None

            method_name = method_name_node.text()
            # Validate that the method name is not empty
            if not method_name or not method_name.strip():
                return None

            return {
                'name': method_name,
                'start_line': method_range.start.line,
                'end_line': method_range.end.line,
                'node': method_node,
            }
        except Exception:
            return None

    def _extract_js_arrow_function(self, arrow_node) -> Optional[Dict[str, Any]]:
        """Extract arrow function information from JavaScript."""
        try:
            # Arrow functions need parent context to get name
            parent = arrow_node.parent()
            if parent and parent.kind() == 'variable_declarator':
                name_node = parent.field('name')
                if name_node:
                    func_name = name_node.text()
                    # Validate that the function name is not empty
                    if not func_name or not func_name.strip():
                        return None

                    arrow_range = arrow_node.range()
                    return {
                        'name': func_name,
                        'start_line': arrow_range.start.line,
                        'end_line': arrow_range.end.line,
                        'node': arrow_node,
                    }
            return None
        except Exception:
            return None

    def _extract_python_class(self, class_node) -> Optional[Dict[str, Any]]:
        """Extract class information from Python class node."""
        try:
            class_range = class_node.range()
            class_name_node = class_node.field('name')
            if not class_name_node:
                return None

            class_name = class_name_node.text()
            return {
                'name': class_name,
                'start_line': class_range.start.line,
                'end_line': class_range.end.line,
                'node': class_node,
            }
        except Exception:
            return None

    def _extract_oop_class(self, class_node, language: str) -> Optional[Dict[str, Any]]:
        """Extract class information from OOP language class node."""
        try:
            class_range = class_node.range()
            class_name_node = class_node.field('name')
            if not class_name_node:
                return None

            class_name = class_name_node.text()
            return {
                'name': class_name,
                'start_line': class_range.start.line,
                'end_line': class_range.end.line,
                'node': class_node,
            }
        except Exception:
            return None

    def _extract_go_type(self, type_node) -> Optional[Dict[str, Any]]:
        """Extract type information from Go type declaration."""
        try:
            type_range = type_node.range()
            # Look for struct types
            type_spec_nodes = type_node.find_all(kind='type_spec')
            for spec_node in type_spec_nodes:
                name_node = spec_node.field('name')
                type_field = spec_node.field('type')
                if name_node and type_field and type_field.kind() == 'struct_type':
                    return {
                        'name': name_node.text(),
                        'start_line': type_range.start.line,
                        'end_line': type_range.end.line,
                        'node': type_node,
                    }
            return None
        except Exception:
            return None

    def _extract_js_class(self, class_node) -> Optional[Dict[str, Any]]:
        """Extract class information from JavaScript class node."""
        try:
            class_range = class_node.range()
            class_name_node = class_node.field('name')
            if not class_name_node:
                return None

            class_name = class_name_node.text()
            return {
                'name': class_name,
                'start_line': class_range.start.line,
                'end_line': class_range.end.line,
                'node': class_node,
            }
        except Exception:
            return None

    def _extract_call_name(self, call_node, language: str) -> Optional[str]:
        """Extract the function name from a call node."""
        try:
            # Get the function being called
            func_field = call_node.field('function')
            if not func_field:
                # Try 'method' field for some languages
                func_field = call_node.field('method')

            if not func_field:
                return None

            # Handle different call patterns
            if func_field.kind() == 'identifier':
                return func_field.text()
            elif func_field.kind() in ('attribute', 'member_expression', 'selector_expression'):
                # For method calls like obj.method()
                # Get the full chain or just the method name
                return func_field.text()
            elif func_field.kind() == 'field_identifier':
                return func_field.text()
            else:
                return func_field.text()

        except Exception:
            return None

    def find_function_at_line(
        self, root: SgRoot, line_number: int, language: str
    ) -> Optional[Dict[str, Any]]:
        """Find the function containing the specified line number.

        Args:
            root: SgRoot object
            line_number: Line number to search for
            language: Programming language

        Returns:
            Function information dict or None if not found
        """
        try:
            node = root.root()
        except Exception:
            return None

        # Use the same logic as find_functions to get all functions and find the one containing the line
        try:
            if language == 'python':
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_range = func_node.range()
                    if func_range.start.line <= line_number <= func_range.end.line:
                        func_info = self._extract_python_function(func_node)
                        if func_info:
                            return func_info

            elif language == 'go':
                # Check function declarations
                func_nodes = node.find_all(kind='function_declaration')
                for func_node in func_nodes:
                    func_range = func_node.range()
                    if func_range.start.line <= line_number <= func_range.end.line:
                        func_info = self._extract_go_function(func_node)
                        if func_info:
                            return func_info

                # Check method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    method_range = method_node.range()
                    if method_range.start.line <= line_number <= method_range.end.line:
                        func_info = self._extract_go_method(method_node)
                        if func_info:
                            return func_info

            elif language in ('c', 'cpp'):
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_range = func_node.range()
                    if func_range.start.line <= line_number <= func_range.end.line:
                        func_info = self._extract_c_function(func_node, language)
                        if func_info:
                            return func_info

            elif language == 'java':
                # Check method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    method_range = method_node.range()
                    if method_range.start.line <= line_number <= method_range.end.line:
                        func_info = self._extract_java_method(method_node)
                        if func_info:
                            return func_info

                # Check constructor declarations
                constructor_nodes = node.find_all(kind='constructor_declaration')
                for constructor_node in constructor_nodes:
                    constructor_range = constructor_node.range()
                    if constructor_range.start.line <= line_number <= constructor_range.end.line:
                        func_info = self._extract_java_constructor(constructor_node)
                        if func_info:
                            return func_info

            elif language == 'php':
                # Check function definitions
                func_nodes = node.find_all(kind='function_definition')
                for func_node in func_nodes:
                    func_range = func_node.range()
                    if func_range.start.line <= line_number <= func_range.end.line:
                        func_info = self._extract_php_function(func_node)
                        if func_info:
                            return func_info

                # Check method declarations
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    method_range = method_node.range()
                    if method_range.start.line <= line_number <= method_range.end.line:
                        func_info = self._extract_php_method(method_node)
                        if func_info:
                            return func_info

            elif language == 'csharp':
                method_nodes = node.find_all(kind='method_declaration')
                for method_node in method_nodes:
                    method_range = method_node.range()
                    if method_range.start.line <= line_number <= method_range.end.line:
                        func_info = self._extract_csharp_method(method_node)
                        if func_info:
                            return func_info

            elif language in ('javascript', 'typescript', 'tsx'):
                # Check function declarations
                func_nodes = node.find_all(kind='function_declaration')
                for func_node in func_nodes:
                    func_range = func_node.range()
                    if func_range.start.line <= line_number <= func_range.end.line:
                        func_info = self._extract_js_function(func_node)
                        if func_info:
                            return func_info

                # Check method definitions
                method_nodes = node.find_all(kind='method_definition')
                for method_node in method_nodes:
                    method_range = method_node.range()
                    if method_range.start.line <= line_number <= method_range.end.line:
                        func_info = self._extract_js_method(method_node)
                        if func_info:
                            return func_info

                # Check arrow functions
                arrow_nodes = node.find_all(kind='arrow_function')
                for arrow_node in arrow_nodes:
                    arrow_range = arrow_node.range()
                    if arrow_range.start.line <= line_number <= arrow_range.end.line:
                        func_info = self._extract_js_arrow_function(arrow_node)
                        if func_info:
                            return func_info

        except Exception:
            # If any error occurs, return None
            pass

        return None

    def find_imports(self, root: SgRoot, language: str) -> List[str]:
        """Find all import statements in the AST.

        Args:
            root: SgRoot object
            language: Programming language

        Returns:
            List of import paths/names
        """
        imports = []
        node = root.root()

        if language == 'python':
            # Find import statements
            import_nodes = node.find_all(kind='import_statement')
            for import_node in import_nodes:
                # Get dotted name
                dotted_nodes = import_node.find_all(kind='dotted_name')
                for dotted in dotted_nodes:
                    imports.append(dotted.text())

            # Find import_from statements
            import_from_nodes = node.find_all(kind='import_from_statement')
            for import_node in import_from_nodes:
                dotted_nodes = import_node.find_all(kind='dotted_name')
                for dotted in dotted_nodes:
                    imports.append(dotted.text())

        elif language in ('c', 'cpp'):
            # Find #include directives
            include_nodes = node.find_all(kind='preproc_include')
            for include_node in include_nodes:
                # Look for string literal or system_lib_string
                children = include_node.children()
                for child in children:
                    if child.kind() == 'string_literal':
                        imports.append(child.text().strip('"'))
                    elif child.kind() == 'system_lib_string':
                        imports.append(child.text().strip('<>'))

        elif language == 'go':
            # Find import declarations
            import_nodes = node.find_all(kind='import_declaration')
            for import_node in import_nodes:
                # Find string literals
                string_nodes = import_node.find_all(kind='interpreted_string_literal')
                for string_node in string_nodes:
                    imports.append(string_node.text().strip('"'))

        elif language == 'java':
            # Find import declarations
            import_nodes = node.find_all(kind='import_declaration')
            for import_node in import_nodes:
                imports.append(import_node.text())

        elif language in ('javascript', 'typescript', 'tsx'):
            # Find import statements
            import_nodes = node.find_all(kind='import_statement')
            for import_node in import_nodes:
                imports.append(import_node.text())

        return imports

    def extract_comprehensive_ast_data(
        self, content: str, language: str
    ) -> Dict[str, Any]:
        """Extract comprehensive AST data including functions, classes, calls, and imports.

        Args:
            content: Source code content
            language: Programming language

        Returns:
            Dictionary with AST data in the format expected by repo_tree
        """
        ast_data = {"functions": {}, "classes": {}, "calls": [], "imports": []}

        root = self.parse_code(content, language)
        if not root:
            return ast_data

        # Extract functions
        functions = self.find_functions(root, language)
        for func_info in functions:
            func_key = func_info['name']
            if 'class' in func_info and func_info['class']:
                func_key = f"{func_info['class']}.{func_info['name']}"

            # Find function calls within this function
            calls = self.find_function_calls(
                root, language, func_info['start_line'], func_info['end_line']
            )

            ast_data["functions"][func_key] = {
                "name": func_info['name'],
                "start_line": func_info['start_line'],
                "end_line": func_info['end_line'],
                "class": func_info.get('class'),
                "calls": list(calls),
                "local_vars": {},  # Simplified for now
            }

            # Add to calls list
            for call in calls:
                ast_data["calls"].append(
                    {
                        "name": call,
                        "line": func_info['start_line'],
                        "caller": func_key,
                        "class": func_info.get('class'),
                    }
                )

        # Extract classes
        classes = self.find_classes(root, language)
        for class_info in classes:
            # Find methods for this class
            methods = [
                func_data["name"]
                for func_key, func_data in ast_data["functions"].items()
                if func_data.get("class") == class_info['name']
            ]

            ast_data["classes"][class_info['name']] = {
                "name": class_info['name'],
                "methods": methods,
                "instance_vars": {},  # Simplified for now
                "base_classes": [],  # Simplified for now
                "start_line": class_info['start_line'],
                "end_line": class_info['end_line'],
            }

        # Extract imports
        ast_data["imports"] = self.find_imports(root, language)

        return ast_data
