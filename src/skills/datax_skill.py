"""
DataX Skill - DataX 数据同步任务错误分析

○ 不是 Agent，使用预定义规则
"""

from typing import Optional
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel
from ..models.alert import AlertContext
from .base import BaseSkill


class DataXSkill(BaseSkill):
    """
    DataX 任务分析 Skill

    常见错误类型:
    - config_error: 配置错误
    - source_connection: 源端连接失败
    - sink_connection: 目标端连接失败
    - data_transform: 数据转换错误
    - write_error: 写入错误
    """

    skill_name = "datax"
    task_types = ["DATAX"]

    # 预定义的错误模式
    error_patterns = {
        "config_error": "Configuration error",
        "json_parse_error": "JSON parse error",
        "source_connection": "source connection failed",
        "sink_connection": "sink connection failed",
        "connection_timeout": "Connection timed out",
        "data_transform": "Data transform error",
        "type_convert": "Type conversion error",
        "write_error": "Write error",
        "primary_key_conflict": "Duplicate entry",
        "column_not_match": "column not match",
    }

    # 预定义的建议模板
    suggestion_templates = {
        "config_error": "检查 DataX job 配置文件",
        "json_parse_error": "检查 JSON 配置格式是否正确",
        "source_connection": "检查源端数据库连接配置",
        "sink_connection": "检查目标端数据库连接配置",
        "connection_timeout": "检查网络连接或增加超时时间",
        "data_transform": "检查数据类型转换配置",
        "type_convert": "检查字段类型是否匹配",
        "write_error": "检查写入权限和表结构",
        "primary_key_conflict": "检查主键是否重复",
        "column_not_match": "检查列名是否匹配",
    }

    # DataX 错误一般不可自动修复
    auto_fixable_errors = []

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """使用预定义规则分析日志"""
        for error_type, pattern in self.error_patterns.items():
            if pattern.lower() in log_content.lower():
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=self._extract_error_message(log_content, pattern),
                    matched_pattern=pattern,
                    can_auto_fix=False,
                    confidence=0.8,
                )

        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            can_auto_fix=False,
            confidence=0.5,
        )

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if pattern.lower() in line.lower():
                start = max(0, i - 3)
                end = min(len(lines), i + 5)
                return "\n".join(lines[start:end])
        return pattern


__all__ = ["DataXSkill"]