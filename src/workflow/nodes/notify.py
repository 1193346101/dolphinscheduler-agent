"""
notify_dingtalk node

Send DingTalk notification - full implementation
"""

from ..state import AgentState
from ...tools.dingtalk_enterprise import DingTalkEnterpriseTool


def notify_dingtalk(state: AgentState) -> AgentState:
    """
    Send DingTalk notification

    Send different notification based on approval status:
    - No approval needed: Error analysis notification
    - Needs approval: Approval request notification

    Args:
        state: Current state

    Returns:
        Updated state (notification_sent, notification_content, approval_message_id)
    """
    project_config = state.get("project_config")
    dingtalk_config = project_config.get("dingtalk") if project_config else None

    if not dingtalk_config:
        return {
            **state,
            "notification_sent": False,
            "notification_content": None,
            "approval_message_id": None,
        }

    tool = DingTalkEnterpriseTool(
        client_id=dingtalk_config.get("client_id", ""),
        client_secret=dingtalk_config.get("client_secret", "")
    )

    approval_required = state.get("approval_required", False)

    if approval_required:
        # Approval request notification
        content = tool.build_approval_request(
            task_type=state.get("task_type", ""),
            workflow_code=state.get("workflow_code", ""),
            task_code=state.get("task_code", ""),
            risk_level=state.get("risk_level", ""),
            impact_summary=state.get("impact_summary", ""),
            suggested_actions=state.get("suggested_actions", []),
            risk_factors=state.get("risk_factors", []),
            approve_url="/approval/approve",
            reject_url="/approval/reject"
        )
        buttons = content.get("buttons", [])
    else:
        # Error analysis notification (include execution results)
        error_analysis = state.get("error_analysis", {})
        execution_results = state.get("execution_results", [])
        execution_success = state.get("execution_success", False)
        token_consumption = state.get("token_consumption", 0)
        token_details = state.get("token_details", {})
        report_url = state.get("report_url", "")

        content = tool.build_error_notification(
            task_type=state.get("task_type", ""),
            workflow_name=state.get("workflow_name", ""),
            workflow_code=state.get("workflow_code", ""),
            task_name=state.get("task_name", ""),
            task_code=state.get("task_code", ""),
            project_name=state.get("project_name", ""),
            risk_level=state.get("risk_level", ""),
            error_category=state.get("error_category", ""),
            error_patterns=state.get("error_patterns", []),
            error_description=error_analysis.get("error_message", ""),
            suggested_actions=state.get("suggested_actions", []),
            execution_results=execution_results,
            execution_success=execution_success,
            ds_url=project_config.get("ds_api_url", ""),
            token_consumption=token_consumption,
            token_details=token_details,
            report_url=report_url,
        )
        buttons = None

    # Send notification
    try:
        msg_id = tool.send_notification(
            robot_code=dingtalk_config.get("robot_code", ""),
            user_ids=dingtalk_config.get("notify_users", []),
            title=content.get("title", ""),
            content=content.get("content", ""),
            buttons=buttons
        )

        return {
            **state,
            "notification_sent": True,
            "notification_content": content.get("content", ""),
            "approval_message_id": msg_id,
        }
    except Exception as e:
        return {
            **state,
            "notification_sent": False,
            "notification_content": f"Send failed: {str(e)}",
            "approval_message_id": None,
        }


__all__ = ["notify_dingtalk"]