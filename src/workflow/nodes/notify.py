"""
notify_dingtalk 节点

发送钉钉通知 (placeholder)
"""

from typing import Dict, Any
from ..state import AgentState


def notify_dingtalk(state: AgentState) -> AgentState:
    """
    发送钉钉通知 (placeholder)

    后续实现:
    - 调用 DingTalkEnterpriseTool 发送结果通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (notification_sent, notification_content)
    """
    # Placeholder: 返回状态不变
    # TODO: 实现钉钉通知逻辑
    return {
        **state,
        "notification_sent": False,
        "notification_content": None,
    }


__all__ = ["notify_dingtalk"]