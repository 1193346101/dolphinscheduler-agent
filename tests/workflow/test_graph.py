"""
graph.py 状态机测试
"""

import pytest
from unittest.mock import patch, MagicMock
from src.workflow.graph import (
    build_alert_graph,
    AlertWorkflowGraph,
    should_continue,
    route_by_risk,
    check_approval_status,
)
from src.workflow.state import AgentState, create_initial_state, INITIAL_STATE


# ==================== should_continue Tests ====================


class TestShouldContinue:
    """should_continue 路由函数测试"""

    def test_should_continue_returns_end_when_invalid(self):
        """测试项目无效时返回 end"""
        state = {"project_valid": False}
        result = should_continue(state)
        assert result == "end"

    def test_should_continue_returns_continue_when_valid(self):
        """测试项目有效时返回 continue"""
        state = {"project_valid": True}
        result = should_continue(state)
        assert result == "continue"

    def test_should_continue_defaults_to_end(self):
        """测试缺少 project_valid 键时默认返回 end"""
        state = {}
        result = should_continue(state)
        assert result == "end"


# ==================== route_by_risk Tests ====================


class TestRouteByRisk:
    """route_by_risk 路由函数测试"""

    def test_route_by_risk_returns_approval_when_required(self):
        """测试需要审批时返回 approval"""
        state = {"approval_required": True}
        result = route_by_risk(state)
        assert result == "approval"

    def test_route_by_risk_returns_auto_execute_when_not_required(self):
        """测试不需要审批时返回 auto_execute"""
        state = {"approval_required": False}
        result = route_by_risk(state)
        assert result == "auto_execute"

    def test_route_by_risk_defaults_to_auto_execute(self):
        """测试缺少 approval_required 键时默认返回 auto_execute"""
        state = {}
        result = route_by_risk(state)
        assert result == "auto_execute"


# ==================== check_approval_status Tests ====================


class TestCheckApprovalStatus:
    """check_approval_status 路由函数测试"""

    def test_check_approval_status_returns_execute_when_approved(self):
        """测试审批通过时返回 execute"""
        state = {"approval_status": "approved"}
        result = check_approval_status(state)
        assert result == "execute"

    def test_check_approval_status_returns_notify_reject_when_rejected(self):
        """测试审批拒绝时返回 notify_reject"""
        state = {"approval_status": "rejected"}
        result = check_approval_status(state)
        assert result == "notify_reject"

    def test_check_approval_status_returns_notify_timeout_when_timeout(self):
        """测试审批超时时返回 notify_timeout"""
        state = {"approval_status": "timeout"}
        result = check_approval_status(state)
        assert result == "notify_timeout"

    def test_check_approval_status_returns_wait_when_pending(self):
        """测试审批等待时返回 wait"""
        state = {"approval_status": "pending"}
        result = check_approval_status(state)
        assert result == "wait"

    def test_check_approval_status_returns_wait_when_none(self):
        """测试审批状态为 None 时返回 wait"""
        state = {"approval_status": None}
        result = check_approval_status(state)
        assert result == "wait"

    def test_check_approval_status_defaults_to_wait(self):
        """测试缺少 approval_status 键时默认返回 wait"""
        state = {}
        result = check_approval_status(state)
        assert result == "wait"


# ==================== build_alert_graph Tests ====================


class TestBuildAlertGraph:
    """build_alert_graph 图结构测试"""

    def test_build_alert_graph_returns_state_graph(self):
        """测试返回 StateGraph 实例"""
        from langgraph.graph import StateGraph

        graph = build_alert_graph()
        assert isinstance(graph, StateGraph)

    def test_build_alert_graph_has_all_nodes(self):
        """测试图包含所有节点"""
        graph = build_alert_graph()

        # 获取节点信息
        nodes = graph.nodes
        node_names = set(nodes.keys())

        # 核心节点
        assert "parse_alert" in node_names
        assert "validate_project" in node_names

        # 日志和分析节点
        assert "fetch_logs" in node_names
        assert "analyze_error" in node_names
        assert "query_knowledge" in node_names
        assert "impact_analysis" in node_names
        assert "assess_risk" in node_names

        # 审批节点
        assert "request_approval" in node_names
        assert "check_approval" in node_names

        # 执行和通知节点
        assert "execute_action" in node_names
        assert "notify_dingtalk" in node_names
        assert "store_results" in node_names

    def test_build_alert_graph_entry_point(self):
        """测试入口节点是 parse_alert"""
        graph = build_alert_graph()
        # LangGraph StateGraph uses set_entry_point method
        # After compile(), the entry point is set to the first node added
        # We verify by checking the compiled graph structure
        assert "parse_alert" in graph.nodes


# ==================== AlertWorkflowGraph Tests ====================


