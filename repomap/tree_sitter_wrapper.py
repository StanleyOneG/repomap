"""Tree-sitter wrapper for parsing source code files."""

from typing import Dict, Optional, Any
import logging
from pathlib import Path
from tree_sitter_languages import get_language, get_parser

logger = logging.getLogger(__name__)

class TreeSitterWrapper:
    """Wrapper class for tree-sitter functionality."""

    def __init__(self):
        """Initialize the TreeSitterWrapper."""
        self.parsers: Dict[str, Any] = {}
        self.languages: Dict[str, Any] = {}

    def _get_language_by_extension(self, file_path: str) -> Optional[str]:
        """Get tree-sitter language based on file extension.
        
        Args:
            file_path (str): Path to the source code file
            
        Returns:
            Optional[str]: Language identifier or None if unsupported
        """
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.java': 'java',
            '.rb': 'ruby',
            '.go': 'go',
            '.rs': 'rust',
            '.php': 'php'
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_to_lang.get(ext)

    def _get_parser(self, language_id: str) -> Any:
        """Get or create parser for a language.
        
        Args:
            language_id (str): Language identifier
            
        Returns:
            Any: Tree-sitter parser instance
            
        Raises:
            ValueError: If language is not supported
        """
        if language_id not in self.parsers:
            try:
                language = get_language(language_id)
                parser = get_parser(language_id)
                parser.set_language(language)
                
                self.languages[language_id] = language
                self.parsers[language_id] = parser
                
            except Exception as e:
                logger.error(f"Failed to initialize parser for {language_id}: {e}")
                raise ValueError(f"Language {language_id} is not supported")
                
        return self.parsers[language_id]

    def parse_source_file(self, file_path: str, content: str) -> Optional[Dict]:
        """Parse source code file and return syntax tree.
        
        Args:
            file_path (str): Path to source code file
            content (str): Source code content
            
        Returns:
            Optional[Dict]: Parsed syntax tree or None if parsing fails
            
        Raises:
            ValueError: If file type is not supported
        """
        language_id = self._get_language_by_extension(file_path)
        if not language_id:
            logger.warning(f"Unsupported file type: {file_path}")
            return None
            
        try:
            parser = self._get_parser(language_id)
            tree = parser.parse(bytes(content, 'utf8'))
            
            # Convert tree to dictionary structure
            def node_to_dict(node):
                result = {
                    'type': node.type,
                    'start_point': node.start_point,
                    'end_point': node.end_point,
                    'children': []
                }
                
                # Add text for leaf nodes
                if len(node.children) == 0:
                    result['text'] = content[node.start_byte:node.end_byte]
                
                # Process children recursively
                for child in node.children:
                    result['children'].append(node_to_dict(child))
                    
                return result
            
            return node_to_dict(tree.root_node)
            
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return None

def parse_source_file(file_path: str, content: str) -> Optional[Dict]:
    """Convenience function to parse a source code file.
    
    Args:
        file_path (str): Path to source code file
        content (str): Source code content
        
    Returns:
        Optional[Dict]: Parsed syntax tree
    """
    parser = TreeSitterWrapper()
    return parser.parse_source_file(file_path, content)
