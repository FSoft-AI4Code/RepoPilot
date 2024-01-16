import json
import subprocess
import ast
import sys
import importlib.util
import os


class ImportAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imported_names = {}
        self.used_attributes = set()

    def visit_Import(self, node):
        for alias in node.names:
            self.imported_names[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imported_names[alias.asname or alias.name] = full_name
        self.generic_visit(node)

    def visit_Attribute(self, node):
        full_name = self._resolve_full_name(node)
        if full_name:
            self.used_attributes.add(full_name)
        self.generic_visit(node)

    def _resolve_full_name(self, node):
        names = []
        while isinstance(node, ast.Attribute):
            names.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name) and node.id in self.imported_names:
            names.append(self.imported_names[node.id])
        else:
            return None
        names.reverse()
        return '.'.join(names)

class DependencyAnalyzer:
    def __init__(self, project_root):
        self.project_root = project_root
        self.file_dependencies = {}

    def _is_standard_library(self, name):
        if name in sys.builtin_module_names:
            return True
        if self.project_root in sys.path:
            sys.path.remove(self.project_root)
        try:
            file_location = importlib.util.find_spec(name).origin
            return "python" in file_location.lower() and "site-packages" not in file_location
        except (ImportError, AttributeError, TypeError):
            return False

    def _is_internal_module(self, name):
        sys.path.insert(0, self.project_root)
        try:
            module_spec = importlib.util.find_spec(name)
            if module_spec and module_spec.origin:
                sys.path.remove(self.project_root)
                return os.path.commonpath([self.project_root, module_spec.origin]) == self.project_root
        except (ImportError, AttributeError, TypeError):
            return False
        return False

    def _filter_dependencies(self, dependencies):
        internal_deps = set()
        for dep in dependencies:
            base_module = dep.split('.')[0]
            if not self._is_standard_library(base_module) and self._is_internal_module(base_module):
                internal_deps.add(dep)
        return internal_deps

    def _remove_parent_modules(self, imports, used_attributes):
        final_dependencies = set(imports)
        for attribute in used_attributes:
            parts = attribute.split('.')
            for i in range(1, len(parts)):
                parent_module = '.'.join(parts[:i])
                if parent_module in imports:
                    final_dependencies.discard(parent_module)
        final_dependencies.update(used_attributes)
        return final_dependencies

    def _filter_redundant_paths(self, used_attributes):
        filtered_attributes = set()
        for attr in used_attributes:
            if not any(other.startswith(f"{attr}.") for other in used_attributes if other != attr):
                filtered_attributes.add(attr)
        return filtered_attributes

    def extract_dependencies(self, script):
        tree = ast.parse(script)
        analyzer = ImportAnalyzer()
        analyzer.visit(tree)
        all_dependencies = self._remove_parent_modules(analyzer.imported_names.values(), self._filter_redundant_paths(analyzer.used_attributes))
        internal_dependencies = self._filter_dependencies(all_dependencies)
        return sorted(internal_dependencies)

    def read_all_files_in_folder(self, folder_path):
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                if file_path.endswith('.py'):
                    with open(file_path, 'r') as f:
                        content = f.read()
                        dependencies = self.extract_dependencies(content)
                        print(f'File: {file_path}')
                        print(f'Dependencies: {dependencies}')
                        self.file_dependencies[file_path] = {'dependencies': dependencies}

class RepoManager:
    def __init__(self, project_root):
        self.project_root = project_root
        self.dependency_analyzer = DependencyAnalyzer(project_root)

    def clone_repo(self, repo_name, target_dir=None):
        repo_url = f"https://github.com/{repo_name}.git"
        clone_dir = target_dir if target_dir else repo_name.split('/')[-1]
        if os.path.exists(clone_dir) and os.path.isdir(clone_dir):
            print(f"Repository already exists: {clone_dir}")
            return
        result = subprocess.run(["git", "clone", repo_url, clone_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print(f"Repository cloned successfully: {repo_url}")
        else:
            print(f"Error cloning repository: {result.stderr}")

    def analyze_examples_folder(self, repo_path):
        examples_path = os.path.join(repo_path, 'examples')
        if os.path.exists(examples_path) and os.path.isdir(examples_path):
            self.dependency_analyzer.read_all_files_in_folder(examples_path)
            return "Successfully analyzed all files in the 'examples' folder."
        else:
            return "'examples' folder not found in the repository."

    def analyze_docs_and_nested_examples(self, repo_path):
        docs_path = os.path.join(repo_path, 'docs')
        if os.path.exists(docs_path) and os.path.isdir(docs_path):
            contents = os.listdir(docs_path)
            if 'examples' in contents:
                examples_path = os.path.join(docs_path, 'examples')
                self.dependency_analyzer.read_all_files_in_folder(examples_path)
                return "Successfully analyzed all files in the 'examples' folder inside 'docs'."
            else:
                return "'examples' folder not found in the 'docs' folder."
        else:
            return "'docs' folder not found in the repository."


def main():
    with open('swe-bench-dev.json') as f:
        datas = json.load(f)
    repo_names = list(set(data['repo'] for data in datas))

    # Read existing data from the file, if it exists
    if os.path.exists('file_dependencies.json'):
        with open('file_dependencies.json', 'r') as f:
            aggregated_file_dependencies = json.load(f)
    else:
        aggregated_file_dependencies = {}

    for name in repo_names:
        print(f"Analyzing repository: {name}")
        repo_dir = name.split('/')[-1]  # Extract the repository directory name
        repo_path = os.path.join(os.getcwd(), repo_dir)  # Full path to the repository

        repo_manager = RepoManager(repo_path)
        repo_manager.clone_repo(name)

        print(repo_manager.analyze_examples_folder(repo_path))
        print(repo_manager.analyze_docs_and_nested_examples(repo_path))

        # Update the aggregated file dependencies
        aggregated_file_dependencies.update(repo_manager.dependency_analyzer.file_dependencies)

        # Write the updated file dependencies back to the file
        with open('file_dependencies.json', 'w') as f:
            json.dump(aggregated_file_dependencies, f, indent=4)

if __name__ == "__main__":
    main()
