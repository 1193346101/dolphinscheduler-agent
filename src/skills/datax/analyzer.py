"""
DataX Skill - DataX 数据同步任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 DataX 错误模式
- KNOWN_NEEDS_LLM: 所有错误都需 LLM 分析具体原因
- UNKNOWN: 无匹配，完全交给 LLM

改进: 使用 preprocess_log 进行预处理，保留 legacy 分析作为 fallback
"""

import re
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.risk import RiskLevel
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log


class DataXSkill(BaseSkill):
    """
    DataX 任务分析 Skill

    DataX 错误通常涉及数据库连接、数据转换、权限等，需要人工干预

    使用 preprocess_log 进行预处理，然后使用 legacy 分析
    """

    skill_name = "datax"
    task_types = ["DATAX"]

    def _get_scripts_dir(self) -> Optional[Path]:
        """获取 scripts 目录"""
        scripts_dir = Path(__file__).parent / "scripts"
        if scripts_dir.exists():
            return scripts_dir
        return None

    def _get_patterns_file(self) -> Optional[Path]:
        """获取 patterns.md 文件路径"""
        patterns_file = Path(__file__).parent / "patterns.md"
        if patterns_file.exists():
            return patterns_file
        return None

    # 错误模式: (pattern, category, llm_hint)
    error_patterns: Dict[str, Tuple[str, str, str]] = {
        # === 配置错误 ===
        "config_error": (
            "Configuration error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 配置错误，请检查 job 配置文件"
        ),
        "json_parse_error": (
            "JSON parse error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX JSON 配置解析失败，请检查 JSON 格式是否正确"
        ),

        # === 连接错误 ===
        "source_connection": (
            "source connection failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 源端数据库连接失败，请检查源端连接配置（URL、用户名、密码、网络）"
        ),
        "sink_connection": (
            "sink connection failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 目标端数据库连接失败，请检查目标端连接配置"
        ),
        "connection_timeout": (
            "Connection timed out",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 数据库连接超时，请检查网络和超时设置"
        ),

        # === 数据错误 ===
        "data_transform": (
            "Data transform error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 数据转换错误，请检查数据类型转换配置"
        ),
        "type_convert": (
            "Type conversion error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 类型转换失败，请分析源字段类型和目标字段类型"
        ),
        "column_not_match": (
            "column not match",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 列名不匹配，请检查源表和目标表的列名配置"
        ),
        "primary_key_conflict": (
            "Duplicate entry",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 主键冲突，请分析数据是否有重复主键"
        ),

        # === 写入错误 ===
        "write_error": (
            "Write error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 写入错误，请检查写入权限和目标表结构"
        ),
        "batch_write_failed": (
            "batch write failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 批量写入失败，请分析失败的具体批次和原因"
        ),

        # === 权限错误 ===
        "permission_denied": (
            "Permission denied",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 权限不足，请检查数据库用户权限"
        ),
        "access_denied": (
            "Access denied",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 访问被拒绝，请检查数据库访问权限"
        ),

        # === 性能错误 ===
        "speed_limit": (
            "speed limit",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX 速度限制，请检查流量控制配置"
        ),
        "channel_error": (
            "channel error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "DataX Channel 错误，请检查并发配置"
        ),
    }

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 DataX 任务错误 - 使用 preprocess_log + legacy fallback"""
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="datax")
        error_blocks = preprocessed.get("error_blocks", [])

        if not error_blocks:
            # 没有错误块，使用 legacy 分析
            return self._legacy_analyze(log_content, context)

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 尝试使用 match_error.py 脚本（如果存在）
        patterns_file = self._get_patterns_file()
        if patterns_file:
            try:
                # 尝试导入 match_error
                scripts_dir = self._get_scripts_dir()
                if scripts_dir:
                    # 动态导入 match_error.py
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "match_error",
                        scripts_dir / "match_error.py"
                    )
                    match_error_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(match_error_module)

                    match_result = match_error_module.match_error(error_text, str(patterns_file))
                    if match_result.get("error_type") != "unknown":
                        category = ErrorCategory(match_result["category"])
                        return ErrorAnalysis(
                            error_type=match_result["error_type"],
                            category=category,
                            error_message=match_result.get("error_message", error_text[:500]),
                            matched_pattern=match_result.get("matched_pattern", ""),
                            llm_hint=match_result.get("extra", "") if category == ErrorCategory.KNOWN_NEEDS_LLM else "",
                            original_log_error=error_text[:300],
                            analysis_process=f"匹配模式: {match_result.get('matched_pattern', '')}",
                            reasoning=match_result.get("extra", "") or "根据模式匹配结果分析",
                        )
            except Exception:
                pass  # Fallback to legacy

        # 3. Fallback: 使用 legacy 分析
        return self._legacy_analyze(error_text, context)

    def _legacy_analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """Legacy 分析方法 - 作为 fallback"""
        log_lower = log_content.lower()

        for error_type, (pattern, category, llm_hint) in self.error_patterns.items():
            if pattern.lower() in log_lower:
                error_message = self._extract_error_message(log_content, pattern)
                return ErrorAnalysis(
                    error_type=error_type,
                    category=ErrorCategory.KNOWN_NEEDS_LLM,
                    error_message=error_message,
                    matched_pattern=pattern,
                    llm_hint=llm_hint,
                    original_log_error=error_message,
                    analysis_process=f"通过内置模式库匹配: {error_type}",
                    reasoning=llm_hint or "已知错误类型，需进一步分析具体原因",
                )

        return ErrorAnalysis(
            error_type="unknown",
            category=ErrorCategory.UNKNOWN,
            error_message=log_content[:500],
            original_log_error=log_content[:300],
            analysis_process="无匹配错误模式",
            reasoning="未知错误类型，建议人工分析或查阅相关文档",
        )

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息片段"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if pattern.lower() in line.lower():
                start = max(0, i - 3)
                end = min(len(lines), i + 5)
                return "\n".join(lines[start:end])
        return pattern


__all__ = ["DataXSkill"]