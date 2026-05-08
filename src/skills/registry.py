"""
Skill 注册表 - 管理所有 Skills
"""

from typing import Optional
from .base import BaseSkill
from .spark_skill import SparkSkill
from .shell_skill import ShellSkill
from .python_skill import PythonSkill
from .datax_skill import DataXSkill
from ..models.analysis import ErrorAnalysis
from ..models.alert import AlertContext


class SkillRegistry:
    """
    Skill 注册表

    根据 taskType 返回对应的 Skill
    """

    def __init__(self):
        self._skills = {
            "SPARK": SparkSkill(),
            "SPARK_STREAMING": SparkSkill(),
            "SHELL": ShellSkill(),
            "PYTHON": PythonSkill(),
            "DATAX": DataXSkill(),
        }
        self._default_skill = DefaultSkill()

    def get_skill(self, task_type: str) -> BaseSkill:
        """
        根据 taskType 获取 Skill

        Args:
            task_type: 任务类型

        Returns:
            BaseSkill
        """
        return self._skills.get(task_type.upper(), self._default_skill)

    def register_skill(self, task_types: list[str], skill: BaseSkill) -> None:
        """注册新 Skill"""
        for task_type in task_types:
            self._skills[task_type.upper()] = skill


class DefaultSkill(BaseSkill):
    """默认 Skill - 处理未知任务类型"""

    skill_name = "default"
    task_types = []

    error_patterns = {
        "general_error": "Error",
        "exception": "Exception",
        "failed": "Failed",
    }

    suggestion_templates = {
        "general_error": "请查看完整日志确认错误原因",
        "exception": "请查看异常堆栈确认错误原因",
        "failed": "请检查任务配置和执行环境",
    }

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """默认分析"""
        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            can_auto_fix=False,
            confidence=0.3,
        )


# 全局注册表
skill_registry = SkillRegistry()


__all__ = ["SkillRegistry", "skill_registry"]