# REPOMAP

A Python library and CLI tool for generating repository AST maps and analyzing code structure from GitLab and GitHub repositories. Built on **ast-grep** for fast, accurate parsing across 10 programming languages.

## Features

- Generate repository AST trees from GitLab and GitHub repositories
- Analyze function calls, class structures, and import relationships
- Create call stacks from specific lines in source code
- Smart caching with commit hash comparison to skip unnecessary regeneration
- High-performance local cloning with multiprocessing support
- Output as Pydantic models for type-safe analysis

### Supported Languages

| Language | Extensions |
|----------|------------|
| Python | `.py`, `.pyx`, `.pyi` |
| C | `.c`, `.h` |
| C++ | `.cpp`, `.hpp`, `.cc`, `.cxx` |
| Go | `.go` |
| Java | `.java` |
| PHP | `.php` |
| C# | `.cs` |
| JavaScript | `.js`, `.jsx`, `.mjs` |
| TypeScript | `.ts` |
| TSX | `.tsx` |

## Installation

```bash
pip install repomap-suite
```

## Usage as a Library

> **Note:** The library uses multiprocessing internally for building repository AST trees. Wrap your code in an `if __name__ == "__main__":` block when running scripts directly.

### Environment Setup

```bash
export GITLAB_TOKEN=your_gitlab_token
export GITHUB_TOKEN=your_github_token
```

### Basic Usage

```python
import os
from repomap import RepoTreeGenerator

def main():
    # Initialize generator
    generator = RepoTreeGenerator(
        token=os.getenv("GITHUB_TOKEN"),
        use_multiprocessing=True,  # default: True
        use_local_clone=True,      # default: True (faster via shallow clone)
    )

    # Generate repository AST tree
    tree = generator.generate_repo_tree(
        "https://github.com/user/repo",
        ref="main"  # optional: branch, tag, or commit
    )

    # Save to file
    generator.save_repo_tree(tree, "output.json")

if __name__ == "__main__":
    main()
```

### Smart Caching (Skip Unchanged Repositories)

```python
import os
from repomap import RepoTreeGenerator

def main():
    generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))

    repo_url = "https://github.com/user/repo"
    output_path = "repo-tree.json"

    # Check if existing tree is still current (compares commit hashes)
    if generator.is_repo_tree_up_to_date(repo_url, ref="main", output_path=output_path):
        print("Tree is up to date, skipping regeneration")
    else:
        print("Repository changed, regenerating...")
        tree = generator.generate_repo_tree(repo_url, ref="main")
        generator.save_repo_tree(tree, output_path)

    # Or use the convenience method that handles this automatically:
    tree = generator.generate_repo_tree_if_needed(
        repo_url,
        ref="main",
        output_path=output_path,
        force=False  # set True to regenerate regardless
    )

if __name__ == "__main__":
    main()
```

### Analyzing Repository Structure

```python
import os
from repomap import RepoTreeGenerator

def analyze_functions():
    generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))
    tree = generator.generate_repo_tree("https://github.com/user/repo")

    for file_path, file_data in tree["files"].items():
        language = file_data["language"]
        ast_data = file_data["ast"]

        # Get all functions and their calls
        for func_name, func_info in ast_data["functions"].items():
            print(f"Function: {func_name}")
            print(f"  Language: {language}")
            print(f"  Lines: {func_info['start_line']}-{func_info['end_line']}")
            print(f"  Calls: {func_info['calls']}")

if __name__ == "__main__":
    analyze_functions()
```

### Working with Pydantic Models

```python
import os
from repomap import RepoTreeGenerator
from repomap.schemas import RepoStructureModel, FileASTModel

def main():
    # Generate and save repository tree
    generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))
    tree = generator.generate_repo_tree("https://github.com/user/repo")
    generator.save_repo_tree(tree, "output.json")

    # Load as Pydantic model for type-safe access
    with open("output.json", "r") as f:
        repo_structure = RepoStructureModel.model_validate_json(f.read())

    # Check if cross-reference population succeeded
    if repo_structure.is_called_by_population_failed:
        print("Warning: called_by field population failed")

    # Access file AST data
    file_ast: FileASTModel = repo_structure.files.get("src/main.py")
    if file_ast:
        print(f"Language: {file_ast.language}")
        print(f"Imports: {file_ast.ast.imports}")

        # Iterate functions
        for func_name, func_details in file_ast.ast.functions.items():
            print(f"Function: {func_name}")
            print(f"  Lines: {func_details.start_line}-{func_details.end_line}")
            print(f"  Is method: {func_details.is_method}")

            # See where this function is called from
            for call_site in func_details.called_by:
                print(f"  Called by: {call_site.caller_function_name} "
                      f"in {call_site.file_path}:{call_site.line_number}")

if __name__ == "__main__":
    main()
```

