"""
Check Confirmation Node - 检查用户确认状态

处理用户确认回复，根据状态决定下一步：
- confirmed: 用户确认，继续执行
- rejected: 用户拒绝，取消操作
- pending: 仍在等待确认（不应该到达此节点）

流程:
1. 检查 confirmation_status 字段
2. 根据状态更新 execute_approved
3. 返回新的状态
"""

from ..state import ChatState


def check_confirmation_node(state: ChatState) -> ChatState:
    """
    检查用户确认状态节点

    Args:
        state: Current ChatState with confirmation_status

    Returns:
        Updated ChatState with execute_approved set accordingly
    """
    confirmation_status = state.get("confirmation_status", "pending")
    confirmed_action = state.get("confirmed_action", "")
    confirmation_id = state.get("confirmation_id", "")

    print(f"[check_confirmation] 确认ID: {confirmation_id}, 状态: {confirmation_status}")

    if confirmation_status == "confirmed":
        # 用户已确认，批准执行
        print(f"[check_confirmation] 用户已确认操作: {confirmed_action}")
        return {
            **state,
            "pending_confirmation": False,
            "execute_approved": True,
            "response_content": None,  # 清空之前的确认消息
        }

    elif confirmation_status == "rejected":
        # 用户拒绝，取消操作
        print(f"[check_confirmation] 用户已拒绝操作: {confirmed_action}")
        return {
            **state,
            "pending_confirmation": False,
            "execute_approved": False,
            "response_content": "❌ 操作已取消，未执行。",
            "error_message": None,
        }

    else:
        # 仍在等待确认（不应该到达此节点）
        print(f"[check_confirmation] 仍在等待确认")
        return {
            **state,
            "pending_confirmation": True,
            "execute_approved": False,
            "response_content": '⏳ 正在等待您的确认，请回复"确认"或"取消"。',
        }


__all__ = ["check_confirmation_node"]