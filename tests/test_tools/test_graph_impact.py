"""
GraphImpactTool 测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.tools.graph_impact import GraphImpactTool


class TestGraphImpactTool:
    """GraphImpactTool 测试类"""

    def test_analyze_workflow_downstream_graph_unavailable(self):
        """测试图谱不可用时的下游分析"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_downstream') as mock_query:
            mock_query.return_value = {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": "Graph not found"
            }

            result = tool.analyze_workflow_downstream("project_1", "workflow_1")

            assert result["graph_available"] is False
            assert result["downstream_count"] == 0
            assert result["downstream_workflows"] == []
            assert result["impact_level"] == "low"

    def test_analyze_workflow_downstream_no_downstream(self):
        """测试无下游工作流"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_downstream') as mock_query:
            mock_query.return_value = {
                "found": True,
                "direct": [],
                "all": [],
                "count": 0,
                "message": "No downstream"
            }

            with patch.object(tool, '_get_workflow_names') as mock_names:
                mock_names.return_value = {}

                result = tool.analyze_workflow_downstream("project_1", "workflow_1")

                assert result["graph_available"] is True
                assert result["downstream_count"] == 0
                assert result["impact_level"] == "low"

    def test_analyze_workflow_downstream_medium_impact(self):
        """测试中等影响（1-5 个下游）"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_downstream') as mock_query:
            mock_query.return_value = {
                "found": True,
                "direct": ["wf_2"],
                "all": ["wf_2", "wf_3", "wf_4"],
                "count": 3,
                "message": "Found 3 downstream"
            }

            with patch.object(tool, '_get_workflow_names') as mock_names:
                mock_names.return_value = {
                    "wf_2": "工作流2",
                    "wf_3": "工作流3",
                    "wf_4": "工作流4",
                }

                result = tool.analyze_workflow_downstream("project_1", "workflow_1")

                assert result["graph_available"] is True
                assert result["downstream_count"] == 3
                assert len(result["downstream_workflows"]) == 3
                assert result["impact_level"] == "medium"

    def test_analyze_workflow_downstream_high_impact(self):
        """测试高影响（>5 个下游）"""
        tool = GraphImpactTool()

        downstream = [f"wf_{i}" for i in range(10)]

        with patch.object(tool.querier, 'query_workflow_downstream') as mock_query:
            mock_query.return_value = {
                "found": True,
                "direct": downstream[:3],
                "all": downstream,
                "count": 10,
                "message": "Found 10 downstream"
            }

            with patch.object(tool, '_get_workflow_names') as mock_names:
                mock_names.return_value = {f"wf_{i}": f"工作流{i}" for i in range(10)}

                result = tool.analyze_workflow_downstream("project_1", "workflow_1")

                assert result["graph_available"] is True
                assert result["downstream_count"] == 10
                assert result["impact_level"] == "high"

    def test_analyze_task_downstream_graph_unavailable(self):
        """测试图谱不可用时的任务下游分析"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_nodes') as mock_query:
            mock_query.return_value = {
                "found": False,
                "tasks": [],
                "message": "Graph not found"
            }

            result = tool.analyze_task_downstream("project_1", "workflow_1", "task_1")

            assert result["graph_available"] is False
            assert result["downstream_count"] == 0
            assert result["downstream_tasks"] == []

    def test_analyze_task_downstream_task_not_found(self):
        """测试任务不在工作流中"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_nodes') as mock_query:
            mock_query.return_value = {
                "found": True,
                "tasks": ["task_2", "task_3"],
                "message": "Found 2 tasks"
            }

            result = tool.analyze_task_downstream("project_1", "workflow_1", "task_1")

            assert result["graph_available"] is True
            assert result["downstream_count"] == 0
            assert result["downstream_tasks"] == []

    def test_analyze_workflow_nodes_graph_unavailable(self):
        """测试图谱不可用时的节点分析"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_nodes') as mock_query:
            mock_query.return_value = {
                "found": False,
                "tasks": [],
                "message": "Graph not found"
            }

            result = tool.analyze_workflow_nodes("project_1", "workflow_1")

            assert result["graph_available"] is False
            assert result["task_count"] == 0
            assert result["tasks"] == []

    def test_analyze_workflow_nodes_success(self):
        """测试成功获取工作流节点"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_nodes') as mock_query:
            mock_query.return_value = {
                "found": True,
                "tasks": ["task_1", "task_2", "task_3"],
                "task_names": {
                    "task_1": "数据抽取",
                    "task_2": "数据转换",
                    "task_3": "数据加载",
                },
                "task_types": {
                    "task_1": "SPARK",
                    "task_2": "SQL",
                    "task_3": "PYTHON",
                },
                "spark_classes": {
                    "task_1": "com.example.SparkJob",
                },
                "message": "Found 3 tasks"
            }

            result = tool.analyze_workflow_nodes("project_1", "workflow_1")

            assert result["graph_available"] is True
            assert result["task_count"] == 3
            assert len(result["tasks"]) == 3
            assert result["task_names"]["task_1"] == "数据抽取"
            assert result["task_types"]["task_1"] == "SPARK"
            assert result["spark_classes"]["task_1"] == "com.example.SparkJob"

    def test_build_impact_summary_no_downstream(self):
        """测试无下游时的影响摘要"""
        tool = GraphImpactTool()

        summary = tool.build_impact_summary(
            workflow_code="workflow_1",
            downstream_workflows=[],
            downstream_tasks=[],
            workflow_names={},
        )

        assert "workflow_1" in summary
        assert "无下游依赖" in summary

    def test_build_impact_summary_with_downstream(self):
        """测试有下游时的影响摘要"""
        tool = GraphImpactTool()

        summary = tool.build_impact_summary(
            workflow_code="workflow_1",
            downstream_workflows=["wf_2", "wf_3"],
            downstream_tasks=["task_1", "task_2"],
            workflow_names={
                "wf_2": "数据同步",
                "wf_3": "数据加工",
            },
        )

        assert "下游工作流" in summary
        assert "数据同步" in summary
        assert "数据加工" in summary
        assert "下游任务" in summary

    def test_build_impact_summary_truncate_long_list(self):
        """测试截断长列表"""
        tool = GraphImpactTool()

        downstream = [f"wf_{i}" for i in range(15)]
        names = {f"wf_{i}": f"工作流{i}" for i in range(15)}

        summary = tool.build_impact_summary(
            workflow_code="workflow_1",
            downstream_workflows=downstream,
            downstream_tasks=[],
            workflow_names=names,
        )

        assert "以及另外 5 个工作流" in summary

    def test_calculate_impact_level_low(self):
        """测试低影响级别计算"""
        tool = GraphImpactTool()

        assert tool._calculate_impact_level(0) == "low"

    def test_calculate_impact_level_medium(self):
        """测试中等影响级别计算"""
        tool = GraphImpactTool()

        assert tool._calculate_impact_level(1) == "medium"
        assert tool._calculate_impact_level(3) == "medium"
        assert tool._calculate_impact_level(5) == "medium"

    def test_calculate_impact_level_high(self):
        """测试高影响级别计算"""
        tool = GraphImpactTool()

        assert tool._calculate_impact_level(6) == "high"
        assert tool._calculate_impact_level(10) == "high"
        assert tool._calculate_impact_level(100) == "high"

    def test_get_workflow_names(self):
        """测试获取工作流名称"""
        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_info') as mock_info:
            mock_info.side_effect = [
                {"found": True, "name": "工作流A"},
                {"found": True, "name": "工作流B"},
                {"found": False, "name": None},
            ]

            names = tool._get_workflow_names("project_1", ["wf_1", "wf_2", "wf_3"])

            assert names["wf_1"] == "工作流A"
            assert names["wf_2"] == "工作流B"
            assert names["wf_3"] == "wf_3"  # 未找到时返回 code

    def test_find_task_downstream_direct(self):
        """测试直接下游任务"""
        tool = GraphImpactTool()

        task_depends = [
            {"source": "task_1", "target": "task_2"},
            {"source": "task_2", "target": "task_3"},
        ]
        workflow_tasks = {"task_1", "task_2", "task_3"}

        downstream = tool._find_task_downstream("task_1", task_depends, workflow_tasks)

        assert "task_2" in downstream
        assert "task_3" in downstream

    def test_find_task_downstream_multiple_paths(self):
        """测试多路径下游"""
        tool = GraphImpactTool()

        task_depends = [
            {"source": "task_1", "target": "task_2"},
            {"source": "task_1", "target": "task_3"},
            {"source": "task_2", "target": "task_4"},
            {"source": "task_3", "target": "task_4"},
        ]
        workflow_tasks = {"task_1", "task_2", "task_3", "task_4"}

        downstream = tool._find_task_downstream("task_1", task_depends, workflow_tasks)

        assert len(downstream) == 3
        assert "task_2" in downstream
        assert "task_3" in downstream
        assert "task_4" in downstream

    def test_find_task_downstream_no_downstream(self):
        """测试无下游任务"""
        tool = GraphImpactTool()

        task_depends = [
            {"source": "task_1", "target": "task_2"},
        ]
        workflow_tasks = {"task_1", "task_2", "task_3"}

        downstream = tool._find_task_downstream("task_3", task_depends, workflow_tasks)

        assert downstream == []

    def test_find_task_downstream_filter_out_of_workflow(self):
        """测试过滤工作流外的任务"""
        tool = GraphImpactTool()

        task_depends = [
            {"source": "task_1", "target": "task_2"},
            {"source": "task_2", "target": "task_external"},  # 工作流外
        ]
        workflow_tasks = {"task_1", "task_2"}

        downstream = tool._find_task_downstream("task_1", task_depends, workflow_tasks)

        assert "task_2" in downstream
        assert "task_external" not in downstream

    def test_analyze_task_downstream_with_real_downstream(self):
        """测试有真实下游的任务分析"""
        import tempfile
        from src.graph.storage import GraphStorage
        from src.graph.models import Graph, GraphNodes, GraphEdges, TaskNode, WorkflowNode
        from src.graph.indexer import GraphIndexer

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)

            # 创建测试图谱
            graph = Graph(
                project_code="test_proj",
                project_name="Test",
                scanned_at="2026-05-08T10:00:00",
                version=1,
                nodes=GraphNodes(
                    workflows=[WorkflowNode(code="wf_1", name="WF1", schedule_type="CRON", schedule_cron="0 0 * * *", is_sub_workflow=False, parent_workflow=None)],
                    tasks=[
                        TaskNode(code="task_1", name="Task 1", workflow_code="wf_1", task_type="SPARK", spark_main_class=None, params={}),
                        TaskNode(code="task_2", name="Task 2", workflow_code="wf_1", task_type="SPARK", spark_main_class=None, params={}),
                        TaskNode(code="task_3", name="Task 3", workflow_code="wf_1", task_type="SPARK", spark_main_class=None, params={}),
                    ],
                    tables=[],
                    classes=[]
                ),
                edges=GraphEdges(
                    workflow_depends_workflow=[],
                    workflow_calls_subworkflow=[],
                    workflow_contains_task=[
                        {"source": "wf_1", "target": "task_1"},
                        {"source": "wf_1", "target": "task_2"},
                        {"source": "wf_1", "target": "task_3"},
                    ],
                    task_depends_task=[
                        {"source": "task_1", "target": "task_2"},
                        {"source": "task_2", "target": "task_3"},
                    ],
                    task_produces_table=[],
                    task_consumes_table=[],
                    class_maps_to_task=[]
                )
            )

            storage.save_graph("test_proj", graph.to_dict())
            indexer = GraphIndexer(storage)
            indexer.generate_all_indexes("test_proj")

            tool = GraphImpactTool(storage)

            # 分析 task_1 的下游
            result = tool.analyze_task_downstream("test_proj", "wf_1", "task_1")

            assert result["graph_available"] is True
            assert result["downstream_count"] == 2
            assert "task_2" in result["downstream_tasks"]
            assert "task_3" in result["downstream_tasks"]
            assert result["task_names"]["task_1"] == "Task 1"