"""
K8sLogTool - Kubernetes 日志获取工具

使用 kubernetes-client 获取 Spark on K8s Pod 日志
"""

import os
from typing import Dict, Optional

# Initialize module-level variables for mocking
K8S_AVAILABLE = False
client = None
config = None

try:
    from kubernetes import client as _client
    from kubernetes import config as _config
    client = _client
    config = _config
    K8S_AVAILABLE = True
except ImportError:
    pass


class K8sLogTool:
    """
    Kubernetes Pod 日志获取工具

    通过 Pod labels 筛选 Spark 应用相关 Pod
    """

    def __init__(
        self,
        namespace: str = "spark-apps",
        kubeconfig_path: Optional[str] = None
    ):
        """
        初始化

        Args:
            namespace: Spark 应用命名空间
            kubeconfig_path: kubeconfig 文件路径（可选）
        """
        self.namespace = namespace
        self.kubeconfig_path = kubeconfig_path
        self._api = None

        if K8S_AVAILABLE:
            self._init_k8s_client()

    def _init_k8s_client(self):
        """初始化 K8s 客户端"""
        if self.kubeconfig_path:
            config.load_kube_config(config_file=self.kubeconfig_path)
        elif os.environ.get("KUBECONFIG"):
            config.load_kube_config()
        else:
            # 尝试 in-cluster 配置
            try:
                config.load_incluster_config()
            except config.ConfigException:
                # 回退到默认 kubeconfig
                config.load_kube_config()

        self._api = client.CoreV1Api()

    def fetch_logs(self, app_name: str) -> Dict[str, str]:
        """
        获取 Spark 应用 Pod 日志

        Args:
            app_name: Spark 应用名称

        Returns:
            日志字典 {"driver-pod": "...", "executor-1": "...", ...}
        """
        if not K8S_AVAILABLE or not self._api:
            return {}

        try:
            label_selector = self._build_label_selector(app_name)

            pods = self._api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=label_selector
            )

            logs = {}
            for pod in pods.items:
                pod_name = pod.metadata.name

                # 只获取 Running 或 Succeeded/Failed Pod 的日志
                if pod.status.phase not in ["Running", "Succeeded", "Failed"]:
                    continue

                try:
                    log_content = self._api.read_pod_log(
                        name=pod_name,
                        namespace=self.namespace,
                        tail_lines=500  # 只获取最近 500 行
                    )
                    logs[pod_name] = log_content
                except client.ApiException:
                    pass

            return logs

        except client.ApiException:
            return {}

    def _build_label_selector(self, app_name: str) -> str:
        """构建 Pod label selector"""
        # Spark on K8s 使用 spark-app-name label
        return f"spark-app-name={app_name}"


__all__ = ["K8sLogTool"]