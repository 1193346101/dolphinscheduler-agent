"""
Query Workflow Instances Node - 查询工作流实例列表（运行记录）
"""

import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config.projects import projects_registry
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

    # 查找项目配置
    project_config = projects_registry.get_by_name(project_name)
    if not project_config:
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

    # 调用 dsctl 直接查询项目所有实例
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    all_instances = []
    try:
        instances_result = client.list_workflow_instances(
            project_code=int(project_code),
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
                    wf_name = inst.get("workflowName", "未命名")
                    all_instances.append({
                        "workflow_name": wf_name,
                        "workflow_code": inst.get("workflowCode", ""),
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
        response = f"项目 **{project_name}** 在 {query_date} 暂无工作流实例运行"
    else:
        # 状态中文映射
        state_desc = {
            "SUCCESS": "✅",
            "FAILURE": "❌",
            "RUNNING": "🔄",
            "WAITTING": "⏳",
            "PAUSE": "⏸️",
            "STOP": "🛑",
        }

        # 按状态分组统计
        success_count = sum(1 for i in all_instances if i["state"] == "SUCCESS")
        failure_count = sum(1 for i in all_instances if i["state"] == "FAILURE")
        running_count = sum(1 for i in all_instances if i["state"] == "RUNNING")

        instance_list = []
        for inst in all_instances[:30]:  # 最多显示30个
            state_icon = state_desc.get(inst["state"], "❓")
            # 显示完整日期时间
            start_time = inst["start_time"] if inst["start_time"] else "N/A"
            end_time = inst["end_time"] if inst["end_time"] else "运行中"
            instance_list.append(
                f"{inst['workflow_name']} | ID:{inst['instance_id']} | {state_icon} | {start_time} → {end_time}"
            )

        response = f"### {project_name} ({query_date})\n\n"
        response += f"✅ {success_count} | ❌ {failure_count} | 🔄 {running_count}\n\n"
        response += "\n".join(instance_list)

    return {
        **state,
        "result_data": {"instances": all_instances, "count": len(all_instances)},
        "response_content": response,
    }


__all__ = ["query_workflow_instances_node"]