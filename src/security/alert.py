"""
安全告警模块
"""

from typing import Optional
from datetime import datetime


class SecurityAlert:
    """安全告警发送器"""

    def __init__(self):
        from ..integrations.dingtalk import DingTalkNotifier
        self.notifier = DingTalkNotifier()

    def send_high_risk_alert(
        self,
        operation_type: str,
        operation_detail: str,
        result: str,
        risk_level: str,
        reason: Optional[str] = None,
    ) -> bool:
        """发送高风险操作告警

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            result: 执行结果 (blocked/failed/success)
            risk_level: 风险等级
            reason: 原因/说明

        Returns:
            发送是否成功
        """
        # 根据结果确定标题
        if result == "blocked":
            title = "⛔ 禁止操作拦截"
            footer = "💡 此操作已被安全策略拦截，如需执行请联系管理员审核。"
        elif result == "failed":
            title = "⚠️ 高风险操作失败"
            footer = "💡 此操作已被审计日志记录，请确认操作合规。"
        else:  # success
            title = "🔴 高风险操作执行"
            footer = "💡 此操作已被审计日志记录，请确认操作合规。"

        # 格式化时间
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建 Markdown 内容
        content = f"""### {title}

**操作类型**: {operation_type}
**操作详情**: {operation_detail}
**执行结果**: {result}
**风险等级**: {risk_level}
**时间**: {timestamp}
"""
        if reason:
            content += f"\n**原因/说明**: {reason}\n"

        content += f"\n---\n{footer}"

        return self.notifier.send_markdown(title, content)

    def send_blocked_alert(
        self,
        operation_type: str,
        operation_detail: str,
        reason: str,
    ) -> bool:
        """发送禁止操作拦截告警（CRITICAL）

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            reason: 拦截原因

        Returns:
            发送是否成功
        """
        return self.send_high_risk_alert(
            operation_type=operation_type,
            operation_detail=operation_detail,
            result="blocked",
            risk_level="CRITICAL",
            reason=reason,
        )

    def send_high_risk_execution_alert(
        self,
        operation_type: str,
        operation_detail: str,
        result: str,
        error: Optional[str] = None,
    ) -> bool:
        """发送高风险执行告警（HIGH）

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            result: 执行结果 (success/failed)
            error: 错误信息（如果失败）

        Returns:
            发送是否成功
        """
        return self.send_high_risk_alert(
            operation_type=operation_type,
            operation_detail=operation_detail,
            result=result,
            risk_level="HIGH",
            reason=error,
        )


__all__ = ["SecurityAlert"]