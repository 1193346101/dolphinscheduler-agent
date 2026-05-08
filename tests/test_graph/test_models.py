"""
Models 测试
"""

import pytest
from src.graph.models import (
    Graph, WorkflowNode, TaskNode, TableNode, ClassNode,
    GraphNodes, GraphEdges
)


class TestModels:

    def test_workflow_node_creation(self):
        """测试工作流节点创建"""
        workflow = WorkflowNode(
            code="123",
            name="daily_etl",
            schedule_type="CRON",
            schedule_cron="0 8 * * *",
            is_sub_workflow=False,
            parent_workflow=None
        )

        assert workflow.code == "123"
        assert workflow.name == "daily_etl"
        assert workflow.schedule_type == "CRON"

    def test_task_node_creation(self):
        """测试任务节点创建"""
        task = TaskNode(
            code="789",
            name="spark_transform",
            workflow_code="123",
            task_type="SPARK",
            spark_main_class="com.example.TransformJob",
            params={}
        )

        assert task.code == "789"
        assert task.task_type == "SPARK"
        assert task.spark_main_class == "com.example.TransformJob"

    def test_table_node_creation(self):
        """测试表节点创建"""
        table = TableNode(
            full_name="hive.db.target_table",
            table_type="HIVE"
        )

        assert table.full_name == "hive.db.target_table"
        assert table.table_type == "HIVE"

    def test_class_node_creation(self):
        """测试类节点创建"""
        cls = ClassNode(
            name="com.example.TransformJob",
            file_path="/code/com/example/TransformJob.java",
            cross_project=False,
            source_project=None,
            tables_input=["hive.db.source_table"],
            tables_output=["hive.db.target_table"]
        )

        assert cls.name == "com.example.TransformJob"
        assert cls.tables_input == ["hive.db.source_table"]

    def test_graph_creation(self):
        """测试图谱创建"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )

        assert graph.project_code == "123"
        assert graph.nodes.workflows == []
        assert graph.edges.workflow_depends_workflow == []

    def test_graph_add_workflow(self):
        """测试添加工作流"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )

        workflow = WorkflowNode(code="123", name="test", schedule_type="CRON", schedule_cron="", is_sub_workflow=False, parent_workflow=None)
        graph.nodes.workflows.append(workflow)

        assert len(graph.nodes.workflows) == 1

    def test_graph_to_dict(self):
        """测试转换为字典"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )

        workflow = WorkflowNode(code="123", name="test", schedule_type="CRON", schedule_cron="0 8 * * *", is_sub_workflow=False, parent_workflow=None)
        graph.nodes.workflows.append(workflow)

        data = graph.to_dict()

        assert data["project_code"] == "123"
        assert len(data["nodes"]["workflows"]) == 1

    def test_graph_from_dict(self):
        """测试从字典创建"""
        data = {
            "project_code": "123",
            "project_name": "test_project",
            "scanned_at": "2026-05-08T10:00:00",
            "version": 1,
            "nodes": {
                "workflows": [
                    {"code": "123", "name": "test", "schedule_type": "CRON", "schedule_cron": "", "is_sub_workflow": False, "parent_workflow": None}
                ],
                "tasks": [],
                "tables": [],
                "classes": []
            },
            "edges": {
                "workflow_depends_workflow": [],
                "task_depends_task": [],
                "workflow_contains_task": [],
                "task_produces_table": [],
                "task_consumes_table": [],
                "class_maps_to_task": []
            }
        }

        graph = Graph.from_dict(data)

        assert graph.project_code == "123"
        assert len(graph.nodes.workflows) == 1