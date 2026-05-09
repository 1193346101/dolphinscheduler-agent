"""
DataX Skill - DataX 数据同步任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 DataX 错误模式
- KNOWN_NEEDS_LLM: 所有错误都需 LLM 分析具体原因
- UNKNOWN: 无匹配，完全交给 LLM
"""

import re
from typing import Optional, Dict, Tuple
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel
from ..models.alert import AlertContext
from .base import BaseSkill


class DataXSkill(BaseSkill):
    """
    DataX 任务分析 Skill

    DataX 错误通常涉及数据库连接、数据转换、权限等，需要人工干预
    """

    skill_name = "datax"
    task_types = ["DATAX"]

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
        """分析 DataX 任务错误"""
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
                )

        return ErrorAnalysis(
            error_type="unknown",
            category=ErrorCategory.UNKNOWN,
            error_message=log_content[:500],
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