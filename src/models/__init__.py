"""
公共数据模型
"""

from .alert import AlertInfo, AlertContext
from .risk import RiskLevel, RiskAssessment, AutoFixAction
from .analysis import ErrorAnalysis, AnalysisResult

__all__ = [
    "AlertInfo",
    "AlertContext",
    "RiskLevel",
    "RiskAssessment",
    "AutoFixAction",
    "ErrorAnalysis",
    "AnalysisResult",
]