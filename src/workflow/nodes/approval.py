"""
approval 节点

request_approval 和 check_approval (placeholder)
"""

from typing import Dict, Any
from ..state import AgentState


def request_approval(state: AgentState) -> AgentState:
    """
    请求审批 (placeholder)

    后续实现:
    - 调用 DingTalkEnterpriseTool 发送审批请求
    - 记录消息 ID

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status, approval_message_id)
    """
    # Placeholder: 设置审批状态为 pending
    # TODO: 实现审批请求逻辑
    return {
        **state,
        "approval_status": "pending",
        "approval_message_id": None,
    }


def check_approval(state: AgentState) -> AgentState:
    """
    检查审批状态 (placeholder)

    后续实现:
    - 调用 ApprovalTool 检查审批结果
    - 处理超时

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status)
    """
    # Placeholder: 返回状态不变
    # TODO: 实现审批检查逻辑
    # 当前审批状态保持不变，由路由函数决定下一步
    return state


__all__ = ["request_approval", "check_approval"]