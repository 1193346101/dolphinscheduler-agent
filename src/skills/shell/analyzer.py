"""
Shell Skill - Shell 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Shell 错误模式
- AUTO_FIXABLE: 路径验证、拼写错误（通过 ossutil）
- KNOWN_NEEDS_LLM: 已知类型（语法错误等），给 LLM 提供提示
- UNKNOWN: 无匹配，完全交给 LLM

重构版: 使用公共 pattern_matcher 模块，移除硬编码模式表
所有模式维护在 patterns.md 文件中，符合 anthropics/skills 规范
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.risk import RiskLevel
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log
from ..common.oss_validator import get_oss_validator
from ..common.pattern_matcher import PatternMatcher, MatchResult


class ShellSkill(BaseSkill):
    """
    Shell 任务分析 Skill - 重构版

    使用公共 pattern_matcher 模块进行模式匹配，移除硬编码模式表。
    """

    skill_name = "shell"
    task_types = ["SHELL"]

    # Pattern Matcher（延迟初始化）
    _matcher: Optional[PatternMatcher] = None

    def _get_matcher(self) -> PatternMatcher:
        """获取模式匹配器"""
        if self._matcher is None:
            patterns_file = str(Path(__file__).parent / "patterns.md")
            self._matcher = PatternMatcher("shell", patterns_file)
        return self._matcher

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析 Shell 脚本错误 - 使用公共 pattern_matcher

        流程:
        1. preprocess_log - 日志预处理
        2. PatternMatcher.match - 模式匹配
        3. _build_analysis - 构建 ErrorAnalysis
        """
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="shell")
        error_blocks = preprocessed.get("error_blocks", [])

        # 没有错误块时返回 UNKNOWN
        if not error_blocks:
            return ErrorAnalysis(
                error_type="unknown",
                category=ErrorCategory.UNKNOWN,
                error_message=log_content[:500],
                original_log_error=log_content[:300],
                analysis_process="无错误块提取",
                reasoning="日志预处理未发现错误信息，建议人工分析",
            )

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 使用 PatternMatcher 进行模式匹配
        matcher = self._get_matcher()
        match_result = matcher.match(error_text)

        # 3. 构建 ErrorAnalysis
        return self._build_analysis(
            match_result,
            preprocessed,
            error_blocks[0] if error_blocks else error_text[:300],
        )

    def _build_analysis(
        self,
        match_result: MatchResult,
        preprocessed: Dict[str, Any],
        original_error: str,
    ) -> ErrorAnalysis:
        """
        根据匹配结果构建 ErrorAnalysis

        Args:
            match_result: 模式匹配结果
            preprocessed: 预处理结果
            original_error: 原始错误片段

        Returns:
            ErrorAnalysis 完整分析结果
        """
        category = ErrorCategory(match_result.category)

        # 构建分析过程说明
        analysis_parts = []
        if preprocessed.get("error_blocks"):
            analysis_parts.append(f"提取错误块 {len(preprocessed['error_blocks'])} 个")
        if match_result.matched_pattern:
            analysis_parts.append(f"匹配模式: {match_result.error_type}")
        analysis_process = ", ".join(analysis_parts) if analysis_parts else "通过错误模式库匹配"

        # 根据 category 设置不同字段
        quick_fix = None
        llm_hint = None
        reasoning = match_result.hint

        if category == ErrorCategory.AUTO_FIXABLE:
            # AUTO_FIXABLE: 直接返回修复方案
            quick_fix = self._parse_fix_action(match_result.hint, match_result.extra_info)
            reasoning = match_result.hint or "根据错误模式匹配结果，提供标准修复方案"

        elif category == ErrorCategory.KNOWN_NEEDS_LLM:
            # KNOWN_NEEDS_LLM: 给 LLM 提供提示
            llm_hint = match_result.hint
            reasoning = match_result.hint or "已知错误类型，需进一步分析具体原因"

        else:
            # UNKNOWN: 未知错误
            reasoning = "未知错误类型，建议人工分析或查阅相关文档"

        return ErrorAnalysis(
            error_type=match_result.error_type,
            category=category,
            error_message=match_result.error_message,
            matched_pattern=match_result.matched_pattern,
            quick_fix=quick_fix,
            llm_hint=llm_hint,
            original_log_error=original_error,
            analysis_process=analysis_process,
            reasoning=reasoning,
        )

    def _parse_fix_action(
        self,
        hint: str,
        extra_info: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        解析 fix_action

        Args:
            hint: 提示字符串（可能是 JSON）
            extra_info: 额外信息

        Returns:
            修复动作字典或 None
        """
        # Shell 错误通常无法自动修复，除非是路径验证类
        if extra_info and "fix_action" in extra_info:
            return extra_info["fix_action"]

        # 从 hint 解析 JSON
        if hint and hint.startswith('{'):
            try:
                fix_action = json.loads(hint)
                return {
                    "action_type": fix_action.get("action_type", "path_verification"),
                    "verified_path": fix_action.get("verified_path"),
                    "suggestion": fix_action.get("suggestion", ""),
                }
            except json.JSONDecodeError:
                pass

        return None

    def suggest(self, analysis: ErrorAnalysis) -> list[str]:
        """补充建议"""
        suggestions = []

        # 基于错误类型给出补充建议
        if analysis.error_type in ["syntax_error", "unexpected_eof", "unexpected_token"]:
            suggestions.append("检查 Shell 脚本语法：引号闭合、括号匹配、if/for/while 结构")
        elif analysis.error_type in ["permission_denied", "access_denied"]:
            suggestions.append("检查文件或目录权限，确认执行用户有足够权限")
        elif analysis.error_type in ["no_such_file", "file_not_found", "directory_not_exist"]:
            suggestions.append("检查文件路径是否存在，确认路径拼写正确")
        elif analysis.error_type in ["connection_refused", "connection_timeout"]:
            suggestions.append("检查目标服务是否运行，确认网络连通性")
        elif analysis.error_type in ["disk_full", "no_space_left"]:
            suggestions.append("清理磁盘空间或更换输出路径")

        return suggestions


__all__ = ["ShellSkill"]