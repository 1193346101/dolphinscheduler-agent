"""
execute_action 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.execute import execute_action


class TestExecuteAction:

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_rerun_action(self, mock_dsctl):
        """测试重跑动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_rerun.return_value = Mock(
            success=True, stdout="OK", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "rerun", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert result["execution_success"] is True
        assert len(result["executed_actions"]) == 1

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_recover_action(self, mock_dsctl):
        """测试恢复动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(
            success=True, stdout="Recovery started", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert len(result["executed_actions"]) > 0

    def test_execute_high_risk_without_approval(self):
        """测试高风险动作无审批"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = None
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}

        result = execute_action(state)

        # 高风险无审批应该跳过
        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 0

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_high_risk_with_approval(self, mock_dsctl):
        """测试高风险动作已审批"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(
            success=True, stdout="OK", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = "approved"
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert len(result["executed_actions"]) > 0

    def test_execute_no_actions(self):
        """测试无动作列表"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["suggested_actions"] = []
        state["project_config"] = {}

        result = execute_action(state)

        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 0

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_config_change_action(self, mock_dsctl):
        """测试配置变更动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_rerun.return_value = Mock(
            success=True, stdout="Config changed and rerun", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "config-change", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert result["execution_success"] is True
        assert len(result["executed_actions"]) == 1

    def test_execute_notify_only_action(self):
        """测试仅通知动作"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["suggested_actions"] = [{"action_type": "notify-only", "risk_level": "LOW"}]
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}

        result = execute_action(state)

        assert result["execution_success"] is True
        assert len(result["executed_actions"]) == 1

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_action_failure(self, mock_dsctl):
        """测试动作执行失败"""
        mock_instance = Mock()
        mock_instance.workflow_instance_rerun.return_value = Mock(
            success=False, stdout="", stderr="Error: workflow not found", returncode=1
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["suggested_actions"] = [{"action_type": "rerun", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 1
        assert result["execution_results"][0]["status"] == "failed"

    def test_execute_unknown_action_type(self):
        """测试未知动作类型"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["suggested_actions"] = [{"action_type": "unknown-type", "risk_level": "LOW"}]
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}

        result = execute_action(state)

        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 0
        assert result["execution_results"][0]["status"] == "skipped"