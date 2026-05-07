"""
SparkHistTool - Spark History Server 日志获取工具

通过 Spark History Server REST API 获取应用日志
"""

import re
import requests
from typing import Dict, Optional


class SparkHistTool:
    """
    Spark History Server 日志获取工具

    API:
    - GET /api/v1/applications/{app_id} - 获取应用信息
    - GET /api/v1/applications/{app_id}/logs - 获取日志
    """

    def __init__(self, history_url: str):
        """
        初始化

        Args:
            history_url: Spark History Server URL (如 http://host:18082)
        """
        self.history_url = history_url.rstrip("/")

    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取应用日志

        Args:
            application_id: Spark 应用 ID (如 application_123456_789)

        Returns:
            日志字典 {"driver": "...", "executor_1": "...", ...}
        """
        try:
            # 获取应用详情（包含 attempts）
            url = f"{self.history_url}/api/v1/applications/{application_id}"
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return {}

            app_data = response.json()
            logs = {}

            # 解析 attempts 获取日志
            for attempt in app_data.get("attempts", []):
                attempt_id = attempt.get("id", "")
                log_content = attempt.get("logs", "")

                if attempt_id == "driver":
                    logs["driver"] = log_content
                else:
                    logs[f"executor_{attempt_id}"] = log_content

            return logs

        except requests.RequestException:
            return {}

    def extract_app_id(self, log_content: str) -> Optional[str]:
        """
        从日志内容提取 Spark application_id

        Args:
            log_content: 日志文本

        Returns:
            application_id 或 None
        """
        # 匹配 application_xxx_yyy 格式
        patterns = [
            r"application_\d+_\d+",
            r"app-\d+-\d+",
        ]

        for pattern in patterns:
            match = re.search(pattern, log_content)
            if match:
                return match.group(0)

        return None


__all__ = ["SparkHistTool"]