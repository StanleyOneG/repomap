"""Command-line interface for repository map generation."""

import argparse
import json
import logging
import os
import sys
from typing import Optional

from repomap import __version__
from repomap.callstack import CallStackGenerator
from repomap.core import fetch_repo_structure
from repomap.repo_tree import RepoTreeGenerator
from repomap.utils import setup_logging, store_repo_map

logger = logging.getLogger(__name__)


def parse_args(args=None) -> argparse.Namespace:  # noqa: C901
    """Parse command line arguments.

    Args:
        args: List of arguments to parse. If None, uses sys.argv[1:].

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate repository map from GitLab repository",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("repo_url", help="GitLab repository URL", nargs='?')

    parser.add_argument(
        "-t",
        "--token",
        help="GitLab access token (overrides environment variable)",
        default=None,
    )

    parser.add_argument(
        "-o", "--output", help="Output file path", default="repomap.json"
    )

    parser.add_argument(
        "-v", "--verbose", help="Enable verbose logging", action="store_true"
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Repository AST tree arguments
    parser.add_argument(
        "--repo-tree", action="store_true", help="Generate repository AST tree"
    )
    parser.add_argument(
        "--ref",
        help="Git reference (branch, tag, commit) to use for repository AST tree",
    )

    # Call stack arguments
    parser.add_argument(
        "--call-stack",
        action="store_true",
        help="Generate call stack for a specific line in a file",
    )

    parser.add_argument(
        "--target-file", help="URL to the target file for call stack generation"
    )

    parser.add_argument(
        "--line", type=int, help="Line number in target file for call stack generation"
    )

    parser.add_argument(
        "--structure-file", help="Path to repository structure JSON file"
    )

    parser.add_argument("--output-stack", help="Output file path for call stack")

    # Print function arguments
    function_group = parser.add_mutually_exclusive_group()
    function_group.add_argument(
        "--print-function",
        action="store_true",
        help="Print the function containing a specific line in a file",
    )
    function_group.add_argument(
        "--print-function-by-name",
        action="store_true",
        help="Print function code by its name in a repository",
    )
    parser.add_argument(
        "--name",
        help="Function name to search for when using --print-function-by-name",
    )
    parser.add_argument(
        "--repo-tree-path",
        help="Path to repository tree JSON file when using --print-function-by-name",
    )

    args = parser.parse_args(args)

    # Validate arguments
    if args.print_function:
        if not all([args.target_file, args.line]):
            parser.error("--print-function requires --target-file and --line")
    elif args.print_function_by_name:
        if not all([args.name, args.repo_tree_path]):
            parser.error(
                "--print-function-by-name requires --name and --repo-tree-path"
            )
    elif args.call_stack:
        if not all([args.target_file, args.line]):
            parser.error("--call-stack requires --target-file and --line")
    if not args.repo_url and not (
        args.call_stack or args.print_function or args.print_function_by_name
    ):
        parser.error(
            "repo_url is required when not using --call-stack or --print-function"
        )

    return args


def main() -> Optional[int]:  # noqa: C901
    """Main entry point for the CLI.

    Returns:
        Optional[int]: Exit code (0 for success, non-zero for error)
    """
    args = parse_args()

    log_level = 'DEBUG' if args.verbose else 'INFO'
    setup_logging(log_level)

    try:
        if args.repo_tree:
            # Generate repository AST tree
            logger.info(f"Generating repository AST tree for {args.repo_url}")
            generator = RepoTreeGenerator(args.token)
            repo_tree = generator.generate_repo_tree(args.repo_url, args.ref)

            # Save repository AST tree
            generator.save_repo_tree(repo_tree, args.output)
            logger.info(f"Repository AST tree saved to {args.output}")
            return 0

        elif args.print_function or args.print_function_by_name:
            generator = CallStackGenerator(token=args.token)
            try:
                if args.print_function:
                    # Print function content by line
                    logger.info(
                        f"Getting function content for {args.target_file}:{args.line}"
                    )
                    function_content = generator.get_function_content_by_line(
                        args.target_file, args.line
                    )
                    print(function_content)
                    return 0
                else:
                    # Print function content by name
                    logger.info(f"Getting function content for {args.name}")
                    function_contents = generator.get_function_content_by_name(
                        args.repo_tree_path, args.name
                    )

                    # Print each function implementation with its class context
                    for class_name, content in function_contents.items():
                        if class_name == 'global':
                            # For global functions (not in a class)
                            print("Global function:")
                            print(content)
                        else:
                            # For class methods
                            print(f"\nIn class {class_name}:")
                            print(content)
                    return 0
            except ValueError as e:
                error_msg = str(e)
                logger.error(error_msg)
                print(error_msg, file=sys.stderr)
                return 1

        elif args.call_stack:
            # Generate call stack
            logger.info(f"Generating call stack for {args.target_file}:{args.line}")
            generator = CallStackGenerator(args.token)
            call_stack = generator.generate_call_stack(args.target_file, args.line)

            if args.output_stack:
                generator.save_call_stack(call_stack, args.output_stack)
                logger.info(f"Call stack saved to {args.output_stack}")
            else:
                # Print to stdout if no output file specified
                print(json.dumps(call_stack, indent=2))
            return 0

        # Only fetch repository structure if not using print function commands
        logger.info(f"Fetching repository structure from {args.repo_url}")
        repo_structure = fetch_repo_structure(args.repo_url, args.token)

        # Process each file in the repository
        repo_map = {
            "metadata": {"url": args.repo_url, "version": __version__},
            "structure": repo_structure,
            "ast_data": {},
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
                                "mode": item.get("mode", "100644"),
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
