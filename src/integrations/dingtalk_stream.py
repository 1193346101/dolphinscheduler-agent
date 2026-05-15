"""
钉钉 Stream 模式消息接收器

使用 dingtalk-stream SDK 接收机器人消息，无需公网地址

支持消息类型：
1. 用户对话消息 - 通过 ChatAgent 处理
2. DolphinScheduler 告警 JSON - 通过 AlertWorkflow 处理
3. 确认/取消回复 - 处理危险操作的确认流程

内置功能：
- 审批超时定时检查（后台线程）
"""

import json
import re
import threading
import time
import traceback
from typing import Optional, Tuple

import dingtalk_stream
from dingtalk_stream.chatbot import ChatbotMessage, CallbackMessage, AckMessage

from ..config import settings
from ..chat.graph import get_chat_graph
from ..chat.state import create_chat_state
from ..chat.nodes.request_confirmation import (
    get_pending_confirmation_by_user,
    update_confirmation_status,
)
from ..workflow.graph import AlertWorkflowGraph
from ..tools.approval_tool import ApprovalTool
from ..knowledge.manager import knowledge_manager

# 最近执行结果缓存（用于关联用户反馈）
# 格式: {user_id: {"entry_id": "...", "task_name": "...", "timestamp": ...}}
_recent_executions: dict = {}

# 反馈关键词
FEEDBACK_VALID_KEYWORDS = ["修复正确", "有效", "✅", "正确"]
FEEDBACK_INVALID_KEYWORDS = ["修复错误", "无效", "❌", "错误"]


# 告警 JSON 特征模式
ALERT_JSON_PATTERNS = [
    r'"projectCode"\s*:',
    r'"processDefinitionCode"\s*:',
    r'"taskInstanceId"\s*:',
    r'"taskType"\s*:',
    r'"alerts"\s*:',
]

# 确认关键词
CONFIRM_KEYWORDS = ["确认", "✅", "同意", "执行", "是", "ok", "yes"]
CANCEL_KEYWORDS = ["取消", "❌", "拒绝", "不", "否", "cancel", "no"]


def is_alert_json(content: str) -> bool:
    """
    判断消息是否为 DolphinScheduler 告警 JSON

    Args:
        content: 消息内容

    Returns:
        是否为告警 JSON
    """
    if not content or not content.strip():
        return False

    # 尝试解析 JSON
    try:
        data = json.loads(content.strip())

        # 检查是否包含告警特征字段
        if isinstance(data, dict):
            # 直接告警格式
            if "alerts" in data:
                return True
            # 单条告警格式
            alert_fields = ["projectCode", "processDefinitionCode", "taskInstanceId", "taskType"]
            if any(field in data for field in alert_fields):
                return True

        # 列表格式告警
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                alert_fields = ["projectCode", "processDefinitionCode", "taskInstanceId"]
                if any(field in first_item for field in alert_fields):
                    return True

    except json.JSONDecodeError:
        # 不是有效 JSON，检查是否包含告警特征字符串
        content_stripped = content.strip()
        matches = sum(1 for pattern in ALERT_JSON_PATTERNS if re.search(pattern, content_stripped))
        if matches >= 2:
            return True

    return False


def _is_feedback_message(content: str) -> bool:
    """
    判断消息是否为反馈消息（修复正确/错误）

    Args:
        content: 消息内容

    Returns:
        是否为反馈消息
    """
    content_lower = content.lower()
    for keyword in FEEDBACK_VALID_KEYWORDS + FEEDBACK_INVALID_KEYWORDS:
        if keyword.lower() in content_lower:
            return True
    return False


def _get_feedback_type(content: str) -> str:
    """
    从消息内容提取反馈类型

    Args:
        content: 消息内容

    Returns:
        "valid" 或 "invalid"
    """
    content_lower = content.lower()
    for keyword in FEEDBACK_VALID_KEYWORDS:
        if keyword.lower() in content_lower:
            return "valid"
    for keyword in FEEDBACK_INVALID_KEYWORDS:
        if keyword.lower() in content_lower:
            return "invalid"
    return "unknown"


def save_recent_execution(user_id: str, entry_id: str, task_name: str):
    """
    保存最近执行结果（供用户反馈时关联）

    Args:
        user_id: 用户 ID
        entry_id: 知识库条目 ID
        task_name: 任务名称
    """
    _recent_executions[user_id] = {
        "entry_id": entry_id,
        "task_name": task_name,
        "timestamp": time.time(),
    }


