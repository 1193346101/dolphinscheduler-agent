"""
Python Skill - Python 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Python 错误模式
- KNOWN_NEEDS_LLM: 所有错误都需 LLM 分析具体原因
- UNKNOWN: 无匹配，完全交给 LLM
"""

import re
from typing import Optional, Dict, Tuple
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel
from ..models.alert import AlertContext
from .base import BaseSkill


class PythonSkill(BaseSkill):
    """
    Python 任务分析 Skill

    Python 错误大多数需要人工检查代码，因此都归类为 KNOWN_NEEDS_LLM
    """

    skill_name = "python"
    task_types = ["PYTHON"]

    # 错误模式: (pattern, category, llm_hint)
    error_patterns: Dict[str, Tuple[str, str, str]] = {
        # === 语法错误 ===
        "syntax_error": (
            "SyntaxError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 语法错误，请分析具体位置和原因（如缩进、括号、引号问题）"
        ),
        "indentation_error": (
            "IndentationError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 缩进错误，请检查缩进是否一致"
        ),

        # === 导入错误 ===
        "module_not_found": (
            "ModuleNotFoundError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 模块不存在，请分析缺失的模块名和安装方式"
        ),
        "import_error": (
            "ImportError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 导入错误，请分析导入失败的原因"
        ),

        # === 类型错误 ===
        "type_error": (
            "TypeError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 类型错误，请分析类型不匹配的具体原因"
        ),
        "value_error": (
            "ValueError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 值错误，请分析值无效的原因"
        ),
        "attribute_error": (
            "AttributeError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 属性不存在，请分析对象类型和属性名"
        ),

        # === 数据结构错误 ===
        "key_error": (
            "KeyError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 字典 key 不存在，请分析缺失的 key 和字典内容"
        ),
        "index_error": (
            "IndexError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 索引越界，请分析列表长度和索引值"
        ),

        # === 运行时错误 ===
        "runtime_error": (
            "RuntimeError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 运行时错误，请分析具体运行时问题"
        ),
        "zero_division": (
            "ZeroDivisionError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 除零错误，请分析除数为零的情况"
        ),
        "name_error": (
            "NameError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 变量名未定义，请检查变量定义"
        ),

        # === 文件错误 ===
        "file_not_found": (
            "FileNotFoundError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 文件不存在，请检查文件路径"
        ),
        "permission_error": (
            "PermissionError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 权限错误，请检查文件权限"
        ),

        # === 内存错误 ===
        "memory_error": (
            "MemoryError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 内存不足，请分析内存使用情况"
        ),
        "recursion_error": (
            "RecursionError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 递归深度超限，请检查递归逻辑"
        ),

        # === 其他 ===
        "stop_iteration": (
            "StopIteration:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 迭代器耗尽，请检查迭代逻辑"
        ),
        "assertion_error": (
            "AssertionError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 断言失败，请分析断言条件"
        ),
        "not_implemented": (
            "NotImplementedError:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Python 功能未实现，请检查代码"
        ),
    }

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 Python 任务错误"""
        for error_type, (pattern, category, llm_hint) in self.error_patterns.items():
            if pattern in log_content:
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
        """提取错误消息片段（Python traceback 通常较长）"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if pattern in line:
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                return "\n".join(lines[start:end])
        return pattern


__all__ = ["PythonSkill"]