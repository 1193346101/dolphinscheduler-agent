"""
Query Logs Node - 查询工作流/任务日志
"""

import json
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config import settings


def query_logs_node(state: ChatState) -> ChatState:
    """
    查询工作流或任务日志

    Args:
        state: ChatState with workflow_code or workflow_instance_id populated

    Returns:
        Updated ChatState with logs
    """
    workflow_code = state.get("workflow_code", "")
    workflow_instance_id = state.get("workflow_instance_id", "")
    task_code = state.get("task_code", "")

    if not workflow_code and not workflow_instance_id:
        return {
            **state,
            "error_message": "请提供工作流code或实例ID",
            "response_content": "请提供工作流code或实例ID，例如：工作流 12345 的日志",
        }

    # 调用 dsctl 查询日志
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 根据参数选择查询方式
    if workflow_instance_id:
        # 查询实例日志
        result = client.get_workflow_instance_logs(workflow_instance_id)
    elif workflow_code:
        # 查询最近一次执行的日志
        # 先获取最近的实例ID
        instances_result = client.list_workflow_instances(
            workflow_code=int(workflow_code),
            page_size=1,
        )
        if instances_result.success:
            try:
                data = json.loads(instances_result.stdout)
                instances = data.get("data", {}).get("totalList", [])
                if instances:
                    latest_instance = instances[0]
                    workflow_instance_id = latest_instance.get("id")
                    result = client.get_workflow_instance_logs(workflow_instance_id)
                else:
                    return {
                        **state,
                        "error_message": "无运行实例",
                        "response_content": f"工作流 {workflow_code} 暂无运行实例",
                    }
            except json.JSONDecodeError:
                return {
                    **state,
                    "error_message": "解析失败",
                    "response_content": f"查询工作流 {workflow_code} 实例失败",
                }
        else:
            return {
                **state,
                "error_message": instances_result.stderr,
                "response_content": f"查询工作流实例失败: {instances_result.stderr}",
            }
    else:
        result = None

    if result and result.success:
        # 解析日志
        log_content = result.stdout[:2000]  # 限制长度

        response = f"""### 日志查询

**工作流**: {workflow_code}
**实例**: {workflow_instance_id}

---

{log_content}"""

        return {
            **state,
            "result_data": {"logs": log_content},
            "response_content": response,
        }

    else:
        return {
            **state,
            "error_message": result.stderr if result else "无日志",
            "response_content": f"查询日志失败: {result.stderr if result else '无日志'}",
        }


__all__ = ["query_logs_node"]