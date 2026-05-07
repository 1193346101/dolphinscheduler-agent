"""
YARNLogTool - YARN Gateway 日志获取工具

通过 Knox Gateway 代理 YARN ResourceManager API 获取 container 日志
"""

import requests
from typing import Dict, Optional
from requests.auth import HTTPBasicAuth


class YARNLogTool:
    """
    YARN Gateway 日志获取工具

    通过 Knox Gateway 访问 YARN API
    """

    def __init__(
        self,
        gateway_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_type: str = "basic"
    ):
        """
        初始化

        Args:
            gateway_url: Knox Gateway YARN URL
            username: 认证用户名
            password: 认证密码
            auth_type: basic / kerberos
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.username = username
        self.password = password
        self.auth_type = auth_type

    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取 YARN container 日志

        Args:
            application_id: YARN 应用 ID

        Returns:
            日志字典 {"container_1": "...", ...}
        """
        try:
            url = self._build_app_url(application_id)

            auth = None
            if self.username and self.password:
                auth = HTTPBasicAuth(self.username, self.password)

            response = requests.get(url, auth=auth, timeout=15, verify=False)

            if response.status_code != 200:
                return {}

            app_data = response.json()
            logs = {}

            # 解析 containers
            containers = app_data.get("app", {}).get("containers", [])
            for container in containers:
                container_id = container.get("id", "")
                log_content = self._fetch_container_log(container_id, auth)
                if log_content:
                    logs[container_id] = log_content

            return logs

        except requests.RequestException:
            return {}

    def _build_app_url(self, application_id: str) -> str:
        """构建应用 API URL"""
        return f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"

    def _fetch_container_log(self, container_id: str, auth) -> Optional[str]:
        """获取单个 container 日志"""
        try:
            url = f"{self.gateway_url}/ws/v1/cluster/apps/{container_id.split('_')[0]}_{container_id.split('_')[1]}/containers/{container_id}/logs"
            response = requests.get(url, auth=auth, timeout=10, verify=False)

            if response.status_code == 200:
                return response.text
            return None
        except requests.RequestException:
            return None


__all__ = ["YARNLogTool"]