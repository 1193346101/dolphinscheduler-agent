"""
Skill 基类

Skill 是"快速预判器"：
- 快速匹配已知错误模式
- AUTO_FIXABLE 类型直接返回修复方案
- RESOURCE_SUGGESTED 类型智能计算 + LLM 验证
- KNOWN_NEEDS_LLM 类型给 LLM 提供上下文提示
- UNKNOWN 类型完全交给 LLM

新增能力：
- OSS 文件验证（使用 ossutil 检查文件是否存在）
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .common.oss_validator import OSSValidator, OSSCheckResult, get_oss_validator


class BaseSkill(ABC):
    """
    Skill 基类

    每个 Skill 是特定任务类型的错误专家：
    - 快速识别常见错误模式
    - 对可自动修复的错误直接给出方案
    - 对需要推理的错误给 LLM 提供上下文
    - 支持 OSS 文件验证（检查文件是否存在）
    """

    skill_name: str = ""
    task_types: list[str] = []

    # OSS 验证器（延迟初始化）
    _oss_validator: Optional[OSSValidator] = None

    @abstractmethod
    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析日志内容

        返回四类结果:
        - AUTO_FIXABLE: 已知且可直接修复，返回 quick_fix
        - RESOURCE_SUGGESTED: 资源问题，返回 skill_suggestion + LLM 验证
        - KNOWN_NEEDS_LLM: 已知类型，返回 llm_hint 供 LLM 分析
        - UNKNOWN: 无匹配，交给 LLM 完全分析

        Args:
            log_content: 日志内容
            context: 告警上下文

        Returns:
            ErrorAnalysis 分析结果
        """
        pass

    def get_oss_validator(self) -> Optional[OSSValidator]:
        """
        获取 OSS 验证器实例

        Returns:
            OSSValidator 或 None（如果未配置）
        """
        if self._oss_validator is None:
            self._oss_validator = get_oss_validator()
        return self._oss_validator

    def check_oss_path(self, oss_path: str) -> Optional[OSSCheckResult]:
        """
        检查 OSS 路径是否存在

        Args:
            oss_path: OSS 路径，如 oss://bucket/path/ 或 bucket/path/

        Returns:
            OSSCheckResult 或 None（如果未配置 OSS）
        """
        validator = self.get_oss_validator()
        if validator and validator.is_configured():
            return validator.check_exists(oss_path)
        return None

    def check_oss_partition(self, partition_path: str) -> Optional[OSSCheckResult]:
        """
        检查 OSS 分区路径是否有数据文件

        Args:
            partition_path: 分区路径

        Returns:
            OSSCheckResult 或 None（如果未配置 OSS）
        """
        validator = self.get_oss_validator()
        if validator and validator.is_configured():
            return validator.check_partition(partition_path)
        return None

    def extract_oss_path_from_log(self, log_content: str) -> Optional[str]:
        """
        从日志中提取 OSS 路径

        Args:
            log_content: 日志内容

        Returns:
            OSS 路径或 None
        """
        import re

        # 匹配 oss://bucket/path 格式
        oss_pattern = r'oss://[a-zA-Z0-9\-_]+/[^\s\'"]+'
        match = re.search(oss_pattern, log_content)
        if match:
            return match.group(0)

        # 匹配 /path/to/file 格式（可能是 HDFS/OSS 路径）
        hdfs_pattern = r'(?:hdfs:|file:)?(/[a-zA-Z0-9\-_/]+(?:/[a-zA-Z0-9\-_\.]+)?)'
        match = re.search(hdfs_pattern, log_content)
        if match:
            return match.group(1)

        return None

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