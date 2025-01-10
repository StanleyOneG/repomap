"""Command-line interface for repository map generation."""

import argparse
import logging
import os
import sys
from typing import Optional

from repomap import __version__
from repomap.core import fetch_repo_structure
from repomap.utils import store_repo_map, setup_logging
from repomap.callstack import CallStackGenerator

logger = logging.getLogger(__name__)

def parse_args(args=None) -> argparse.Namespace:
    """Parse command line arguments.
    
    Args:
        args: List of arguments to parse. If None, uses sys.argv[1:].
    
    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate repository map from GitLab repository",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "repo_url",
        help="GitLab repository URL",
        nargs='?'  # Make repo_url optional
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
    
    # Call stack arguments
    parser.add_argument(
        "--call-stack",
        action="store_true",
        help="Generate call stack for a specific line in a file"
    )
    
    parser.add_argument(
        "--target-file",
        help="URL to the target file for call stack generation"
    )
    
    parser.add_argument(
        "--line",
        type=int,
        help="Line number in target file for call stack generation"
    )
    
    parser.add_argument(
        "--structure-file",
        help="Path to repository structure JSON file"
    )
    
    parser.add_argument(
        "--output-stack",
        help="Output file path for call stack"
    )
    
    args = parser.parse_args(args)
    
    # Validate arguments
    if args.call_stack:
        if not all([args.target_file, args.line, args.structure_file, args.output_stack]):
            parser.error("--call-stack requires --target-file, --line, --structure-file, and --output-stack")
    else:
        if not args.repo_url:
            parser.error("repo_url is required when not using --call-stack")
    
    return args

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
        if args.call_stack:
            # Generate call stack
            logger.info(f"Generating call stack for {args.target_file}:{args.line}")
            generator = CallStackGenerator(args.structure_file, args.token)
            call_stack = generator.generate_call_stack(args.target_file, args.line)
            generator.save_call_stack(call_stack, args.output_stack)
            logger.info(f"Call stack saved to {args.output_stack}")
            return 0
            
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
