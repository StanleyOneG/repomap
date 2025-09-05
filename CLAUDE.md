# Project Overview

This project, `repomap`, is a Python library and command-line tool for generating repository maps and analyzing code structure from GitLab and GitHub repositories. It can be used to create an Abstract Syntax Tree (AST) of a repository, which can then be used to analyze function calls, find function definitions, and generate call stacks.

The tool supports multiple programming languages, including C, C++, Python, PHP, Go, C#, Java, and JavaScript. It uses the `tree-sitter` library for parsing source code and creating the AST. The repository structure is fetched using the GitLab or GitHub API, and the results are provided as Pydantic models.

The project is structured as a Python package with a `repomap` directory containing the source code and a `tests` directory for unit tests. It uses `poetry` for dependency management and packaging.

## Building and Running

### Installation

The project can be installed using `pip`:

```bash
pip install repomap-suite
```

### CLI Usage

The command-line interface is the primary way to use the tool. The main command is `repomap`.

**Generate Repository Map:**

```bash
repomap https://your-gitlab-or-github-repo-url -o output.json
```

**Generate Call Stack:**

```bash
repomap --call-stack \
  --target-file FILE-URL \
  --line LINE-NUMBER \
  --structure-file REPO-STRUCTURE-FILE-PATH \
  --output-stack PATH-TO-OUTPUT-CALLSTACK
```

**Print Function By Name:**

```bash
repomap --print-function-by-name --name FUNCTION-NAME --repo-tree-path REPO-TREE-PATH
```

**Print Function By Line:**

```bash
repomap --print-function-by-line --line LINE-NUMBER --target-file URL-TO-FILE-IN-REPO
```

### Development

To set up the project for development:

1.  Clone the repository.
2.  Install dependencies using `poetry`:

    ```bash
    poetry install
    ```

### Testing

To run the tests:

```bash
poetry run pytest
```

## Development Conventions

*   **Dependency Management:** The project uses `poetry` to manage dependencies. Dependencies are listed in the `pyproject.toml` file.
*   **Code Style:** The project uses `black` for code formatting and `isort` for import sorting. The configuration for these tools can be found in the `pyproject.toml` file.
*   **Linting:** The project uses `flake8` for linting. The configuration can be found in the `.flake8` file.
*   **Type Checking:** The project uses `mypy` for static type checking. The configuration can be found in the `mypy.ini` file.
*   **Testing:** The project uses `pytest` for testing. Tests are located in the `tests` directory.
*   **Pre-commit Hooks:** The project uses `pre-commit` to run checks before committing code. The configuration can be found in the `.pre-commit-config.yaml` file (although this file is not present in the provided file listing).
