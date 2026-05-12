"""
Query Workflow Node - 查询项目工作流列表

重构版：使用全局 Token，通过项目名自动查找项目 code
"""

import json
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient, project_resolver
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

    # 通过项目名查找项目 code（使用全局 Token）
    project_code, resolved_name = project_resolver.resolve(project_name)

    if not project_code:
        return {
            **state,
            "error_message": f"未找到项目: {project_name}",
            "response_content": f"未找到项目 **{project_name}**，请确认项目名称是否正确",
        }

    # 使用解析后的项目名（如果有）
    display_name = resolved_name or project_name

    # 调用 dsctl 查询工作流列表（使用全局配置）
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
        response = f"项目 **{display_name}** 下暂无工作流"
    else:
        workflow_list = []
        for wf in workflows:
            if isinstance(wf, dict):
                name = wf.get("name", "未命名")
                code = str(wf.get("code", ""))
                release_state = wf.get("releaseState", "OFFLINE")

                # 状态图标
                state_icon = {
                    "ONLINE": "✅",
                    "OFFLINE": "⬇️",
                    "SCHEDULE": "🕐",
                }.get(release_state, "❓")

                workflow_list.append(f"{name} 项目编码: {code} {state_icon}")
            else:
                workflow_list.append(f"{wf}")

        response = f"### {display_name} 工作流列表\n\n共 {len(workflows)} 个\n\n" + "\n".join(workflow_list)

    return {
        **state,
        "result_data": {"workflows": workflows, "count": len(workflows), "project_code": project_code},
        "response_content": response,
        "project_name": display_name,
    }


__all__ = ["query_workflow_node"]