"""
SparkHistTool - Spark History Server 日志获取工具

通过 Spark History Server REST API 获取应用日志

API:
- GET /api/v1/applications/{app_id} - 获取应用信息
- GET /api/v1/applications/{app_id}/logs - 获取日志 (ZIP压缩的 event log)
"""

import re
import requests
import zipfile
import io
from typing import Dict, Optional, List


class SparkHistTool:
    """
    Spark History Server 日志获取工具

    返回的日志是 ZIP 压缩的 SparkListener event log (JSON 格式)
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
            日志字典 {"event_log": "..."} - 解压后的 event log JSON 行
        """
        try:
            # 获取应用详情（包含 attempts）
            url = f"{self.history_url}/api/v1/applications/{application_id}"
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return {}

            app_data = response.json()
            logs = {}

            # 获取完整日志 (ZIP 格式)
            logs_url = f"{self.history_url}/api/v1/applications/{application_id}/logs"
            logs_response = requests.get(logs_url, timeout=30)

            if logs_response.status_code == 200:
                # 解压 ZIP 文件
                try:
                    zip_buffer = io.BytesIO(logs_response.content)
                    with zipfile.ZipFile(zip_buffer, 'r') as z:
                        for name in z.namelist():
                            content = z.read(name)
                            # 解码为文本
                            event_log_text = content.decode('utf-8', errors='ignore')
                            logs["event_log"] = event_log_text
                            logs["event_log_size"] = len(event_log_text)
                except zipfile.BadZipFile:
                    # 如果不是 ZIP，直接返回文本
                    logs["event_log"] = logs_response.text

            # 添加应用基本信息
            logs["app_name"] = app_data.get("name", "")
            attempts = app_data.get("attempts", [])
            if attempts:
                logs["attempt_count"] = len(attempts)
                logs["last_attempt_duration"] = attempts[-1].get("duration", 0)

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

    def extract_errors_from_event_log(self, event_log: str) -> List[Dict]:
        """
        从 event log JSON 行提取错误信息

        Args:
            event_log: 解压后的 event log 文本 (每行一个 JSON)

        Returns:
            错误事件列表 [{"event": "SparkListenerTaskEnd", "reason": "..."}]
        """
        import json
        errors = []

        for line in event_log.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                event_type = event.get("Event", "")

                # 提取失败相关事件
                if event_type in [
                    "SparkListenerTaskEnd",
                    "SparkListenerJobEnd",
                    "SparkListenerStageCompleted",
                ]:
                    # 检查是否有失败
                    if event_type == "SparkListenerTaskEnd":
                        reason = event.get("Task End Reason", {})
                        if reason.get("Failure", "") or reason.get("Accumulables", []):
                            errors.append({
                                "event": event_type,
                                "stage_id": event.get("Stage ID"),
                                "task_id": event.get("Task ID"),
                                "reason": str(reason)[:200],
                            })
                    elif event_type == "SparkListenerJobEnd":
                        job_result = event.get("Job Result", {})
                        if job_result.get("Job Result", {}).get("Failure", ""):
                            errors.append({
                                "event": event_type,
                                "job_id": event.get("Job ID"),
                                "reason": str(job_result)[:200],
                            })
                    elif event_type == "SparkListenerStageCompleted":
                        stage_info = event.get("Stage Info", {})
                        if stage_info.get("Failure Reason", ""):
                            errors.append({
                                "event": event_type,
                                "stage_id": stage_info.get("Stage ID"),
                                "reason": stage_info.get("Failure Reason")[:200],
                            })

            except json.JSONDecodeError:
                continue

        return errors


__all__ = ["SparkHistTool"]