def get_recent_execution(user_id: str, max_age_seconds: int = 300) -> Optional[dict]:
    """
    获取用户最近的执行结果

    Args:
        user_id: 用户 ID
        max_age_seconds: 最大年龄（秒），默认5分钟

    Returns:
        执行结果字典或 None
    """
    execution = _recent_executions.get(user_id)
    if not execution:
        return None

    # 检查是否过期
    if time.time() - execution["timestamp"] > max_age_seconds:
        return None

    return execution


class DingTalkStreamHandler(dingtalk_stream.ChatbotHandler):
    """
    钉钉 Stream 消息处理器

    接收用户发送给机器人的消息，根据类型分发处理：
    - 告警 JSON → AlertWorkflow 处理
    - 对话消息 → ChatAgent 处理
    """

    def __init__(self):
        super().__init__()
        self.chat_graph = get_chat_graph()
        self.alert_workflow = AlertWorkflowGraph()

    async def process(self, callback_message: CallbackMessage) -> Tuple[int, str]:
        """
        处理接收到的消息

        Args:
            callback_message: 钉钉回调消息对象

        Returns:
            (status_code, response_message) 元组
        """
        try:
            # callback_message.data 是 dict，需要转换为 ChatbotMessage
            message_dict = callback_message.data
            message = dingtalk_stream.chatbot.ChatbotMessage.from_dict(message_dict)

            # 提取消息内容
            text_list = message.get_text_list()
            content = text_list[0] if text_list else ""

            print(f"[dingtalk-stream] 收到消息: {content[:100]}...")
            print(f"[dingtalk-stream] 发送者: {message.sender_staff_id}")

            if not content or not content.strip():
                self.reply_text("请输入有效消息", message)
                return AckMessage.STATUS_OK, "ok"

            # === 判断消息类型 ===
            if is_alert_json(content):
                print("[dingtalk-stream] 识别为告警 JSON，启动告警处理流程")
                return await self._handle_alert(content, message)

            # === 检查是否为反馈回复（修复正确/错误） ===
            content_stripped = content.strip()
            if _is_feedback_message(content_stripped):
                print("[dingtalk-stream] 识别为反馈消息，查找最近执行结果")
                return await self._handle_feedback_reply(content, message)

            # === 检查是否为确认/取消回复 ===
            content_lower = content_stripped.lower()
            if content_lower in CONFIRM_KEYWORDS or content_lower in CANCEL_KEYWORDS:
                print("[dingtalk-stream] 识别为确认回复，查找待确认请求")
                return await self._handle_confirmation_reply(content, message)

            # === 对话消息处理 ===
            print("[dingtalk-stream] 识别为对话消息，启动对话处理流程")

            # 创建初始状态
            state = create_chat_state(
                message=content,
                user_id=message.sender_staff_id or "unknown",
                conversation_id=message.conversation_id or "unknown",
            )

            # 不再设置 project_code
            # 用户需要在消息中明确指定项目名称，或者从会话标题解析
            # state["project_code"] = None  # 不需要设置

            # 通过 LangGraph 流程执行
            result_state = self.chat_graph.invoke(state)

            # 提取回复内容
            response_content = result_state.get("response_content", "处理完成")

            print(f"[dingtalk-stream] 回复长度: {len(response_content)} 字符")

            # 发送 markdown 回复
            self.reply_markdown("查询结果", response_content, message)

            return AckMessage.STATUS_OK, "ok"

        except Exception as e:
            traceback.print_exc()
            # 尝试直接回复
            try:
                message = dingtalk_stream.chatbot.ChatbotMessage.from_dict(callback_message.data)
                self.reply_text(f"处理出错: {str(e)}", message)
            except:
                print(f"[dingtalk-stream] 无法回复: {e}")
            return AckMessage.STATUS_OK, "error"

    async def _handle_feedback_reply(self, content: str, message: ChatbotMessage) -> Tuple[int, str]:
        """
        处理用户反馈（修复正确/错误）

        用户在收到执行结果通知后，可以回复：
        - ✅ / "修复正确" / "有效" → 确认修复方案有效
        - ❌ / "修复错误" / "无效" → 标记修复方案无效

        Args:
            content: 消息内容
            message: 钉钉消息对象

        Returns:
            (status_code, response_message) 元组
        """
        user_id = message.sender_staff_id or "unknown"
        feedback_type = _get_feedback_type(content)

        print(f"[dingtalk-stream] 用户 {user_id} 反馈: {feedback_type}")

        # 查找用户最近的执行结果
        recent_execution = get_recent_execution(user_id, max_age_seconds=300)

        if not recent_execution:
            print(f"[dingtalk-stream] 用户 {user_id} 无最近的执行结果")
            self.reply_text("没有可反馈的执行结果（超过5分钟），请重新触发告警", message)
            return AckMessage.STATUS_OK, "no_execution"

        entry_id = recent_execution.get("entry_id", "")
        task_name = recent_execution.get("task_name", "")

        if not entry_id:
            print(f"[dingtalk-stream] 执行结果无知识库条目 ID")
            self.reply_text(f"任务 {task_name} 的修复方案未记录到知识库", message)
            return AckMessage.STATUS_OK, "no_entry"

        # 提取用户补充说明（如果反馈无效）
        human_suggestion = None
        if feedback_type == "invalid":
            # 从消息中提取说明（去掉关键词后的内容）
            content_clean = content.strip()
            for keyword in FEEDBACK_INVALID_KEYWORDS:
                content_clean = content_clean.replace(keyword, "")
            human_suggestion = content_clean.strip() if content_clean.strip() else None

        # 更新知识库状态
        success = knowledge_manager.confirm(
            entry_id=entry_id,
            feedback=feedback_type,
            human_suggestion=human_suggestion,
        )

        if success:
            if feedback_type == "valid":
                response_text = f"✅ 已确认任务 {task_name} 的修复方案正确\n知识库已更新，下次遇到同类问题将自动应用此方案"
                print(f"[dingtalk-stream] 知识库确认成功: {entry_id} -> valid")
            else:
                response_text = f"❌ 已标记任务 {task_name} 的修复方案无效\n"
                if human_suggestion:
                    response_text += f"您的建议: {human_suggestion}\n"
                response_text += "知识库已更新，下次遇到同类问题将重新分析"
                print(f"[dingtalk-stream] 知识库标记无效: {entry_id} -> invalid, suggestion: {human_suggestion}")

            self.reply_markdown("反馈已提交", response_text, message)

            # 清除缓存的执行结果
            _recent_executions.pop(user_id, None)

            return AckMessage.STATUS_OK, "feedback_submitted"
        else:
            print(f"[dingtalk-stream] 知识库更新失败: {entry_id}")
            self.reply_text(f"反馈提交失败，请稍后重试", message)
            return AckMessage.STATUS_OK, "feedback_failed"

    async def _handle_confirmation_reply(self, content: str, message: ChatbotMessage) -> Tuple[int, str]:
        """
        处理确认/取消回复

        Args:
            content: 消息内容
            message: 钉钉消息对象

        Returns:
            (status_code, response_message) 元组
        """
        user_id = message.sender_staff_id or "unknown"
        content_stripped = content.strip().lower()

        # 查找用户的待确认请求
        pending_state = get_pending_confirmation_by_user(user_id)

        if not pending_state:
            print(f"[dingtalk-stream] 用户 {user_id} 无待确认请求")
            self.reply_text("没有待确认的操作，请发送新的指令", message)
            return AckMessage.STATUS_OK, "no_pending"

        confirmation_id = pending_state.get("confirmation_id", "")
        confirmed_action = pending_state.get("confirmed_action", "")

        print(f"[dingtalk-stream] 找到待确认请求: {confirmation_id}, 操作: {confirmed_action}")

        if content_stripped in CONFIRM_KEYWORDS:
            # 用户确认
            print(f"[dingtalk-stream] 用户确认执行: {confirmed_action}")
            update_confirmation_status(confirmation_id, "confirmed")

            # 更新状态并重新执行
            pending_state["confirmation_status"] = "confirmed"
            pending_state["execute_approved"] = True
            pending_state["pending_confirmation"] = False

            # 通过 LangGraph 流程执行
            result_state = self.chat_graph.invoke(pending_state)

            # 提取回复内容
            response_content = result_state.get("response_content", "操作执行完成")
            print(f"[dingtalk-stream] 确认回复长度: {len(response_content)} 字符")

            self.reply_markdown("执行结果", response_content, message)
            return AckMessage.STATUS_OK, "confirmed"

        elif content_stripped in CANCEL_KEYWORDS:
            # 用户取消
            print(f"[dingtalk-stream] 用户取消操作: {confirmed_action}")
            update_confirmation_status(confirmation_id, "rejected")

            self.reply_markdown("操作取消", "❌ 操作已取消，未执行。", message)
            return AckMessage.STATUS_OK, "cancelled"

        return AckMessage.STATUS_OK, "unknown"

    async def _handle_alert(self, content: str, message: ChatbotMessage) -> Tuple[int, str]:
        """
        处理告警 JSON 消息

        Args:
            content: 告警 JSON 内容
            message: 钉钉消息对象

        Returns:
            (status_code, response_message) 元组
        """
        try:
            # 解析告警 JSON
            try:
                payload = json.loads(content.strip())
            except json.JSONDecodeError as e:
                self.reply_text(f"告警 JSON 解析失败: {str(e)}", message)
                return AckMessage.STATUS_OK, "parse_error"

            # 发送确认消息
            self.reply_text("收到告警，正在处理...", message)

            # 处理 alerts 字段格式
            if "alerts" in payload:
                alerts_str = payload.get("alerts", "")
                try:
                    alerts_list = json.loads(alerts_str)
                except json.JSONDecodeError:
                    alerts_list = [payload]

                results = []
                for alert in alerts_list:
                    # 转换字段名以匹配 Agent 预期格式
                    normalized = {
                        "projectCode": alert.get("projectCode", 0),
                        "processDefinitionCode": alert.get("processDefinitionCode", 0),
                        "processInstanceId": alert.get("processId", 0),
                        "taskCode": alert.get("taskCode", 0),
                        "taskInstanceId": alert.get("taskInstanceId", 0),
                        "taskType": alert.get("taskType", "UNKNOWN"),
                        "state": alert.get("taskState", "FAILURE"),
                        "host": alert.get("taskHost"),
                        "projectName": alert.get("projectName"),
                        "processName": alert.get("processName"),
                        "taskName": alert.get("taskName"),
                        "workerGroup": alert.get("workerGroup"),
                        "logPath": alert.get("logPath"),
                        "taskEndTime": alert.get("taskEndTime"),
                    }

                    print(f"[dingtalk-stream] 处理告警: {normalized}")

                    # Execute LangGraph workflow
                    result = self.alert_workflow.run(normalized)

                    # 保存执行结果供用户反馈
                    user_id = message.sender_staff_id or "unknown"
                    if result.get("execution_success") and result.get("knowledge_entry_id"):
                        task_name = normalized.get("taskName", "unknown")
                        save_recent_execution(
                            user_id=user_id,
                            entry_id=result.get("knowledge_entry_id"),
                            task_name=task_name,
                        )
                        print(f"[dingtalk-stream] 保存执行结果: entry_id={result.get('knowledge_entry_id')}")

                    results.append({
                        "project_valid": result.get("project_valid"),
                        "risk_level": result.get("risk_level"),
                        "approval_required": result.get("approval_required"),
                        "execution_success": result.get("execution_success"),
                    })

                # 发送处理结果摘要
                success_count = sum(1 for r in results if r.get("execution_success"))
                total_count = len(results)

                result_msg = f"告警处理完成\n处理数量: {total_count}\n成功: {success_count}"
                self.reply_markdown("告警处理结果", result_msg, message)

                return AckMessage.STATUS_OK, "processed"

            # 单条告警格式
            normalized = {
                "projectCode": payload.get("projectCode", 0),
                "processDefinitionCode": payload.get("processDefinitionCode", 0),
                "processInstanceId": payload.get("processId", payload.get("processInstanceId", 0)),
                "taskCode": payload.get("taskCode", 0),
                "taskInstanceId": payload.get("taskInstanceId", 0),
                "taskType": payload.get("taskType", "UNKNOWN"),
                "state": payload.get("taskState", payload.get("state", "FAILURE")),
                "host": payload.get("host") or payload.get("taskHost"),
                "projectName": payload.get("projectName"),
                "processName": payload.get("processName"),
                "taskName": payload.get("taskName"),
                "workerGroup": payload.get("workerGroup"),
                "logPath": payload.get("logPath"),
            }

            print(f"[dingtalk-stream] 处理单条告警: {normalized}")

            # Execute workflow
            result = self.alert_workflow.run(normalized)

            # 保存执行结果供用户反馈
            user_id = message.sender_staff_id or "unknown"
            if result.get("execution_success") and result.get("knowledge_entry_id"):
                task_name = normalized.get("taskName", "unknown")
                save_recent_execution(
                    user_id=user_id,
                    entry_id=result.get("knowledge_entry_id"),
                    task_name=task_name,
                )
                print(f"[dingtalk-stream] 保存执行结果: entry_id={result.get('knowledge_entry_id')}")

            # 发送处理结果
            result_msg = f"告警处理完成\n风险等级: {result.get('risk_level', 'unknown')}\n状态: {'成功' if result.get('execution_success') else '需审批'}"
            self.reply_markdown("告警处理结果", result_msg, message)

            return AckMessage.STATUS_OK, "processed"

        except Exception as e:
            traceback.print_exc()
            self.reply_text(f"告警处理出错: {str(e)}", message)
            return AckMessage.STATUS_OK, "error"


