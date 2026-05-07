"""
notify_dingtalk 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.notify import notify_dingtalk


class TestNotifyDingtalk:

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_error_analysis(self, mock_dingtalk):
        """测试发送错误分析通知"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_123"
        mock_instance.build_error_notification.return_value = {
            "title": "告警分析",
            "content": "error content"
        }
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["approval_required"] = False
        state["risk_level"] = "LOW"
        state["error_category"] = "RESOURCE"
        state["error_patterns"] = ["oom_executor"]
        state["suggested_actions"] = []
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test_robot",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "notify_users": ["user1"]
            },
            "ds_api_url": "http://ds:12345"
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is True
        assert result["approval_message_id"] == "msg_123"

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_approval_request(self, mock_dingtalk):
        """测试发送审批请求通知"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_approval"
        mock_instance.build_approval_request.return_value = {
            "title": "审批请求",
            "content": "需要审批",
            "buttons": [{"title": "批准", "actionUrl": "/approval/approve"}]
        }
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["approval_required"] = True
        state["risk_level"] = "HIGH"
        state["error_category"] = "RESOURCE"
        state["suggested_actions"] = [{"action_type": "recover-failed"}]
        state["impact_summary"] = "下游 3 个工作流"
        state["risk_factors"] = ["下游依赖多"]
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test_robot",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "notify_users": ["user1"]
            }
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is True

    def test_notify_no_dingtalk_config(self):
        """测试无钉钉配置"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["project_config"] = {}

        result = notify_dingtalk(state)

        assert result["notification_sent"] is False

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_send_failure(self, mock_dingtalk):
        """测试发送失败"""
        mock_instance = Mock()
        mock_instance.send_notification.side_effect = Exception("网络错误")
        mock_instance.build_error_notification.return_value = {"title": "test", "content": "test"}
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["approval_required"] = False
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test",
                "client_id": "test",
                "client_secret": "test",
                "notify_users": ["user1"]
            }
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is False
        assert "发送失败" in result["notification_content"]