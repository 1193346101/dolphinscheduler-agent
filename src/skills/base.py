"""
Skill 基类

○ 不是 Agent，使用预定义规则
○ 不使用 LLM 进行决策
"""

from abc import ABC, abstractmethod
from typing import Optional
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext


class BaseSkill(ABC):
    """
    Skill 基类

    每个 Skill 必须实现:
    1. analyze(): 分析错误原因（预定义规则，不使用 LLM）
    2. suggest(): 给出修复建议
    3. can_auto_fix(): 判断是否可以自动修复
    """

    skill_name: str = ""
    task_types: list[str] = []

    # 预定义的错误模式
    error_patterns: dict[str, str] = {}

    # 预定义的建议模板
    suggestion_templates: dict[str, str] = {}

    # 可自动修复的错误类型
    auto_fixable_errors: list[str] = []

    @abstractmethod
    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析日志内容

        使用预定义规则进行模式匹配，不使用 LLM

        Args:
            log_content: 日志内容
            context: 告警上下文

        Returns:
            ErrorAnalysis 分析结果
        """
        pass

    def suggest(self, analysis: ErrorAnalysis) -> list[str]:
        """
        给出修复建议

        Args:
            analysis: 错误分析结果

        Returns:
            建议列表
        """
        if analysis.error_type in self.suggestion_templates:
            return [self.suggestion_templates[analysis.error_type]]
        return ["请联系运维人员查看"]

    def can_auto_fix(self, analysis: ErrorAnalysis) -> bool:
        """
        判断是否可以自动修复

        Args:
            analysis: 错误分析结果

        Returns:
            是否可以自动修复
        """
        return analysis.error_type in self.auto_fixable_errors

    def get_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """
        获取自动修复动作

        Args:
            analysis: 错误分析结果

        Returns:
            AutoFixAction 或 None
        """
        if not self.can_auto_fix(analysis):
            return None
        return self._build_auto_fix_action(analysis)

    def _build_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """构建自动修复动作（子类实现）"""
        return None

    def get_risk_level(self, analysis: ErrorAnalysis) -> RiskLevel:
        """
        获取修复风险等级

        Args:
            analysis: 错误分析结果

        Returns:
            RiskLevel
        """
        # 配置修改为低风险，可自动执行
        # 脚本修改为中等风险，需人工确认
        if self.can_auto_fix(analysis):
            # 判断修复类型
            action = self._build_auto_fix_action(analysis)
            if action and action.action_type == "modify_config":
                return RiskLevel.LOW  # 配置修改可自动执行
            elif action and action.action_type == "modify_script":
                return RiskLevel.MEDIUM  # 脚本修改需确认
            return RiskLevel.LOW
        return RiskLevel.HIGH


__all__ = ["BaseSkill"]