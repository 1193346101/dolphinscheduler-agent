"""
GraphIndexer 测试
"""

import pytest
import tempfile
from datetime import datetime

from src.graph.storage import GraphStorage
from src.graph.indexer import GraphIndexer
from src.graph.models import (
    Graph,
    GraphNodes,
    GraphEdges,
    WorkflowNode,
    TaskNode,
    TableNode,
    ClassNode,
)


class TestGraphIndexer:
    """GraphIndexer 测试类"""

    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)
            assert indexer.storage == storage

    def test_generate_downstream_index(self):
        """测试生成下游依赖索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

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
                            name="Workflow 1",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf2",
                            name="Workflow 2",
                            schedule_type="CRON",
                            schedule_cron="0 1 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf3",
                            name="Workflow 3",
                            schedule_type="CRON",
                            schedule_cron="0 2 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Task 1",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Task 2",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                        TaskNode(
                            code="task3",
                            name="Task 3",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                    ],
                    tables=[],
                    classes=[]
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
                        {"source": "wf1", "target": "task3"},
                    ],
                    task_depends_task=[
                        {"source": "task1", "target": "task2"},
                        {"source": "task2", "target": "task3"},
                    ],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            index_data = indexer.generate_downstream_index(graph)

            # 验证基本结构
            assert "generated_at" in index_data
            assert "workflow_downstream" in index_data
            assert "task_downstream" in index_data

            # 验证工作流下游索引
            wf_downstream = index_data["workflow_downstream"]
            assert "wf1" in wf_downstream
            assert "wf2" in wf_downstream
            assert "wf3" in wf_downstream

            # wf1 -> wf2 -> wf3, 所以 wf1 的所有下游是 [wf2, wf3]
            assert wf_downstream["wf1"]["direct"] == ["wf2"]
            assert set(wf_downstream["wf1"]["all"]) == {"wf2", "wf3"}
            assert wf_downstream["wf1"]["count"] == 2

            # wf2 -> wf3
            assert wf_downstream["wf2"]["direct"] == ["wf3"]
            assert wf_downstream["wf2"]["all"] == ["wf3"]
            assert wf_downstream["wf2"]["count"] == 1

            # wf3 没有下游
            assert wf_downstream["wf3"]["direct"] == []
            assert wf_downstream["wf3"]["all"] == []
            assert wf_downstream["wf3"]["count"] == 0

            # 验证任务下游索引
            task_downstream = index_data["task_downstream"]
            assert "task1" in task_downstream
            assert "task2" in task_downstream
            assert "task3" in task_downstream

            # task1 -> task2 -> task3
            assert task_downstream["task1"]["direct"] == ["task2"]
            assert set(task_downstream["task1"]["all"]) == {"task2", "task3"}
            assert task_downstream["task1"]["count"] == 2

    def test_generate_table_consumer_index(self):
        """测试生成表消费/生产索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

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
                            name="Workflow 1",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Task 1",
                            workflow_code="wf1",
                            task_type="SPARK",
                            spark_main_class="com.example.ProcessData",
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Task 2",
                            workflow_code="wf1",
                            task_type="SPARK",
                            spark_main_class="com.example.LoadData",
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
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[
                        {"source": "wf1", "target": "task1"},
                        {"source": "wf1", "target": "task2"},
                    ],
                    task_depends_task=[],
                    task_produces_table=[
                        {"source": "task1", "target": "hive.db.target_table"},
                    ],
                    task_consumes_table=[
                        {"source": "task1", "target": "hive.db.source_table"},
                        {"source": "task2", "target": "hive.db.target_table"},
                    ],
                    class_maps_to_task=[
                        {"source": "com.example.ProcessData", "target": "task1"},
                    ]
                )
            )

            index_data = indexer.generate_table_consumer_index(graph)

            # 验证基本结构
            assert "generated_at" in index_data
            assert "table_consumers" in index_data
            assert "table_producers" in index_data

            # 验证表消费索引
            consumers = index_data["table_consumers"]
            assert "hive.db.source_table" in consumers
            assert "task1" in consumers["hive.db.source_table"]["tasks"]
            assert "wf1" in consumers["hive.db.source_table"]["workflows"]
            assert "com.example.ProcessData" in consumers["hive.db.source_table"]["classes"]

            # hive.db.target_table 被 task2 消费
            assert "hive.db.target_table" in consumers
            assert "task2" in consumers["hive.db.target_table"]["tasks"]

            # 验证表生产索引
            producers = index_data["table_producers"]
            assert "hive.db.target_table" in producers
            assert "task1" in producers["hive.db.target_table"]["tasks"]
            assert "wf1" in producers["hive.db.target_table"]["workflows"]
            assert "com.example.ProcessData" in producers["hive.db.target_table"]["classes"]

    def test_generate_workflow_nodes_index(self):
        """测试生成工作流节点索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

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
                            name="Workflow 1",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Data Process Task",
                            workflow_code="wf1",
                            task_type="SPARK",
                            spark_main_class="com.example.ProcessData",
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Data Load Task",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                    ],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[
                        {"source": "wf1", "target": "task1"},
                        {"source": "wf1", "target": "task2"},
                    ],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            index_data = indexer.generate_workflow_nodes_index(graph)

            # 验证基本结构
            assert "generated_at" in index_data
            assert "workflow_tasks" in index_data

            # 验证工作流任务索引
            wf_tasks = index_data["workflow_tasks"]
            assert "wf1" in wf_tasks

            wf1_data = wf_tasks["wf1"]
            assert set(wf1_data["tasks"]) == {"task1", "task2"}
            assert wf1_data["task_names"]["task1"] == "Data Process Task"
            assert wf1_data["task_names"]["task2"] == "Data Load Task"
            assert wf1_data["task_types"]["task1"] == "SPARK"
            assert wf1_data["task_types"]["task2"] == "SHELL"
            assert wf1_data["spark_classes"]["task1"] == "com.example.ProcessData"
            assert "task2" not in wf1_data["spark_classes"]  # task2 没有 spark_main_class

    def test_generate_all_indexes(self):
        """测试生成所有索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 先创建一个图谱
            graph = Graph(
                project_code="test_proj",
                project_name="Test Project",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[
                        WorkflowNode(
                            code="wf1",
                            name="Workflow 1",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf2",
                            name="Workflow 2",
                            schedule_type="CRON",
                            schedule_cron="0 1 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Task 1",
                            workflow_code="wf1",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Task 2",
                            workflow_code="wf2",
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                    ],
                    tables=[
                        TableNode(full_name="hive.db.table1", table_type="HIVE"),
                    ],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[
                        {"source": "wf1", "target": "task1"},
                        {"source": "wf2", "target": "task2"},
                    ],
                    task_depends_task=[],
                    task_produces_table=[
                        {"source": "task1", "target": "hive.db.table1"},
                    ],
                    task_consumes_table=[
                        {"source": "task2", "target": "hive.db.table1"},
                    ],
                    class_maps_to_task=[]
                )
            )

            # 保存图谱
            storage.save_graph("test_proj", graph.to_dict())

            # 创建索引生成器并生成所有索引
            indexer = GraphIndexer(storage)
            indexes = indexer.generate_all_indexes("test_proj")

            # 验证返回的索引
            assert "downstream" in indexes
            assert "table_consumer" in indexes
            assert "workflow_nodes" in indexes

            # 验证索引已保存
            downstream_index = storage.load_index("test_proj", "downstream")
            assert downstream_index is not None
            assert "workflow_downstream" in downstream_index

            table_consumer_index = storage.load_index("test_proj", "table_consumer")
            assert table_consumer_index is not None
            assert "table_consumers" in table_consumer_index

            workflow_nodes_index = storage.load_index("test_proj", "workflow_nodes")
            assert workflow_nodes_index is not None
            assert "workflow_tasks" in workflow_nodes_index

    def test_generate_all_indexes_graph_not_found(self):
        """测试生成索引时图谱不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

            with pytest.raises(ValueError, match="Graph not found"):
                indexer.generate_all_indexes("nonexistent_project")

    def test_find_all_downstream(self):
        """测试 BFS 查找所有下游节点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

            # 创建一个复杂的 DAG
            # A -> B -> D
            # A -> C -> D
            # D -> E
            edges = [
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "B", "target": "D"},
                {"source": "C", "target": "D"},
                {"source": "D", "target": "E"},
            ]

            # A 的所有下游: B, C, D, E
            result_a = indexer._find_all_downstream("A", edges)
            assert set(result_a) == {"B", "C", "D", "E"}

            # D 的所有下游: E
            result_d = indexer._find_all_downstream("D", edges)
            assert result_d == ["E"]

            # E 没有下游
            result_e = indexer._find_all_downstream("E", edges)
            assert result_e == []

            # 孤立节点
            result_isolated = indexer._find_all_downstream("X", edges)
            assert result_isolated == []

    def test_find_all_downstream_with_cycle(self):
        """测试处理环路的下游查找(应避免无限循环)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

            # 创建一个带环路的图
            # A -> B -> C -> A (环)
            # B -> D
            edges = [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "A"},  # 环路
                {"source": "B", "target": "D"},
            ]

            # A 的所有下游: B, C, D (不包含 A 自己)
            result_a = indexer._find_all_downstream("A", edges)
            assert set(result_a) == {"B", "C", "D"}
            # 确保没有重复
            assert len(result_a) == len(set(result_a))

    def test_scanner_indexer_pipeline_integration(self):
        """Integration test: scanner output should work with indexer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage)

            # Simulate scanner output with source/target keys
            # This is what scanner produces after the fix
            graph = Graph(
                project_code="integration_test",
                project_name="Integration Test Project",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[
                        WorkflowNode(
                            code="wf_main",
                            name="Main Workflow",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf_dep",
                            name="Dependency Workflow",
                            schedule_type="CRON",
                            schedule_cron="0 1 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[
                        TaskNode(
                            code="task1",
                            name="Extract Task",
                            workflow_code="wf_main",
                            task_type="SPARK",
                            spark_main_class="com.example.ExtractData",
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Process Task",
                            workflow_code="wf_main",
                            task_type="SPARK",
                            spark_main_class="com.example.ProcessData",
                            params={}
                        ),
                        TaskNode(
                            code="task3",
                            name="Load Task",
                            workflow_code="wf_main",
                            task_type="SPARK",
                            spark_main_class="com.example.LoadData",
                            params={}
                        ),
                    ],
                    tables=[
                        TableNode(full_name="hive.db.source_table", table_type="HIVE"),
                        TableNode(full_name="hive.db.intermediate_table", table_type="HIVE"),
                        TableNode(full_name="hive.db.target_table", table_type="HIVE"),
                    ],
                    classes=[
                        ClassNode(
                            name="com.example.ExtractData",
                            file_path="/src/ExtractData.scala",
                            cross_project=False,
                            source_project=None,
                            tables_input=["hive.db.source_table"],
                            tables_output=["hive.db.intermediate_table"]
                        ),
                        ClassNode(
                            name="com.example.ProcessData",
                            file_path="/src/ProcessData.scala",
                            cross_project=False,
                            source_project=None,
                            tables_input=["hive.db.intermediate_table"],
                            tables_output=["hive.db.target_table"]
                        ),
                    ]
                ),
                edges=GraphEdges(
                    # Workflow dependencies with source/target
                    workflow_depends_workflow=[
                        {"source": "wf_main", "target": "wf_dep"},
                    ],
                    workflow_calls_subworkflow=[],
                    # Workflow contains task with source/target
                    workflow_contains_task=[
                        {"source": "wf_main", "target": "task1"},
                        {"source": "wf_main", "target": "task2"},
                        {"source": "wf_main", "target": "task3"},
                    ],
                    # Task dependencies with source/target
                    task_depends_task=[
                        {"source": "task1", "target": "task2"},
                        {"source": "task2", "target": "task3"},
                    ],
                    # Task-table relationships with source/target
                    task_produces_table=[
                        {"source": "task1", "target": "hive.db.intermediate_table"},
                        {"source": "task2", "target": "hive.db.target_table"},
                    ],
                    task_consumes_table=[
                        {"source": "task1", "target": "hive.db.source_table"},
                        {"source": "task2", "target": "hive.db.intermediate_table"},
                        {"source": "task3", "target": "hive.db.target_table"},
                    ],
                    # Class-task mapping with source/target
                    class_maps_to_task=[
                        {"source": "com.example.ExtractData", "target": "task1"},
                        {"source": "com.example.ProcessData", "target": "task2"},
                    ]
                )
            )

            # Save graph
            storage.save_graph("integration_test", graph.to_dict())

            # Generate all indexes - this should NOT throw errors
            indexes = indexer.generate_all_indexes("integration_test")

            # Verify downstream index works correctly
            assert "workflow_downstream" in indexes["downstream"]
            wf_downstream = indexes["downstream"]["workflow_downstream"]
            assert wf_downstream["wf_main"]["direct"] == ["wf_dep"]

            assert "task_downstream" in indexes["downstream"]
            task_downstream = indexes["downstream"]["task_downstream"]
            assert task_downstream["task1"]["direct"] == ["task2"]
            assert set(task_downstream["task1"]["all"]) == {"task2", "task3"}

            # Verify table consumer index works correctly
            assert "table_consumers" in indexes["table_consumer"]
            consumers = indexes["table_consumer"]["table_consumers"]
            assert "hive.db.source_table" in consumers
            assert "task1" in consumers["hive.db.source_table"]["tasks"]
            assert "wf_main" in consumers["hive.db.source_table"]["workflows"]
            assert "com.example.ExtractData" in consumers["hive.db.source_table"]["classes"]

            # Verify workflow nodes index works correctly
            assert "workflow_tasks" in indexes["workflow_nodes"]
            wf_tasks = indexes["workflow_nodes"]["workflow_tasks"]
            assert set(wf_tasks["wf_main"]["tasks"]) == {"task1", "task2", "task3"}
            assert wf_tasks["wf_main"]["task_types"]["task1"] == "SPARK"