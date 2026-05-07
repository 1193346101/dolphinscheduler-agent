"""
validate_project 节点

验证项目是否存在且 token 有效
"""

from typing import Dict, Any
from ..state import AgentState
from ...config.projects import projects_registry


def validate_project(state: AgentState) -> AgentState:
    """
    验证项目配置

    检查:
    - 项目编码是否存在
    - 返回项目配置

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (project_valid, project_config)
    """
    project_code = state["project_code"]

    # 尝试转换为 int
    try:
        code_int = int(project_code)
    except ValueError:
        return {
            **state,
            "project_valid": False,
            "project_config": None,
        }

    # 查找项目配置
    config = projects_registry.get_by_code(code_int)

    if config:
        # 转换为字典格式
        config_dict = {
            "name": config.name,
            "code": config.code,
            "ds_api_url": config.ds_api_url,
            "ds_api_token": config.ds_api_token,
            "ds_version": config.ds_version,
            "spark_mode": config.effective_spark_mode,
            "spark_history_url": config.effective_spark_history_url,
            "yarn_gateway_url": config.effective_yarn_gateway_url,
            "dingtalk": None,
        }

        if config.dingtalk:
            config_dict["dingtalk"] = {
                "robot_code": config.dingtalk.robot_code,
                "client_id": config.dingtalk.client_id,
                "client_secret": config.dingtalk.client_secret,
                "notify_users": config.dingtalk.notify_users,
            }

        return {
            **state,
            "project_valid": True,
            "project_config": config_dict,
        }

    return {
        **state,
        "project_valid": False,
        "project_config": None,
    }


__all__ = ["validate_project"]