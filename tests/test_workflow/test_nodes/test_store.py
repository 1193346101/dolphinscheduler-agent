"""
store_results 节点测试
"""

import pytest
import tempfile
import os
from src.workflow.state import create_initial_state
from src.workflow.nodes.store import store_results


class TestStoreResults:

    def test_store_logs_success(self):
        """测试存储日志成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })
            state["workflow_code"] = "456"
            state["task_code"] = "789"
            state["driver_logs"] = "driver log"
            state["spark_logs"] = "spark log"
            state["yarn_logs"] = "yarn log"
            state["error_category"] = "RESOURCE"
            state["risk_level"] = "LOW"
            state["project_config"] = {"spark_mode": "yarn"}

            result = store_results(state, base_path=tmpdir)

            assert result["log_stored"] is True
            assert result["log_store_path"] is not None

    def test_store_logs_no_logs(self):
        """测试无日志时不存储"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["driver_logs"] = None
        state["spark_logs"] = None

        result = store_results(state)

        assert result["log_stored"] is False

    def test_store_logs_k8s_mode(self):
        """测试 K8s 模式存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })
            state["workflow_code"] = "456"
            state["task_code"] = "789"
            state["driver_logs"] = "driver log"
            state["spark_logs"] = "spark log"
            state["k8s_logs"] = {"pod-1": "pod log"}
            state["project_config"] = {"spark_mode": "k8s"}

            result = store_results(state, base_path=tmpdir)

            assert result["log_stored"] is True