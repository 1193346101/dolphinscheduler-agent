"""
Run Workflow Node - 手动运行工作流

流程：
1. 检查确认状态（execute_approved）
2. 如果未确认，返回错误
3. 如果已确认，执行工作流
"""

import json
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config import settings


def run_workflow_node(state: ChatState) -> ChatState:
    """
    手动运行工作流

    Args:
        state: ChatState with workflow_code, project_code and execute_approved

    Returns:
        Updated ChatState with run result
    """
    # 检查确认状态
    execute_approved = state.get("execute_approved", False)

    if not execute_approved:
        return {
            **state,
            "error_message": "操作未获批准",
            "response_content": "❌ 操作未获批准，未执行。请先发送运行指令并确认。",
        }

    workflow_code = state.get("workflow_code", "")
    project_code = state.get("project_code", "")
    workflow_name = state.get("workflow_name", "")
    project_name = state.get("project_name", "")
    params = state.get("confirmation_params", {})

    if not workflow_code:
        return {
            **state,
            "error_message": "请提供工作流code",
            "response_content": "请提供工作流code，例如：运行工作流 12345",
        }

    # 默认参数
    worker_group = params.get("worker_group", "all_worker")
    tenant = params.get("tenant", project_name or "default")

    # 调用 dsctl 运行工作流
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 执行运行操作（使用新的参数）
    try:
        result = client.workflow_run(
            project_code=int(project_code) if project_code else None,
            workflow_code=int(workflow_code) if workflow_code else None,
            worker_group=worker_group,
            tenant=tenant,
        )
    except Exception as e:
        return {
            **state,
            "error_message": str(e),
            "response_content": f"运行工作流失败: {str(e)}",
        }

    if result.success:
        # 解析返回的实例ID
        try:
            data = json.loads(result.stdout)
            instance_id = data.get("data", {}).get("id", "未知")
        except:
            instance_id = "未知"

        response = f"""### ✅ 运行成功

**工作流**: {workflow_name or workflow_code}
**项目**: {project_name or project_code}
**实例ID**: {instance_id}
**Worker组**: {worker_group}
**租户**: {tenant}

已触发执行，请稍后查看运行状态。

使用命令查看状态：工作流 {workflow_code} 的状态"""

        return {
            **state,
            "result_data": {"running": True, "workflow_code": workflow_code, "instance_id": instance_id},
            "response_content": response,
            "execute_approved": False,  # 重置确认状态
        }

    else:
        return {
            **state,
            "error_message": result.stderr,
            "response_content": f"❌ 运行工作流失败: {result.stderr}",
            "execute_approved": False,  # 重置确认状态
        }


__all__ = ["run_workflow_node"]