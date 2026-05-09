"""
钉钉机器人进度通知

支持两种方式：
1. Webhook 机器人（推荐，简单可靠）
2. 企业机器人（Client ID + Client Secret）
"""

import time
import json
import requests
from typing import Dict, Optional


class DingTalkWebhookNotifier:
    """钉钉 Webhook 机器人通知器（简单可靠）"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_text(self, content: str) -> bool:
        """发送文本消息"""
        if not self.webhook_url:
            print("[WARN] 钉钉 Webhook URL 未配置，跳过通知")
            return False

        try:
            data = {
                "msgtype": "text",
                "text": {"content": content}
            }
            response = requests.post(self.webhook_url, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    print(f"[OK] 钉钉消息发送成功")
                    return True
                else:
                    print(f"[WARN] 钉钉消息发送失败: {result}")
                    return False
            else:
                print(f"[WARN] 钉钉消息发送失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"[WARN] 钉钉通知异常: {e}")
            return False

    def send_markdown(self, title: str, text: str) -> bool:
        """发送 Markdown 消息"""
        if not self.webhook_url:
            return False

        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": text
                }
            }
            response = requests.post(self.webhook_url, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                return result.get("errcode") == 0
            return False
        except Exception:
            return False

    def send_action_card(self, title: str, text: str, buttons: list) -> bool:
        """
        发送 ActionCard 消息（带按钮）

        Args:
            title: 标题
            text: 内容
            buttons: 按钮列表，格式 [{"title": "按钮名", "actionURL": "链接"}]
        """
        if not self.webhook_url:
            return False

        try:
            data = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "btnOrientation": "1",  # 横向排列按钮
                    "btns": buttons
                }
            }
            response = requests.post(self.webhook_url, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    print(f"[OK] 钉钉 ActionCard 发送成功: {title}")
                    return True
                else:
                    print(f"[WARN] 钉钉 ActionCard 发送失败: {result}")
                    return False
            return False
        except Exception as e:
            print(f"[WARN] ActionCard 发送异常: {e}")
            return False

    def send_approval_request(self, approval_id: str, tool_name: str, command: str, risk_level: str = "MEDIUM") -> bool:
        """
        发送审批请求消息（带按钮）

        Args:
            approval_id: 审批 ID
            tool_name: 工具名称
            command: 要执行的命令
            risk_level: 风险等级
        """
        # 审批 API 地址
        base_url = "http://localhost:8080/approval"

        title = f"权限请求 - {tool_name}"

        text = f"## Agent 权限请求\n\n"
        text += f"**工具:** {tool_name}\n\n"
        text += f"**命令:**\n```\n{command}\n```\n\n"
        text += f"**风险等级:** {risk_level}\n\n"
        text += "---\n\n"
        text += "请选择操作："

        buttons = [
            {
                "title": "✅ 允许",
                "actionURL": f"{base_url}?id={approval_id}&action=allow"
            },
            {
                "title": "❌ 拒绝",
                "actionURL": f"{base_url}?id={approval_id}&action=deny"
            }
        ]

        return self.send_action_card(title, text, buttons)

    def send_alert_received(self, project_name: str, workflow_name: str, task_name: str, task_type: str, error_time: str, error_type: str = None, error_summary: str = None) -> bool:
        """
        发送告警接收通知（包含错误分析信息）

        Args:
            project_name: 项目名称
            workflow_name: 工作流名称
            task_name: 任务名称
            task_type: 任务类型
            error_time: 错误时间
            error_type: 错误类型（如 syntax_error, resource_error）
            error_summary: 错误摘要描述
        """
        title = f"告警接收 - {task_name}"

        text = f"## DolphinScheduler 任务告警\n\n"
        text += f"**项目:** {project_name}\n\n"
        text += f"**工作流:** {workflow_name}\n\n"
        text += f"**任务:** {task_name}\n\n"
        text += f"**类型:** {task_type}\n\n"
        text += f"**时间:** {error_time}\n\n"

        if error_type:
            text += f"**错误类型:** {error_type}\n\n"

        if error_summary:
            text += f"**错误摘要:**\n{error_summary}\n\n"

        text += "---\n\n"
        text += "🤖 Agent 正在分析并处理..."

        return self.send_markdown(title, text)

    def send_execution_result(self, project_name: str, workflow_name: str, task_name: str, success: bool, message: str, error_type: str = None, script_changes: Dict = None, confidence: float = None, action_type: str = None, knowledge_entry_id: str = None) -> bool:
        """
        发送执行结果通知（包含完整的修复信息和知识库确认按钮）

        Args:
            project_name: 项目名称
            workflow_name: 工作流实例名称
            task_name: 任务节点名称
            success: 是否成功
            message: 结果消息
            error_type: 错误类型
            script_changes: 脚本修改内容 {原始内容: 修复内容}
            confidence: 置信度
            action_type: 执行动作类型
            knowledge_entry_id: 知识库条目 ID（用于确认反馈）
        """
        status = "✅ 成功" if success else "❌ 失败"
        title = f"执行结果 - {task_name}"

        text = f"## DolphinScheduler Agent 执行结果\n\n"
        text += f"| 项目 | 工作流实例 | 任务节点名称 |\n"
        text += f"| --- | --- | --- |\n"
        text += f"| {project_name} | {workflow_name} | {task_name} |\n\n"
        text += f"**执行状态:** {status}\n\n"

        if error_type:
            text += f"**错误类型:** `{error_type}`\n\n"

        if action_type:
            text += f"**执行动作:** {action_type}\n\n"

        if confidence:
            text += f"**修复置信度:** {confidence:.2%}\n\n"

        if script_changes:
            text += "**脚本修复详情:**\n\n"
            for original, fixed in script_changes.items():
                # 简化显示，只显示差异部分
                text += f"- ❌ 原始: `{original[:80]}{'...' if len(original) > 80 else ''}`\n"
                text += f"- ✅ 修复: `{fixed[:80]}{'...' if len(fixed) > 80 else ''}`\n\n"

        text += "---\n\n"
        text += f"**执行详情:**\n{message}\n\n"
        text += "---\n\n"

        if success and confidence and knowledge_entry_id:
            # 添加知识库确认提示
            text += "💡 **知识库反馈**\n\n"
            text += "请确认修复是否正确，帮助 Agent 学习改进：\n"
            text += "- 如修复正确，请回复 ✅\n"
            text += "- 如修复错误，请回复 ❌ 并说明正确做法"

            # 尝试发送带按钮的 ActionCard（如果支持）
            buttons = [
                {
                    "title": "✅ 修复正确",
                    "actionURL": f"http://localhost:8080/feedback?entry_id={knowledge_entry_id}&feedback=valid"
                },
                {
                    "title": "❌ 修复错误",
                    "actionURL": f"http://localhost:8080/feedback?entry_id={knowledge_entry_id}&feedback=invalid"
                }
            ]

            # 尝试发送 ActionCard，如果失败则发送 Markdown
            if self.send_action_card(title, text, buttons):
                return True

        return self.send_markdown(title, text)

    def send_progress(self, step: int, total: int, node_name: str, details: Dict) -> bool:
        """发送进度通知"""
        title = f"Agent [{step}/{total}] {node_name}"

        content = f"## DolphinScheduler Agent 处理进度\n\n"
        content += f"**步骤 [{step}/{total}]:** {node_name}\n\n"
        content += "---\n\n"

        for key, value in details.items():
            content += f"- **{key}:** {value}\n"

        return self.send_markdown(title, content)

    def send_final_result(self, result: Dict) -> bool:
        """发送最终处理结果"""
        title = "Agent 处理完成"

        content = f"## DolphinScheduler Agent 处理结果\n\n"
        content += f"**状态:** {result.get('status', 'unknown')}\n\n"
        content += "---\n\n"

        for key, value in result.items():
            if key != "status":
                content += f"- **{key}:** {value}\n"

        return self.send_markdown(title, content)


class DingTalkEnterpriseNotifier:
    """钉钉企业机器人通知器（群消息）"""

    TOKEN_API = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    GROUP_MESSAGE_API = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"

    def __init__(self, client_id: str, client_secret: str, robot_code: str, group_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.robot_code = robot_code
        self.group_id = group_id
        self.access_token: Optional[str] = None
        self.token_expire_time: float = 0

    def _get_access_token(self) -> str:
        """获取企业机器人 access_token"""
        # 检查 token 是否过期，提前 5 分钟刷新
        if self.access_token and time.time() < self.token_expire_time - 300:
            return self.access_token

        response = requests.post(
            self.TOKEN_API,
            headers={"Content-Type": "application/json"},
            json={
                "appKey": self.client_id,
                "appSecret": self.client_secret,
            },
            timeout=10,
        )

        if response.status_code != 200:
            raise Exception(f"获取 access_token 失败: {response.text}")

        data = response.json()
        self.access_token = data.get("accessToken", "")
        expire_in = data.get("expireIn", 7200)
        self.token_expire_time = time.time() + expire_in

        return self.access_token

    def send_progress(self, step: int, total: int, node_name: str, details: Dict) -> bool:
        """发送进度通知到群（企业机器人方式）"""
        if not self.client_id or not self.client_secret or not self.group_id:
            print("[WARN] 钉钉企业机器人配置不完整，跳过通知")
            return False

        title = f"Agent [{step}/{total}] {node_name}"

        content = f"## DolphinScheduler Agent 处理进度\n\n"
        content += f"**步骤 [{step}/{total}]:** {node_name}\n\n"
        content += "---\n\n"

        for key, value in details.items():
            content += f"- **{key}:** {value}\n"

        try:
            access_token = self._get_access_token()

            headers = {
                "Content-Type": "application/json",
                "x-acs-dingtalk-access-token": access_token,
            }

            msg_param = {
                "title": title,
                "text": content,
            }

            payload = {
                "robotCode": self.robot_code,
                "openConversationId": self.group_id,
                "msgKey": "sampleActionCard",
                "msgParam": json.dumps(msg_param),
            }

            response = requests.post(
                self.GROUP_MESSAGE_API,
                headers=headers,
                json=payload,
                timeout=10,
            )

            if response.status_code == 200:
                print(f"[OK] 钉钉群消息发送成功: {title}")
                return True
            else:
                print(f"[WARN] 钉钉群消息发送失败: {response.text}")
                return False

        except Exception as e:
            print(f"[WARN] 钉钉通知异常: {e}")
            return False


def get_notifier_from_settings():
    """从配置创建通知器（优先使用 Webhook）"""
    from ..config import settings

    # 优先使用 Webhook（简单可靠）
    if settings.DINGTALK_WEBHOOK_URL:
        return DingTalkWebhookNotifier(webhook_url=settings.DINGTALK_WEBHOOK_URL)

    # 否则使用企业机器人
    return DingTalkEnterpriseNotifier(
        client_id=settings.DINGTALK_CLIENT_ID,
        client_secret=settings.DINGTALK_CLIENT_SECRET,
        robot_code=settings.DINGTALK_ROBOT_CODE,
        group_id=settings.DINGTALK_GROUP_ID,
    )


__all__ = ["DingTalkWebhookNotifier", "DingTalkEnterpriseNotifier", "get_notifier_from_settings"]