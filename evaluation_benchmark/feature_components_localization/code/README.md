# Dependency Analysis Tool

## Overview
This Python script automates the process of analyzing and extracting dependencies from Python source files within specified GitHub repositories. It identifies both internal and external dependencies by examining import statements in the code.

## Modules and Classes

### ImportAnalyzer (ast.NodeVisitor subclass)
- Analyzes Python AST nodes to extract imported module names and used attributes.
- Methods:
  - `visit_Import`: Processes `import` statements to capture imported modules.
  - `visit_ImportFrom`: Handles `from ... import ...` statements for module-specific imports.
  - `visit_Attribute`: Captures attributes used from the imported modules.
  - `_resolve_full_name`: Resolves the full names of attributes to their respective modules.

### DependencyAnalyzer
- Analyzes dependencies in Python source files.
- Includes methods for internal module and standard library checks, dependency filtering, and extraction.
- Methods:
  - `_is_standard_library`: Determines if a module is part of the Python standard library.
  - `_is_internal_module`: Checks if a module is an internal module within the project.
  - `_filter_dependencies`: Filters out redundant or non-essential dependencies from the list.
  - `_remove_parent_modules`: Removes parent modules when a child module is already included.
  - `_filter_redundant_paths`: Eliminates paths that are redundant in the context of dependency analysis.
  - `extract_dependencies`: Main method to extract a sorted list of dependencies from a given script.
  - `read_all_files_in_folder`: Reads all Python files in a specified folder and extracts their dependencies.

### RepoManager
- Manages repository operations such as cloning and dependency analysis.
- `__init__`: Initializes with a project root directory.
- `clone_repo`: Clones a repository from GitHub.
- `analyze_examples_folder`: Analyzes dependencies in the 'examples' folder of a repository.
- `analyze_docs_and_nested_examples`: Analyzes dependencies in the 'docs' folder and any nested 'examples' folder within it.

## Main Function
- The script reads repository names from a JSON file (`swe-bench-dev.json`).
- Iterates over each repository, clones it, and analyzes dependencies in the 'examples' and 'docs' folders.
- Dependencies from each repository are aggregated and saved in a JSON file (`file_dependencies.json`).

## Usage
1. Place the `swe-bench-dev.json` file in the same directory as the script. This file should contain the repositories to be analyzed:
2. Run this script
```bash
python extract_feature_components_from_useage.py
```
3. The script outputs the dependencies in a structured JSON format (file_dependencies.json).
