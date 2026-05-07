"""
K8sLogTool 测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.tools.k8s_log import K8sLogTool


class TestK8sLogTool:

    def test_init_with_namespace(self):
        """测试初始化"""
        with patch("src.tools.k8s_log.K8S_AVAILABLE", False):
            tool = K8sLogTool(namespace="spark-apps")
            assert tool.namespace == "spark-apps"

    @patch("src.tools.k8s_log.K8S_AVAILABLE", True)
    @patch("src.tools.k8s_log.client")
    @patch("src.tools.k8s_log.config")
    def test_fetch_logs_success(self, mock_config, mock_client):
        """测试获取日志成功"""
        # Create mock pods with proper name attributes
        mock_pod1 = MagicMock()
        mock_pod1.metadata.name = "spark-driver"
        mock_pod1.status.phase = "Running"

        mock_pod2 = MagicMock()
        mock_pod2.metadata.name = "spark-executor-1"
        mock_pod2.status.phase = "Running"

        mock_api = MagicMock()
        mock_api.list_namespaced_pod.return_value = MagicMock(items=[mock_pod1, mock_pod2])
        mock_api.read_pod_log.return_value = "pod log content"
        mock_client.CoreV1Api.return_value = mock_api

        tool = K8sLogTool(namespace="spark-apps")
        result = tool.fetch_logs("spark-app-name")

        assert "spark-driver" in result

    @patch("src.tools.k8s_log.K8S_AVAILABLE", True)
    @patch("src.tools.k8s_log.client")
    @patch("src.tools.k8s_log.config")
    def test_fetch_logs_no_pods(self, mock_config, mock_client):
        """测试无匹配 Pod"""
        mock_api = MagicMock()
        mock_api.list_namespaced_pod.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_api

        tool = K8sLogTool(namespace="spark-apps")
        result = tool.fetch_logs("nonexistent-app")

        assert result == {}

    def test_build_pod_label_selector(self):
        """测试构建 label selector"""
        with patch("src.tools.k8s_log.K8S_AVAILABLE", False):
            tool = K8sLogTool(namespace="spark-apps")

            selector = tool._build_label_selector("my-spark-app")

            assert "spark-app-name=my-spark-app" in selector