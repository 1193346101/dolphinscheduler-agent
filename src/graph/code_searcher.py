"""
CodeSearcher - Code file search by class name

Searches for Java/Scala/Python files by class name.
Used by Scanner to find Spark main class files.
"""

import os
from typing import Dict, List, Optional


class CodeSearcher:
    """
    Code file searcher that locates files by class name.

    Search Strategy:
    1. First: search within project directory ({code_root}/{project_name}/**)
    2. If not found: search globally ({code_root}/**)
    """

    def __init__(self, code_root: str):
        """
        Initialize with code repository root path.

        Args:
            code_root: Root directory containing all code repositories
        """
        self.code_root = code_root

    def class_to_paths(self, class_name: str) -> List[str]:
        """
        Convert class name to possible file paths.

        Handles Scala inner classes by splitting at $.
        Returns paths for .java, .scala, .py files.

        Args:
            class_name: Fully qualified class name (e.g., "com.example.MyClass"
                       or "com.example.Outer$Inner")

        Returns:
            List of possible relative file paths
        """
        paths = []

        # Handle Scala inner classes: Outer$Inner -> Outer
        # Split at $ and take the first part for file path
        simple_class_name = class_name.split('$')[0]

        # Convert class name to path
        # e.g., "com.example.MyClass" -> "com/example/MyClass"
        class_path = simple_class_name.replace('.', os.sep)

        # Generate paths for each supported file extension
        for ext in ['.java', '.scala', '.py']:
            paths.append(f"{class_path}{ext}")

        return paths

    def search_class(self, class_name: str, project_name: str) -> Dict:
        """
        Search for class file by class name.

        First searches in project directory, then globally if not found.

        Args:
            class_name: Fully qualified class name
            project_name: Project name to search first

        Returns:
            Dict with keys:
            - found: bool
            - file_path: str or null
            - cross_project: bool
            - source_project: str or null
        """
        possible_paths = self.class_to_paths(class_name)

        # First: search within project directory
        project_dir = os.path.join(self.code_root, project_name)
        for path in possible_paths:
            full_path = os.path.join(project_dir, path)
            if os.path.isfile(full_path):
                return {
                    "found": True,
                    "file_path": full_path,
                    "cross_project": False,
                    "source_project": project_name
                }

        # Second: search globally if not found in project
        for path in possible_paths:
            # Search in code_root subdirectories
            for root, dirs, files in os.walk(self.code_root):
                # Skip the original project directory (already searched)
                if root.startswith(project_dir):
                    continue

                full_path = os.path.join(root, path)
                if os.path.isfile(full_path):
                    # Extract source project name from path
                    rel_path = os.path.relpath(full_path, self.code_root)
                    source_project = rel_path.split(os.sep)[0] if os.sep in rel_path else None

                    return {
                        "found": True,
                        "file_path": full_path,
                        "cross_project": True,
                        "source_project": source_project
                    }

        # Not found
        return {
            "found": False,
            "file_path": None,
            "cross_project": False,
            "source_project": None
        }

    def read_file_content(self, file_path: str) -> Optional[str]:
        """
        Read file content with UTF-8 encoding.

        Args:
            file_path: Absolute path to file

        Returns:
            File content as string, or None if file doesn't exist or read fails
        """
        try:
            if not os.path.isfile(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (IOError, OSError, UnicodeDecodeError):
            return None


__all__ = ["CodeSearcher"]