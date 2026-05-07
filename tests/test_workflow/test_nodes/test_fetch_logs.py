"""
fetch_logs 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.fetch_logs import fetch_logs


class TestFetchLogs:

    @patch("src.workflow.nodes.fetch_logs.DSCLIClient")
    @patch("src.workflow.nodes.fetch_logs.SparkHistTool")
    def test_fetch_logs_yarn_mode(self, mock_spark, mock_dsctl):
        """测试 YARN 模式日志获取"""
        mock_dsctl_instance = Mock()
        mock_dsctl_instance.get_task_logs.return_value = Mock(
            success=True, stdout="driver log content"
        )
        mock_dsctl.return_value = mock_dsctl_instance

        mock_spark_instance = Mock()
        mock_spark_instance.fetch_logs.return_value = {"driver": "spark history log"}
        mock_spark_instance.extract_app_id.return_value = "application_123_456"
        mock_spark.return_value = mock_spark_instance

        state = create_initial_state({
            "projectCode": "11598158952448",
            "processDefinitionCode": "21451302002208",
            "taskCode": "123456",
            "taskInstanceId": 1377412,
            "taskType": "SPARK",
        })
        state["project_config"] = {
            "spark_mode": "yarn",
            "spark_history_url": "http://spark-history:18082",
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = fetch_logs(state)

        assert result["driver_logs"] is not None

    def test_fetch_logs_no_project_config(self):
        """测试无项目配置"""
        state = create_initial_state({
            "projectCode": "0",
            "processDefinitionCode": "0",
            "taskCode": "0",
            "taskType": "SPARK",
        })
        state["project_config"] = None

        result = fetch_logs(state)

        assert result["log_fetch_error"] is not None