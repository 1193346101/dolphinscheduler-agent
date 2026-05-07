"""
DSCLIClient 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.integrations.dsctl_wrapper import DSCLIClient


class TestDSCLIClient:

    def test_init_with_config(self):
        """测试初始化"""
        client = DSCLIClient(
            api_url="http://ds:12345/dolphinscheduler",
            api_token="test_token"
        )
        assert client.api_url == "http://ds:12345/dolphinscheduler"

    @patch("subprocess.run")
    def test_rerun_workflow_instance(self, mock_run):
        """测试重跑工作流实例"""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_rerun(instance_id=833841)

        assert result.success is True

    @patch("subprocess.run")
    def test_recover_from_failed(self, mock_run):
        """测试从失败恢复"""
        mock_run.return_value = Mock(returncode=0, stdout="Recovery started", stderr="")

        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_recover(instance_id=833841, task_code=123456)

        assert result.success is True

    @patch("subprocess.run")
    def test_get_task_logs(self, mock_run):
        """测试获取任务日志"""
        mock_run.return_value = Mock(returncode=0, stdout="Task log content", stderr="")

        client = DSCLIClient("http://ds:12345", "token")
        result = client.get_task_logs(task_instance_id=1377412)

        assert result.success is True
        assert "Task log content" in result.stdout

    @patch("subprocess.run")
    def test_command_failure(self, mock_run):
        """测试命令失败"""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error: not found")

        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_rerun(instance_id=999)

        assert result.success is False