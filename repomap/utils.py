"""Utility functions for repository map generation and storage."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def store_repo_map(repo_map: Dict, output_path: Optional[str] = None) -> str:
    """Store repository map to a JSON file.

    Args:
        repo_map (Dict): Repository map data to store
        output_path (Optional[str]): Path to output file. If None, uses default 'repomap.json'

    Returns:
        str: Path to the stored file

    Raises:
        IOError: If file cannot be written
    """
    if not output_path:
        output_path = 'repomap.json'

    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(repo_map, f, indent=2, ensure_ascii=False)

        logger.info(f"Repository map saved to {output_path}")
        return str(output_file)

    except IOError as e:
        logger.error(f"Failed to write repository map: {e}")
        raise


def load_repo_map(file_path: str) -> Optional[Dict]:
    """Load repository map from a JSON file.

    Args:
        file_path (str): Path to JSON file

    Returns:
        Optional[Dict]: Repository map data or None if loading fails

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data

    except FileNotFoundError:
        logger.error(f"Repository map file not found: {file_path}")
        raise

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in repository map file: {e}")
        raise


def setup_logging(level: str = 'INFO') -> None:
    """Configure logging for the application.

    Args:
        level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Raises:
        ValueError: If invalid logging level provided
    """
    try:
        numeric_level = getattr(logging, level.upper())
    except AttributeError:
        raise ValueError(f"Invalid log level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)d)',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logger = logging.getLogger('repomap')
    logger.setLevel(numeric_level)

    if level.upper() == 'DEBUG':
        logger.debug("Debug logging enabled")
