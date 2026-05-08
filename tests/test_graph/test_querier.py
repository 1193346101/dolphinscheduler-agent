"""
GraphQuerier 测试
"""

import pytest
import tempfile

from src.graph.storage import GraphStorage
from src.graph.indexer import GraphIndexer
from src.graph.querier import GraphQuerier
from src.graph.models import (
    Graph,
    GraphNodes,
    GraphEdges,
    WorkflowNode,
    TaskNode,
    TableNode,
    ClassNode,
)


class TestGraphQuerier:
    """GraphQuerier 测试类"""

    @pytest.fixture
    def setup_data(self):
        """设置测试数据"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建测试图谱
            graph = Graph(
                project_code="test_proj",
                project_name="Test Project",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[
                        WorkflowNode(
                            code="wf1",
                            name="Data Process Workflow",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf2",
                            name="Data Load Workflow",
                            schedule_type="CRON",
                            schedule_cron="0 1 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf3",
                            name="Data Export Workflow",
                            schedule_type="CRON",
                            schedule_cron="0 2 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Process Data Task",
                            workflow_code="wf1",
                            task_type="SPARK",
                            spark_main_class="com.example.ProcessData",
                            params={"param1": "value1"}
                        ),
                        TaskNode(
                            code="task2",
                            name="Load Data Task",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                        TaskNode(
                            code="task3",
                            name="Export Data Task",
                            workflow_code="wf2",
                            task_type="SPARK",
                            spark_main_class="com.example.ExportData",
                            params={}
                        ),
                    ],
                    tables=[
                        TableNode(full_name="hive.db.source_table", table_type="HIVE"),
                        TableNode(full_name="hive.db.target_table", table_type="HIVE"),
                    ],
                    classes=[
                        ClassNode(
                            name="com.example.ProcessData",
                            file_path="/src/main/scala/ProcessData.scala",
                            cross_project=False,
                            source_project=None,
                            tables_input=["hive.db.source_table"],
                            tables_output=["hive.db.target_table"]
                        ),
                    ]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[
                        {"source": "wf1", "target": "task1"},
                        {"source": "wf1", "target": "task2"},
                        {"source": "wf2", "target": "task3"},
                    ],
                    task_depends_task=[
                        {"source": "task1", "target": "task2"},
                    ],
                    task_produces_table=[
                        {"source": "task1", "target": "hive.db.target_table"},
                    ],
                    task_consumes_table=[
                        {"source": "task1", "target": "hive.db.source_table"},
                        {"source": "task3", "target": "hive.db.target_table"},
                    ],
                    class_maps_to_task=[
                        {"source": "com.example.ProcessData", "target": "task1"},
                    ]
                )
            )

            # 保存图谱
            storage.save_graph("test_proj", graph.to_dict())

            # 生成索引
            indexer = GraphIndexer(storage)
            indexer.generate_all_indexes("test_proj")

            yield storage

    def test_init(self, setup_data):
        """测试初始化"""
        storage = setup_data
        querier = GraphQuerier(storage)
        assert querier.storage == storage

    def test_query_workflow_downstream(self, setup_data):
        """测试查询工作流下游"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询 wf1 的下游
        result = querier.query_workflow_downstream("test_proj", "wf1")

        assert result["found"] is True
        assert "wf2" in result["direct"]
        assert set(result["all"]) == {"wf2", "wf3"}
        assert result["count"] == 2
        assert "Found" in result["message"]

    def test_query_workflow_downstream_not_found(self, setup_data):
        """测试查询不存在的工作流下游"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询不存在的工作流
        result = querier.query_workflow_downstream("test_proj", "nonexistent_wf")

        assert result["found"] is False
        assert result["direct"] == []
        assert result["all"] == []
        assert result["count"] == 0
        assert "not found" in result["message"]

    def test_query_workflow_upstream(self, setup_data):
        """测试查询工作流上游"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询 wf3 的上游 (wf1 -> wf2 -> wf3)
        result = querier.query_workflow_upstream("test_proj", "wf3")

        assert result["found"] is True
        assert set(result["upstream"]) == {"wf1", "wf2"}
        assert "Found" in result["message"]

    def test_query_workflow_upstream_no_upstream(self, setup_data):
        """测试查询无上游的工作流"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # wf1 没有上游
        result = querier.query_workflow_upstream("test_proj", "wf1")

        assert result["found"] is True
        assert result["upstream"] == []

    def test_query_table_consumers(self, setup_data):
        """测试查询表消费者"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询 hive.db.target_table 的消费者
        result = querier.query_table_consumers("test_proj", "hive.db.target_table")

        assert result["found"] is True
        assert "task3" in result["tasks"]
        assert "wf2" in result["workflows"]
        assert "Found" in result["message"]

    def test_query_table_consumers_not_found(self, setup_data):
        """测试查询不存在的表消费者"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_table_consumers("test_proj", "nonexistent_table")

        assert result["found"] is False
        assert result["tasks"] == []
        assert result["workflows"] == []
        assert result["classes"] == []

    def test_query_table_producers(self, setup_data):
        """测试查询表生产者"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询 hive.db.target_table 的生产者
        result = querier.query_table_producers("test_proj", "hive.db.target_table")

        assert result["found"] is True
        assert "task1" in result["tasks"]
        assert "wf1" in result["workflows"]
        assert "com.example.ProcessData" in result["classes"]
        assert "Found" in result["message"]

    def test_query_table_producers_not_found(self, setup_data):
        """测试查询不存在的表生产者"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_table_producers("test_proj", "nonexistent_table")

        assert result["found"] is False
        assert result["tasks"] == []
        assert result["workflows"] == []
        assert result["classes"] == []

    def test_query_workflow_nodes(self, setup_data):
        """测试查询工作流节点"""
        storage = setup_data
        querier = GraphQuerier(storage)

        # 查询 wf1 的节点
        result = querier.query_workflow_nodes("test_proj", "wf1")

        assert result["found"] is True
        assert set(result["tasks"]) == {"task1", "task2"}
        assert result["task_names"]["task1"] == "Process Data Task"
        assert result["task_names"]["task2"] == "Load Data Task"
        assert result["task_types"]["task1"] == "SPARK"
        assert result["task_types"]["task2"] == "SHELL"
        assert result["spark_classes"]["task1"] == "com.example.ProcessData"
        assert "Found" in result["message"]

    def test_query_workflow_nodes_not_found(self, setup_data):
        """测试查询不存在的工作流节点"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_workflow_nodes("test_proj", "nonexistent_wf")

        assert result["found"] is False
        assert result["tasks"] == []
        assert result["task_names"] == {}
        assert result["task_types"] == {}
        assert result["spark_classes"] == {}

    def test_query_no_graph(self):
        """测试图谱不存在时的查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            querier = GraphQuerier(storage)

            # 测试各种查询方法
            result = querier.query_workflow_downstream("nonexistent", "wf1")
            assert result["found"] is False
            assert "not found" in result["message"]

            result = querier.query_workflow_upstream("nonexistent", "wf1")
            assert result["found"] is False
            assert "not found" in result["message"]

            result = querier.query_table_consumers("nonexistent", "table1")
            assert result["found"] is False
            assert "not found" in result["message"]

            result = querier.query_table_producers("nonexistent", "table1")
            assert result["found"] is False
            assert "not found" in result["message"]

            result = querier.query_workflow_nodes("nonexistent", "wf1")
            assert result["found"] is False
            assert "not found" in result["message"]

    def test_query_no_index(self, setup_data):
        """测试索引不存在时的查询"""
        storage = setup_data

        # 创建一个新的存储,只有图谱没有索引
        with tempfile.TemporaryDirectory() as tmpdir:
            new_storage = GraphStorage(data_dir=tmpdir)

            # 复制图谱但不生成索引
            graph_data = storage.load_graph("test_proj")
            new_storage.save_graph("test_proj", graph_data)

            querier = GraphQuerier(new_storage)

            # 测试各种查询方法
            result = querier.query_workflow_downstream("test_proj", "wf1")
            assert result["found"] is False
            assert "index not found" in result["message"].lower()

            result = querier.query_table_consumers("test_proj", "table1")
            assert result["found"] is False
            assert "index not found" in result["message"].lower()

            result = querier.query_workflow_nodes("test_proj", "wf1")
            assert result["found"] is False
            assert "index not found" in result["message"].lower()

    def test_query_workflow_info(self, setup_data):
        """测试查询工作流详细信息"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_workflow_info("test_proj", "wf1")

        assert result["found"] is True
        assert result["code"] == "wf1"
        assert result["name"] == "Data Process Workflow"
        assert result["schedule_type"] == "CRON"
        assert result["schedule_cron"] == "0 0 * * *"
        assert result["is_sub_workflow"] is False
        assert result["parent_workflow"] is None
        assert "Found workflow" in result["message"]

    def test_query_workflow_info_not_found(self, setup_data):
        """测试查询不存在的工作流信息"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_workflow_info("test_proj", "nonexistent_wf")

        assert result["found"] is False
        assert "not found" in result["message"]

    def test_query_task_info(self, setup_data):
        """测试查询任务详细信息"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_task_info("test_proj", "task1")

        assert result["found"] is True
        assert result["code"] == "task1"
        assert result["name"] == "Process Data Task"
        assert result["workflow_code"] == "wf1"
        assert result["task_type"] == "SPARK"
        assert result["spark_main_class"] == "com.example.ProcessData"
        assert result["params"] == {"param1": "value1"}
        assert "Found task" in result["message"]

    def test_query_task_info_not_found(self, setup_data):
        """测试查询不存在的任务信息"""
        storage = setup_data
        querier = GraphQuerier(storage)

        result = querier.query_task_info("test_proj", "nonexistent_task")

        assert result["found"] is False
        assert "not found" in result["message"]

    def test_query_cross_project_table_lineage(self):
        """测试跨项目表血缘查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建项目 A 的图谱
            graph_a = Graph(
                project_code="project_a",
                project_name="Project A",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[WorkflowNode(code="wf_a1", name="Workflow A1", schedule_type="CRON", schedule_cron="0 0 * * *", is_sub_workflow=False, parent_workflow=None)],
                    tasks=[TaskNode(code="task_a1", name="Task A1", workflow_code="wf_a1", task_type="SPARK", spark_main_class="com.a.Process", params={})],
                    tables=[TableNode(full_name="hive.db.shared_table", table_type="HIVE")],
                    classes=[ClassNode(name="com.a.Process", file_path="/a/Process.scala", cross_project=False, source_project=None, tables_input=["hive.db.shared_table"], tables_output=["hive.db.output_a"])]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[{"source": "wf_a1", "target": "task_a1"}],
                    task_depends_task=[],
                    task_produces_table=[{"source": "task_a1", "target": "hive.db.output_a"}],
                    task_consumes_table=[{"source": "task_a1", "target": "hive.db.shared_table"}],
                    class_maps_to_task=[{"source": "com.a.Process", "target": "task_a1"}]
                )
            )
            storage.save_graph("project_a", graph_a.to_dict())
            indexer_a = GraphIndexer(storage)
            indexer_a.generate_all_indexes("project_a")

            # 创建项目 B 的图谱（消费 shared_table）
            graph_b = Graph(
                project_code="project_b",
                project_name="Project B",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[WorkflowNode(code="wf_b1", name="Workflow B1", schedule_type="CRON", schedule_cron="0 1 * * *", is_sub_workflow=False, parent_workflow=None)],
                    tasks=[TaskNode(code="task_b1", name="Task B1", workflow_code="wf_b1", task_type="SPARK", spark_main_class="com.b.Consume", params={})],
                    tables=[TableNode(full_name="hive.db.shared_table", table_type="HIVE")],
                    classes=[ClassNode(name="com.b.Consume", file_path="/b/Consume.scala", cross_project=True, source_project="project_a", tables_input=["hive.db.shared_table"], tables_output=["hive.db.output_b"])]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[{"source": "wf_b1", "target": "task_b1"}],
                    task_depends_task=[],
                    task_produces_table=[{"source": "task_b1", "target": "hive.db.output_b"}],
                    task_consumes_table=[{"source": "task_b1", "target": "hive.db.shared_table"}],
                    class_maps_to_task=[{"source": "com.b.Consume", "target": "task_b1"}]
                )
            )
            storage.save_graph("project_b", graph_b.to_dict())
            indexer_b = GraphIndexer(storage)
            indexer_b.generate_all_indexes("project_b")

            querier = GraphQuerier(storage)

            # 查询跨项目血缘
            result = querier.query_cross_project_table_lineage("hive.db.shared_table")

            assert result["found"] is True
            # 项目 A 消费 shared_table
            assert any(p["project_code"] == "project_a" for p in result["consumers"])
            # 项目 B 也消费 shared_table
            assert any(p["project_code"] == "project_b" for p in result["consumers"])
            # 跨项目引用
            assert len(result["cross_project_references"]) > 0

    def test_query_cross_project_workflow_downstream(self):
        """测试跨项目工作流下游查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建项目 A 的图谱（产出表）
            graph_a = Graph(
                project_code="project_a",
                project_name="Project A",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[WorkflowNode(code="wf_a1", name="Workflow A1", schedule_type="CRON", schedule_cron="0 0 * * *", is_sub_workflow=False, parent_workflow=None)],
                    tasks=[TaskNode(code="task_a1", name="Task A1", workflow_code="wf_a1", task_type="SPARK", spark_main_class="com.a.Producer", params={})],
                    tables=[TableNode(full_name="hive.db.output_table", table_type="HIVE")],
                    classes=[ClassNode(name="com.a.Producer", file_path="/a/Producer.scala", cross_project=False, source_project=None, tables_input=[], tables_output=["hive.db.output_table"])]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[{"source": "wf_a1", "target": "task_a1"}],
                    task_depends_task=[],
                    task_produces_table=[{"source": "task_a1", "target": "hive.db.output_table"}],
                    task_consumes_table=[],
                    class_maps_to_task=[{"source": "com.a.Producer", "target": "task_a1"}]
                )
            )
            storage.save_graph("project_a", graph_a.to_dict())
            indexer_a = GraphIndexer(storage)
            indexer_a.generate_all_indexes("project_a")

            # 创建项目 B 的图谱（消费项目 A 的表）
            graph_b = Graph(
                project_code="project_b",
                project_name="Project B",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[WorkflowNode(code="wf_b1", name="Workflow B1", schedule_type="CRON", schedule_cron="0 1 * * *", is_sub_workflow=False, parent_workflow=None)],
                    tasks=[TaskNode(code="task_b1", name="Task B1", workflow_code="wf_b1", task_type="SPARK", spark_main_class="com.b.Consumer", params={})],
                    tables=[TableNode(full_name="hive.db.output_table", table_type="HIVE")],
                    classes=[ClassNode(name="com.b.Consumer", file_path="/b/Consumer.scala", cross_project=True, source_project="project_a", tables_input=["hive.db.output_table"], tables_output=[])]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[{"source": "wf_b1", "target": "task_b1"}],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[{"source": "task_b1", "target": "hive.db.output_table"}],
                    class_maps_to_task=[{"source": "com.b.Consumer", "target": "task_b1"}]
                )
            )
            storage.save_graph("project_b", graph_b.to_dict())
            indexer_b = GraphIndexer(storage)
            indexer_b.generate_all_indexes("project_b")

            querier = GraphQuerier(storage)

            # 查询项目 A 工作流的跨项目下游
            result = querier.query_cross_project_workflow_downstream("project_a", "wf_a1")

            assert result["found"] is True
            # 本项目下游为空
            assert result["local_downstream"] == []
            # 跨项目下游包含项目 B 的工作流
            assert len(result["cross_project_downstream"]) > 0
            assert any(d["project_code"] == "project_b" for d in result["cross_project_downstream"])

    def test_list_all_projects(self):
        """测试列出所有项目"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建多个项目图谱
            for project_code in ["proj1", "proj2", "proj3"]:
                graph = Graph(
                    project_code=project_code,
                    project_name=f"Project {project_code}",
                    scanned_at="2026-05-08T10:00:00",
                    version=1,
                    nodes=GraphNodes(workflows=[], tasks=[], tables=[], classes=[]),
                    edges=GraphEdges(
                        workflow_depends_workflow=[],
                        workflow_calls_subworkflow=[],
                        workflow_contains_task=[],
                        task_depends_task=[],
                        task_produces_table=[],
                        task_consumes_table=[],
                        class_maps_to_task=[]
                    )
                )
                storage.save_graph(project_code, graph.to_dict())

            querier = GraphQuerier(storage)
            projects = querier._list_all_projects()

            assert len(projects) == 3
            assert "proj1" in projects
            assert "proj2" in projects
            assert "proj3" in projects