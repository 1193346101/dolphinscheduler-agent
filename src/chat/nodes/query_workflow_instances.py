"""
Query Workflow Instances Node - 查询工作流实例列表（运行记录）

重构版：使用全局 Token，通过项目名自动查找项目 code
"""

import json
from datetime import datetime, date, timedelta
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient, project_resolver
from ...config import settings


def query_workflow_instances_node(state: ChatState) -> ChatState:
    """
    查询工作流实例列表（今天的运行记录）

    Args:
        state: ChatState with project_name populated

    Returns:
        Updated ChatState with workflow instance list
    """
    project_name = state.get("project_name", "")
    query_date = state.get("query_date")  # 可选，默认今天

    if not project_name:
        return {
            **state,
            "error_message": "请提供项目名称",
            "response_content": "请提供项目名称，例如：ad_monitor 下今天有哪些工作流实例",
        }

    # 通过项目名查找项目 code（使用全局 Token）
    project_code, resolved_name = project_resolver.resolve(project_name)

    if not project_code:
        return {
            **state,
            "error_message": f"未找到项目: {project_name}",
            "response_content": f"未找到项目 **{project_name}**，请确认项目名称是否正确",
        }

    # 使用解析后的项目名
    display_name = resolved_name or project_name

    # 计算时间范围（默认今天）
    today = date.today()

    # 处理 query_date（可能是"今天"、"昨天"或日期格式）
    if not query_date or query_date in ["今天", "今日"]:
        query_date = today.strftime("%Y-%m-%d")
    elif query_date in ["昨天", "昨日"]:
        yesterday = today - timedelta(days=1)
        query_date = yesterday.strftime("%Y-%m-%d")

    start_time = f"{query_date} 00:00:00"
    end_time = f"{query_date} 23:59:59"

    # 调用 dsctl
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 1. 先获取工作流定义列表（建立 code -> name 映射）
    workflows_result = client.list_workflows(project_code)
    workflow_name_map = {}

    if workflows_result.success:
        wf_data = json.loads(workflows_result.stdout)
        if isinstance(wf_data, dict):
            wf_list = wf_data.get("data", [])
            if isinstance(wf_list, dict):
                wf_list = wf_list.get("workflows", wf_list.get("list", []))
        elif isinstance(wf_data, list):
            wf_list = wf_data
        else:
            wf_list = []

        for wf in wf_list:
            if isinstance(wf, dict):
                code = wf.get("code")
                name = wf.get("name", "未命名")
                workflow_name_map[code] = name

    # 2. 查询项目所有实例
    all_instances = []
    try:
        instances_result = client.list_workflow_instances(
            project_code=project_code,
            page_size=100,
            start_time=start_time,
            end_time=end_time,
        )

        if instances_result.success:
            instances_data = json.loads(instances_result.stdout)
            if isinstance(instances_data, dict):
                instance_list = instances_data.get("data", {}).get("totalList", [])
            elif isinstance(instances_data, list):
                instance_list = instances_data
            else:
                instance_list = []

            for inst in instance_list:
                if isinstance(inst, dict):
                    # 使用 workflowDefinitionCode 查工作流名称
                    wf_code = inst.get("workflowDefinitionCode")
                    wf_name = workflow_name_map.get(wf_code, inst.get("name", "未命名"))
                    all_instances.append({
                        "workflow_name": wf_name,
                        "workflow_code": wf_code,
                        "instance_id": inst.get("id"),
                        "state": inst.get("state", "UNKNOWN"),
                        "start_time": inst.get("startTime", ""),
                        "end_time": inst.get("endTime", ""),
                    })
    except Exception as e:
        return {
            **state,
            "error_message": str(e),
            "response_content": f"查询实例失败: {e}",
        }

    # 按开始时间排序（最新的在前）
    all_instances.sort(key=lambda x: x.get("start_time", ""), reverse=True)

    # 格式化响应
    if not all_instances:
        response = f"**{display_name}** {query_date} 无运行实例"
    else:
        # 统计各状态数量
        success_count = sum(1 for i in all_instances if i["state"] == "SUCCESS")
        failure_count = sum(1 for i in all_instances if i["state"] == "FAILURE")
        running_count = sum(1 for i in all_instances if i["state"] == "RUNNING")

        # 构建响应内容（钉钉 Markdown 格式）
        lines = []
        lines.append(f"## {display_name}")
        lines.append(f"**日期**: {query_date}")
        lines.append("")
        lines.append(f"**成功**: {success_count} | **失败**: {failure_count} | **运行中**: {running_count}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for inst in all_instances[:50]:
            wf_name = inst["workflow_name"]
            inst_id = inst["instance_id"]
            start = inst["start_time"]
            end = inst["end_time"] or "运行中"

            # 状态图标
            state_icon = {"SUCCESS": "成功", "FAILURE": "失败", "RUNNING": "运行中"}.get(inst["state"], inst["state"])

            lines.append(f"- **{wf_name}**")
            lines.append(f"  - 实例: `{inst_id}`")
            lines.append(f"  - 状态: {state_icon}")
            lines.append(f"  - 开始: {start}")
            lines.append(f"  - 结束: {end}")
            lines.append("")

        response = "\n".join(lines)

    return {
        **state,
        "result_data": {"instances": all_instances, "count": len(all_instances), "project_code": project_code},
        "response_content": response,
        "project_name": display_name,
    }


__all__ = ["query_workflow_instances_node"]