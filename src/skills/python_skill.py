"""
Python Skill - Python 任务错误分析

○ 不是 Agent，使用预定义规则
"""

import re
from typing import Optional
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel
from ..models.alert import AlertContext
from .base import BaseSkill


class PythonSkill(BaseSkill):
    """
    Python 任务分析 Skill

    常见错误类型:
    - syntax_error: Python 语法错误
    - module_not_found: 模块不存在
    - import_error: 导入错误
    - runtime_error: 运行时异常
    """

    skill_name = "python"
    task_types = ["PYTHON"]

    # 预定义的错误模式
    error_patterns = {
        "syntax_error": "SyntaxError:",
        "module_not_found": "ModuleNotFoundError:",
        "import_error": "ImportError:",
        "key_error": "KeyError:",
        "type_error": "TypeError:",
        "value_error": "ValueError:",
        "attribute_error": "AttributeError:",
        "index_error": "IndexError:",
        "runtime_error": "RuntimeError:",
    }

    # 预定义的建议模板
    suggestion_templates = {
        "syntax_error": "检查 Python 语法，特别是缩进、括号和引号",
        "module_not_found": "检查模块是否安装: pip install <module>",
        "import_error": "检查导入路径是否正确",
        "key_error": "检查字典 key 是否存在",
        "type_error": "检查类型是否正确",
        "value_error": "检查值是否在有效范围内",
        "attribute_error": "检查对象是否有该属性",
        "index_error": "检查索引是否在有效范围内",
        "runtime_error": "检查运行时环境",
    }

    # Python 错误一般不可自动修复（需要人工检查代码）
    auto_fixable_errors = []

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """使用预定义规则分析日志"""
        for error_type, pattern in self.error_patterns.items():
            if pattern in log_content:
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=self._extract_error_message(log_content, pattern),
                    matched_pattern=pattern,
                    can_auto_fix=False,
                    confidence=0.85,
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
            if pattern in line:
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                return "\n".join(lines[start:end])
        return pattern


__all__ = ["PythonSkill"]