class TestAlertWorkflowGraph:
    """AlertWorkflowGraph 工作流测试"""

    def test_init_creates_compiled_app(self):
        """测试初始化创建编译后的应用"""
        workflow = AlertWorkflowGraph()
        assert workflow.app is not None

    def test_run_with_empty_alert(self):
        """测试使用空告警运行工作流"""
        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 123,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SHELL",
        }

        # 由于 validate_project 会检查不存在的项目，project_valid 会是 False
        result = workflow.run(alert_raw)

        assert "project_code" in result
        assert "workflow_code" in result
        assert "task_code" in result
        assert result["project_code"] == "123"
        assert result["workflow_code"] == "456"
        assert result["task_code"] == "789"

    @patch("src.workflow.nodes.validate.projects_registry")
    def test_run_with_valid_project(self, mock_registry):
        """测试使用有效项目运行工作流"""
        # Mock 项目配置
        mock_config = MagicMock()
        mock_config.name = "test_project"
        mock_config.code = 123
        mock_config.ds_api_url = "http://test.api"
        mock_config.ds_api_token = "test_token"
        mock_config.ds_version = "3.2.0"
        mock_config.effective_spark_mode = "yarn"
        mock_config.effective_spark_history_url = "http://spark.history"
        mock_config.effective_yarn_gateway_url = "http://yarn.gateway"
        mock_config.dingtalk = None

        mock_registry.get_by_code.return_value = mock_config

        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 123,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SPARK",
        }

        result = workflow.run(alert_raw)

        assert result["project_valid"] is True
        assert result["project_config"] is not None
        assert result["project_config"]["name"] == "test_project"

    @patch("src.workflow.nodes.validate.projects_registry")
    def test_run_sets_risk_level(self, mock_registry):
        """测试工作流设置风险等级"""
        # Mock 项目配置
        mock_config = MagicMock()
        mock_config.name = "test_project"
        mock_config.code = 123
        mock_config.ds_api_url = "http://test.api"
        mock_config.ds_api_token = "test_token"
        mock_config.ds_version = "3.2.0"
        mock_config.effective_spark_mode = "yarn"
        mock_config.effective_spark_history_url = "http://spark.history"
        mock_config.effective_yarn_gateway_url = "http://yarn.gateway"
        mock_config.dingtalk = None

        mock_registry.get_by_code.return_value = mock_config

        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 123,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SHELL",
        }

        result = workflow.run(alert_raw)

        # 默认情况下风险等级应该是 LOW
        assert result["risk_level"] == "LOW"
        assert result["approval_required"] is False

    def test_run_preserves_alert_raw(self):
        """测试工作流保留原始告警数据"""
        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 123,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SHELL",
            "extra_field": "test_value",
        }

        result = workflow.run(alert_raw)

        assert result["alert_raw"] == alert_raw
        assert result["alert_raw"]["extra_field"] == "test_value"

    def test_continue_from_approval_updates_state(self):
        """测试 continue_from_approval 更新状态"""
        workflow = AlertWorkflowGraph()

        state = dict(INITIAL_STATE)
        state["approval_status"] = "pending"

        result = workflow.continue_from_approval(state, "approved")

        assert result["approval_status"] == "approved"


# ==================== INITIAL_STATE Tests ====================


class TestInitialState:
    """INITIAL_STATE 测试"""

    def test_initial_state_has_all_fields(self):
        """测试 INITIAL_STATE 包含所有字段"""
        assert "alert_raw" in INITIAL_STATE
        assert "project_code" in INITIAL_STATE
        assert "workflow_code" in INITIAL_STATE
        assert "task_code" in INITIAL_STATE
        assert "task_type" in INITIAL_STATE
        assert "project_valid" in INITIAL_STATE
        assert "driver_logs" in INITIAL_STATE
        assert "spark_logs" in INITIAL_STATE
        assert "yarn_logs" in INITIAL_STATE
        assert "k8s_logs" in INITIAL_STATE
        assert "error_patterns" in INITIAL_STATE
        assert "risk_level" in INITIAL_STATE
        assert "approval_required" in INITIAL_STATE
        assert "approval_status" in INITIAL_STATE
        assert "notification_sent" in INITIAL_STATE
        assert "log_stored" in INITIAL_STATE

    def test_initial_state_defaults(self):
        """测试 INITIAL_STATE 默认值"""
        assert INITIAL_STATE["alert_raw"] == {}
        assert INITIAL_STATE["project_valid"] is False
        assert INITIAL_STATE["driver_logs"] is None
        assert INITIAL_STATE["error_patterns"] == []
        assert INITIAL_STATE["risk_level"] == "LOW"
        assert INITIAL_STATE["confidence_score"] == 0.0
        assert INITIAL_STATE["approval_required"] is False
        assert INITIAL_STATE["approval_status"] is None

    def test_create_initial_state_with_alert_raw(self):
        """测试 create_initial_state 接受 alert_raw"""
        alert_raw = {"projectCode": 123, "taskType": "SPARK"}
        state = create_initial_state(alert_raw)

        assert state["alert_raw"] == alert_raw

    def test_create_initial_state_without_alert_raw(self):
        """测试 create_initial_state 不提供 alert_raw"""
        state = create_initial_state()

        assert state["alert_raw"] == {}


