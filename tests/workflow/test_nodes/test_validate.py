"""
validate_project 节点测试
"""

import pytest
from src.workflow.state import create_initial_state
from src.workflow.nodes.validate import validate_project
from src.config.projects import projects_registry, ProjectConfig, DingTalkConfig


def test_validate_project_valid():
    """测试有效项目"""
    # 先注册一个测试项目
    test_config = ProjectConfig(
        name="test_project",
        code=123456,
        ds_api_url="http://test:12345/dolphinscheduler",
        ds_api_token="test_token",
    )
    projects_registry.register(test_config)

    state = create_initial_state(
        alert_raw={},
        project_code="123456",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = validate_project(state)

    assert result["project_valid"] is True
    assert result["project_config"] is not None
    assert result["project_config"]["name"] == "test_project"


def test_validate_project_invalid_code():
    """测试无效项目编码"""
    state = create_initial_state(
        alert_raw={},
        project_code="999999",  # 不存在的编码
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = validate_project(state)

    assert result["project_valid"] is False
    assert result["project_config"] is None


def test_validate_project_non_numeric_code():
    """测试非数字项目编码"""
    state = create_initial_state(
        alert_raw={},
        project_code="invalid",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = validate_project(state)

    assert result["project_valid"] is False
    assert result["project_config"] is None


def test_validate_project_with_dingtalk_config():
    """测试项目包含钉钉配置"""
    dingtalk = DingTalkConfig(
        robot_code="test_robot",
        client_id="test_client_id",
        client_secret="test_secret",
        notify_users=["user1", "user2"],
    )

    test_config = ProjectConfig(
        name="test_project_dingtalk",
        code=789012,
        ds_api_url="http://test:12345/dolphinscheduler",
        ds_api_token="test_token",
        dingtalk=dingtalk,
    )
    projects_registry.register(test_config)

    state = create_initial_state(
        alert_raw={},
        project_code="789012",
        workflow_code="",
        task_code="",
        task_type="SHELL",
        error_time="",
    )

    result = validate_project(state)

    assert result["project_valid"] is True
    assert result["project_config"]["dingtalk"] is not None
    assert result["project_config"]["dingtalk"]["robot_code"] == "test_robot"
    assert result["project_config"]["dingtalk"]["notify_users"] == ["user1", "user2"]