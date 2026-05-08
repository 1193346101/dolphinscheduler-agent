"""
MermaidGenerator 测试
"""

import pytest
import tempfile
import os

from src.graph.mermaid_generator import MermaidGenerator
from src.graph.storage import GraphStorage
from src.graph.models import Graph, GraphNodes, GraphEdges, WorkflowNode


class TestMermaidGenerator:

    def test_init(self):
        """测试初始化"""
        # 无参数初始化
        generator = MermaidGenerator()
        assert generator.storage is None

        # 带存储初始化
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)
            assert generator.storage == storage

    def test_generate_downstream_graph(self):
        """测试生成下游依赖图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [
                        {"code": "wf1", "name": "daily_etl", "schedule_type": "CRON", "schedule_cron": "0 0 * * *", "is_sub_workflow": False, "parent_workflow": None},
                        {"code": "wf2", "name": "daily_summary", "schedule_type": "CRON", "schedule_cron": "0 1 * * *", "is_sub_workflow": False, "parent_workflow": None},
                        {"code": "wf3", "name": "weekly_report", "schedule_type": "CRON", "schedule_cron": "0 2 * * 1", "is_sub_workflow": False, "parent_workflow": None},
                    ],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {
                    "workflow_depends_workflow": [
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf1", "target": "wf3"},
                    ],
                    "workflow_calls_subworkflow": [],
                    "workflow_contains_task": [],
                    "task_depends_task": [],
                    "task_produces_table": [],
                    "task_consumes_table": [],
                    "class_maps_to_task": []
                }
            }

            storage.save_graph("test_project", graph_data)

            # 创建下游索引
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {
                    "wf1": {
                        "direct": ["wf2", "wf3"],
                        "all": ["wf2", "wf3"],
                        "count": 2
                    },
                    "wf2": {
                        "direct": [],
                        "all": [],
                        "count": 0
                    },
                    "wf3": {
                        "direct": [],
                        "all": [],
                        "count": 0
                    }
                },
                "task_downstream": {}
            }
            storage.save_index("test_project", "downstream", index_data)

            # 生成下游图谱
            result = generator.generate_downstream_graph("test_project", "wf1")

            # 验证结果
            assert "graph TD" in result
            assert "wf1[daily_etl]" in result
            assert "wf2[daily_summary]" in result
            assert "wf3[weekly_report]" in result
            assert "wf1[daily_etl] --> wf2[daily_summary]" in result
            assert "wf1[daily_etl] --> wf3[weekly_report]" in result

    def test_generate_downstream_graph_empty(self):
        """测试生成下游依赖图谱 - 无下游"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [
                        {"code": "wf1", "name": "daily_etl", "schedule_type": "CRON", "schedule_cron": "0 0 * * *", "is_sub_workflow": False, "parent_workflow": None},
                    ],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {
                    "workflow_depends_workflow": [],
                    "workflow_calls_subworkflow": [],
                    "workflow_contains_task": [],
                    "task_depends_task": [],
                    "task_produces_table": [],
                    "task_consumes_table": [],
                    "class_maps_to_task": []
                }
            }

            storage.save_graph("test_project", graph_data)

            # 创建下游索引
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {
                    "wf1": {
                        "direct": [],
                        "all": [],
                        "count": 0
                    }
                },
                "task_downstream": {}
            }
            storage.save_index("test_project", "downstream", index_data)

            # 生成下游图谱
            result = generator.generate_downstream_graph("test_project", "wf1")

            # 验证结果 - 应该只包含起始节点
            assert "graph TD" in result
            assert "wf1[daily_etl]" in result

    def test_generate_downstream_graph_not_found(self):
        """测试生成下游依赖图谱 - 工作流不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {}
            }

            storage.save_graph("test_project", graph_data)

            # 创建空下游索引
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {},
                "task_downstream": {}
            }
            storage.save_index("test_project", "downstream", index_data)

            # 生成下游图谱
            result = generator.generate_downstream_graph("test_project", "nonexistent")

            # 验证结果
            assert "graph TD" in result
            assert "not found" in result.lower()

    def test_generate_path_graph(self):
        """测试生成路径图谱"""
        generator = MermaidGenerator()

        path = ["wf1", "wf2", "wf3", "wf4"]
        names = {
            "wf1": "daily_etl",
            "wf2": "daily_summary",
            "wf3": "weekly_report",
            "wf4": "monthly_dashboard"
        }

        result = generator.generate_path_graph(path, names)

        # 验证结果
        assert "graph LR" in result
        assert "wf1[daily_etl]" in result
        assert "wf2[daily_summary]" in result
        assert "wf3[weekly_report]" in result
        assert "wf4[monthly_dashboard]" in result
        assert "wf1 --> wf2" in result
        assert "wf2 --> wf3" in result
        assert "wf3 --> wf4" in result

    def test_generate_path_graph_without_names(self):
        """测试生成路径图谱 - 无名称映射"""
        generator = MermaidGenerator()

        path = ["wf1", "wf2", "wf3"]

        result = generator.generate_path_graph(path)

        # 验证结果 - 使用代码作为名称
        assert "graph LR" in result
        assert "wf1[wf1]" in result
        assert "wf2[wf2]" in result
        assert "wf3[wf3]" in result

    def test_generate_path_graph_empty(self):
        """测试生成路径图谱 - 空路径"""
        generator = MermaidGenerator()

        result = generator.generate_path_graph([])

        # 验证结果
        assert "graph LR" in result
        assert "Empty path" in result

    def test_generate_path_graph_single_node(self):
        """测试生成路径图谱 - 单节点"""
        generator = MermaidGenerator()

        result = generator.generate_path_graph(["wf1"], {"wf1": "test"})

        # 验证结果 - 单节点无边
        assert "graph LR" in result
        assert "wf1[test]" in result
        assert "-->" not in result

    def test_generate_full_graph(self):
        """测试生成完整图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [
                        {"code": "wf1", "name": "daily_etl", "schedule_type": "CRON", "schedule_cron": "0 0 * * *", "is_sub_workflow": False, "parent_workflow": None},
                        {"code": "wf2", "name": "daily_summary", "schedule_type": "CRON", "schedule_cron": "0 1 * * *", "is_sub_workflow": False, "parent_workflow": None},
                        {"code": "wf3", "name": "weekly_report", "schedule_type": "CRON", "schedule_cron": "0 2 * * 1", "is_sub_workflow": False, "parent_workflow": None},
                    ],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {
                    "workflow_depends_workflow": [
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                    ],
                    "workflow_calls_subworkflow": [],
                    "workflow_contains_task": [],
                    "task_depends_task": [],
                    "task_produces_table": [],
                    "task_consumes_table": [],
                    "class_maps_to_task": []
                }
            }

            storage.save_graph("test_project", graph_data)

            # 生成完整图谱
            result = generator.generate_full_graph("test_project")

            # 验证结果
            assert "graph TD" in result
            assert "wf1[daily_etl]" in result
            assert "wf2[daily_summary]" in result
            assert "wf3[weekly_report]" in result
            assert "wf1[daily_etl] --> wf2[daily_summary]" in result
            assert "wf2[daily_summary] --> wf3[weekly_report]" in result

    def test_generate_full_graph_empty(self):
        """测试生成完整图谱 - 空项目"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建空图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {}
            }

            storage.save_graph("test_project", graph_data)

            # 生成完整图谱
            result = generator.generate_full_graph("test_project")

            # 验证结果
            assert "graph TD" in result
            assert "No workflows found" in result

    def test_generate_full_graph_not_found(self):
        """测试生成完整图谱 - 项目不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 不保存任何图谱
            result = generator.generate_full_graph("nonexistent")

            # 验证结果
            assert "graph TD" in result
            assert "not found" in result.lower()

    def test_generate_table_lineage_graph(self):
        """测试生成表血缘图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [
                        {"code": "wf1", "name": "etl_job", "schedule_type": "CRON", "schedule_cron": "0 0 * * *", "is_sub_workflow": False, "parent_workflow": None},
                        {"code": "wf2", "name": "report_job", "schedule_type": "CRON", "schedule_cron": "0 1 * * *", "is_sub_workflow": False, "parent_workflow": None},
                    ],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {}
            }

            storage.save_graph("test_project", graph_data)

            # 创建表消费索引
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "table_consumers": {
                    "hive.db.table1": {
                        "workflows": ["wf2"],
                        "tasks": ["task2"],
                        "classes": []
                    }
                },
                "table_producers": {
                    "hive.db.table1": {
                        "workflows": ["wf1"],
                        "tasks": ["task1"],
                        "classes": []
                    }
                }
            }
            storage.save_index("test_project", "table_consumer", index_data)

            # 生成表血缘图谱
            result = generator.generate_table_lineage_graph("test_project", "hive.db.table1")

            # 验证结果
            assert "graph LR" in result
            assert "table[[db.table1]]" in result  # 简短表名
            assert "wf1[etl_job]" in result  # 生产者
            assert "wf2_c[report_job]" in result  # 消费者

    def test_generate_table_lineage_graph_not_found(self):
        """测试生成表血缘图谱 - 表不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            generator = MermaidGenerator(storage=storage)

            # 创建图谱数据
            graph_data = {
                "project_code": "test_project",
                "project_name": "Test Project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {
                    "workflows": [],
                    "tasks": [],
                    "tables": [],
                    "classes": []
                },
                "edges": {}
            }

            storage.save_graph("test_project", graph_data)

            # 创建空表消费索引
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "table_consumers": {},
                "table_producers": {}
            }
            storage.save_index("test_project", "table_consumer", index_data)

            # 生成表血缘图谱
            result = generator.generate_table_lineage_graph("test_project", "nonexistent.table")

            # 验证结果
            assert "graph LR" in result
            assert "not found" in result.lower()

    def test_no_storage(self):
        """测试无存储实例"""
        generator = MermaidGenerator()

        result = generator.generate_downstream_graph("test", "wf1")
        assert "Storage not initialized" in result

        result = generator.generate_full_graph("test")
        assert "Storage not initialized" in result

        result = generator.generate_table_lineage_graph("test", "table1")
        assert "Storage not initialized" in result

    def test_short_table_name(self):
        """测试简短表名生成"""
        generator = MermaidGenerator()

        # 三段式表名
        assert generator._short_table_name("hive.db.table") == "db.table"

        # 两段式表名
        assert generator._short_table_name("db.table") == "db.table"

        # 单段表名
        assert generator._short_table_name("table") == "table"

    def test_empty_graph(self):
        """测试空图谱生成"""
        generator = MermaidGenerator()

        result = generator._empty_graph("TD", "Test message")
        assert "graph TD" in result
        assert "empty[Test message]" in result

        result = generator._empty_graph("LR", "Another message")
        assert "graph LR" in result
        assert "empty[Another message]" in result