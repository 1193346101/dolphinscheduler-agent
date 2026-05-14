"""
Recover Failure Node - 恢复失败的工作流

流程：
1. 检查确认状态（execute_approved）
2. 如果未确认，返回错误
3. 如果已确认，执行恢复
"""

import json
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config import settings


def recover_failure_node(state: ChatState) -> ChatState:
    """
    恢复失败的工作流

    Args:
        state: ChatState with workflow_code/workflow_instance_id and execute_approved

    Returns:
        Updated ChatState with recovery result
    """
    # 检查确认状态
    execute_approved = state.get("execute_approved", False)

    if not execute_approved:
        return {
            **state,
            "error_message": "操作未获批准",
            "response_content": "❌ 操作未获批准，未执行。请先发送恢复指令并确认。",
        }

    workflow_code = state.get("workflow_code", "")
    workflow_instance_id = state.get("workflow_instance_id", "")
    workflow_name = state.get("workflow_name", "")

    if not workflow_code and not workflow_instance_id:
        return {
            **state,
            "error_message": "请提供工作流code或实例ID",
            "response_content": "请提供工作流code或实例ID，例如：恢复工作流 12345",
        }

    # 调用 dsctl 恢复工作流
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 执行恢复操作（使用 workflow_instance_recover_failed）
    try:
        if workflow_instance_id:
            result = client.workflow_instance_recover_failed(int(workflow_instance_id))
        else:
            # 如果只有 workflow_code，需要先获取失败实例
            # 这里简化处理，假设用户提供了 instance_id
            return {
                **state,
                "error_message": "需要实例ID",
                "response_content": f"请提供工作流实例ID，例如：恢复实例 123456",
                "execute_approved": False,
            }
    except Exception as e:
        return {
            **state,
            "error_message": str(e),
            "response_content": f"恢复工作流失败: {str(e)}",
            "execute_approved": False,
        }

    if result.success:
        response = f"""### ✅ 恢复成功

**工作流**: {workflow_name or workflow_code}
**实例ID**: {workflow_instance_id}

已触发恢复操作，请稍后查看执行状态。

{result.stdout[:500] if result.stdout else ''}"""

        return {
            **state,
            "result_data": {"recovered": True, "workflow_code": workflow_code, "instance_id": workflow_instance_id},
            "response_content": response,
            "execute_approved": False,  # 重置确认状态
        }

    else:
        return {
            **state,
            "error_message": result.stderr,
            "response_content": f"❌ 恢复工作流失败: {result.stderr}",
            "execute_approved": False,  # 重置确认状态
        }


__all__ = ["recover_failure_node"]