class DingTalkStreamClient:
    """
    钉钉 Stream 客户端封装

    启动后持续从钉钉服务器拉取消息
    SDK 内置断线重连和心跳保活机制

    内置功能:
    - 审批超时定时检查（后台线程，每60秒检查一次）
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.client_id = client_id or settings.DINGTALK_CLIENT_ID
        self.client_secret = client_secret or settings.DINGTALK_CLIENT_SECRET
        self.approval_tool = ApprovalTool()
        self.alert_workflow = AlertWorkflowGraph()
        self._running = False

        if not self.client_id or not self.client_secret:
            raise ValueError("钉钉 Stream 模式需要配置 DINGTALK_CLIENT_ID 和 DINGTALK_CLIENT_SECRET")

    def _check_approval_timeout(self):
        """
        定时检查审批超时（后台线程）

        每60秒检查一次，对超时的审批请求:
        1. 更新状态为 timeout
        2. 发送超时通知
        """
        while self._running:
            try:
                # 检查过期请求
                expired_ids = self.approval_tool.check_expired()

                for request_id in expired_ids:
                    print(f"[dingtalk-stream] 审批超时: {request_id}")

                    # 更新状态
                    self.approval_tool.update_status(request_id, "timeout")

                    # 获取请求详情并继续工作流
                    request = self.approval_tool.get_request(request_id)
                    if request and request.workflow_state:
                        # 继续工作流（发送超时通知）
                        self.alert_workflow.continue_from_approval(
                            request.workflow_state,
                            "timeout"
                        )

            except Exception as e:
                print(f"[dingtalk-stream] 审批超时检查异常: {e}")

            # 每60秒检查一次
            time.sleep(60)

    def run(self):
        """
        启动 Stream 客户端

        SDK 使用 start_forever() 自动处理：
        - WebSocket 心跳保活 (ping_interval=60)
        - 断线自动重连
        - 网络异常恢复

        同时启动审批超时检查后台线程
        """
        self._running = True

        # 启动审批超时检查后台线程
        timeout_thread = threading.Thread(
            target=self._check_approval_timeout,
            daemon=True,
            name="approval_timeout_checker"
        )
        timeout_thread.start()

        print("=" * 60)
        print("DingTalk Stream Client 启动")
        print("=" * 60)
        print(f"Client ID: {self.client_id}")
        print()
        print("SDK 自动机制:")
        print("  - 心跳保活: 60秒间隔")
        print("  - 断线重连: 自动恢复")
        print()
        print("后台任务:")
        print("  - 审批超时检查: 每60秒")
        print(f"  - 审批超时时间: {settings.APPROVAL_TIMEOUT_MINUTES} 分钟")
        print()
        print("等待消息...")
        print("-" * 60)

        # 创建凭证
        credential = dingtalk_stream.Credential(self.client_id, self.client_secret)

        # 创建 Stream 客户端
        client = dingtalk_stream.DingTalkStreamClient(credential)

        # 注册聊天机器人处理器
        client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
            DingTalkStreamHandler(),
        )

        # 启动客户端（永久运行，自动重连）
        client.start_forever()


__all__ = [
    "DingTalkStreamClient",
    "DingTalkStreamHandler",
    "is_alert_json",
    "save_recent_execution",
    "get_recent_execution",
]