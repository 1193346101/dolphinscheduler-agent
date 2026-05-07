"""
DingTalkEnterpriseTool 测试

注意: access_token 和消息发送需要 Mock
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.dingtalk_enterprise import DingTalkEnterpriseTool, DingTalkError


class TestDingTalkEnterpriseTool:

    def test_init_with_credentials(self):
        """测试初始化"""
        tool = DingTalkEnterpriseTool(
            client_id="test_client_id",
            client_secret="test_secret",
        )

        assert tool.client_id == "test_client_id"
        assert tool.client_secret == "test_secret"
        assert tool.access_token is None

    @patch("requests.post")
    def test_get_access_token_success(self, mock_post):
        """测试获取 access_token 成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessToken": "test_token_123",
            "expireIn": 7200,
        }
        mock_post.return_value = mock_response

        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        token = tool._get_access_token()

        assert token == "test_token_123"
        assert tool.access_token == "test_token_123"

    @patch("requests.post")
    def test_get_access_token_failure(self, mock_post):
        """测试获取 access_token 失败"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        tool = DingTalkEnterpriseTool("test_id", "test_secret")

        with pytest.raises(DingTalkError):
            tool._get_access_token()

    @patch("requests.post")
    def test_send_notification_success(self, mock_post):
        """测试发送通知成功"""
        # Mock token response
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {"accessToken": "test_token", "expireIn": 7200}

        # Mock message response
        message_response = Mock()
        message_response.status_code = 200
        message_response.json.return_value = {"processQueryKeys": "msg_123"}

        mock_post.side_effect = [token_response, message_response]

        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        result = tool.send_notification(
            robot_code="test_robot",
            user_ids=["user1", "user2"],
            title="Test Alert",
            content="Test content",
        )

        assert result == "msg_123"

    def test_build_error_notification(self):
        """测试构建错误通知"""
        tool = DingTalkEnterpriseTool("test_id", "test_secret")

        result = tool.build_error_notification(
            task_type="SPARK",
            workflow_code="123456",
            task_code="789012",
            risk_level="LOW",
            error_category="RESOURCE",
            error_patterns=["OutOfMemoryError", "Container killed"],
            suggested_actions=[{"description": "增加内存配置"}],
            ds_url="http://test:12345/dolphinscheduler",
        )

        assert result["title"] == "告警分析: SPARK"
        assert "OutOfMemoryError" in result["content"]
        assert "增加内存配置" in result["content"]

    def test_build_approval_request(self):
        """测试构建审批请求"""
        tool = DingTalkEnterpriseTool("test_id", "test_secret")

        result = tool.build_approval_request(
            task_type="SPARK",
            workflow_code="123456",
            task_code="789012",
            risk_level="HIGH",
            impact_summary="影响 10 个下游任务",
            suggested_actions=[{"description": "从失败恢复"}],
            risk_factors=["recover-failed: HIGH"],
            approve_url="/approval/approve",
            reject_url="/approval/reject",
        )

        assert result["title"] == "需要审批: HIGH 风险"
        assert "影响 10 个下游任务" in result["content"]
        assert len(result["buttons"]) == 2
        assert result["buttons"][0]["title"] == "批准"