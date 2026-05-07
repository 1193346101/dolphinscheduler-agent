"""
SparkHistTool 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.spark_hist import SparkHistTool


class TestSparkHistTool:

    def test_init_with_url(self):
        """测试初始化"""
        tool = SparkHistTool(history_url="http://spark-history:18082")
        assert tool.history_url == "http://spark-history:18082"

    @patch("requests.get")
    def test_fetch_logs_success(self, mock_get):
        """测试获取日志成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "attempts": [{
                "id": "driver",
                "logs": "driver stdout content"
            }]
        }
        mock_get.return_value = mock_response

        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_123_456")

        assert "driver" in result
        assert "driver stdout content" in result["driver"]

    @patch("requests.get")
    def test_fetch_logs_application_not_found(self, mock_get):
        """测试应用不存在"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_invalid")

        assert result == {}  # 返回空字典

    @patch("requests.get")
    def test_fetch_logs_with_executor_logs(self, mock_get):
        """测试包含 executor 日志"""
        mock_app_response = Mock()
        mock_app_response.status_code = 200
        mock_app_response.json.return_value = {
            "attempts": [
                {"id": "driver", "logs": "driver log"},
                {"id": "1", "logs": "executor 1 log"},
                {"id": "2", "logs": "executor 2 log"}
            ]
        }

        mock_get.return_value = mock_app_response

        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_123_456")

        assert len(result) == 3
        assert "executor_1" in result

    def test_extract_app_id_from_log(self):
        """测试从日志提取 app_id"""
        tool = SparkHistTool(history_url="http://test:18082")

        log = "Starting Spark application application_20260507_12345"
        app_id = tool.extract_app_id(log)

        assert app_id == "application_20260507_12345"

    def test_extract_app_id_not_found(self):
        """测试日志中无 app_id"""
        tool = SparkHistTool(history_url="http://test:18082")

        log = "Some random log content"
        app_id = tool.extract_app_id(log)

        assert app_id is None