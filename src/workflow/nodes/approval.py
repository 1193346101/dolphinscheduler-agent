"""
approval node

request_approval and check_approval - full implementation
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...tools.approval_tool import ApprovalTool
from ...tools.dingtalk_progress import get_notifier_from_settings


approval_tool = ApprovalTool()


def request_approval(state: AgentState) -> AgentState:
    """
    Request approval

    Use ApprovalTool to create approval request:
    - Save state snapshot
    - Set 30 minute timeout
    - Send DingTalk approval button message

    Args:
        state: Current state

    Returns:
        Updated state (approval_status, approval_request_id, approval_message_id)
    """
    dingtalk_message_id = state.get("approval_message_id")

    # Create approval request
    request_id = approval_tool.create_request(
        state=state,
        timeout_minutes=30,
        dingtalk_message_id=dingtalk_message_id
    )

    # Send DingTalk approval button message
    suggested_actions = state.get("suggested_actions", [])
    if suggested_actions:
        # Get first action as approval content
        action = suggested_actions[0]
        tool_name = action.get("action_type", "unknown")
        risk_level = action.get("risk_level", "MEDIUM")

        # Build command description
        command_desc = f"Execute {tool_name} action"
        if action.get("changes"):
            command_desc = str(action.get("changes"))

        # Send approval request message
        notifier = get_notifier_from_settings()
        notifier.send_approval_request(
            approval_id=request_id,
            tool_name=tool_name,
            command=command_desc,
            risk_level=risk_level
        )

    return {
        **state,
        "approval_status": "pending",
        "approval_request_id": request_id,
        "approval_message_id": dingtalk_message_id,
    }


def check_approval(state: AgentState) -> AgentState:
    """
    Check approval status

    Check approval request status:
    - approved: Continue execution
    - rejected: End process
    - timeout: Mark timeout
    - pending: Waiting

    Args:
        state: Current state

    Returns:
        Updated state (approval_status)
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

    # Return current approval status
    return {
        **state,
        "approval_status": request.status,
    }


__all__ = ["request_approval", "check_approval"]