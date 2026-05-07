"""
LogStoreTool - 日志存储工具

存储日志到本地目录，保留 7 天，自动清理
"""

import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, Optional
import yaml


class LogStoreTool:
    """
    日志存储工具

    目录结构:
    logs/alerts/
    ├── 2026-05-07/
    │   ├── workflow_code/
    │   │   ├── task_code/
    │   │   │   ├── driver.log
    │   │   │   ├── spark.log
    │   │   │   ├── yarn.log (或 k8s/)
    │   │   │   └── metadata.yaml
    """

    DEFAULT_BASE_PATH = "logs/alerts"
    DEFAULT_RETENTION_DAYS = 7

    def __init__(self, base_path: str = DEFAULT_BASE_PATH, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.base_path = base_path
        self.retention_days = retention_days

    def store_logs(
        self,
        workflow_code: str,
        task_code: str,
        driver_logs: str,
        spark_logs: str,
        yarn_logs: Optional[str] = None,
        k8s_logs: Optional[Dict[str, str]] = None,
        spark_mode: str = "yarn",
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        存储日志

        Args:
            workflow_code: 工作流编码
            task_code: 任务编码
            driver_logs: Driver 日志
            spark_logs: Spark History 日志
            yarn_logs: YARN 日志 (Spark on YARN)
            k8s_logs: K8s Pod 日志 (Spark on K8s)
            spark_mode: yarn 或 k8s
            metadata: 元数据

        Returns:
            存储路径
        """
        date_path = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")

        store_path = os.path.join(self.base_path, date_path, workflow_code, task_code)
        os.makedirs(store_path, exist_ok=True)

        # 存储基础日志
        files = {
            "driver.log": driver_logs,
            "spark.log": spark_logs,
        }

        # 根据 Spark 模式存储不同来源日志
        if spark_mode == "yarn" and yarn_logs:
            files["yarn.log"] = yarn_logs
        elif spark_mode == "k8s" and k8s_logs:
            k8s_dir = os.path.join(store_path, "k8s")
            os.makedirs(k8s_dir, exist_ok=True)
            for pod_name, logs in k8s_logs.items():
                files[f"k8s/{pod_name}.log"] = logs

        # 写入文件
        for filename, content in files.items():
            file_path = os.path.join(store_path, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content if content else "")

        # 存储元数据
        sources = ["dsctl", "spark-history"]
        if spark_mode == "yarn":
            sources.append("yarn-gateway")
        else:
            sources.append("k8s-api")

        meta = metadata or {}
        meta.update({
            "workflow_code": workflow_code,
            "task_code": task_code,
            "timestamp": timestamp,
            "spark_mode": spark_mode,
            "sources": sources,
        })

        with open(os.path.join(store_path, "metadata.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(meta, f)

        return store_path

    def cleanup_old_logs(self) -> int:
        """
        删除超过保留期的日志

        Returns:
            删除的目录数量
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_path = cutoff_date.strftime("%Y-%m-%d")
        deleted_count = 0

        if not os.path.exists(self.base_path):
            return 0

        for date_dir in os.listdir(self.base_path):
            if date_dir < cutoff_path:
                dir_path = os.path.join(self.base_path, date_dir)
                if os.path.isdir(dir_path):
                    shutil.rmtree(dir_path)
                    deleted_count += 1

        return deleted_count

    def get_log_path(self, workflow_code: str, task_code: str) -> Optional[str]:
        """
        查找最新日志路径

        Args:
            workflow_code: 工作流编码
            task_code: 任务编码

        Returns:
            日志路径或 None
        """
        if not os.path.exists(self.base_path):
            return None

        for date_dir in sorted(os.listdir(self.base_path), reverse=True):
            potential_path = os.path.join(self.base_path, date_dir, workflow_code, task_code)
            if os.path.exists(potential_path):
                return potential_path

        return None

    def log_cleanup_result(self, deleted_count: int) -> None:
        """记录清理结果"""
        cleanup_log_path = os.path.join(self.base_path, "..", "cleanup.log")
        with open(cleanup_log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}: 删除了 {deleted_count} 个日期目录\n")


__all__ = ["LogStoreTool"]