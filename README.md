# REPOMAP

A Python library and CLI tool for generating repository maps and analyzing code structure from GitLab and GitHub repositories as Pydantic models. 

Can be used both as a CLI tool and as a Python library.

## Features

- Generate repository structure maps from GitLab and GitHub repositories
- Create call stacks from specific lines in source code files

> **Note:** Currently tested on C/C++ and Python languages. Other languages may not work as expected.
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
pip install repomap-suite
```

## Usage as a Library

> **Note:** Since the library uses multiprocessing internally for building repository ast tree, it's important to wrap your code in an `if __name__ == "__main__":` block when running scripts with `RepoTreeGenerator` directly. This ensures proper behavior of multiprocessing on all platforms.

You can disable multiprocessing by using:
```python
RepoTreeGenerator(use_multiprocessing=False) # default: True
```

### Basic Usage

#### Env keys set

```bash
export GITLAB_TOKEN=your_token
export GITHUB_TOKEN=your_token
```

```python
import os
from repomap import RepoTreeGenerator

def main():
    # Generate repository AST tree
    generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))
    tree = generator.generate_repo_tree("https://github.com/user/repo")
    generator.save_repo_tree(tree, "output.json")

if __name__ == "__main__":
    main()
```

### Example: Analyzing Function Calls

```python
import os
from repomap import RepoTreeGenerator

def analyze_functions():
    # Initialize generator
    repo_tree_generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))

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
import os
from repomap import CallStackGenerator

# Initialize generator
call_stack_generator = CallStackGenerator(token=os.getenv("GITHUB_TOKEN"))

# Get function content by line number
content = call_stack_generator.get_function_content_by_line(
    "https://github.com/user/repo/file.py",
    line_number=42
)

# Get function content by name (returns dict mapping class names to implementations)
contents = call_stack_generator.get_function_content_by_name(
    "repo_tree.json",  # Path to previously generated repo tree
    "my_function"
)
for class_name, implementation in contents.items():
    print(f"Implementation in {class_name}:")
    print(implementation)

# Generate call stack for a specific line
call_stack = call_stack_generator.generate_call_stack(
    "https://github.com/user/repo/file.py",
    line_number=42
)
for call in call_stack:
    print(f"Function: {call['function']}")
    print(f"Calls: {call['calls']}")
```

### Example: Working with repository tree as Pydantic models

**Simple example of analyzing file:**

```python
import os
from repomap import RepoTreeGenerator
from repomap.schemas import RepoStructureModel, FileASTModel

def generate_repo_tree():
    # Generate repository AST tree
    generator = RepoTreeGenerator(token=os.getenv("GITHUB_TOKEN"))
    tree = generator.generate_repo_tree("https://github.com/StanleyOneG/repomap")
    generator.save_repo_tree(tree, "output.json")

def analyze_repo_tree():
    with open("output.json", "r") as f:
        repo_structure = RepoStructureModel.model_validate_json(f.read())


    assert not repo_structure.is_called_by_population_failed # check if `called_by` field successfully populated
    callstack_file_tree = repo_structure.files.get("repomap/callstack.py") # is a FileASTModel object
    
    print("###### Language:\n")
    print(callstack_file_tree.language) # What programming language is this file?
    print("\n###### Imports:\n")
    print(callstack_file_tree.ast.imports) # What imports are in this file?
    print("\n###### Functions:\n")
    print(callstack_file_tree.ast.functions) # What functions are defined in this file?
    print("\n###### Where `CallStackGenerator.get_function_content_by_name` method is called\n")
    print(callstack_file_tree.ast.functions.get("CallStackGenerator.get_function_content_by_name").called_by) # What functions call this method and in what lines?
    

if __name__ == "__main__":
    generate_repo_tree()
    analyze_repo_tree()
```

**The beauty is that we now have all advantages of Pydantic models**

## CLI Usage

### Generate Repository Map

```bash
repomap https://your-gitlab-or-github-repo-url -o output.json
```

Options:
- `-t, --token`: GitLab/GitHub access token (overrides environment variable)
- `-o, --output`: Output file path (default: repomap.json)
- `-v, --verbose`: Enable verbose logging
- `--ref`: GitLab/GitHub branch or tag (defaults to default branch)


### Print Function By Name

```bash
repomap --print-function-by-name --name FUNCTION-NAME --repo-tree-path REPO-TREE-PATH
```

Options:
- `--name`: Name of the function to print
- `--repo-tree-path`: Path to the repository tree JSON file generated earlier

### Print Function By Line

```bash
repomap --print-function-by-line --line LINE-NUMBER --target-file URL-TO-FILE-IN-REPO
```

Options:
- `--line`: Line number of the function to print
- `--target-file`: Url of the file in a repo within branch/ref 

Example:
```bash
repomap --print-function-by-line --line 42 --target-file https://github.com/StanleyOneG/repomap/blob/feat-new-pydantic-schemas/repomap/cli.py
```

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
