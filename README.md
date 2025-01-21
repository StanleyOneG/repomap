# repomap

A tool for generating repository maps and analyzing code structure from GitLab and GitHub repositories. Can be used both as a CLI tool and as a Python library.

## Features

- Generate repository structure maps from GitLab and GitHub repositories
- Create call stacks from specific lines in source code files
- Support for multiple programming languages:
  - C
  - C++
  - Python
  - PHP
  - Go
  - C#
  - Java
  - JavaScript

## Installation

```bash
pip install repomap
```

## Usage as a Library

> **Note:** Since the library uses multiprocessing internally, it's important to wrap your code in an `if __name__ == "__main__":` block when running scripts directly. This ensures proper behavior of multiprocessing on all platforms.

### Basic Usage

```python
from repomap import RepoTreeGenerator, fetch_repo_structure

def main():
    # Generate repository AST tree
    generator = RepoTreeGenerator(token="your_token")
    tree = generator.generate_repo_tree("https://github.com/user/repo")
    generator.save_repo_tree(tree, "output.json")

    # Or use lower-level API to fetch repository structure
    structure = fetch_repo_structure("https://github.com/user/repo", token="your_token")

if __name__ == "__main__":
    main()
```

### Example: Analyzing Function Calls

```python
from repomap import RepoTreeGenerator

def analyze_functions():
    # Initialize generator
    repo_tree_generator = RepoTreeGenerator(token="your_token")

    # Generate AST tree
    tree = generator.generate_repo_tree("https://github.com/user/repo")

    # Access function information
    for file_path, file_data in tree["files"].items():
        if file_data["language"] == "python":  # or any other supported language
            ast_data = file_data["ast"]
            
            # Get all functions and their calls
            for func_name, func_info in ast_data["functions"].items():
                print(f"Function: {func_name}")
                print(f"Calls: {func_info['calls']}")
                print(f"Lines: {func_info['start_line']}-{func_info['end_line']}")

if __name__ == "__main__":
    analyze_functions()
```

### Example: Working with Function Content and Call Stacks

```python
from repomap import CallStackGenerator

# Initialize generator
call_stack_generator = CallStackGenerator(token="your_token")

# Get function content by line number
content = generator.get_function_content_by_line(
    "https://github.com/user/repo/file.py",
    line_number=42
)

# Get function content by name (returns dict mapping class names to implementations)
contents = generator.get_function_content_by_name(
    "repo_tree.json",  # Path to previously generated repo tree
    "my_function"
)
for class_name, implementation in contents.items():
    print(f"Implementation in {class_name}:")
    print(implementation)

# Generate call stack for a specific line
call_stack = generator.generate_call_stack(
    "https://github.com/user/repo/file.py",
    line_number=42
)
for call in call_stack:
    print(f"Function: {call['function']}")
    print(f"Calls: {call['calls']}")
```

## CLI Usage

### Generate Repository Map

```bash
repomap https://your-gitlab-repo-url -o output.json
```

Options:
- `-t, --token`: GitLab/GitHub access token (overrides environment variable)
- `-o, --output`: Output file path (default: repomap.json)
- `-v, --verbose`: Enable verbose logging

### Generate Call Stack

```bash
repomap --call-stack \
  --target-file FILE-URL \
  --line LINE-NUMBER \
  --structure-file REPO-STRUCTURE-FILE-PATH \
  --output-stack PATH-TO-OUTPUT-CALLSTACK
```

Options:
- `--target-file`: URL to the target file for call stack generation
- `--line`: Line number in target file for call stack generation
- `--structure-file`: Path to repository structure JSON file
- `--output-stack`: Output file path for call stack

Example:
```bash
repomap --call-stack \
  --target-file https://gitlab.com/repo/src/main.py \
  --line 42 \
  --structure-file repo-structure.json \
  --output-stack call-stack.json
```

The generated call stack will be saved in JSON format with the following structure:
```json
[
  {
    "function": "main",
    "file": "https://gitlab.com/repo/src/main.py",
    "line": 42,
    "calls": ["helper1", "helper2"]
  }
]
```

## Development

### Setup

1. Clone the repository
2. Install dependencies:
```bash
poetry install
```

### Testing

Run tests with:
```bash
poetry run pytest
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request


### TODO:
1. Add Pydantic models output for functions
2. Refactor