"""
风险评估模型
"""

from enum import Enum
from dataclasses import dataclass, field


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"           # 低风险: 配置调整、简单脚本修改
    MEDIUM = "medium"     # 中风险: 依赖上传、环境变量修改
    HIGH = "high"         # 高风险: 删除任务、修改依赖关系
    CRITICAL = "critical" # 严重风险: 删除工作流、跨项目修改


@dataclass
class RiskAssessment:
    """风险评估结果"""

    risk_level: RiskLevel
    affected_downstream: int = 0
    requires_approval: bool = False
    reason: str = ""

    @property
    def can_auto_fix(self) -> bool:
        """是否可以自动修复"""
        return self.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]


@dataclass
class AutoFixAction:
    """自动修复动作"""

    action_type: str  # modify_config, modify_script
    config_changes: dict = field(default_factory=dict)  # 配置变更 {"spark.executor.memory": "4g"}
    script_changes: dict = field(default_factory=dict)  # 脚本变更 {"wrong_cmd": "correct_cmd"}

    # 修复后操作
    need_recover: bool = True  # 是否需要恢复工作流


__all__ = ["RiskLevel", "RiskAssessment", "AutoFixAction"]