"""
Dispatcher - 请求分发器

○ 不是 Agent，使用预定义规则判断请求类型

判断规则:
- 有 processInstanceId/taskCode 字段 → 告警请求 → AlertAgent
- 用户自由文本 → 对话请求 → ChatAgent
"""

from typing import Any

from .agent.alert_agent import AlertAgent
from .agent.chat_agent import ChatAgent


def dispatch_request(request: dict[str, Any]) -> dict[str, Any]:
    """
    请求分发（预定义规则，不使用 LLM）

    Args:
        request: 请求内容

    Returns:
        处理结果
    """
    # 判断是否是告警请求
    if is_alert_request(request):
        alert_agent = AlertAgent()
        return alert_agent.handle_alert(request)
    else:
        chat_agent = ChatAgent()
        return chat_agent.handle_chat(request)


def is_alert_request(request: dict[str, Any]) -> bool:
    """
    判断是否是告警请求（预定义规则）

    告警请求特征:
    - 有 processInstanceId 字段
    - 有 taskCode 字段
    - 有 taskType 字段

    Args:
        request: 请求内容

    Returns:
        是否是告警请求
    """
    alert_fields = ["processInstanceId", "taskCode", "taskType", "processDefinitionCode"]
    return any(field in request for field in alert_fields)


__all__ = ["dispatch_request", "is_alert_request", "AlertAgent", "ChatAgent"]