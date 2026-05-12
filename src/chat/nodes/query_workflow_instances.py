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

    # 调用 dsctl 查询工作流列表（先获取所有工作流定义）
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 1. 先获取工作流定义列表
    workflows_result = client.list_workflows(project_code)
    if not workflows_result.success:
        return {
            **state,
            "error_message": workflows_result.stderr or "查询失败",
            "response_content": f"查询工作流失败: {workflows_result.stderr or '未知错误'}",
        }

    # 解析工作流定义
    try:
        data = json.loads(workflows_result.stdout)
        if isinstance(data, dict):
            inner_data = data.get("data", [])
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

    # 构建工作流编码到名称的映射
    workflow_map = {}
    for wf in workflows:
        if isinstance(wf, dict):
            code = str(wf.get("code", ""))
            name = wf.get("name", "未命名")
            workflow_map[code] = name

    # 2. 查询每个工作流今天的实例（限制前10个工作流，避免请求过多）
    all_instances = []
    seen_ids = set()  # 去重
    checked_count = 0
    max_check = 10  # 只检查前10个工作流

    for wf_code, wf_name in workflow_map.items():
        if checked_count >= max_check:
            break
        checked_count += 1

        try:
            instances_result = client.list_workflow_instances(
                project_code=int(project_code),
                workflow_code=int(wf_code),
                page_size=20,
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
                        inst_id = inst.get("id")
                        # 去重：同一个实例ID只记录一次
                        if inst_id not in seen_ids:
                            seen_ids.add(inst_id)
                            all_instances.append({
                                "workflow_name": wf_name,
                                "workflow_code": wf_code,
                                "instance_id": inst_id,
                                "state": inst.get("state", "UNKNOWN"),
                                "start_time": inst.get("startTime", ""),
                                "end_time": inst.get("endTime", ""),
                            })
        except Exception:
            continue

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