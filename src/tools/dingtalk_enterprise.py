"""
DingTalkEnterpriseTool - 钉钉企业机器人工具

使用 Client ID + Client Secret 获取 access_token，发送消息
"""

import time
import json
import requests
from typing import Dict, List, Optional


class DingTalkError(Exception):
    """钉钉 API 错误"""
    pass


class DingTalkEnterpriseTool:
    """
    钉钉企业机器人

    认证流程:
    1. 使用 Client ID + Client Secret 获取 access_token
    2. 使用 access_token 调用消息发送 API
    """

    TOKEN_API = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    MESSAGE_API = "https://api.dingtalk.com/v1.0/robot/oToMessages"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
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
                "clientId": self.client_id,
                "clientSecret": self.client_secret,
            },
            timeout=10,
        )

        if response.status_code != 200:
            raise DingTalkError(f"获取 access_token 失败: {response.text}")

        data = response.json()
        self.access_token = data.get("accessToken", "")
        expire_in = data.get("expireIn", 7200)
        self.token_expire_time = time.time() + expire_in

        return self.access_token

    def send_notification(
        self,
        robot_code: str,
        user_ids: List[str],
        title: str,
        content: str,
        buttons: Optional[List[Dict]] = None,
    ) -> str:
        """
        发送通知

        Args:
            robot_code: 机器人编码
            user_ids: 接收用户 ID 列表
            title: 标题
            content: Markdown 内容
            buttons: 可选按钮列表

        Returns:
            消息 ID
        """
        access_token = self._get_access_token()

        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        }

        # 构建消息参数
        msg_param = {
            "title": title,
            "text": content,
        }

        if buttons:
            msg_param["btns"] = buttons

        payload = {
            "robotCode": robot_code,
            "userIds": user_ids,
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(msg_param),
        }

        response = requests.post(
            self.MESSAGE_API,
            headers=headers,
            json=payload,
            timeout=10,
        )

        if response.status_code != 200:
            raise DingTalkError(f"发送消息失败: {response.text}")

        data = response.json()
        return data.get("processQueryKeys", "")

    def build_error_notification(
        self,
        task_type: str,
        workflow_name: str,
        workflow_code: str,
        task_name: str,
        task_code: str,
        project_name: str,
        risk_level: str,
        error_category: str,
        error_patterns: List[str],
        error_description: str,
        suggested_actions: List[Dict],
        execution_results: List[Dict],
        execution_success: bool,
        ds_url: str,
    ) -> Dict:
        """构建错误通知内容（增强版）"""
        title = f"DolphinScheduler Agent 执行结果"

        # 执行状态图标
        status_icon = "✅ 成功" if execution_success else "❌ 失败"

        # 构建执行结果部分
        exec_result_text = ""
        if execution_results:
            for r in execution_results:
                action_type = r.get("action", {}).get("action_type", "unknown")
                status = r.get("status", "unknown")
                output = r.get("output", "")[:100] if r.get("output") else ""
                exec_result_text += f"- **{action_type}**: {status}\n"
                if output:
                    exec_result_text += f"  输出: {output}\n"

        # 构建修复动作部分
        actions_text = ""
        for a in suggested_actions:
            action_type = a.get("action_type", "unknown")
            config_changes = a.get("config_changes", {})
            if config_changes:
                actions_text += f"- **{action_type}**: {json.dumps(config_changes)}\n"
            else:
                actions_text += f"- **{action_type}**: {a.get('description', '')}\n"

        content = f"""## {status_icon}

**项目:** {project_name} ({workflow_code[:8]}...)
**工作流:** {workflow_name}
**任务:** {task_name}

---

### 错误分析
- **类型:** {task_type}
- **分类:** {error_category}
- **风险等级:** {risk_level}
- **错误模式:** {', '.join(error_patterns[:3]) or '未识别'}

### 错误描述
{error_description[:200] or '无详细信息'}

---

### 修复动作
{actions_text or '无建议动作'}

### 执行结果
{exec_result_text or '未执行'}

---
[查看工作流]({ds_url}/#/workflow/{workflow_code})
"""

        return {
            "title": title,
            "content": content,
            "single_url": f"{ds_url}/#/workflow/{workflow_code}",
        }

    def build_approval_request(
        self,
        task_type: str,
        workflow_code: str,
        task_code: str,
        risk_level: str,
        impact_summary: str,
        suggested_actions: List[Dict],
        risk_factors: List[str],
        approve_url: str,
        reject_url: str,
    ) -> Dict:
        """构建审批请求内容"""
        title = f"需要审批: {risk_level} 风险"

        content = f"""## 动作审批请求

**工作流:** {workflow_code}
**任务:** {task_code}
**类型:** {task_type}
**风险等级:** {risk_level}

### 影响摘要
{impact_summary}

### 提议的动作
{chr(10).join(f'- {a.get("description", a.get("action_type", "unknown"))}' for a in suggested_actions)}

### 风险因素
{chr(10).join(f'- {f}' for f in risk_factors)}

请批准或拒绝这些动作。
"""

        buttons = [
            {"title": "批准", "actionUrl": approve_url},
            {"title": "拒绝", "actionUrl": reject_url},
        ]

        return {
            "title": title,
            "content": content,
            "buttons": buttons,
        }


__all__ = ["DingTalkEnterpriseTool", "DingTalkError"]