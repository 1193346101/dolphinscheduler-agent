"""
DingTalk Webhook API - 接收钉钉对话消息

处理钉钉机器人发送的消息，通过 LangGraph 流程执行查询
"""

from typing import Optional, Any, Dict
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..state import ChatState, create_chat_state
from ..graph import get_chat_graph


# 创建路由
router = APIRouter(prefix="/dingtalk", tags=["dingtalk"])


# ============ 钉钉消息模型 ============

class DingTalkMessage(BaseModel):
    """钉钉消息格式"""
    msgtype: str
    text: Optional[Dict[str, str]] = None
    markdown: Optional[Dict[str, str]] = None
    # 钉钉会发送的额外字段
    senderNick: Optional[str] = None
    senderId: Optional[str] = None
    conversationId: Optional[str] = None
    conversationTitle: Optional[str] = None
    createAt: Optional[int] = None


class DingTalkRequest(BaseModel):
    """钉钉请求格式"""
    msgtype: str
    text: Optional[Dict[str, str]] = None
    markdown: Optional[Dict[str, str]] = None
    senderNick: Optional[str] = None
    senderId: Optional[str] = None
    conversationId: Optional[str] = None
    conversationTitle: Optional[str] = None
    sessionWebhook: Optional[str] = None
    sessionWebhookExpiredTime: Optional[int] = None
    createAt: Optional[int] = None
    # admin 额外字段
    isAdmin: Optional[bool] = None
    isAdminInDing: Optional[bool] = None
    isOwner: Optional[bool] = None
    robotCode: Optional[str] = None


class DingTalkResponse(BaseModel):
    """钉钉响应格式"""
    msgtype: str = "markdown"
    markdown: Dict[str, str]


# ============ API 端点 ============

@router.post("/message")
async def handle_dingtalk_message(request: Request):
    """
    处理钉钉消息

    流程:
    1. 解析钉钉消息格式，提取用户消息
    2. 创建初始状态
    3. 通过 LangGraph 流程图执行完整流程:
       - parse_intent: 解析意图
       - route: 根据意图路由到对应节点
       - scan_graph/query_lineage/visualize: 执行对应操作
       - format_response: 格式化响应
    4. 返回钉钉格式的响应

    钉钉消息格式示例:
    {
        "msgtype": "text",
        "text": {"content": "工作流 wf_001 的下游"},
        "senderId": "user_001",
        "conversationId": "conv_001"
    }
    """
    try:
        payload = await request.json()

        # 提取消息内容
        msgtype = payload.get("msgtype", "text")
        content = extract_message_content(payload, msgtype)

        if not content or not content.strip():
            return JSONResponse(content={
                "msgtype": "text",
                "text": {"content": "请输入有效消息"}
            })

        # 提取用户和会话信息
        user_id = payload.get("senderId", "unknown")
        conversation_id = payload.get("conversationId", "unknown")

        # 创建初始状态
        state = create_chat_state(
            message=content,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        # 设置 project_name (从会话标题获取，用户在消息中也可以指定)
        project_name = extract_project_code(payload)  # 函数名不变，但返回的是项目名
        if project_name:
            state["project_name"] = project_name

        # 通过 LangGraph 流程图执行
        graph = get_chat_graph()
        state = graph.invoke(state)

        # 构建钉钉响应
        response_content = state.get("response_content", "处理完成")

        return JSONResponse(content={
            "msgtype": "markdown",
            "markdown": {
                "title": "查询结果",
                "text": response_content
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def extract_message_content(payload: Dict[str, Any], msgtype: str) -> str:
    """
    从钉钉消息中提取消息内容

    Args:
        payload: 钉钉请求 payload
        msgtype: 消息类型 (text, markdown, etc.)

    Returns:
        消息内容字符串
    """
    if msgtype == "text":
        text_data = payload.get("text", {})
        return text_data.get("content", "")
    elif msgtype == "markdown":
        markdown_data = payload.get("markdown", {})
        # 从 markdown 的 title 或 text 中提取
        return markdown_data.get("text", "") or markdown_data.get("title", "")
    else:
        # 其他类型尝试从 text 字段获取
        return payload.get("text", {}).get("content", "")


def extract_project_code(payload: Dict[str, Any]) -> Optional[str]:
    """
    从钉钉请求中提取项目名称（不再返回 project_code）

    用户通过项目名称操作，系统自动查找 project_code

    Args:
        payload: 钉钉请求 payload

    Returns:
        项目名称或 None（不再返回代码）
    """
    conversation_title = payload.get("conversationTitle", "")

    # 从会话标题解析项目名称
    # 例如: "项目-ad_monitor-告警群" -> "ad_monitor"
    if conversation_title:
        import re
        # Match pattern like: 项目-<project_name> or 项目<separator><project_name>
        match = re.search(r'项目[^\w]*([a-zA-Z0-9_-]+)', conversation_title)
        if match:
            return match.group(1)

    # 不再使用 DEFAULT_PROJECT_CODE 配置
    # 用户需要在消息中明确指定项目名称
    return None


__all__ = ["router", "handle_dingtalk_message"]