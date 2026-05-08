"""
CodeSearcher tests
"""

import pytest
import tempfile
import os
from src.graph.code_searcher import CodeSearcher


class TestCodeSearcher:

    def test_init_with_code_root(self):
        """Test initialization with code root"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)
            assert searcher.code_root == tmpdir

    def test_class_to_path_java(self):
        """Test class name to path conversion for Java"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)

            paths = searcher.class_to_paths("com.example.MyClass")

            # Should return 3 paths for .java, .scala, .py
            assert len(paths) == 3

            # Check Java path
            java_path = [p for p in paths if p.endswith('.java')][0]
            assert java_path == os.path.join("com", "example", "MyClass.java")

    def test_class_to_path_scala(self):
        """Test class name to path conversion for Scala with inner class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)

            # Scala inner class: Outer$Inner
            paths = searcher.class_to_paths("com.example.Outer$Inner")

            # Should split at $ and use Outer
            scala_path = [p for p in paths if p.endswith('.scala')][0]
            assert scala_path == os.path.join("com", "example", "Outer.scala")

            # Java path should also use Outer
            java_path = [p for p in paths if p.endswith('.java')][0]
            assert java_path == os.path.join("com", "example", "Outer.java")

    def test_class_to_path_python(self):
        """Test class name to path conversion for Python"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)

            paths = searcher.class_to_paths("mypackage.mymodule.MyClass")

            python_path = [p for p in paths if p.endswith('.py')][0]
            assert python_path == os.path.join("mypackage", "mymodule", "MyClass.py")

    def test_search_in_project_found(self):
        """Test searching for class in project directory - found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project structure
            project_dir = os.path.join(tmpdir, "myproject")
            package_dir = os.path.join(project_dir, "com", "example")
            os.makedirs(package_dir)

            # Create a Java file
            java_file = os.path.join(package_dir, "MyClass.java")
            with open(java_file, 'w', encoding='utf-8') as f:
                f.write("package com.example;\npublic class MyClass {}")

            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.example.MyClass", "myproject")

            assert result["found"] is True
            assert result["file_path"] == java_file
            assert result["cross_project"] is False
            assert result["source_project"] == "myproject"

    def test_search_in_project_not_found_global_found(self):
        """Test searching - not in project, found globally"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two projects
            project_a = os.path.join(tmpdir, "project_a")
            project_b = os.path.join(tmpdir, "project_b")

            package_a = os.path.join(project_a, "com", "example")
            package_b = os.path.join(project_b, "com", "other")

            os.makedirs(package_a)
            os.makedirs(package_b)

            # Create file in project_b, not project_a
            java_file = os.path.join(package_b, "SharedClass.scala")
            with open(java_file, 'w', encoding='utf-8') as f:
                f.write("package com.other\nclass SharedClass")

            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.other.SharedClass", "project_a")

            assert result["found"] is True
            assert result["file_path"] == java_file
            assert result["cross_project"] is True
            assert result["source_project"] == "project_b"

    def test_search_not_found(self):
        """Test searching - class not found anywhere"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty project
            project_dir = os.path.join(tmpdir, "myproject")
            os.makedirs(project_dir)

            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.nonexistent.MissingClass", "myproject")

            assert result["found"] is False
            assert result["file_path"] is None
            assert result["cross_project"] is False
            assert result["source_project"] is None

    def test_read_file_content(self):
        """Test reading file content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test.txt")
            content = "Hello, World!\nTest content"
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write(content)

            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.read_file_content(test_file)

            assert result == content

    def test_read_file_content_not_found(self):
        """Test reading file content - file not found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.read_file_content("/nonexistent/path/file.txt")

            assert result is None

    def test_read_file_content_invalid_encoding(self):
        """Test reading file content - invalid UTF-8"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with invalid UTF-8 content
            test_file = os.path.join(tmpdir, "binary.bin")
            with open(test_file, 'wb') as f:
                f.write(b'\xff\xfe\xfd\xfc')  # Invalid UTF-8 bytes

            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.read_file_content(test_file)

            # Should return None on encoding error
            assert result is None