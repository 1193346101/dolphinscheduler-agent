"""
Skills 模块

○ 不是 Agent，使用预定义规则
○ 不使用 LLM 进行决策
"""

from .base import BaseSkill
from .spark.skill import SparkSkill
from .shell.skill import ShellSkill
from .python.skill import PythonSkill
from .datax.skill import DataXSkill
from .registry import SkillRegistry, skill_registry

__all__ = [
    "BaseSkill",
    "SparkSkill",
    "ShellSkill",
    "PythonSkill",
    "DataXSkill",
    "SkillRegistry",
    "skill_registry",
]