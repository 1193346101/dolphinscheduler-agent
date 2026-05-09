"""
钉钉企业机器人集成

使用 Client ID + Client Secret 认证
"""

import time
import json
import requests
from typing import Optional, List

from ..config import settings


class DingTalkNotifier:
    """
    钉钉企业机器人通知

    使用企业机器人 API 发送群消息
    """

    TOKEN_API = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    GROUP_MESSAGE_API = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"

    def __init__(self):
        self.client_id = settings.DINGTALK_CLIENT_ID
        self.client_secret = settings.DINGTALK_CLIENT_SECRET
        self.robot_code = settings.DINGTALK_ROBOT_CODE
        self.group_id = settings.DINGTALK_GROUP_ID
        self.access_token: Optional[str] = None
        self.token_expire_time: float = 0

    def _get_access_token(self) -> str:
        """获取企业机器人 access_token"""
        # 检查 token 是否过期
        if self.access_token and time.time() < self.token_expire_time - 300:
            return self.access_token

        if not self.client_id or not self.client_secret:
            raise ValueError("钉钉企业机器人配置不完整")

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

    def _send_message(self, msg_key: str, msg_param: dict) -> bool:
        """发送群消息"""
        if not self.robot_code or not self.group_id:
            return False

        try:
            access_token = self._get_access_token()

            headers = {
                "Content-Type": "application/json",
                "x-acs-dingtalk-access-token": access_token,
            }

            payload = {
                "robotCode": self.robot_code,
                "openConversationId": self.group_id,
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param),
            }

            response = requests.post(
                self.GROUP_MESSAGE_API,
                headers=headers,
                json=payload,
                timeout=10,
            )

            if response.status_code == 200:
                print(f"[OK] 钉钉群消息发送成功")
                return True
            else:
                print(f"[WARN] 钉钉群消息发送失败: {response.text}")
                return False

        except Exception as e:
            print(f"[WARN] 钉钉群消息异常: {e}")
            return False

    def send_text(self, content: str) -> bool:
        """发送文本消息"""
        return self._send_message("sampleText", {"content": content})

    def send_markdown(self, title: str, text: str) -> bool:
        """发送 Markdown 消息"""
        return self._send_message("sampleMarkdown", {"title": title, "text": text})

    def send_action_card(
        self,
        title: str,
        text: str,
        buttons: list[dict],
    ) -> bool:
        """发送 ActionCard 消息"""
        return self._send_message("sampleActionCard", {
            "title": title,
            "text": text,
            "btns": buttons,
        })

    def notify_alert(
        self,
        alert_info: dict,
        analysis: dict,
        fix_result: Optional[dict] = None,
    ) -> bool:
        """发送告警通知"""
        title = f"DolphinScheduler 任务告警 - {alert_info.get('taskType', 'UNKNOWN')}"

        error_msg = analysis.get('error_message', 'N/A')
        if error_msg and len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."

        text = f"""### 任务失败告警

**项目**: {alert_info.get('projectName') or 'N/A'}
**工作流**: {alert_info.get('processDefinitionName') or 'N/A'}
**任务**: {alert_info.get('taskName') or 'N/A'}
**类型**: {alert_info.get('taskType') or 'N/A'}
**失败时间**: {alert_info.get('endTime') or 'N/A'}

---

### 错误分析

**错误类型**: {analysis.get('error_type', 'unknown')}
**错误信息**: {error_msg}

---

### 处理结果

"""

        if fix_result:
            if fix_result.get('status') == 'auto_fixed':
                text += f"""**状态**: 自动修复成功
**修复动作**: {fix_result.get('fix_action', 'N/A')}
"""
            elif fix_result.get('status') == 'approval_required':
                suggestion = fix_result.get('fix_suggestion')
                if suggestion:
                    text += f"""**状态**: 需审批确认
**建议修复**: {suggestion.get('action_type', 'N/A')}
**变更内容**: {suggestion.get('changes', 'N/A')}
"""
                else:
                    text += "**状态**: 需人工处理\n"
            else:
                text += f"""**状态**: {fix_result.get('status', 'N/A')}
"""
        else:
            text += "**状态**: 需人工处理\n"

        return self.send_markdown(title, text)

    def notify_approval_request(
        self,
        approval_info: dict,
    ) -> bool:
        """发送审批请求通知"""
        return self.send_action_card(
            title="操作审批请求",
            text=f"""### 待审批操作

**操作类型**: {approval_info.get('operation_type', 'N/A')}
**风险等级**: {approval_info.get('risk_level', 'N/A')}
**内容**: {approval_info.get('content', 'N/A')}
**影响范围**: {approval_info.get('impact', 'N/A')}

请确认是否执行此操作。
""",
            buttons=[
                {"title": "批准", "actionURL": approval_info.get("approve_url", "")},
                {"title": "拒绝", "actionURL": approval_info.get("reject_url", "")},
            ],
        )


__all__ = ["DingTalkNotifier"]