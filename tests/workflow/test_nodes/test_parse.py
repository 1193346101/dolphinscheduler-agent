"""
parse_alert 节点测试
"""

import pytest
from src.workflow.state import create_initial_state, AgentState
from src.workflow.nodes.parse import parse_alert


def test_parse_alert_extract_project_code():
    """测试提取项目编码"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SPARK",
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["project_code"] == "11598158952448"


def test_parse_alert_extract_workflow_code():
    """测试提取工作流编码"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SPARK",
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["workflow_code"] == "21451302002208"


def test_parse_alert_extract_task_code():
    """测试提取任务编码"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SPARK",
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["task_code"] == "123456789"


def test_parse_alert_extract_task_type():
    """测试提取任务类型"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SPARK",
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["task_type"] == "SPARK"


def test_parse_alert_normalize_task_type():
    """测试任务类型规范化"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "spark",  # 小写
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["task_type"] == "SPARK"


def test_parse_alert_default_unknown_task_type():
    """测试未知任务类型默认为 SHELL"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SQL",  # 不在预定义类型中
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["task_type"] == "SHELL"


def test_parse_alert_extract_error_time():
    """测试提取错误时间"""
    state = create_initial_state(
        alert_raw={
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456789,
            "taskType": "SPARK",
            "endTime": "2025-05-07 14:30:00",
        },
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["error_time"] == "2025-05-07 14:30:00"


def test_parse_alert_missing_fields():
    """测试缺失字段使用默认值"""
    state = create_initial_state(
        alert_raw={},  # 空数据
        project_code="",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = parse_alert(state)

    assert result["project_code"] == "0"
    assert result["workflow_code"] == "0"
    assert result["task_code"] == "0"
    assert result["task_type"] == "SHELL"
    assert result["error_time"] == ""