"""
Skill 基类

Skill 是"快速预判器"：
- 快速匹配已知错误模式
- AUTO_FIXABLE 类型直接返回修复方案
- RESOURCE_SUGGESTED 类型智能计算 + LLM 验证
- KNOWN_NEEDS_LLM 类型给 LLM 提供上下文提示
- UNKNOWN 类型调用 LLM 分析并记录候选

新增能力：
- OSS 文件验证（使用 ossutil 检查文件是否存在）
- UNKNOWN 时自动调用 LLM 并记录新错误候选
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .common.oss_validator import OSSValidator, OSSCheckResult, get_oss_validator
from .common.error_candidates import ErrorCandidateStore, create_candidate_from_llm
from ..tools.llm_client import LLMClient


class BaseSkill(ABC):
    """
    Skill 基类

    每个 Skill 是特定任务类型的错误专家：
    - 快速识别常见错误模式
    - 对可自动修复的错误直接给出方案
    - 对需要推理的错误给 LLM 提供上下文
    - 支持 OSS 文件验证（检查文件是否存在）
    - UNKNOWN 时调用 LLM 分析并记录候选（供人工审核）
    """

    skill_name: str = ""
    task_types: list[str] = []

    # OSS 验证器（延迟初始化）
    _oss_validator: Optional[OSSValidator] = None

    # LLM 客户端（延迟初始化）
    _llm_client: Optional[LLMClient] = None

    # 候选存储（延迟初始化）
    _candidate_store: Optional[ErrorCandidateStore] = None

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

    def get_llm_client(self) -> Optional[LLMClient]:
        """
        获取 LLM 客户端实例

        Returns:
            LLMClient 或 None（如果未配置）
        """
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def get_candidate_store(self) -> ErrorCandidateStore:
        """
        获取候选存储实例

        Returns:
            ErrorCandidateStore
        """
        if self._candidate_store is None:
            self._candidate_store = ErrorCandidateStore()
        return self._candidate_store

    def analyze_with_llm_fallback(
        self,
        log_content: str,
        initial_analysis: ErrorAnalysis,
        context: AlertContext,
        enable_candidate_record: bool = True
    ) -> ErrorAnalysis:
        """
        UNKNOWN 时调用 LLM 分析并记录候选

        Args:
            log_content: 原始日志内容
            initial_analysis: Skill 初步分析结果（通常是 UNKNOWN）
            context: 告警上下文
            enable_candidate_record: 是否记录新错误候选

        Returns:
            增强的 ErrorAnalysis（包含 LLM 分析结果）
        """
        # 只有 UNKNOWN 才需要 LLM fallback
        if initial_analysis.category != ErrorCategory.UNKNOWN:
            return initial_analysis

        # 获取 LLM 客户端
        llm_client = self.get_llm_client()
        if not llm_client:
            # LLM 未配置，返回原始结果
            return initial_analysis

        # 构建 Skill 结果供 LLM 参考
        skill_result = {
            "error_type": initial_analysis.error_type,
            "category": initial_analysis.category.value,
            "llm_hint": initial_analysis.llm_hint,
        }

        # 调用 LLM 分析
        try:
            llm_result = llm_client.analyze(
                log_excerpt=log_content[:2000],
                task_type=context.alert_info.task_type if context.alert_info else self.skill_name,
                skill_result=skill_result
            )

            # 更新分析结果
            enhanced_analysis = ErrorAnalysis(
                error_type=llm_result.get("error_category", "unknown").lower(),
                category=ErrorCategory.UNKNOWN,  # 保持 UNKNOWN，但有了 LLM 分析结果
                error_message=initial_analysis.error_message,
                matched_pattern=None,
                quick_fix=None,
                llm_hint=llm_result.get("error_description", ""),
                original_log_error=initial_analysis.original_log_error,
                analysis_process=f"Skill: {initial_analysis.analysis_process} + LLM深度分析",
                reasoning=llm_result.get("error_description", ""),
            )

            # 如果 LLM 建议可以自动修复
            if llm_result.get("can_auto_fix") and llm_result.get("suggested_actions"):
                actions = llm_result.get("suggested_actions", [])
                if actions:
                    action = actions[0]
                    if action.get("action_type") == "modify_script":
                        enhanced_analysis.quick_fix = {
                            "action_type": "modify_script",
                            "script_changes": action.get("script_changes", {}),
                        }
                        enhanced_analysis.category = ErrorCategory.AUTO_FIXABLE
                    elif action.get("action_type") == "modify_config":
                        enhanced_analysis.quick_fix = {
                            "action_type": "modify_config",
                            "config_changes": action.get("config_changes", {}),
                        }
                        enhanced_analysis.category = ErrorCategory.AUTO_FIXABLE

            # 记录新错误候选
            if enable_candidate_record and llm_result.get("confidence", 0) >= 0.5:
                try:
                    store = self.get_candidate_store()
                    candidate = create_candidate_from_llm(
                        skill_name=self.skill_name,
                        original_log=log_content,
                        llm_result=llm_result,
                        task_type=context.alert_info.task_type if context.alert_info else ""
                    )
                    store.add(candidate)
                    print(f"[{self.skill_name}] Recorded new error candidate: {candidate.suggested_type}")
                except Exception as e:
                    print(f"[{self.skill_name}] Error recording candidate: {e}")

            return enhanced_analysis

        except Exception as e:
            print(f"[{self.skill_name}] LLM analysis error: {e}")
            return initial_analysis

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