"""
notify_dingtalk 节点

发送钉钉通知 - 完整实现
"""

from ..state import AgentState
from ...tools.dingtalk_enterprise import DingTalkEnterpriseTool


def notify_dingtalk(state: AgentState) -> AgentState:
    """
    发送钉钉通知

    根据审批状态发送不同类型通知:
    - 无需审批: 错误分析通知
    - 需审批: 审批请求通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (notification_sent, notification_content, approval_message_id)
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
        # 审批请求通知
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
        # 错误分析通知
        content = tool.build_error_notification(
            task_type=state.get("task_type", ""),
            workflow_code=state.get("workflow_code", ""),
            task_code=state.get("task_code", ""),
            risk_level=state.get("risk_level", ""),
            error_category=state.get("error_category", ""),
            error_patterns=state.get("error_patterns", []),
            suggested_actions=state.get("suggested_actions", []),
            ds_url=project_config.get("ds_api_url", "")
        )
        buttons = None

    # 发送通知
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
            "notification_content": f"发送失败: {str(e)}",
            "approval_message_id": None,
        }


__all__ = ["notify_dingtalk"]