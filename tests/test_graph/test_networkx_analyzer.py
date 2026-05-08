"""
NetworkXAnalyzer 测试
"""

import pytest
import tempfile
import os
import networkx as nx

from src.graph.storage import GraphStorage
from src.graph.networkx_analyzer import NetworkXAnalyzer
from src.graph.models import (
    Graph, GraphNodes, GraphEdges,
    WorkflowNode, TaskNode, TableNode, ClassNode
)


class TestNetworkXAnalyzer:

    def test_init(self):
        """测试初始化"""
        # 无存储初始化
        analyzer = NetworkXAnalyzer()
        assert analyzer.storage is None

        # 带存储初始化
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            analyzer = NetworkXAnalyzer(storage=storage)
            assert analyzer.storage == storage

    def test_build_workflow_graph(self):
        """测试构建工作流图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建测试图谱数据
            graph = Graph(
                project_code="test_project",
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
                            schedule_type="MANUAL",
                            schedule_cron="",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)
            g = analyzer.build_workflow_graph("test_project")

            assert isinstance(g, nx.DiGraph)
            assert len(g.nodes) == 3
            assert len(g.edges) == 2
            assert g.has_edge("wf1", "wf2")
            assert g.has_edge("wf2", "wf3")

    def test_build_workflow_graph_with_from_to_keys(self):
        """测试构建工作流图 - 使用 from/to 键格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
                project_name="Test Project",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[
                        WorkflowNode(
                            code="wf_a",
                            name="Workflow A",
                            schedule_type="CRON",
                            schedule_cron="0 0 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf_b",
                            name="Workflow B",
                            schedule_type="CRON",
                            schedule_cron="0 1 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"from": "wf_a", "to": "wf_b"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)
            g = analyzer.build_workflow_graph("test_project")

            assert isinstance(g, nx.DiGraph)
            assert len(g.nodes) == 2
            assert len(g.edges) == 1
            assert g.has_edge("wf_a", "wf_b")

    def test_build_task_graph(self):
        """测试构建任务图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
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
                            task_type="SHELL",
                            spark_main_class=None,
                            params={}
                        ),
                        TaskNode(
                            code="task2",
                            name="Task 2",
                            workflow_code="wf1",
                            task_type="SPARK",
                            spark_main_class="com.example.Main",
                            params={}
                        ),
                        TaskNode(
                            code="task3",
                            name="Task 3",
                            workflow_code="wf1",
                            task_type="PYTHON",
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
                    workflow_contains_task=[],
                    task_depends_task=[
                        {"source": "task1", "target": "task2"},
                        {"source": "task2", "target": "task3"},
                    ],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)
            g = analyzer.build_task_graph("test_project", "wf1")

            assert isinstance(g, nx.DiGraph)
            assert len(g.nodes) == 3
            assert len(g.edges) == 2
            assert g.has_edge("task1", "task2")
            assert g.has_edge("task2", "task3")

    def test_find_shortest_path(self):
        """测试查找最短路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
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
                            schedule_type="MANUAL",
                            schedule_cron="",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            # 查找路径
            path = analyzer.find_shortest_path("test_project", "wf1", "wf3")
            assert path == ["wf1", "wf2", "wf3"]

            # 无路径的情况
            path = analyzer.find_shortest_path("test_project", "wf3", "wf1")
            assert path == []

            # 节点不存在的情况
            path = analyzer.find_shortest_path("test_project", "nonexistent", "wf3")
            assert path == []

    def test_find_all_paths(self):
        """测试查找所有路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建一个有两条路径的图: wf1 -> wf2 -> wf4 和 wf1 -> wf3 -> wf4
            graph = Graph(
                project_code="test_project",
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
                            schedule_type="MANUAL",
                            schedule_cron="",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                        WorkflowNode(
                            code="wf4",
                            name="Workflow 4",
                            schedule_type="CRON",
                            schedule_cron="0 2 * * *",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf1", "target": "wf3"},
                        {"source": "wf2", "target": "wf4"},
                        {"source": "wf3", "target": "wf4"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            # 查找所有路径
            paths = analyzer.find_all_paths("test_project", "wf1", "wf4")
            assert len(paths) == 2
            assert ["wf1", "wf2", "wf4"] in paths
            assert ["wf1", "wf3", "wf4"] in paths

            # 无路径的情况
            paths = analyzer.find_all_paths("test_project", "wf4", "wf1")
            assert paths == []

    def test_find_cycles(self):
        """测试查找环"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建一个有环的图: wf1 -> wf2 -> wf3 -> wf1
            graph = Graph(
                project_code="test_project",
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
                            schedule_type="MANUAL",
                            schedule_cron="",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                        {"source": "wf3", "target": "wf1"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            cycles = analyzer.find_cycles("test_project")
            assert len(cycles) == 1
            # 环可能以不同顺序返回，检查是否包含相同的节点
            assert set(cycles[0]) == {"wf1", "wf2", "wf3"}

    def test_find_cycles_no_cycle(self):
        """测试查找环 - 无环的情况"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
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
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            cycles = analyzer.find_cycles("test_project")
            assert cycles == []

    def test_calculate_degree(self):
        """测试计算入度和出度"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建图: wf1 -> wf2 -> wf3
            # wf2 有入度 1，出度 1
            graph = Graph(
                project_code="test_project",
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
                            schedule_type="MANUAL",
                            schedule_cron="",
                            is_sub_workflow=False,
                            parent_workflow=None
                        ),
                    ],
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[
                        {"source": "wf1", "target": "wf2"},
                        {"source": "wf2", "target": "wf3"},
                    ],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[],
                    task_depends_task=[],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            # wf1: out_degree=1, in_degree=0
            degree = analyzer.calculate_degree("test_project", "wf1")
            assert degree == {"in_degree": 0, "out_degree": 1}

            # wf2: out_degree=1, in_degree=1
            degree = analyzer.calculate_degree("test_project", "wf2")
            assert degree == {"in_degree": 1, "out_degree": 1}

            # wf3: out_degree=0, in_degree=1
            degree = analyzer.calculate_degree("test_project", "wf3")
            assert degree == {"in_degree": 1, "out_degree": 0}

            # 不存在的节点
            degree = analyzer.calculate_degree("test_project", "nonexistent")
            assert degree == {"in_degree": 0, "out_degree": 0}

    def test_build_workflow_graph_empty_storage(self):
        """测试构建工作流图 - 空存储"""
        analyzer = NetworkXAnalyzer()
        g = analyzer.build_workflow_graph("test_project")

        assert isinstance(g, nx.DiGraph)
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_build_workflow_graph_not_found(self):
        """测试构建工作流图 - 图谱不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            analyzer = NetworkXAnalyzer(storage=storage)

            g = analyzer.build_workflow_graph("nonexistent_project")

            assert isinstance(g, nx.DiGraph)
            assert len(g.nodes) == 0
            assert len(g.edges) == 0

    def test_cache_workflow_graph(self):
        """测试工作流图缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
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
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges()
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            # 第一次构建
            g1 = analyzer.build_workflow_graph("test_project")
            # 第二次应该从缓存获取
            g2 = analyzer.build_workflow_graph("test_project")

            assert g1 is g2  # 应该是同一个对象

    def test_clear_cache(self):
        """测试清除缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            graph = Graph(
                project_code="test_project",
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
                    tasks=[],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges()
            )

            storage.save_graph("test_project", graph.to_dict())

            analyzer = NetworkXAnalyzer(storage=storage)

            # 构建并缓存
            g1 = analyzer.build_workflow_graph("test_project")
            assert len(analyzer._workflow_graph_cache) == 1

            # 清除缓存
            analyzer.clear_cache()
            assert len(analyzer._workflow_graph_cache) == 0
            assert len(analyzer._task_graph_cache) == 0