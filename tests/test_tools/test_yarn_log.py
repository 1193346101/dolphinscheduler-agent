"""
YARNLogTool 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.yarn_log import YARNLogTool


class TestYARNLogTool:

    def test_init_with_gateway_url(self):
        """测试初始化"""
        tool = YARNLogTool(
            gateway_url="https://knox:8443/gateway/default/yarn",
            username="yarn_user",
            password="yarn_pass"
        )
        assert tool.gateway_url == "https://knox:8443/gateway/default/yarn"

    @patch("requests.get")
    def test_fetch_logs_success(self, mock_get):
        """测试获取日志成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "app": {
                "containers": [
                    {"id": "container_1", "log": "driver log"},
                    {"id": "container_2", "log": "executor log"}
                ]
            }
        }
        mock_get.return_value = mock_response

        tool = YARNLogTool("https://knox:8443", "user", "pass")
        result = tool.fetch_logs("application_123_456")

        assert "container_1" in result

    @patch("requests.get")
    def test_fetch_logs_not_found(self, mock_get):
        """测试应用不存在"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        tool = YARNLogTool("https://knox:8443", "user", "pass")
        result = tool.fetch_logs("application_invalid")

        assert result == {}

    def test_build_yarn_api_url(self):
        """测试构建 YARN API URL"""
        tool = YARNLogTool("https://knox:8443/gateway/default/yarn", "user", "pass")

        url = tool._build_app_url("application_123_456")

        assert "application_123_456" in url
        assert "ws/v1/cluster/apps" in url