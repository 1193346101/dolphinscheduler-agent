"""
钉钉机器人集成
"""

import hmac
import hashlib
import base64
import time
import urllib.parse
from typing import Optional
import requests

from ..config import settings


class DingTalkNotifier:
    """
    钉钉机器人通知

    支持:
    - 文本消息
    - Markdown 消息
    - ActionCard 消息（带按钮）
    """

    def __init__(self):
        self.webhook = settings.DINGTALK_WEBHOOK
        self.secret = settings.DINGTALK_SECRET

    def _sign(self) -> tuple[str, str]:
        """生成签名"""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def _send(self, message: dict) -> bool:
        """发送消息"""
        if not self.webhook:
            return False

        url = self.webhook
        if self.secret:
            timestamp, sign = self._sign()
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        try:
            resp = requests.post(
                url,
                json=message,
                timeout=10,
            )
            return resp.json().get("errcode") == 0
        except Exception:
            return False

    def send_text(self, content: str) -> bool:
        """发送文本消息"""
        return self._send({
            "msgtype": "text",
            "text": {"content": content},
        })

    def send_markdown(self, title: str, text: str) -> bool:
        """发送 Markdown 消息"""
        return self._send({
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
        })

    def send_action_card(
        self,
        title: str,
        text: str,
        buttons: list[dict],
        btn_orientation: str = "1",
    ) -> bool:
        """
        发送 ActionCard 消息（带按钮）

        Args:
            title: 标题
            text: Markdown 内容
            buttons: 按钮列表 [{"title": "按钮名", "actionURL": "链接"}]
            btn_orientation: 0 纵向，1 横向

        Returns:
            是否成功
        """
        return self._send({
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": text,
                "btnOrientation": btn_orientation,
                "btns": buttons,
            },
        })

    def notify_alert(
        self,
        alert_info: dict,
        analysis: dict,
        fix_result: Optional[dict] = None,
    ) -> bool:
        """发送告警通知"""
        title = f"DolphinScheduler 任务告警 - {alert_info.get('taskType', 'UNKNOWN')}"

        # 错误信息截取前 100 字符
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
                {"title": "批准 ✓", "actionURL": approval_info.get("approve_url", "")},
                {"title": "拒绝 ✗", "actionURL": approval_info.get("reject_url", "")},
            ],
        )


__all__ = ["DingTalkNotifier"]