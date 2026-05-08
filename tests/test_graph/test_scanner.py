"""
Tests for GraphScanner
"""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

from src.graph.storage import GraphStorage
from src.graph.scanner import GraphScanner
from src.graph.models import (
    Graph,
    GraphNodes,
    GraphEdges,
    WorkflowNode,
    TaskNode,
    TableNode,
    ClassNode,
)
from src.integrations.dsctl_wrapper import CLIResult


class TestGraphScannerInit(unittest.TestCase):
    """Test GraphScanner initialization"""

    def test_init(self):
        """Test basic initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage, "/path/to/code")

            assert scanner.storage is storage
            assert scanner.code_searcher is not None
            assert scanner.sql_parser is not None


class TestGraphScannerScanProject(unittest.TestCase):
    """Test scan_project method"""

    def test_scan_project_empty(self):
        """Test scanning project with empty workflows"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage, tmpdir)

            # Mock DSCLIClient
            mock_dsctl = Mock()
            mock_result = CLIResult(
                success=True,
                stdout="[]",
                stderr="",
                returncode=0
            )
            mock_dsctl.list_workflows.return_value = mock_result

            with patch.object(
                GraphScanner, '_fetch_workflows',
                return_value=[]
            ) as mock_fetch:
                stats = scanner.scan_project(
                    project_code="123",
                    project_name="test_project",
                    ds_api_url="http://localhost:12345",
                    ds_api_token="test_token"
                )

                assert stats["workflows_count"] == 0
                assert stats["tasks_count"] == 0
                assert stats["tables_count"] == 0

                # Check graph saved
                graph_data = storage.load_graph("123")
                assert graph_data is not None
                assert graph_data["project_code"] == "123"
                assert graph_data["project_name"] == "test_project"

    def test_scan_project_with_workflow(self):
        """Test scanning project with workflows"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage, tmpdir)

            # Mock workflow data
            workflows = [
                {"code": 1001, "name": "workflow_1", "version": 1},
                {"code": 1002, "name": "workflow_2", "version": 2},
            ]

            workflow_detail = {
                "workflow": {
                    "code": 1001,
                    "name": "workflow_1",
                    "schedule": {"crontab": "0 0 * * *"},
                },
                "tasks": [
                    {
                        "code": 2001,
                        "name": "spark_task",
                        "taskType": "SPARK",
                        "taskParams": {"mainArgs": "--class com.example.MyClass"}
                    },
                    {
                        "code": 2002,
                        "name": "shell_task",
                        "taskType": "SHELL",
                        "taskParams": {}
                    },
                ],
                "relations": [
                    {"preTaskCode": 0, "postTaskCode": 2001},
                    {"preTaskCode": 2001, "postTaskCode": 2002},
                ],
            }

            # Mock DSCLIClient
            mock_dsctl = Mock()
            mock_list_result = CLIResult(
                success=True,
                stdout=json.dumps(workflows),
                stderr="",
                returncode=0
            )
            mock_dsctl.list_workflows.return_value = mock_list_result

            mock_detail_result = CLIResult(
                success=True,
                stdout=json.dumps(workflow_detail),
                stderr="",
                returncode=0
            )
            mock_dsctl.describe_workflow.return_value = mock_detail_result

            # Mock CodeSearcher to return no class found
            with patch.object(
                scanner.code_searcher, 'search_class',
                return_value={"found": False, "file_path": None}
            ):
                with patch('src.graph.scanner.DSCLIClient', return_value=mock_dsctl):
                    stats = scanner.scan_project(
                        project_code="123",
                        project_name="test_project",
                        ds_api_url="http://localhost:12345",
                        ds_api_token="test_token"
                    )

                    assert stats["workflows_count"] == 2
                    assert stats["tasks_count"] == 4  # 2 tasks per workflow


class TestExtractSparkMainClass(unittest.TestCase):
    """Test _extract_spark_main_class method"""

    def setUp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.storage = GraphStorage(data_dir=tmpdir)
            self.scanner = GraphScanner(self.storage, tmpdir)

    def test_extract_spark_main_class_with_class(self):
        """Test extracting class from mainArgs with --class"""
        params = {
            "mainArgs": "--class com.example.MySparkJob --master yarn --deploy-mode cluster"
        }
        result = self.scanner._extract_spark_main_class(params)
        assert result == "com.example.MySparkJob"

    def test_extract_spark_main_class_without_class(self):
        """Test extracting from mainArgs without --class"""
        params = {
            "mainArgs": "--master yarn --deploy-mode cluster"
        }
        result = self.scanner._extract_spark_main_class(params)
        assert result is None

    def test_extract_spark_main_class_empty_params(self):
        """Test extracting from empty params"""
        params = {}
        result = self.scanner._extract_spark_main_class(params)
        assert result is None

    def test_extract_spark_main_class_empty_mainargs(self):
        """Test extracting from empty mainArgs"""
        params = {"mainArgs": ""}
        result = self.scanner._extract_spark_main_class(params)
        assert result is None

    def test_extract_spark_main_class_quoted(self):
        """Test extracting class with quoted value"""
        params = {
            "mainArgs": "--class 'com.example.MyClass' --master yarn"
        }
        result = self.scanner._extract_spark_main_class(params)
        assert result == "'com.example.MyClass'" or result == "com.example.MyClass"


class TestParseWorkflowDependencies(unittest.TestCase):
    """Test _parse_workflow_dependencies method"""

    def setUp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.storage = GraphStorage(data_dir=tmpdir)
            self.scanner = GraphScanner(self.storage, tmpdir)
            self.graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2024-01-01T00:00:00",
                version=1,
                nodes=GraphNodes(),
                edges=GraphEdges(),
            )

    def test_parse_workflow_dependencies_with_dependent_task(self):
        """Test parsing workflow with DEPENDENT task"""
        workflow_data = {
            "tasks": [
                {
                    "taskType": "DEPENDENT",
                    "taskParams": {
                        "dependence": {
                            "projectCode": 456,
                            "processDefinitionCode": 2001
                        }
                    }
                }
            ]
        }

        self.scanner._parse_workflow_dependencies(
            workflow_data,
            "1001",
            self.graph
        )

        assert len(self.graph.edges.workflow_depends_workflow) == 1
        edge = self.graph.edges.workflow_depends_workflow[0]
        assert edge["source"] == "1001"
        assert edge["target"] == "2001"

    def test_parse_workflow_dependencies_no_dependent(self):
        """Test parsing workflow without DEPENDENT task"""
        workflow_data = {
            "tasks": [
                {
                    "taskType": "SPARK",
                    "taskParams": {"mainArgs": "--class com.example.Test"}
                }
            ]
        }

        self.scanner._parse_workflow_dependencies(
            workflow_data,
            "1001",
            self.graph
        )

        assert len(self.graph.edges.workflow_depends_workflow) == 0


class TestParseTaskDependencies(unittest.TestCase):
    """Test _parse_task_dependencies method"""

    def setUp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.storage = GraphStorage(data_dir=tmpdir)
            self.scanner = GraphScanner(self.storage, tmpdir)
            self.graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2024-01-01T00:00:00",
                version=1,
                nodes=GraphNodes(),
                edges=GraphEdges(),
            )

    def test_parse_task_dependencies_with_relations(self):
        """Test parsing task dependencies"""
        relations = [
            {"preTaskCode": 0, "postTaskCode": 1001},  # Start task, no pre
            {"preTaskCode": 1001, "postTaskCode": 1002},
            {"preTaskCode": 1002, "postTaskCode": 1003},
        ]

        self.scanner._parse_task_dependencies(
            relations,
            "workflow_1",
            self.graph
        )

        # Should have 2 edges (skip preTaskCode=0)
        assert len(self.graph.edges.task_depends_task) == 2

        # Check edges
        edges = self.graph.edges.task_depends_task
        assert edges[0]["source"] == "1001"
        assert edges[0]["target"] == "1002"
        assert edges[1]["source"] == "1002"
        assert edges[1]["target"] == "1003"

    def test_parse_task_dependencies_empty(self):
        """Test parsing empty task dependencies"""
        relations = []

        self.scanner._parse_task_dependencies(
            relations,
            "workflow_1",
            self.graph
        )

        assert len(self.graph.edges.task_depends_task) == 0


class TestParseClassTables(unittest.TestCase):
    """Test _parse_class_tables method"""

    def test_parse_class_tables_found(self):
        """Test parsing class file when found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage, tmpdir)
            graph = Graph(
                project_code="123",
                project_name="test_project",
                scanned_at="2024-01-01T00:00:00",
                version=1,
                nodes=GraphNodes(),
                edges=GraphEdges(),
            )
            all_tables = set()

            # Create a test Scala file
            test_file = os.path.join(tmpdir, "MyClass.scala")
            with open(test_file, "w") as f:
                f.write("""
val sql1 = "INSERT INTO hive.db.output_table SELECT * FROM hive.db.input_table"
val sql2 = "INSERT OVERWRITE hive.db.output_table2 FROM hive.db.input_table2 JOIN hive.db.input_table3 ON id"
""")

            with patch.object(
                scanner.code_searcher, 'search_class',
                return_value={
                    "found": True,
                    "file_path": test_file,
                    "cross_project": False,
                    "source_project": "test_project"
                }
            ):
                scanner._parse_class_tables(
                    "com.example.MyClass",
                    "task_1001",
                    graph,
                    "test_project",
                    all_tables
                )

                # Check tables
                assert len(all_tables) > 0

                # Check ClassNode
                assert len(graph.nodes.classes) == 1
                class_node = graph.nodes.classes[0]
                assert class_node.name == "com.example.MyClass"
                assert class_node.file_path == test_file
                assert len(class_node.tables_input) > 0
                assert len(class_node.tables_output) > 0

                # Check edges
                assert len(graph.edges.class_maps_to_task) == 1

    def test_parse_class_tables_not_found(self):
        """Test parsing when class file not found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage, tmpdir)
            graph = Graph(
                project_code="123",
                project_name="test_project",
                scanned_at="2024-01-01T00:00:00",
                version=1,
                nodes=GraphNodes(),
                edges=GraphEdges(),
            )
            all_tables = set()

            with patch.object(
                scanner.code_searcher, 'search_class',
                return_value={"found": False, "file_path": None}
            ):
                scanner._parse_class_tables(
                    "com.example.NotFound",
                    "task_1001",
                    graph,
                    "test_project",
                    all_tables
                )

                # No tables or classes added
                assert len(all_tables) == 0
                assert len(graph.nodes.classes) == 0


if __name__ == "__main__":
    unittest.main()