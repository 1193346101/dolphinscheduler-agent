"""
RiskAssessTool - 风险评估工具

根据操作类型和下游影响评估风险等级
"""

from typing import Dict, List


class RiskAssessTool:
    """
    风险评估工具

    规则:
    - LOW: 单配置变更、临时重试、无下游影响
    - MEDIUM: 多配置变更、多次重试、下游 <5
    - HIGH: 结构性变更、下游 >5、调度修改
    - CRITICAL: 删除操作、跨项目影响
    """

    def assess(self, suggested_actions: List[Dict], downstream_count: int) -> Dict:
        """
        评估风险等级

        Args:
            suggested_actions: 建议的动作列表
            downstream_count: 下游任务数量

        Returns:
            {
                "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
                "risk_factors": ["factor1", "factor2"],
                "approval_required": bool
            }
        """
        max_risk = "LOW"
        risk_factors = []

        for action in suggested_actions:
            action_risk = self._assess_action(action, downstream_count)
            risk_factors.append(f"{action.get('action_type', 'unknown')}: {action_risk}")

            if self._risk_level_value(action_risk) > self._risk_level_value(max_risk):
                max_risk = action_risk

        return {
            "risk_level": max_risk,
            "risk_factors": risk_factors,
            "approval_required": max_risk in ["HIGH", "CRITICAL"],
        }

    def _assess_action(self, action: Dict, downstream_count: int) -> str:
        """评估单个动作的风险"""
        action_type = action.get("action_type", "")

        # CRITICAL 条件
        if action_type in ["delete", "cross_project"]:
            return "CRITICAL"

        # HIGH 条件
        if action_type == "recover-failed" and downstream_count > 5:
            return "HIGH"
        if action_type == "config-change" and action.get("structural"):
            return "HIGH"

        # MEDIUM 条件
        if action_type == "config-change" and action.get("multi_param"):
            return "MEDIUM"
        if action_type == "rerun" and action.get("retry_count", 0) > 3:
            return "MEDIUM"
        if action_type == "recover-failed" and downstream_count >= 1:
            return "MEDIUM"

        # 默认 LOW
        return "LOW"

    def _risk_level_value(self, level: str) -> int:
        """将风险等级转换为数值"""
        mapping = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        return mapping.get(level, 0)


__all__ = ["RiskAssessTool"]