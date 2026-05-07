"""
approval 节点

request_approval 和 check_approval - 完整实现
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...tools.approval_tool import ApprovalTool


approval_tool = ApprovalTool()


def request_approval(state: AgentState) -> AgentState:
    """
    请求审批

    使用 ApprovalTool 创建审批请求:
    - 保存状态快照
    - 设置 30 分钟超时
    - 记录钉钉消息 ID

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status, approval_request_id, approval_message_id)
    """
    dingtalk_message_id = state.get("approval_message_id")

    # 创建审批请求
    request_id = approval_tool.create_request(
        state=state,
        timeout_minutes=30,
        dingtalk_message_id=dingtalk_message_id
    )

    return {
        **state,
        "approval_status": "pending",
        "approval_request_id": request_id,
        "approval_message_id": dingtalk_message_id,
    }


def check_approval(state: AgentState) -> AgentState:
    """
    检查审批状态

    检查审批请求状态:
    - approved: 继续执行
    - rejected: 结束流程
    - timeout: 标记超时
    - pending: 等待中

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status)
    """
    request_id = state.get("approval_request_id")

    if not request_id:
        return state

    request = approval_tool.get_request(request_id)

    if not request:
        return {
            **state,
            "approval_status": "not_found",
        }

    # 返回当前审批状态
    return {
        **state,
        "approval_status": request.status,
    }


__all__ = ["request_approval", "check_approval"]