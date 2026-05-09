"""
validate_project node

Verify project exists and token is valid
"""

from typing import Dict, Any
from ..state import AgentState
from ...config.projects import projects_registry, ProjectConfig, SparkLogConfig
from ...config import settings


def validate_project(state: AgentState) -> AgentState:
    """
    Validate project config
    """
    print("\n" + "="*50)
    print("[2/10] validate_project - Validate project")
    print("="*50)

    project_code = state["project_code"]
    print(f"  >> Checking project code: {project_code}")

    # Try to convert to int
    try:
        code_int = int(project_code)
    except ValueError:
        print("[FAIL] Invalid project code format")
        return {
            **state,
            "project_valid": False,
            "project_config": None,
        }

    # Find project config
    config = projects_registry.get_by_code(code_int)

    # If project config not found, use global default config
    if not config:
        print(f"  >> Project {code_int} not configured, using global default")
        if settings.DS_API_URL and settings.DS_API_TOKEN:
            # Create default config
            config = ProjectConfig(
                name=f"project_{code_int}",
                code=code_int,
                ds_api_url=settings.DS_API_URL,
                ds_api_token=settings.DS_API_TOKEN,
                ds_version=settings.DS_VERSION,
                spark_log=SparkLogConfig(
                    mode="yarn",
                    history_url=settings.SPARK_HISTORY_URL,
                ),
            )
            print(f"  >> Using default DS API: {settings.DS_API_URL}")
        else:
            print("[FAIL] No project config and global DS API URL/Token not set")
            return {
                **state,
                "project_valid": False,
                "project_config": None,
            }

    if config:
        print(f"  >> Project name: {config.name}")
        print(f"  >> DS API: {config.ds_api_url}")

        print("[OK] Project validation passed")
        # Convert to dict format
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

    print("[FAIL] Project not configured, skip processing")
    return {
        **state,
        "project_valid": False,
        "project_config": None,
    }


__all__ = ["validate_project"]