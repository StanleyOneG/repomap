"""Command-line interface for repository map generation."""

import argparse
import logging
import os
import sys
from typing import Optional

from repomap import __version__
from repomap.config import settings
from repomap.core import fetch_repo_structure
from repomap.tree_sitter_wrapper import parse_source_file
from repomap.utils import store_repo_map, setup_logging

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate repository map from GitLab repository",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "repo_url",
        help="GitLab repository URL"
    )
    
    parser.add_argument(
        "-t", "--token",
        help="GitLab access token (overrides environment variable)",
        default=None
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output file path",
        default="repomap.json"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        help="Enable verbose logging",
        action="store_true"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    
    return parser.parse_args()

def main() -> Optional[int]:
    """Main entry point for the CLI.
    
    Returns:
        Optional[int]: Exit code (0 for success, non-zero for error)
    """
    args = parse_args()
    
    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    setup_logging(log_level)
    
    try:
        # Fetch repository structure
        logger.info(f"Fetching repository structure from {args.repo_url}")
        repo_structure = fetch_repo_structure(args.repo_url, args.token)
        
        # Process each file in the repository
        repo_map = {
            "metadata": {
                "url": args.repo_url,
                "version": __version__
            },
            "structure": repo_structure,
            "ast_data": {}
        }
        
        def process_files(structure, current_path=""):
            """Recursively process files in repository structure."""
            if not isinstance(structure, dict):
                return
                
            for name, item in structure.items():
                path = os.path.join(current_path, name)
                
                if isinstance(item, dict):
                    if "type" in item and item["type"] == "blob":
                        try:
                            # TODO: Fetch file content from GitLab
                            # For now, we'll just store the file info
                            repo_map["ast_data"][path] = {
                                "path": path,
                                "size": item.get("size", 0),
                                "mode": item.get("mode", "100644")
                            }
                        except Exception as e:
                            logger.warning(f"Failed to process {path}: {e}")
                    else:
                        # This is a directory
                        process_files(item, path)
        
        process_files(repo_structure)
        
        # Store repository map
        output_path = store_repo_map(repo_map, args.output)
        logger.info(f"Repository map saved to {output_path}")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1

if __name__ == "__main__":
    sys.exit(main())
