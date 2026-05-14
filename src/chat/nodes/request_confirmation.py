"""
Request Confirmation Node - 请求用户确认

用于危险操作（run_workflow, recover_failure）前的用户确认流程。

流程:
1. 构建确认消息（包含操作详情）
2. 生成确认 ID
3. 发送钉钉确认消息
4. 存储确认请求（供后续检查）
"""

import uuid
from datetime import datetime
from typing import Dict

from ..state import ChatState
from ...config import settings
from ...tools.dingtalk_enterprise import DingTalkEnterpriseTool


# 存储待确认请求（内存缓存，重启后丢失）
_pending_confirmations: Dict[str, ChatState] = {}


def request_confirmation_node(state: ChatState) -> ChatState:
    """
    请求用户确认节点

    发送钉钉确认消息，等待用户回复"确认"或"取消"

    Args:
        state: Current ChatState with intent and confirmation_params

    Returns:
        Updated ChatState with confirmation fields
    """
    intent_type = state.get("intent_type", "unknown")
    params = state.get("confirmation_params", {})
    user_id = state.get("user_id", "unknown")
    workflow_code = state.get("workflow_code")
    workflow_name = state.get("workflow_name", "")
    project_name = state.get("project_name", "")

    # 生成确认 ID
    confirmation_id = f"confirm_{user_id}_{uuid.uuid4().hex[:8]}"

    # 构建确认消息
    confirmation_message = build_confirmation_message(
        intent_type=intent_type,
        workflow_code=workflow_code,
        workflow_name=workflow_name,
        project_name=project_name,
        params=params,
    )

    # 发送钉钉确认消息
    dingtalk = DingTalkEnterpriseTool(
        client_id=settings.DINGTALK_CLIENT_ID,
        client_secret=settings.DINGTALK_CLIENT_SECRET
    )

    try:
        dingtalk.send_notification(
            robot_code=settings.DINGTALK_ROBOT_CODE,
            user_ids=[user_id] if user_id else [],
            title=f"操作确认 - {intent_type}",
            content=confirmation_message,
        )

        print(f"[request_confirmation] 已发送确认请求: {confirmation_id}")

        # 存储待确认请求
        _pending_confirmations[confirmation_id] = {
            **state,
            "confirmation_id": confirmation_id,
            "confirmation_status": "pending",
            "pending_confirmation": True,
        }

        return {
            **state,
            "pending_confirmation": True,
            "confirmation_message": confirmation_message,
            "confirmed_action": intent_type,
            "confirmation_params": params,
            "confirmation_status": "pending",
            "confirmation_id": confirmation_id,
            "response_content": '已发送确认请求，请回复"确认"执行或"取消"拒绝',
        }

    except Exception as e:
        print(f"[request_confirmation] 发送失败: {e}")
        return {
            **state,
            "pending_confirmation": False,
            "error_message": f"发送确认请求失败: {str(e)}",
        }


def build_confirmation_message(
    intent_type: str,
    workflow_code: str,
    workflow_name: str,
    project_name: str,
    params: Dict,
) -> str:
    """
    构建确认消息内容

    Args:
        intent_type: 意图类型
        workflow_code: 工作流编码
        workflow_name: 工作流名称
        project_name: 项目名称
        params: 参数

    Returns:
        Markdown 格式的确认消息
    """
    action_desc = get_action_description(intent_type)

    # 构建参数描述
    param_desc = ""
    if workflow_code:
        param_desc += f"工作流编码: **{workflow_code}**\n"
    if workflow_name:
        param_desc += f"工作流名称: **{workflow_name}**\n"
    if project_name:
        param_desc += f"项目名称: **{project_name}**\n"
    if params:
        worker_group = params.get("worker_group", "all_worker")
        tenant = params.get("tenant", project_name or "default")
        param_desc += f"Worker 组: **{worker_group}**\n"
        param_desc += f"租户: **{tenant}**\n"

    return f"""## ⚠️ 操作确认

**操作类型:** {action_desc}

---

### 操作详情

{param_desc}

---

### 请确认是否执行

- 回复 **"确认"** 执行此操作
- 回复 **"取消"** 拒绝此操作

---

⏰ 确认请求时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""


def get_action_description(intent_type: str) -> str:
    """获取操作描述"""
    descriptions = {
        "run_workflow": "执行/运行工作流",
        "recover_failure": "恢复失败的工作流",
        "workflow_rerun": "重新运行工作流",
    }
    return descriptions.get(intent_type, intent_type)


def get_pending_confirmation(confirmation_id: str) -> ChatState:
    """
    获取待确认请求

    Args:
        confirmation_id: 确认 ID

    Returns:
        存储的 ChatState 或 None
    """
    return _pending_confirmations.get(confirmation_id)


def get_pending_confirmation_by_user(user_id: str) -> ChatState:
    """
    获取用户的待确认请求

    Args:
        user_id: 用户 ID

    Returns:
        存储的 ChatState 或 None
    """
    for conf_id, state in _pending_confirmations.items():
        if conf_id.startswith(f"confirm_{user_id}_"):
            return state
    return None


def update_confirmation_status(confirmation_id: str, status: str) -> None:
    """
    更新确认状态

    Args:
        confirmation_id: 确认 ID
        status: "confirmed" | "rejected"
    """
    if confirmation_id in _pending_confirmations:
        _pending_confirmations[confirmation_id]["confirmation_status"] = status
        _pending_confirmations[confirmation_id]["pending_confirmation"] = False


def clear_confirmation(confirmation_id: str) -> None:
    """
    清除确认请求

    Args:
        confirmation_id: 确认 ID
    """
    if confirmation_id in _pending_confirmations:
        del _pending_confirmations[confirmation_id]


__all__ = [
    "request_confirmation_node",
    "get_pending_confirmation",
    "get_pending_confirmation_by_user",
    "update_confirmation_status",
    "clear_confirmation",
]