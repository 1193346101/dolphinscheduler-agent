"""
告警数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AlertInfo:
    """告警信息"""

    # 基本信息 (无默认值字段在前)
    project_code: int
    process_definition_code: int
    process_instance_id: int
    task_code: int
    task_instance_id: int
    task_type: str  # SPARK, SHELL, PYTHON, DATAX
    state: str  # FAILURE, SUCCESS

    # 有默认值字段在后
    project_name: Optional[str] = None
    process_definition_name: Optional[str] = None
    process_instance_name: Optional[str] = None
    task_name: Optional[str] = None
    host: Optional[str] = None  # 执行主机
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    worker_group: Optional[str] = None
    tenant_code: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class AlertContext:
    """告警处理上下文"""

    alert_info: AlertInfo

    # 分析过程数据
    log_content: Optional[str] = None
    spark_app_id: Optional[str] = None
    impact_report: Optional[dict] = None

    # 知识库匹配结果
    knowledge_entries: list = field(default_factory=list)

    # 分析结果
    error_analysis: Optional[dict] = None

    # 修复方案
    fix_suggestion: Optional[dict] = None

    # 风险评估
    risk_level: Optional[str] = None
    requires_approval: bool = False


__all__ = ["AlertInfo", "AlertContext"]