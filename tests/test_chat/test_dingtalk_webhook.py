"""Tests for DingTalk webhook API functionality."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.chat.api.dingtalk_webhook import router, handle_dingtalk_message
from src.chat.api.dingtalk_webhook import extract_message_content, extract_project_code


# 创建测试应用
def create_test_app():
    app = FastAPI()
    app.include_router(router)
    return app


class TestExtractMessageContent:
    """Tests for extract_message_content function."""

    def test_extract_text_content(self):
        """测试提取文本消息内容"""
        payload = {
            "msgtype": "text",
            "text": {"content": "工作流 wf_001 的下游"}
        }

        content = extract_message_content(payload, "text")
        assert content == "工作流 wf_001 的下游"

    def test_extract_markdown_content(self):
        """测试提取 Markdown 消息内容"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "测试标题",
                "text": "工作流 wf_001 的下游"
            }
        }

        content = extract_message_content(payload, "markdown")
        assert content == "工作流 wf_001 的下游"

    def test_extract_markdown_from_title(self):
        """测试从标题提取 Markdown 内容"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "工作流 wf_001 的下游"
            }
        }

        content = extract_message_content(payload, "markdown")
        assert content == "工作流 wf_001 的下游"

    def test_extract_unknown_type(self):
        """测试提取未知类型消息"""
        payload = {
            "msgtype": "unknown",
            "text": {"content": "测试内容"}
        }

        content = extract_message_content(payload, "unknown")
        assert content == "测试内容"

    def test_extract_empty_content(self):
        """测试提取空内容"""
        payload = {
            "msgtype": "text",
            "text": {}
        }

        content = extract_message_content(payload, "text")
        assert content == ""


class TestExtractProjectCode:
    """Tests for extract_project_code function."""

    def test_extract_from_title(self):
        """测试从会话标题提取项目代码"""
        payload = {
            "conversationTitle": "项目-proj_001-告警群"
        }

        project_code = extract_project_code(payload)
        assert project_code == "proj_001"

    def test_extract_from_title_without_prefix(self):
        """测试从标题提取（无项目前缀）"""
        payload = {
            "conversationTitle": "告警群"
        }

        project_code = extract_project_code(payload)
        # Without "项目" prefix, returns default
        assert project_code == "default_project"

    def test_extract_default_without_title(self):
        """测试无标题时返回默认"""
        payload = {}

        project_code = extract_project_code(payload)
        assert project_code == "default_project"

    def test_extract_from_complex_title(self):
        """测试从复杂标题提取"""
        payload = {
            "conversationTitle": "项目-my_project告警群"
        }

        project_code = extract_project_code(payload)
        # Extracts word characters after "项目"
        assert project_code == "my_project"


class TestDingTalkWebhookAPI:
    """Tests for DingTalk webhook API endpoints."""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        app = create_test_app()
        return TestClient(app)

    def test_handle_text_message(self, client):
        """测试处理文本消息"""
        mock_state_result = {
            "message": "工作流 wf_001 的下游",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "lineage_query",
            "query_type": "downstream",
            "workflow_code": "wf_001",
            "project_code": "proj_001",
            "result_data": {
                "found": True,
                "direct": ["wf_002"],
                "all": ["wf_002"],
                "count": 1,
            },
            "response_content": "### 工作流 wf_001 下游依赖\n...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = mock_state_result

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "工作流 wf_001 的下游"},
                "senderId": "user_001",
                "conversationId": "conv_001",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["msgtype"] == "markdown"
            assert "markdown" in data

    def test_handle_help_message(self, client):
        """测试处理帮助消息"""
        mock_state_result = {
            "message": "帮助",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "help",
            "response_content": "### 帮助\n...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = mock_state_result

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "帮助"},
                "senderId": "user_001",
                "conversationId": "conv_001",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["msgtype"] == "markdown"

    def test_handle_empty_message(self, client):
        """测试处理空消息"""
        response = client.post("/dingtalk/message", json={
            "msgtype": "text",
            "text": {"content": ""},
            "senderId": "user_001",
            "conversationId": "conv_001",
        })

        assert response.status_code == 200
        data = response.json()
        assert "请输入有效消息" in data["text"]["content"]

    def test_handle_unknown_intent(self, client):
        """测试处理未知意图"""
        mock_state_result = {
            "message": "随机消息",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "unknown",
            "response_content": "抱歉，我不理解您的消息...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = mock_state_result

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "随机消息"},
                "senderId": "user_001",
                "conversationId": "conv_001",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["msgtype"] == "markdown"

    def test_handle_scan_graph_intent(self, client):
        """测试处理扫描图谱意图"""
        mock_state_result = {
            "message": "扫描项目 my_project 图谱",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "scan_graph",
            "project_name": "my_project",
            "response_content": "### 扫描图谱\n...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = mock_state_result

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "扫描项目 my_project 图谱"},
                "senderId": "user_001",
                "conversationId": "conv_001",
            })

            assert response.status_code == 200

    def test_project_code_extraction_in_request(self, client):
        """测试请求中项目代码提取"""
        mock_state_result = {
            "message": "工作流 wf_001 的下游",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "lineage_query",
            "query_type": "downstream",
            "workflow_code": "wf_001",
            "project_code": "proj_from_title",
            "response_content": "### 工作流 wf_001 下游依赖\n...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = mock_state_result

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "工作流 wf_001 的下游"},
                "senderId": "user_001",
                "conversationId": "conv_001",
                "conversationTitle": "项目-proj_from_title-告警群",
            })

            assert response.status_code == 200
            # Verify graph.invoke was called with state containing project_code
            mock_graph.invoke.assert_called_once()
            invoke_arg = mock_graph.invoke.call_args[0][0]
            assert invoke_arg["project_code"] == "proj_from_title"


class TestDingTalkMessageModels:
    """Tests for Pydantic models."""

    def test_dingtalk_request_model(self):
        """测试钉钉请求模型"""
        from src.chat.api.dingtalk_webhook import DingTalkRequest

        request = DingTalkRequest(
            msgtype="text",
            text={"content": "测试消息"},
            senderId="user_001",
            conversationId="conv_001",
        )

        assert request.msgtype == "text"
        assert request.text["content"] == "测试消息"
        assert request.senderId == "user_001"

    def test_dingtalk_response_model(self):
        """测试钉钉响应模型"""
        from src.chat.api.dingtalk_webhook import DingTalkResponse

        response = DingTalkResponse(
            markdown={"title": "标题", "text": "内容"}
        )

        assert response.msgtype == "markdown"
        assert response.markdown["title"] == "标题"


class TestDingTalkWebhookIntegration:
    """Integration tests for DingTalk webhook."""

    def test_full_workflow_with_mock(self):
        """测试完整工作流（mock 方式）"""
        app = create_test_app()
        client = TestClient(app)

        # 完整的模拟状态流转
        final_state = {
            "message": "工作流 wf_123 的下游",
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "intent_type": "lineage_query",
            "query_type": "downstream",
            "workflow_code": "wf_123",
            "project_code": "proj_001",
            "result_data": {
                "found": True,
                "direct": ["wf_456", "wf_789"],
                "all": ["wf_456", "wf_789", "wf_abc"],
                "count": 3,
            },
            "response_content": "### 工作流 wf_123 下游依赖\n...",
        }

        mock_graph = Mock()
        mock_graph.invoke.return_value = final_state

        with patch('src.chat.api.dingtalk_webhook.get_chat_graph',
                   return_value=mock_graph):

            response = client.post("/dingtalk/message", json={
                "msgtype": "text",
                "text": {"content": "工作流 wf_123 的下游"},
                "senderId": "user_001",
                "conversationId": "conv_001",
                "conversationTitle": "项目-proj_001-告警群",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["msgtype"] == "markdown"
            assert "wf_123" in data["markdown"]["text"]