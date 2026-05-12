"""
Run Workflow Node - 手动运行工作流
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
        state: ChatState with workflow_code populated

    Returns:
        Updated ChatState with run result
    """
    workflow_code = state.get("workflow_code", "")

    if not workflow_code:
        return {
            **state,
            "error_message": "请提供工作流code",
            "response_content": "请提供工作流code，例如：运行工作流 12345",
        }

    # 调用 dsctl 运行工作流
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 执行运行操作
    result = client.run_workflow(workflow_code)

    if result.success:
        # 解析返回的实例ID
        try:
            data = json.loads(result.stdout)
            instance_id = data.get("data", {}).get("id", "未知")
        except:
            instance_id = "未知"

        response = f"""### 运行成功

**工作流**: {workflow_code}
**实例ID**: {instance_id}

已触发执行，请稍后查看运行状态。

使用命令查看状态：工作流 {workflow_code} 的状态"""

        return {
            **state,
            "result_data": {"running": True, "workflow_code": workflow_code, "instance_id": instance_id},
            "response_content": response,
        }

    else:
        return {
            **state,
            "error_message": result.stderr,
            "response_content": f"运行工作流失败: {result.stderr}",
        }


__all__ = ["run_workflow_node"]