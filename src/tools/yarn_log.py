"""
YARNLogTool - YARN Gateway 日志获取工具

通过 Knox Gateway 代理 YARN ResourceManager API 获取应用信息
"""

import requests
from typing import Dict, Optional, List, Any
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

        # 初始化安全模块
        from ..security import CommandGuard, AuditLogger
        self.guard = CommandGuard()
        self.audit = AuditLogger()

    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取 YARN 应用信息（增加安全检查）

        Args:
            application_id: YARN 应用 ID

        Returns:
            应用信息字典 {"app_name", "state", "diagnostics", ...}
        """
        url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"

        # 安全检查
        guard_result = self.guard.check_http_request("GET", url)

        if guard_result.blocked:
            self.audit.log_blocked(
                operation_type="http",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            return {"error": guard_result.reason}

        try:
            # 获取应用详情
            response = requests.get(
                url,
                auth=self.auth,
                timeout=15,
                verify=False  # Knox 可能使用自签名证书
            )

            if response.status_code != 200:
                self.audit.log_failed(
                    operation_type="http",
                    operation_detail=f"GET {url}",
                    error=f"HTTP {response.status_code}",
                )
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

            # 记录审计
            self.audit.log_success(
                operation_type="http",
                operation_detail=f"GET {url}",
                risk_level="LOW",
            )

            return logs

        except requests.RequestException as e:
            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=str(e),
            )
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

    # ============ Executor 日志获取（深度分析） ============

    def get_containers(self, application_id: str) -> list:
        """
        获取应用的所有 Container ID

        API: /ws/v1/cluster/apps/{app_id}/containers

        Args:
            application_id: YARN 应用 ID

        Returns:
            Container ID 列表
        """
        url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}/containers"

        # 安全检查
        guard_result = self.guard.check_http_request("GET", url)

        if guard_result.blocked:
            self.audit.log_blocked(
                operation_type="http",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            return []

        try:
            response = requests.get(
                url,
                auth=self.auth,
                timeout=15,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                containers = data.get("containers", {}).get("container", [])
                return [c.get("id") for c in containers]

            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=f"HTTP {response.status_code}",
            )
            return []

        except requests.RequestException as e:
            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=str(e),
            )
            return []

    def fetch_container_log(
        self,
        application_id: str,
        container_id: str,
        max_length: int = 5000
    ) -> str:
        """
        获取特定 Container 的日志

        API: /ws/v1/cluster/apps/{app_id}/containers/{container_id}/logs

        Args:
            application_id: YARN 应用 ID
            container_id: Container ID
            max_length: 最大返回长度（避免日志过大）

        Returns:
            日志内容（截取前 max_length 字符）
        """
        url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}/containers/{container_id}/logs"

        # 安全检查
        guard_result = self.guard.check_http_request("GET", url)

        if guard_result.blocked:
            self.audit.log_blocked(
                operation_type="http",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            return ""

        try:
            response = requests.get(
                url,
                auth=self.auth,
                timeout=30,
                verify=False
            )

            if response.status_code == 200:
                log_content = response.text
                # 截取避免过大
                return log_content[:max_length]

            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=f"HTTP {response.status_code}",
            )
            return ""

        except requests.RequestException as e:
            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=str(e),
            )
            return ""

    def fetch_executor_logs(
        self,
        application_id: str,
        max_executors: int = 3,
        max_length_per_executor: int = 5000
    ) -> Dict[str, str]:
        """
        获取所有 Executor 日志（限制数量避免过大）

        流程:
        1. 获取 Container 列表
        2. 过滤 Executor（container_seq > 1）
        3. 获取每个 Executor 日志

        Container ID 格式:
        container_e01_{cluster_timestamp}_{app_seq}_{attempt_seq}_{container_seq}
        - container_seq = 1: Driver
        - container_seq > 1: Executor

        Args:
            application_id: YARN 应用 ID
            max_executors: 最大获取 Executor 数量（默认 3）
            max_length_per_executor: 每个 Executor 日志最大长度

        Returns:
            {container_id: log_content}
        """
        containers = self.get_containers(application_id)
        executor_logs = {}

        for container_id in containers:
            # 解析 Container 序号
            parts = container_id.split("_")
            if len(parts) >= 1:
                try:
                    seq = int(parts[-1])
                    # Container 序号 > 1 的通常是 Executor
                    if seq > 1:
                        log = self.fetch_container_log(
                            application_id,
                            container_id,
                            max_length_per_executor
                        )
                        if log:
                            executor_logs[container_id] = log

                            # 限制数量
                            if len(executor_logs) >= max_executors:
                                break
                except ValueError:
                    # 无法解析序号，跳过
                    continue

        # 记录审计
        if executor_logs:
            self.audit.log_success(
                operation_type="http",
                operation_detail=f"fetch_executor_logs for {application_id}",
                risk_level="LOW",
            )

        return executor_logs

    def get_container_info(self, application_id: str, container_id: str) -> Dict:
        """
        获取特定 Container 的详细信息

        API: /ws/v1/cluster/apps/{app_id}/containers/{container_id}

        Args:
            application_id: YARN 应用 ID
            container_id: Container ID

        Returns:
            Container 信息 {
                id, state, exit_status, allocated_memory_mb,
                allocated_vcores, assigned_node, started_time, finished_time
            }
        """
        url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}/containers/{container_id}"

        # 安全检查
        guard_result = self.guard.check_http_request("GET", url)

        if guard_result.blocked:
            self.audit.log_blocked(
                operation_type="http",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            return {"error": guard_result.reason}

        try:
            response = requests.get(
                url,
                auth=self.auth,
                timeout=15,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                container = data.get("container", {})

                result = {
                    "id": container.get("id", ""),
                    "state": container.get("state", ""),
                    "exit_status": container.get("exitStatus", -1),
                    "allocated_memory_mb": container.get("allocatedMB", 0),
                    "allocated_vcores": container.get("allocatedVCores", 0),
                    "assigned_node": container.get("assignedNodeId", ""),
                    "started_time": container.get("startedTime", 0),
                    "finished_time": container.get("finishedTime", 0),
                    "node_http_address": container.get("nodeHttpAddress", ""),
                }

                self.audit.log_success(
                    operation_type="http",
                    operation_detail=f"GET {url}",
                    risk_level="LOW",
                )

                return result

            return {"error": f"HTTP {response.status_code}"}

        except requests.RequestException as e:
            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=str(e),
            )
            return {"error": str(e)}

    # ============ Executor 日志智能提取（增强版） ============

    def _fetch_full_container_log(
        self,
        application_id: str,
        container_id: str,
        max_length: int = 100000
    ) -> str:
        """
        获取完整 Container 日志（内部方法，支持更大数据量）

        Args:
            application_id: YARN 应用 ID
            container_id: Container ID
            max_length: 最大返回长度（默认 100KB）

        Returns:
            日志内容
        """
        url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}/containers/{container_id}/logs"

        guard_result = self.guard.check_http_request("GET", url)

        if guard_result.blocked:
            self.audit.log_blocked(
                operation_type="http",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            return ""

        try:
            response = requests.get(
                url,
                auth=self.auth,
                timeout=60,  # 增加超时时间
                verify=False
            )

            if response.status_code == 200:
                log_content = response.text
                return log_content[:max_length]

            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=f"HTTP {response.status_code}",
            )
            return ""

        except requests.RequestException as e:
            self.audit.log_failed(
                operation_type="http",
                operation_detail=f"GET {url}",
                error=str(e),
            )
            return ""

    def smart_extract_container_log(
        self,
        application_id: str,
        container_id: str,
        extract_strategy: str = "smart",
        task_type: str = "SPARK"
    ) -> Dict[str, Any]:
        """
        智能提取 Container 日志

        替代固定截取，使用 pattern 匹配提取关键信息，避免遗漏尾部错误。

        Args:
            application_id: YARN 应用 ID
            container_id: Container ID
            extract_strategy: 提取策略
                - "smart": ERROR块 + 配置行 + Executor事件 + 首尾摘要
                - "head_tail": 首2000 + 尾3000
                - "errors_only": 只提取错误块
                - "full": 完整日志（限100KB）
            task_type: 任务类型（默认 SPARK）
                - SPARK: Spark Executor 日志
                - FLINK: Flink TaskManager 日志
                - DATAX: DataX Worker 日志

        Returns:
            {
                "container_id": container_id,
                "raw_content": 完整日志（限100KB）,
                "error_blocks": 错误块列表,
                "config_lines": 任务配置行（根据 task_type 提取）,
                "executor_events": Executor生命周期事件,
                "summary": {"head": ..., "tail": ...},
                "extract_stats": {"total_length": ..., "error_block_count": ...}
            }
        """
        # 1. 获取完整日志（限制 100KB）
        full_log = self._fetch_full_container_log(application_id, container_id, max_length=100000)

        if not full_log:
            return {
                "container_id": container_id,
                "error": "无法获取日志",
                "raw_content": "",
            }

        result = {
            "container_id": container_id,
            "raw_content": full_log,
            "extract_stats": {
                "total_length": len(full_log),
                "strategy": extract_strategy,
            }
        }

        # 2. 根据策略提取
        if extract_strategy == "smart":
            # 智能提取：复用 preprocess_log.py 函数
            try:
                from ..skills.common.preprocess_log import (
                    extract_error_blocks,
                    extract_config_lines,
                    extract_executor_events,
                )

                result["error_blocks"] = extract_error_blocks(full_log)
                result["config_lines"] = extract_config_lines(full_log, task_type)
                result["executor_events"] = extract_executor_events(full_log)

                # Fallback: 如果无错误块，使用首尾截取
                if not result["error_blocks"]:
                    result["summary"] = {
                        "head": full_log[:2000],
                        "tail": full_log[-3000:] if len(full_log) > 5000 else ""
                    }
                else:
                    # 有错误块时，保留少量头部作为上下文
                    result["summary"] = {
                        "head": full_log[:500],
                        "tail": ""
                    }

                result["extract_stats"]["error_block_count"] = len(result["error_blocks"])
                result["extract_stats"]["config_line_count"] = len(result.get("config_lines", []))

            except ImportError:
                # 如果导入失败，使用首尾截取
                result["summary"] = {
                    "head": full_log[:2000],
                    "tail": full_log[-3000:] if len(full_log) > 5000 else ""
                }
                result["error_blocks"] = []
                result["extract_stats"]["fallback"] = "preprocess_log import failed"

        elif extract_strategy == "head_tail":
            result["summary"] = {
                "head": full_log[:2000],
                "tail": full_log[-3000:] if len(full_log) > 5000 else ""
            }

        elif extract_strategy == "errors_only":
            try:
                from ..skills.common.preprocess_log import extract_error_blocks
                result["error_blocks"] = extract_error_blocks(full_log)
                result["extract_stats"]["error_block_count"] = len(result["error_blocks"])
            except ImportError:
                result["error_blocks"] = []

        elif extract_strategy == "full":
            # 完整日志，不做提取
            pass

        # 记录审计
        self.audit.log_success(
            operation_type="http",
            operation_detail=f"smart_extract_container_log for {container_id}",
            risk_level="LOW",
        )

        return result

    def fetch_executor_logs_smart(
        self,
        application_id: str,
        max_executors: int = 3,
        extract_strategy: str = "smart"
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取 Executor 日志（智能提取）

        替代 fetch_executor_logs，支持智能提取策略。

        Args:
            application_id: YARN 应用 ID
            max_executors: 最大获取 Executor 数量
            extract_strategy: 提取策略 ("smart", "head_tail", "errors_only")

        Returns:
            {container_id: {"error_blocks": [], "config_lines": [], ...}}
        """
        containers = self.get_containers(application_id)
        executor_logs = {}

        for container_id in containers:
            # 解析 Container 序号
            parts = container_id.split("_")
            if len(parts) >= 1:
                try:
                    seq = int(parts[-1])
                    # Container 序号 > 1 的通常是 Executor
                    if seq > 1:
                        log_data = self.smart_extract_container_log(
                            application_id,
                            container_id,
                            extract_strategy
                        )
                        if log_data and not log_data.get("error"):
                            executor_logs[container_id] = log_data

                            # 限制数量
                            if len(executor_logs) >= max_executors:
                                break
                except ValueError:
                    # 无法解析序号，跳过
                    continue

        return executor_logs


__all__ = ["YARNLogTool"]