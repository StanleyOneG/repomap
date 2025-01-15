"""Setup configuration for repomap package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="repomap",
    version="0.1.0",
    author="Stanislav Goncharuk",
    description="Repository map generator for GitLab repositories",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/username/repomap",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "python-gitlab>=4.4.0",
        "tree-sitter-languages>=1.10.2",
        "tree-sitter>=0.21.3",
        "python-dotenv>=1.0.1",
    ],
    entry_points={
        "console_scripts": [
            "repomap=repomap.cli:main",
        ],
    },
)