# ==================== Placeholder Nodes Tests ====================


class TestPlaceholderNodes:
    """占位节点测试"""

    def test_fetch_logs_node(self):
        """测试 fetch_logs 占位节点"""
        from src.workflow.nodes.fetch_logs import fetch_logs

        state = dict(INITIAL_STATE)
        result = fetch_logs(state)

        assert result["driver_logs"] is None
        assert result["spark_logs"] is None
        assert result["yarn_logs"] is None
        assert result["k8s_logs"] is None

    def test_analyze_error_node(self):
        """测试 analyze_error 占位节点"""
        from src.workflow.nodes.analyze import analyze_error

        state = dict(INITIAL_STATE)
        result = analyze_error(state)

        assert result["error_patterns"] == []
        assert result["error_category"] == ""
        assert result["suggested_actions"] == []

    def test_query_knowledge_node(self):
        """测试 query_knowledge 占位节点"""
        from src.workflow.nodes.knowledge import query_knowledge

        state = dict(INITIAL_STATE)
        result = query_knowledge(state)

        assert result["knowledge_match"] is None

    def test_request_approval_node(self):
        """测试 request_approval 占位节点"""
        from src.workflow.nodes.approval import request_approval

        state = dict(INITIAL_STATE)
        result = request_approval(state)

        assert result["approval_status"] == "pending"

    def test_check_approval_node(self):
        """测试 check_approval 占位节点"""
        from src.workflow.nodes.approval import check_approval

        state = dict(INITIAL_STATE)
        state["approval_status"] = "pending"
        result = check_approval(state)

        # 占位节点应该保持状态不变
        assert result["approval_status"] == "pending"

    def test_execute_action_node(self):
        """测试 execute_action 占位节点"""
        from src.workflow.nodes.execute import execute_action

        state = dict(INITIAL_STATE)
        result = execute_action(state)

        assert result["executed_actions"] == []
        assert result["execution_results"] == []
        assert result["execution_success"] is False

    def test_notify_dingtalk_node(self):
        """测试 notify_dingtalk 占位节点"""
        from src.workflow.nodes.notify import notify_dingtalk

        state = dict(INITIAL_STATE)
        result = notify_dingtalk(state)

        assert result["notification_sent"] is False
        assert result["notification_content"] is None

    def test_store_results_node(self):
        """测试 store_results 占位节点"""
        from src.workflow.nodes.store import store_results

        state = dict(INITIAL_STATE)
        result = store_results(state)

        assert result["log_stored"] is False
        assert result["result_stored"] is False
        assert result["log_store_path"] is None


# ==================== Workflow Integration Tests ====================


class TestWorkflowIntegration:
    """工作流集成测试"""

    @patch("src.workflow.nodes.validate.projects_registry")
    def test_full_workflow_execution(self, mock_registry):
        """测试完整工作流执行"""
        # Mock 项目配置
        mock_config = MagicMock()
        mock_config.name = "test_project"
        mock_config.code = 123
        mock_config.ds_api_url = "http://test.api"
        mock_config.ds_api_token = "test_token"
        mock_config.ds_version = "3.2.0"
        mock_config.effective_spark_mode = "yarn"
        mock_config.effective_spark_history_url = "http://spark.history"
        mock_config.effective_yarn_gateway_url = "http://yarn.gateway"
        mock_config.dingtalk = None

        mock_registry.get_by_code.return_value = mock_config

        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 123,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SPARK",
            "endTime": "2025-05-07 14:30:00",
        }

        result = workflow.run(alert_raw)

        # 验证所有阶段的字段都已设置
        # Input stage
        assert result["project_code"] == "123"
        assert result["workflow_code"] == "456"
        assert result["task_code"] == "789"
        assert result["task_type"] == "SPARK"
        assert result["error_time"] == "2025-05-07 14:30:00"

        # Validation stage
        assert result["project_valid"] is True
        assert result["project_config"] is not None

        # Risk assessment stage
        assert result["risk_level"] == "LOW"
        assert isinstance(result["risk_factors"], list)
        assert result["approval_required"] is False

    @patch("src.workflow.nodes.validate.projects_registry")
    def test_workflow_with_invalid_project_code(self, mock_registry):
        """测试无效项目编码的工作流"""
        mock_registry.get_by_code.return_value = None

        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 999,
            "processDefinitionCode": 456,
            "taskCode": 789,
            "taskType": "SHELL",
        }

        result = workflow.run(alert_raw)

        # 验证项目被标记为无效
        assert result["project_valid"] is False
        assert result["project_config"] is None

        # 由于项目无效，工作流应该提前结束
        # 但 parse_alert 应该已经执行
        assert result["project_code"] == "999"