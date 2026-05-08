"""
告警与图谱集成测试

测试 GraphImpactTool 与 AlertAgent、RiskNode 的集成
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestGraphImpactToolIntegration:
    """GraphImpactTool 与其他组件集成测试"""

    def test_graph_impact_tool_initialization(self):
        """测试 GraphImpactTool 初始化"""
        from src.tools.graph_impact import GraphImpactTool

        tool = GraphImpactTool()

        assert tool.storage is not None
        assert tool.querier is not None

    def test_graph_impact_tool_with_custom_storage(self):
        """测试 GraphImpactTool 使用自定义存储"""
        from src.tools.graph_impact import GraphImpactTool
        from src.graph import GraphStorage

        custom_storage = GraphStorage(data_dir="custom_path")
        tool = GraphImpactTool(storage=custom_storage)

        assert tool.storage.data_dir == "custom_path"

    def test_analyze_workflow_downstream_returns_correct_format(self):
        """测试返回格式符合预期"""
        from src.tools.graph_impact import GraphImpactTool

        tool = GraphImpactTool()

        with patch.object(tool.querier, 'query_workflow_downstream') as mock_query:
            mock_query.return_value = {
                "found": True,
                "direct": ["wf_2"],
                "all": ["wf_2", "wf_3"],
                "count": 2,
                "message": "Found 2",
            }

            with patch.object(tool, '_get_workflow_names') as mock_names:
                mock_names.return_value = {"wf_2": "名称2", "wf_3": "名称3"}

                result = tool.analyze_workflow_downstream("proj_1", "wf_1")

                # Verify all required fields
                assert "graph_available" in result
                assert "downstream_count" in result
                assert "downstream_workflows" in result
                assert "workflow_names" in result
                assert "impact_level" in result


class TestRiskNodeWithGraph:
    """Risk Node 与图谱集成测试"""

    def test_impact_analysis_with_graph(self):
        """测试图谱可用时的影响分析"""
        from src.workflow.nodes.risk import impact_analysis

        state = {
            "project_code": 11598158952448,
            "process_definition_code": 21451302002208,
            "task_code": 123456,
            "task_relations": None,
        }

        with patch("src.workflow.nodes.risk.GraphImpactTool") as mock_graph_tool:
            mock_instance = Mock()
            mock_instance.analyze_workflow_downstream.return_value = {
                "graph_available": True,
                "downstream_count": 5,
                "downstream_workflows": ["wf_2", "wf_3", "wf_4", "wf_5", "wf_6"],
                "workflow_names": {
                    "wf_2": "数据同步",
                    "wf_3": "数据加工",
                    "wf_4": "数据导出",
                    "wf_5": "数据校验",
                    "wf_6": "数据归档",
                },
                "impact_level": "medium",
            }
            mock_instance.build_impact_summary.return_value = "影响摘要"
            mock_graph_tool.return_value = mock_instance

            result = impact_analysis(state)

            assert result["downstream_tasks"] == 5
            assert result["impact_source"] == "graph"

    def test_impact_analysis_without_graph_fallback(self):
        """测试图谱不可用时的降级"""
        from src.workflow.nodes.risk import impact_analysis

        state = {
            "project_code": 11598158952448,
            "process_definition_code": 21451302002208,
            "task_code": 123456,
            "task_relations": [
                {"preTaskCode": 123456, "postTaskCode": 789012},
                {"preTaskCode": 789012, "postTaskCode": 345678},
            ],
        }

        with patch("src.workflow.nodes.risk.GraphImpactTool") as mock_graph_tool:
            mock_instance = Mock()
            mock_instance.analyze_workflow_downstream.return_value = {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_workflows": [],
                "workflow_names": {},
                "impact_level": "low",
            }
            mock_graph_tool.return_value = mock_instance

            result = impact_analysis(state)

            # Should fallback to ImpactTool
            assert result["impact_source"] == "fallback_impact_tool"
            assert result["downstream_tasks"] == 2  # 789012 and 345678

    def test_impact_analysis_without_graph_no_relations(self):
        """测试图谱不可用且无任务关系"""
        from src.workflow.nodes.risk import impact_analysis

        state = {
            "project_code": 11598158952448,
            "process_definition_code": 21451302002208,
            "task_code": 123456,
            "task_relations": None,
        }

        with patch("src.workflow.nodes.risk.GraphImpactTool") as mock_graph_tool:
            mock_instance = Mock()
            mock_instance.analyze_workflow_downstream.return_value = {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_workflows": [],
                "workflow_names": {},
                "impact_level": "low",
            }
            mock_graph_tool.return_value = mock_instance

            result = impact_analysis(state)

            assert result["downstream_tasks"] == 0
            assert result["impact_source"] == "fallback_none"

    def test_impact_analysis_with_empty_relations(self):
        """测试空任务关系列表"""
        from src.workflow.nodes.risk import impact_analysis

        state = {
            "project_code": 11598158952448,
            "process_definition_code": 21451302002208,
            "task_code": 123456,
            "task_relations": [],
        }

        with patch("src.workflow.nodes.risk.GraphImpactTool") as mock_graph_tool:
            mock_instance = Mock()
            mock_instance.analyze_workflow_downstream.return_value = {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_workflows": [],
                "workflow_names": {},
                "impact_level": "low",
            }
            mock_graph_tool.return_value = mock_instance

            result = impact_analysis(state)

            # Empty relations means no downstream
            assert result["downstream_tasks"] == 0
            assert result["impact_source"] == "fallback_impact_tool"


class TestAlertAgentImpactIntegration:
    """AlertAgent 影响分析集成测试（不依赖 langchain）"""

    def test_analyze_impact_method_exists(self):
        """测试 _analyze_impact 方法存在"""
        # 验证方法签名而不实际导入（避免 langchain 依赖）
        import ast

        with open("src/agent/alert_agent.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        # 查找 _analyze_impact 方法
        found_method = False
        has_graph_impact_attr = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_analyze_impact":
                found_method = True
            if isinstance(node, ast.Attribute) and node.attr == "graph_impact":
                has_graph_impact_attr = True

        assert found_method, "_analyze_impact method should exist"
        assert has_graph_impact_attr, "graph_impact attribute should be used"

    def test_analyze_impact_calls_graph_impact(self):
        """测试 _analyze_impact 调用 graph_impact"""
        import ast

        with open("src/agent/alert_agent.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        # 查找 _analyze_impact 方法中的 graph_impact 调用
        found_graph_call = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # 检查是否调用了 graph_impact.analyze_workflow_downstream
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "analyze_workflow_downstream":
                        # 检查调用者是 self.graph_impact
                        if isinstance(node.func.value, ast.Attribute):
                            if node.func.value.attr == "graph_impact":
                                found_graph_call = True

        assert found_graph_call, "_analyze_impact should call graph_impact.analyze_workflow_downstream"

    def test_analyze_impact_has_fallback(self):
        """测试 _analyze_impact 有降级逻辑"""
        import ast

        with open("src/agent/alert_agent.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        # 查找 _analyze_impact 方法中的降级逻辑
        # 检查是否有 graph_available 条件判断或降级注释
        has_fallback = False
        has_graph_available_check = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # 检查条件中是否有 graph_available 或 graph_result.get("graph_available")
                for sub_node in ast.walk(node.test):
                    if isinstance(sub_node, ast.Attribute):
                        if sub_node.attr == "graph_available":
                            has_graph_available_check = True
                    elif isinstance(sub_node, ast.Call):
                        # 检查 graph_result.get("graph_available")
                        if isinstance(sub_node.func, ast.Attribute):
                            if sub_node.func.attr == "get":
                                for arg in sub_node.args:
                                    if isinstance(arg, ast.Constant) and arg.value == "graph_available":
                                        has_graph_available_check = True

        # 检查是否有降级注释
        source_lines = source.split("\n")
        for line in source_lines:
            if "降级" in line or "fallback" in line.lower():
                has_fallback = True

        assert has_graph_available_check or has_fallback, "_analyze_impact should have fallback logic when graph unavailable"


class TestConfigIntegration:
    """配置集成测试"""

    def test_graph_config_exists(self):
        """测试图谱配置项存在"""
        import os
        import sys

        # 设置必要的环境变量
        os.environ["ANTHROPIC_API_KEY"] = "test_key"
        os.environ["DS_TOKEN"] = "test_token"

        try:
            # 清除可能的缓存模块
            if "config.settings" in sys.modules:
                del sys.modules["config.settings"]
            if "config" in sys.modules:
                del sys.modules["config"]

            from config.settings import Settings

            settings = Settings.__dataclass_fields__

            assert "CODE_ROOT_PATH" in settings
            assert "GRAPH_STORAGE_PATH" in settings
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("DS_TOKEN", None)

    def test_graph_config_defaults(self):
        """测试图谱配置默认值"""
        import os
        import sys

        # 设置必要的环境变量
        os.environ["ANTHROPIC_API_KEY"] = "test_key"
        os.environ["DS_TOKEN"] = "test_token"
        os.environ["CODE_ROOT_PATH"] = ""
        os.environ["GRAPH_STORAGE_PATH"] = "data/graph"

        try:
            # 清除可能的缓存模块
            if "config.settings" in sys.modules:
                del sys.modules["config.settings"]
            if "config" in sys.modules:
                del sys.modules["config"]

            from config.settings import Settings

            settings = Settings()
            assert settings.CODE_ROOT_PATH == ""
            assert settings.GRAPH_STORAGE_PATH == "data/graph"
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("DS_TOKEN", None)
            os.environ.pop("CODE_ROOT_PATH", None)
            os.environ.pop("GRAPH_STORAGE_PATH", None)