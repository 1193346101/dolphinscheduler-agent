"""
错误分析模型
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ErrorAnalysis:
    """错误分析结果"""

    error_type: str  # oom_executor, oom_driver, class_not_found, syntax_error...
    error_message: str
    matched_pattern: Optional[str] = None

    # Spark 特有信息
    spark_app_id: Optional[str] = None
    executor_count: Optional[int] = None

    # 是否可自动修复
    can_auto_fix: bool = False

    # 置信度
    confidence: float = 0.8


@dataclass
class AnalysisResult:
    """完整分析结果"""

    error_analysis: ErrorAnalysis

    # 建议列表
    suggestions: list[str] = field(default_factory=list)

    # 知识库匹配的知识条目
    matched_knowledge: list = field(default_factory=list)

    # 下游影响
    downstream_impact: Optional[dict] = None


__all__ = ["ErrorAnalysis", "AnalysisResult"]