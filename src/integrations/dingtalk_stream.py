"""
钉钉 Stream 模式消息接收器

使用 dingtalk-stream SDK 接收机器人消息，无需公网地址
"""

from typing import Optional, Tuple

import dingtalk_stream
from dingtalk_stream.chatbot import ChatbotMessage, CallbackMessage, AckMessage

from ..config import settings
from ..chat.graph import get_chat_graph
from ..chat.state import create_chat_state


class DingTalkStreamHandler(dingtalk_stream.ChatbotHandler):
    """
    钉钉 Stream 消息处理器

    接收用户发送给机器人的消息，通过 ChatAgent 处理后返回回复
    """

    def __init__(self):
        super().__init__()
        self.chat_graph = get_chat_graph()

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

            print(f"[dingtalk-stream] 收到消息: {content}")
            print(f"[dingtalk-stream] 发送者: {message.sender_staff_id}")

            if not content or not content.strip():
                self.reply_text("请输入有效消息", message)
                return AckMessage.STATUS_OK, "ok"

            # 创建初始状态
            state = create_chat_state(
                message=content,
                user_id=message.sender_staff_id or "unknown",
                conversation_id=message.conversation_id or "unknown",
            )

            # 设置 project_code (从配置中获取默认)
            state["project_code"] = settings.DEFAULT_PROJECT_CODE or "default_project"

            # 通过 LangGraph 流程执行
            result_state = self.chat_graph.invoke(state)

            # 提取回复内容
            response_content = result_state.get("response_content", "处理完成")

            print(f"[dingtalk-stream] 回复长度: {len(response_content)} 字符")

            # 发送 markdown 回复
            self.reply_markdown("查询结果", response_content, message)

            return AckMessage.STATUS_OK, "ok"

        except Exception as e:
            import traceback
            traceback.print_exc()
            # 尝试直接回复
            try:
                message = dingtalk_stream.chatbot.ChatbotMessage.from_dict(callback_message.data)
                self.reply_text(f"处理出错: {str(e)}", message)
            except:
                print(f"[dingtalk-stream] 无法回复: {e}")
            return AckMessage.STATUS_OK, "error"


class DingTalkStreamClient:
    """
    钉钉 Stream 客户端封装

    启动后持续从钉钉服务器拉取消息
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.client_id = client_id or settings.DINGTALK_CLIENT_ID
        self.client_secret = client_secret or settings.DINGTALK_CLIENT_SECRET

        if not self.client_id or not self.client_secret:
            raise ValueError("钉钉 Stream 模式需要配置 DINGTALK_CLIENT_ID 和 DINGTALK_CLIENT_SECRET")

    def run(self):
        """
        启动 Stream 客户端

        持续运行，接收并处理消息
        """
        print("=" * 60)
        print("DingTalk Stream Client 启动")
        print("=" * 60)
        print(f"Client ID: {self.client_id}")
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

        # 启动客户端
        client.start_forever()


__all__ = ["DingTalkStreamClient", "DingTalkStreamHandler"]