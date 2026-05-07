"""
LogStoreTool 测试
"""

import os
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from src.tools.log_store import LogStoreTool


class TestLogStoreTool:

    def test_store_logs_yarn_mode(self):
        """测试存储日志 - YARN 模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)

            result = tool.store_logs(
                workflow_code="123456",
                task_code="789012",
                driver_logs="driver log content",
                spark_logs="spark log content",
                yarn_logs="yarn log content",
                spark_mode="yarn",
            )

            assert os.path.exists(result)
            assert os.path.exists(os.path.join(result, "driver.log"))
            assert os.path.exists(os.path.join(result, "spark.log"))
            assert os.path.exists(os.path.join(result, "yarn.log"))
            assert os.path.exists(os.path.join(result, "metadata.yaml"))

    def test_store_logs_k8s_mode(self):
        """测试存储日志 - K8s 模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)

            result = tool.store_logs(
                workflow_code="123456",
                task_code="789012",
                driver_logs="driver log content",
                spark_logs="spark log content",
                k8s_logs={"driver_pod": "pod log", "executor_1": "executor log"},
                spark_mode="k8s",
            )

            assert os.path.exists(result)
            assert os.path.exists(os.path.join(result, "k8s", "driver_pod.log"))
            assert os.path.exists(os.path.join(result, "k8s", "executor_1.log"))
            assert not os.path.exists(os.path.join(result, "yarn.log"))

    def test_store_logs_creates_directory_structure(self):
        """测试创建目录结构"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)

            result = tool.store_logs(
                workflow_code="wf1",
                task_code="task1",
                driver_logs="log",
                spark_logs="log",
            )

            # 验证日期目录存在
            date_path = datetime.now().strftime("%Y-%m-%d")
            assert os.path.exists(os.path.join(tmpdir, date_path))
            assert os.path.exists(os.path.join(tmpdir, date_path, "wf1"))
            assert os.path.exists(os.path.join(tmpdir, date_path, "wf1", "task1"))

    def test_cleanup_old_logs(self):
        """测试清理过期日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir, retention_days=7)

            # 创建过期目录
            old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            old_path = os.path.join(tmpdir, old_date, "wf1", "task1")
            os.makedirs(old_path)
            with open(os.path.join(old_path, "driver.log"), "w") as f:
                f.write("old log")

            # 创建新目录
            new_date = datetime.now().strftime("%Y-%m-%d")
            new_path = os.path.join(tmpdir, new_date, "wf2", "task2")
            os.makedirs(new_path)
            with open(os.path.join(new_path, "driver.log"), "w") as f:
                f.write("new log")

            deleted = tool.cleanup_old_logs()

            assert deleted == 1
            assert not os.path.exists(os.path.join(tmpdir, old_date))
            assert os.path.exists(os.path.join(tmpdir, new_date))

    def test_get_log_path_returns_latest(self):
        """测试获取最新日志路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)

            # 创建多个日期目录
            for i in range(3):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                path = os.path.join(tmpdir, date, "wf1", "task1")
                os.makedirs(path)
                with open(os.path.join(path, "driver.log"), "w") as f:
                    f.write(f"day {i}")

            result = tool.get_log_path("wf1", "task1")

            # 返回今天的路径（最新的）
            today = datetime.now().strftime("%Y-%m-%d")
            assert result == os.path.join(tmpdir, today, "wf1", "task1")

    def test_get_log_path_not_found(self):
        """测试未找到日志路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)

            result = tool.get_log_path("nonexistent", "task")

            assert result is None