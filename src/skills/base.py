"""
Skill 基类

Skill 是"快速预判器"：
- 快速匹配已知错误模式
- AUTO_FIXABLE 类型直接返回修复方案
- KNOWN_NEEDS_LLM 类型给 LLM 提供上下文提示
- UNKNOWN 类型完全交给 LLM

LLM 是"深度分析师"：
- 对 KNOWN_NEEDS_LLM 进行具体定位和原因分析
- 对 UNKNOWN 进行完全分析
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext


class BaseSkill(ABC):
    """
    Skill 基类

    每个 Skill 是特定任务类型的错误专家：
    - 快速识别常见错误模式
    - 对可自动修复的错误直接给出方案
    - 对需要推理的错误给 LLM 提供上下文
    """

    skill_name: str = ""
    task_types: list[str] = []

    @abstractmethod
    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析日志内容

        返回三类结果:
        - AUTO_FIXABLE: 已知且可直接修复，返回 quick_fix
        - KNOWN_NEEDS_LLM: 已知类型，返回 llm_hint 供 LLM 分析
        - UNKNOWN: 无匹配，交给 LLM 完全分析

        Args:
            log_content: 日志内容
            context: 告警上下文

        Returns:
            ErrorAnalysis 分析结果
        """
        pass

    def get_risk_level(self, analysis: ErrorAnalysis) -> RiskLevel:
        """
        获取修复风险等级

        AUTO_FIXABLE: 低风险（拼写修正、配置调整）
        其他: 高风险（需人工确认）
        """
        if analysis.category == ErrorCategory.AUTO_FIXABLE:
            return RiskLevel.LOW
        return RiskLevel.HIGH

    def build_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """
        构建自动修复动作（仅 AUTO_FIXABLE 有）

        由具体 Skill 实现
        """
        if analysis.category != ErrorCategory.AUTO_FIXABLE:
            return None

        quick_fix = analysis.quick_fix
        if not quick_fix:
            return None

        action_type = quick_fix.get("action_type")
        if action_type == "modify_script":
            return AutoFixAction(
                action_type="modify_script",
                script_changes=quick_fix.get("script_changes", {}),
                need_recover=True,
            )
        elif action_type == "modify_config":
            return AutoFixAction(
                action_type="modify_config",
                config_changes=quick_fix.get("config_changes", {}),
                need_recover=True,
            )
        elif action_type == "rerun":
            return AutoFixAction(
                action_type="rerun",
                need_recover=True,
            )

        return None


__all__ = ["BaseSkill"]