### Working with Call Stacks

```python
import os
from repomap import CallStackGenerator

def main():
    generator = CallStackGenerator(token=os.getenv("GITHUB_TOKEN"))

    # Get function content by line number
    file_url = "https://github.com/user/repo/blob/main/src/utils.py"
    content = generator.get_function_content_by_line(
        file_url=file_url,
        line_number=42
    )
    print(content)

    # Get function content by name (searches entire repo tree)
    # Returns dict mapping "file_path:class_or_global" to function content
    contents = generator.get_function_content_by_name(
        ast_tree="repo-tree.json",  # path to JSON or dict
        function_name="my_function",
        file_path="src/utils.py"    # optional: limit search scope
    )
    for location, code in contents.items():
        print(f"Found in {location}:")
        print(code)

    # Generate call stack for a specific line
    call_stack = generator.generate_call_stack(file_url, line_number=42)
    for call in call_stack:
        print(f"Function: {call['function']}")
        print(f"  File: {call['file']}")
        print(f"  Line: {call['line']}")
        print(f"  Calls: {call['calls']}")

if __name__ == "__main__":
    main()
```

## CLI Usage

### Generate Repository AST Tree

```bash
# Basic usage
repomap https://github.com/user/repo --repo-tree -o output.json

# With specific branch/tag/commit
repomap https://github.com/user/repo --repo-tree --ref main -o output.json

# Use API mode instead of local clone (slower but less disk space)
repomap https://github.com/user/repo --repo-tree --no-local-clone -o output.json
```

The CLI automatically checks if an existing tree is up to date and skips regeneration when the commit hash matches.

### Print Function by Line

```bash
repomap --print-function \
  --target-file https://github.com/user/repo/blob/main/src/utils.py \
  --line 42
```

### Print Function by Name

```bash
# Search entire repository
repomap --print-function-by-name \
  --name my_function \
  --repo-tree-path repo-tree.json

# Search in specific file
repomap --print-function-by-name \
  --name my_function \
  --repo-tree-path repo-tree.json \
  --file-path src/utils.py
```

### Generate Call Stack

```bash
repomap --call-stack \
  --target-file https://github.com/user/repo/blob/main/src/main.py \
  --line 42 \
  --output-stack call-stack.json
```

Output format:

```json
[
  {
    "function": "main",
    "file": "https://github.com/user/repo/blob/main/src/main.py",
    "line": 42,
    "calls": ["helper1", "helper2"]
  }
]
```

### CLI Options Reference

| Option | Description |
|--------|-------------|
| `-t, --token` | GitLab/GitHub access token (overrides env var) |
| `-o, --output` | Output file path (default: repomap.json) |
| `-v, --verbose` | Enable debug logging |
| `--version` | Show version |
| `--repo-tree` | Generate repository AST tree |
| `--ref` | Git reference (branch, tag, commit) |
| `--no-local-clone` | Use API instead of local clone |
| `--call-stack` | Generate call stack mode |
| `--print-function` | Print function at line |
| `--print-function-by-name` | Print function by name |
| `--target-file` | URL to target file |
| `--line` | Line number |
| `--structure-file` | Path to repo structure JSON |
| `--output-stack` | Output path for call stack |
| `--name` | Function name to search |
| `--repo-tree-path` | Path to repo-tree JSON |
| `--file-path` | Limit search to specific file |

## Configuration

### Disabling Multiprocessing

For debugging or environments where multiprocessing causes issues:

```python
generator = RepoTreeGenerator(use_multiprocessing=False)
```

### Using API Mode (No Local Clone)

For environments with limited disk space or when you need to avoid git operations:

```python
generator = RepoTreeGenerator(use_local_clone=False)
```

Note: API mode is slower but doesn't require disk space for cloning.

## Development

### Setup

```bash
git clone https://github.com/StanleyOneG/repomap.git
cd repomap
poetry install
```

### Testing

```bash
poetry run pytest
```

### Code Quality

```bash
poetry run black repomap/
poetry run isort repomap/
poetry run flake8 repomap/
poetry run mypy repomap/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request
