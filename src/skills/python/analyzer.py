"""
Python Skill - Python 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Python 错误模式
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


class PythonSkill(BaseSkill):
    """
    Python 任务分析 Skill - 重构版

    Python 错误大多数需要人工检查代码，因此都归类为 KNOWN_NEEDS_LLM。
    使用公共 pattern_matcher 模块进行模式匹配，移除硬编码模式表。
    """

    skill_name = "python"
    task_types = ["PYTHON"]

    # Pattern Matcher（延迟初始化）
    _matcher: Optional[PatternMatcher] = None

    def _get_matcher(self) -> PatternMatcher:
        """获取模式匹配器"""
        if self._matcher is None:
            patterns_file = str(Path(__file__).parent / "patterns.md")
            self._matcher = PatternMatcher("python", patterns_file)
        return self._matcher

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析 Python 任务错误 - 使用公共 pattern_matcher

        流程:
        1. preprocess_log - 日志预处理
        2. PatternMatcher.match - 模式匹配
        3. _build_analysis - 构建 ErrorAnalysis（含 traceback 解析）
        """
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="python")
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

        # 3. 解析 Python traceback（获取具体位置信息）
        traceback_info = self._parse_traceback(error_text)

        # 4. 构建 ErrorAnalysis
        return self._build_analysis(
            match_result,
            preprocessed,
            error_blocks[0] if error_blocks else error_text[:300],
            traceback_info,
        )

    def _parse_traceback(self, log_content: str) -> Dict[str, Any]:
        """
        解析 Python traceback

        Args:
            log_content: 日志内容

        Returns:
            Traceback 信息字典
        """
        import re
        traceback = {
            "frames": [],
            "root_cause": None,
        }

        # 匹配 Traceback 帧: File "path", line N, in function
        frame_pattern = r'File "([^"]+)", line (\d+), in (\w+)'
        for match in re.finditer(frame_pattern, log_content):
            frame = {
                "file": match.group(1),
                "line": int(match.group(2)),
                "function": match.group(3),
            }
            traceback["frames"].append(frame)

        # Root cause 是最后一个帧（实际出错位置）
        if traceback["frames"]:
            traceback["root_cause"] = traceback["frames"][-1]

        return traceback

    def _build_analysis(
        self,
        match_result: MatchResult,
        preprocessed: Dict[str, Any],
        original_error: str,
        traceback_info: Dict[str, Any],
    ) -> ErrorAnalysis:
        """
        根据匹配结果构建 ErrorAnalysis（含 traceback 信息）

        Args:
            match_result: 模式匹配结果
            preprocessed: 预处理结果
            original_error: 原始错误片段
            traceback_info: Traceback 解析结果

        Returns:
            ErrorAnalysis 完整分析结果
        """
        category = ErrorCategory(match_result.category)

        # 构建分析过程说明
        analysis_parts = []
        if preprocessed.get("error_blocks"):
            analysis_parts.append(f"提取错误块 {len(preprocessed['error_blocks'])} 个")
        if traceback_info.get("frames"):
            analysis_parts.append(f"解析 traceback {len(traceback_info['frames'])} 层")
        if traceback_info.get("root_cause"):
            root = traceback_info["root_cause"]
            analysis_parts.append(f"定位: {root['file']}:{root['line']}")
        if match_result.matched_pattern:
            analysis_parts.append(f"匹配模式: {match_result.error_type}")
        analysis_process = ", ".join(analysis_parts) if analysis_parts else "通过错误模式库匹配"

        # 根据 category 设置不同字段
        quick_fix = None
        llm_hint = None
        reasoning = match_result.hint

        if category == ErrorCategory.AUTO_FIXABLE:
            quick_fix = self._parse_fix_action(match_result.hint, match_result.extra_info)
            reasoning = match_result.hint or "根据错误模式匹配结果，提供标准修复方案"

        elif category == ErrorCategory.KNOWN_NEEDS_LLM:
            # KNOWN_NEEDS_LLM: 给 LLM 提供提示（Python 大多数情况）
            llm_hint = match_result.hint
            # 补充 traceback 定位信息
            if traceback_info.get("root_cause"):
                root = traceback_info["root_cause"]
                llm_hint = f"{match_result.hint}，出错位置: {root['file']} 行 {root['line']} 函数 {root['function']}"
            reasoning = match_result.hint or "已知错误类型，需进一步分析具体原因"

        else:
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
            data_metrics=traceback_info,  # 将 traceback 信息放入 data_metrics
        )

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
        if analysis.error_type in ["syntax_error", "indentation_error"]:
            suggestions.append("检查代码语法：引号闭合、括号匹配、缩进一致性")
        elif analysis.error_type in ["module_not_found", "import_error"]:
            suggestions.append("检查依赖包是否安装：pip install <module>")
            suggestions.append("检查 PYTHONPATH 配置")
        elif analysis.error_type in ["key_error"]:
            suggestions.append("检查字典 key 是否存在，使用 .get() 方法避免异常")
        elif analysis.error_type in ["index_error"]:
            suggestions.append("检查列表索引范围，使用 len() 确认长度")
        elif analysis.error_type in ["file_not_found"]:
            suggestions.append("检查文件路径是否正确，确认文件存在")
        elif analysis.error_type in ["name_error"]:
            suggestions.append("检查变量是否已定义，确认作用域正确")

        return suggestions


__all__ = ["PythonSkill"]