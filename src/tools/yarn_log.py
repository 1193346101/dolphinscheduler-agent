"""
YARNLogTool - YARN Gateway 日志获取工具

通过 Knox Gateway 代理 YARN ResourceManager API 获取应用信息
"""

import requests
from typing import Dict, Optional
from requests.auth import HTTPBasicAuth


class YARNLogTool:
    """
    YARN Gateway 日志获取工具

    通过 Knox Gateway 访问 YARN API (需要 LDAP 认证)
    """

    def __init__(
        self,
        gateway_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        初始化

        Args:
            gateway_url: Knox Gateway YARN URL (如 https://host:8443/gateway/default/yarn)
            username: LDAP 认证用户名
            password: LDAP 认证密码
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(username, password) if username and password else None

    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取 YARN 应用信息

        Args:
            application_id: YARN 应用 ID

        Returns:
            应用信息字典 {"app_name", "state", "diagnostics", ...}
        """
        try:
            # 获取应用详情
            url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"

            response = requests.get(
                url,
                auth=self.auth,
                timeout=15,
                verify=False  # Knox 可能使用自签名证书
            )

            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}", "url": url}

            app_data = response.json().get("app", {})
            logs = {}

            # 提取关键信息
            logs["app_id"] = app_data.get("id", "")
            logs["app_name"] = app_data.get("name", "")
            logs["state"] = app_data.get("state", "")
            logs["final_status"] = app_data.get("finalStatus", "")
            logs["user"] = app_data.get("user", "")
            logs["tracking_url"] = app_data.get("trackingUrl", "")
            logs["started_time"] = app_data.get("startedTime", 0)
            logs["finished_time"] = app_data.get("finishedTime", 0)
            logs["elapsed_time"] = app_data.get("elapsedTime", 0)

            # 诊断信息（错误原因）
            diagnostics = app_data.get("diagnostics", "")
            if diagnostics:
                logs["diagnostics"] = diagnostics

            # 资源使用
            logs["allocated_vcores"] = app_data.get("allocatedVCores", 0)
            logs["allocated_memory_mb"] = app_data.get("allocatedMB", 0)
            logs["running_containers"] = app_data.get("runningContainers", 0)

            return logs

        except requests.RequestException as e:
            return {"error": str(e)}

    def get_app_attempts(self, application_id: str) -> Dict:
        """
        获取应用尝试次数信息

        Args:
            application_id: YARN 应用 ID

        Returns:
            尝试信息 {"attempts": [...]}
        """
        try:
            url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}/appattempts"
            response = requests.get(
                url,
                auth=self.auth,
                timeout=15,
                verify=False
            )

            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}

        except requests.RequestException as e:
            return {"error": str(e)}


__all__ = ["YARNLogTool"]