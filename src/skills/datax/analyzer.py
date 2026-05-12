"""
DataX Skill - DataX 数据同步任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 DataX 错误模式
- KNOWN_NEEDS_LLM: 所有错误都需 LLM 分析具体原因
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
from ..common.pattern_matcher import PatternMatcher, MatchResult


class DataXSkill(BaseSkill):
    """
    DataX 任务分析 Skill - 重构版

    DataX 错误通常涉及数据库连接、数据转换、权限等，需要人工干预。
    使用公共 pattern_matcher 模块进行模式匹配，移除硬编码模式表。
    """

    skill_name = "datax"
    task_types = ["DATAX"]

    # Pattern Matcher（延迟初始化）
    _matcher: Optional[PatternMatcher] = None

    def _get_matcher(self) -> PatternMatcher:
        """获取模式匹配器"""
        if self._matcher is None:
            patterns_file = str(Path(__file__).parent / "patterns.md")
            self._matcher = PatternMatcher("datax", patterns_file)
        return self._matcher

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析 DataX 任务错误 - 使用公共 pattern_matcher + LLM fallback

        流程:
        1. preprocess_log - 日志预处理
        2. PatternMatcher.match - 模式匹配
        3. _build_analysis - 构建 ErrorAnalysis
        4. UNKNOWN -> analyze_with_llm_fallback - LLM 分析并记录候选
        """
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="datax")
        error_blocks = preprocessed.get("error_blocks", [])

        # 没有错误块时返回 UNKNOWN（交给 LLM）
        if not error_blocks:
            initial = ErrorAnalysis(
                error_type="unknown",
                category=ErrorCategory.UNKNOWN,
                error_message=log_content[:500],
                original_log_error=log_content[:300],
                analysis_process="无错误块提取",
                reasoning="日志预处理未发现错误信息，交给 LLM 分析",
            )
            return self.analyze_with_llm_fallback(log_content, initial, context)

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 使用 PatternMatcher 进行模式匹配
        matcher = self._get_matcher()
        match_result = matcher.match(error_text)

        # 3. 构建 ErrorAnalysis（包含 DataX 特有信息）
        initial = self._build_analysis(
            match_result,
            preprocessed,
            error_blocks[0] if error_blocks else error_text[:300],
        )

        # 4. UNKNOWN -> LLM fallback
        if initial.category == ErrorCategory.UNKNOWN:
            return self.analyze_with_llm_fallback(log_content, initial, context)

        return initial

    def _build_analysis(
        self,
        match_result: MatchResult,
        preprocessed: Dict[str, Any],
        original_error: str,
    ) -> ErrorAnalysis:
        """
        根据匹配结果构建 ErrorAnalysis（包含 DataX 特有信息）

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

        # 提取 DataX Job 信息
        job_info = self._extract_job_info(match_result.error_message)

        # 根据 category 设置不同字段
        quick_fix = None
        llm_hint = None
        reasoning = match_result.hint

        if category == ErrorCategory.AUTO_FIXABLE:
            # AUTO_FIXABLE: DataX 很少有可直接修复的情况
            quick_fix = self._parse_fix_action(match_result.hint, match_result.extra_info)
            reasoning = match_result.hint or "根据错误模式匹配结果，提供标准修复方案"

        elif category == ErrorCategory.KNOWN_NEEDS_LLM:
            # KNOWN_NEEDS_LLM: 给 LLM 提供提示（DataX 大多数情况）
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
            data_metrics=job_info,  # 将 Job 信息放入 data_metrics
        )

    def _extract_job_info(self, log_content: str) -> Dict[str, Any]:
        """
        提取 DataX Job 信息

        Args:
            log_content: 日志内容

        Returns:
            Job 信息字典
        """
        import re
        info = {}

        # 提取 Job ID
        job_match = re.search(r'\[job-(\d+)\]', log_content)
        if job_match:
            info['job_id'] = f"job-{job_match.group(1)}"

        # 提取数据库类型
        db_patterns = {
            'mysql': [r'mysql', r'com\.mysql'],
            'oracle': [r'oracle', r'ORA-\d+'],
            'postgresql': [r'postgresql'],
            'sqlserver': [r'sqlserver'],
            'hive': [r'hive'],
        }
        for db_type, patterns in db_patterns.items():
            for p in patterns:
                if re.search(p, log_content, re.IGNORECASE):
                    info['database_type'] = db_type
                    break

        return info

    def _parse_fix_action(
        self,
        hint: str,
        extra_info: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        解析 fix_action

        Args:
            hint: 提示字符串
            extra_info: 额外信息

        Returns:
            修复动作字典或 None
        """
        if extra_info and "fix_action" in extra_info:
            return extra_info["fix_action"]

        if hint and hint.startswith('{'):
            try:
                fix_action = json.loads(hint)
                return fix_action
            except json.JSONDecodeError:
                pass

        return None

    def suggest(self, analysis: ErrorAnalysis) -> list[str]:
        """补充建议"""
        suggestions = []

        # 基于错误类型给出补充建议
        if analysis.error_type in ["connection_refused", "connection_timeout", "source_connection"]:
            suggestions.append("检查数据库连接配置：URL、端口、用户名、密码")
            suggestions.append("确认数据库服务正常运行")
        elif analysis.error_type in ["permission_denied", "access_denied"]:
            suggestions.append("检查数据库用户是否有足够的读写权限")
        elif analysis.error_type in ["type_convert", "data_transform"]:
            suggestions.append("检查源表和目标表的字段类型是否匹配")
        elif analysis.error_type in ["column_not_match"]:
            suggestions.append("检查列名配置是否与实际表结构一致")
        elif analysis.error_type in ["primary_key_conflict"]:
            suggestions.append("考虑数据去重或使用 REPLACE INTO 模式")

        return suggestions


__all__ = ["DataXSkill"]