"""
错误分析模型

分析结果分三类:
- AUTO_FIXABLE: 已知且可直接修复（拼写错误等）
- KNOWN_NEEDS_LLM: 已知类型但需 LLM 深度分析（语法错误位置、具体原因）
- UNKNOWN: 无匹配模式，完全交给 LLM 分析
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
from enum import Enum


class ErrorCategory(Enum):
    """错误分析类别"""
    AUTO_FIXABLE = "AUTO_FIXABLE"       # Skill 可直接修复
    KNOWN_NEEDS_LLM = "KNOWN_NEEDS_LLM"  # 已知类型，需 LLM 分析
    UNKNOWN = "UNKNOWN"                  # 未知错误，完全交给 LLM


@dataclass
class ErrorAnalysis:
    """错误分析结果"""

    # 错误类型标识
    error_type: str                      # oom_executor, syntax_error, command_not_found...

    # 分析类别（核心）
    category: ErrorCategory              # AUTO_FIXABLE / KNOWN_NEEDS_LLM / UNKNOWN

    # 错误消息片段
    error_message: str                   # 日志片段（用于 LLM 分析）

    # 匹配的模式（调试用）
    matched_pattern: Optional[str] = None

    # 快速修复方案（仅 AUTO_FIXABLE 有）
    quick_fix: Optional[Dict] = None     # {"action_type": "modify_script", "script_changes": {"ech": "echo"}}

    # 给 LLM 的提示（仅 KNOWN_NEEDS_LLM 有）
    llm_hint: Optional[str] = None       # 如 "语法错误，请定位具体位置和原因"

    # === 透明化分析报告 ===
    # 原始日志错误信息（从 error_blocks 中提取的关键片段）
    original_log_error: Optional[str] = None

    # 分析过程说明（如何识别出错误类型）
    analysis_process: Optional[str] = None

    # 建议理由（为什么给出这样的修复建议）
    reasoning: Optional[str] = None

    # 任务类型特有信息
    spark_app_id: Optional[str] = None
    executor_count: Optional[int] = None


@dataclass
class AnalysisResult:
    """完整分析结果"""

    error_analysis: ErrorAnalysis

    # 建议列表（从 Skill 或 LLM 获取）
    suggestions: list[str] = field(default_factory=list)

    # 知识库匹配的知识条目
    matched_knowledge: list = field(default_factory=list)

    # 下游影响
    downstream_impact: Optional[dict] = None


__all__ = ["ErrorAnalysis", "AnalysisResult", "ErrorCategory"]