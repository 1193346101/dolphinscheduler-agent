"""
Query Workflow Node - 查询项目工作流列表
"""

import os
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config.projects import projects_registry
from ...config import settings


def query_workflow_node(state: ChatState) -> ChatState:
    """
    查询项目下的工作流列表

    Args:
        state: ChatState with project_name populated

    Returns:
        Updated ChatState with workflow list
    """
    project_name = state.get("project_name", "")

    if not project_name:
        return {
            **state,
            "error_message": "请提供项目名称",
            "response_content": "请提供项目名称，例如：查询项目 ad_monitor 下有哪些工作流",
        }

    # 查找项目配置
    project_config = projects_registry.get_by_name(project_name)
    if not project_config:
        # 尝试作为 project_code 使用
        try:
            project_code = int(project_name)
        except ValueError:
            return {
                **state,
                "error_message": f"未找到项目: {project_name}",
                "response_content": f"未找到项目 **{project_name}**，请确认项目名称是否正确",
            }
    else:
        project_code = project_config.code

    # 调用 dsctl 查询工作流列表（显式传递配置）
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )
    result = client.list_workflows(project_code)

    if not result.success:
        # 检查是否是配置错误
        import json
        try:
            error_data = json.loads(result.stdout)
            if error_data.get("error"):
                error_msg = error_data["error"].get("message", result.stderr)
                return {
                    **state,
                    "error_message": error_msg,
                    "response_content": f"查询失败: {error_msg}",
                }
        except json.JSONDecodeError:
            pass

        return {
            **state,
            "error_message": result.stderr or "查询失败",
            "response_content": f"查询工作流失败: {result.stderr or '未知错误'}",
        }

    # 解析结果
    import json
    try:
        data = json.loads(result.stdout)
        # dsctl 返回格式：{"data": [...]} 或直接列表
        if isinstance(data, dict):
            inner_data = data.get("data", [])
            # inner_data 可能是列表或字典
            if isinstance(inner_data, dict):
                workflows = inner_data.get("workflows", inner_data.get("list", []))
            elif isinstance(inner_data, list):
                workflows = inner_data
            else:
                workflows = []
        elif isinstance(data, list):
            workflows = data
        else:
            workflows = []
    except json.JSONDecodeError:
        workflows = []

    # 处理可能的格式
    if isinstance(workflows, str):
        workflows = [workflows]

    # 格式化响应
    if not workflows:
        response = f"项目 **{project_name}** 下暂无工作流"
    else:
        workflow_list = []
        for wf in workflows:
            if isinstance(wf, dict):
                name = wf.get("name", "未命名")
                code = str(wf.get("code", ""))
                release_state = wf.get("releaseState", "OFFLINE")

                # 状态说明
                state_desc = {
                    "ONLINE": "已发布（可运行）",
                    "OFFLINE": "未发布（不可运行）",
                    "SCHEDULE": "已调度",
                }.get(release_state, release_state)

                workflow_list.append(f"- **{name}**\n  编码: `{code}`\n  状态: {state_desc}")
            else:
                workflow_list.append(f"- {wf}")

        response = f"### 项目 {project_name} 工作流列表\n\n共 **{len(workflows)}** 个工作流:\n\n" + "\n".join(workflow_list)

    return {
        **state,
        "result_data": {"workflows": workflows, "count": len(workflows)},
        "response_content": response,
    }


__all__ = ["query_workflow_node"]