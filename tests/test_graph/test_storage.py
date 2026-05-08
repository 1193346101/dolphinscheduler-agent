"""
Storage 测试
"""

import pytest
import tempfile
import os
from src.graph.storage import GraphStorage


class TestGraphStorage:

    def test_init_with_data_dir(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            assert storage.data_dir == tmpdir

    def test_save_graph(self):
        """测试保存图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph_data = {
                "project_code": "123",
                "project_name": "test_project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {"workflows": [], "tasks": [], "tables": [], "classes": []},
                "edges": {}
            }

            storage.save_graph("123", graph_data)

            # 验证文件存在
            path = os.path.join(tmpdir, "123_graph.json")
            assert os.path.exists(path)

    def test_load_graph(self):
        """测试加载图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph_data = {
                "project_code": "123",
                "project_name": "test_project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {"workflows": [], "tasks": [], "tables": [], "classes": []},
                "edges": {}
            }

            storage.save_graph("123", graph_data)
            loaded = storage.load_graph("123")

            assert loaded["project_code"] == "123"

    def test_load_graph_not_found(self):
        """测试加载不存在的图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            loaded = storage.load_graph("nonexistent")
            assert loaded is None

    def test_save_index(self):
        """测试保存索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {}
            }

            storage.save_index("123", "downstream", index_data)

            path = os.path.join(tmpdir, "123_index_downstream.json")
            assert os.path.exists(path)

    def test_load_index(self):
        """测试加载索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {"123": {"direct": [], "all": [], "count": 0}}
            }

            storage.save_index("123", "downstream", index_data)
            loaded = storage.load_index("123", "downstream")

            assert loaded["workflow_downstream"]["123"]["count"] == 0

    def test_graph_exists(self):
        """测试检查图谱是否存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            assert storage.graph_exists("123") is False

            graph_data = {"project_code": "123", "nodes": {}, "edges": {}}
            storage.save_graph("123", graph_data)

            assert storage.graph_exists("123") is True

    def test_sanitize_code_malicious_input(self):
        """测试恶意代码清理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            assert storage._sanitize_code("../secret") == "___secret"
            assert storage._sanitize_code("test/project") == "test_project"
            assert storage._sanitize_code("") == "unknown"

    def test_path_traversal_sanitized(self):
        """测试路径穿越防护 - 路径被清理后安全保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 恶意 project_code 被清理为安全格式
            graph_data = {"project_code": "../test", "nodes": {}, "edges": {}}
            storage.save_graph("../test", graph_data)

            # 能够正常加载，因为路径被清理
            loaded = storage.load_graph("../test")
            assert loaded is not None
            assert loaded["project_code"] == "../test"