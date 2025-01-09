# RepoMap

A Python package for generating repository maps from GitLab repositories using Tree-sitter for source code parsing.

## Features

- Fetch repository structure from GitLab repositories
- Parse source code using Tree-sitter
- Generate comprehensive repository maps
- Support for multiple programming languages
- Command-line interface
- JSON output format

## Installation

You can install the package using pip:

```bash
pip install repomap
```

Or install from source:

```bash
git clone https://github.com/username/repomap.git
cd repomap
pip install -e .
```

## Usage

### Command Line Interface

Basic usage:

```bash
repomap https://gitlab.com/username/repo-name
```

With options:

```bash
repomap https://gitlab.com/username/repo-name \
    -t your-gitlab-token \
    -o output.json \
    -v
```

Options:
- `-t, --token`: GitLab access token (can also be set via GITLAB_TOKEN environment variable)
- `-o, --output`: Output file path (default: repomap.json)
- `-v, --verbose`: Enable verbose logging
- `--version`: Show version information

### Python API

```python
from repomap.core import fetch_repo_structure
from repomap.tree_sitter_wrapper import parse_source_file
from repomap.utils import store_repo_map

# Fetch repository structure
repo_structure = fetch_repo_structure(
    repo_url="https://gitlab.com/username/repo-name",
    token="your-gitlab-token"
)

# Parse source files and generate map
# ... (see documentation for complete example)

# Store the repository map
store_repo_map(repo_map, "output.json")
```

## Supported Languages

The following programming languages are supported for source code parsing:

- Python (.py)
- JavaScript (.js)
- TypeScript (.ts)
- C++ (.cpp, .hpp)
- C (.c, .h)
- Java (.java)
- Ruby (.rb)
- Go (.go)
- Rust (.rs)
- PHP (.php)

## Requirements

- Python 3.7 or higher
- GitLab access token (for private repositories)
- Required Python packages (installed automatically):
  - requests
  - tree-sitter-languages
  - python-dotenv

## Development

1. Clone the repository:
```bash
git clone https://github.com/username/repomap.git
cd repomap
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

4. Run tests:
```bash
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Authors

- Stanislav

## Acknowledgments

- [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) for providing the parsing capabilities
- [GitLab](https://gitlab.com) for their API
