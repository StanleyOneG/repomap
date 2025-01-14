# repomap

A tool for generating repository maps and analyzing code structure from GitLab repositories.

## Features

- Generate repository structure maps from GitLab repositories
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

## Usage

### Generate Repository Map

```bash
repomap https://your-gitlab-repo-url -o output.json
```

Options:
- `-t, --token`: GitLab access token (overrides environment variable)
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

