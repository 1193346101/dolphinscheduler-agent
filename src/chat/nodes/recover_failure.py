"""
Recover Failure Node - 恢复失败的工作流
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
        state: ChatState with workflow_code populated

    Returns:
        Updated ChatState with recovery result
    """
    workflow_code = state.get("workflow_code", "")

    if not workflow_code:
        return {
            **state,
            "error_message": "请提供工作流code",
            "response_content": "请提供工作流code，例如：恢复工作流 12345",
        }

    # 调用 dsctl 恢复工作流
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 执行恢复操作
    result = client.recover_workflow(workflow_code)

    if result.success:
        response = f"""### 恢复成功

**工作流**: {workflow_code}

已触发恢复操作，请稍后查看执行状态。

{result.stdout[:500] if result.stdout else ''}"""

        return {
            **state,
            "result_data": {"recovered": True, "workflow_code": workflow_code},
            "response_content": response,
        }

    else:
        return {
            **state,
            "error_message": result.stderr,
            "response_content": f"恢复工作流失败: {result.stderr}",
        }


__all__ = ["recover_failure_node"]