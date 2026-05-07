"""
analyze_error 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.analyze import analyze_error


class TestAnalyzeError:

    def test_analyze_spark_task_with_skill(self):
        """测试 Spark 任务 Skill 分析"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["driver_logs"] = "java.lang.OutOfMemoryError: Java heap space"
        state["spark_logs"] = None
        state["project_config"] = {}

        result = analyze_error(state)

        assert "oom_executor" in result.get("error_patterns", []) or result.get("error_category") == "RESOURCE"

    def test_analyze_shell_task(self):
        """测试 Shell 任务分析"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SHELL",
        })
        state["task_type"] = "SHELL"
        state["driver_logs"] = "Error: command not found"
        state["project_config"] = {}

        result = analyze_error(state)

        assert result["error_category"] != ""

    def test_analyze_no_logs(self):
        """测试无日志时的分析"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["driver_logs"] = None
        state["spark_logs"] = None

        result = analyze_error(state)

        assert result["confidence_score"] == 0.0