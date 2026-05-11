"""
Skill 注册表 - 管理所有 Skills

支持两种模式:
1. 静态注册: 直接导入 Skill 类并注册
2. 动态加载: 扫描 SKILL.md 文件并解析元数据

动态加载用于:
- 发现可用的 Skills
- 获取 Skill 的 task_types 映射
- 加载 Skill 元数据 (description, version 等)

静态注册用于:
- 实际执行 Skill 分析逻辑
- 提供 BaseSkill 实例
"""

import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

from .base import BaseSkill
from .spark.analyzer import SparkSkill
from .shell.analyzer import ShellSkill
from .python.analyzer import PythonSkill
from .datax.analyzer import DataXSkill
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.alert import AlertContext


@dataclass
class SkillMetadata:
    """Skill 元数据 (从 SKILL.md 解析)"""

    name: str
    description: str
    task_types: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "task_types": self.task_types,
            "version": self.version,
            "path": str(self.path) if self.path else None,
        }


class SkillRegistry:
    """
    Skill 注册表

    功能:
    - 静态注册: 将 task_type 映射到 Skill 实例
    - 动态加载: 扫描 SKILL.md 文件，解析元数据

    task_skill_map:
    - SPARK/SPARK_STREAMING -> spark-error-analyzer
    - SHELL -> shell-error-analyzer
    - PYTHON -> python-error-analyzer
    - DATAX -> datax-error-analyzer
    """

    # task_type -> skill_name 映射
    task_skill_map: Dict[str, str] = {
        "SPARK": "spark",
        "SPARK_STREAMING": "spark",
        "SHELL": "shell",
        "PYTHON": "python",
        "DATAX": "datax",
    }

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        初始化注册表

        Args:
            skills_dir: Skills 目录路径，默认为 src/skills
        """
        self._skills: Dict[str, BaseSkill] = {
            "SPARK": SparkSkill(),
            "SPARK_STREAMING": SparkSkill(),
            "SHELL": ShellSkill(),
            "PYTHON": PythonSkill(),
            "DATAX": DataXSkill(),
        }
        self._default_skill = DefaultSkill()
        self._metadata: Dict[str, SkillMetadata] = {}
        self._skills_dir = skills_dir or Path(__file__).parent

        # 自动加载所有 Skill 元数据
        self._load_all_skills()

    def _load_all_skills(self) -> None:
        """
        扫描 SKILL.md 文件并加载元数据

        扫描 src/skills/*/SKILL.md 文件
        """
        if not self._skills_dir.exists():
            return

        for skill_dir in self._skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    metadata = self._parse_skill_md(skill_md)
                    if metadata:
                        self._metadata[metadata.name] = metadata

    def _parse_skill_md(self, skill_md_path: Path) -> Optional[SkillMetadata]:
        """
        解析 SKILL.md 文件的 YAML frontmatter

        格式:
        ---
        name: skill-name
        description: Skill description
        task_types:
          - SPARK
          - SPARK_STREAMING
        version: "1.0.0"
        ---

        Markdown content...

        Args:
            skill_md_path: SKILL.md 文件路径

        Returns:
            SkillMetadata 或 None
        """
        try:
            content = skill_md_path.read_text(encoding="utf-8")

            # 解析 YAML frontmatter
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if not match:
                return None

            frontmatter = match.group(1)
            metadata: Dict[str, Any] = {}

            # 解析 YAML (简单实现，避免引入 yaml 依赖)
            for line in frontmatter.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # 解析 key: value
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    # 处理引号包裹的值
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    metadata[key] = value

            # 解析 task_types (多行列表)
            if "task_types" in frontmatter:
                task_types = []
                in_list = False
                for line in frontmatter.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("task_types:"):
                        in_list = True
                        continue
                    if in_list and stripped.startswith("- "):
                        task_types.append(stripped[2:].strip())
                    elif in_list and not stripped.startswith("- ") and stripped:
                        in_list = False
                metadata["task_types"] = task_types

            if "name" not in metadata:
                return None

            return SkillMetadata(
                name=metadata.get("name", ""),
                description=metadata.get("description", ""),
                task_types=metadata.get("task_types", []),
                version=metadata.get("version", "1.0.0"),
                path=skill_md_path.parent,
            )

        except Exception:
            return None

    def get_skill(self, task_type: str) -> BaseSkill:
        """
        根据 taskType 获取 Skill 实例

        Args:
            task_type: 任务类型 (SPARK, SHELL, PYTHON, DATAX 等)

        Returns:
            BaseSkill 实例
        """
        return self._skills.get(task_type.upper(), self._default_skill)

    def get_skill_metadata(self, skill_name: str) -> Optional[SkillMetadata]:
        """
        获取 Skill 元数据

        Args:
            skill_name: Skill 名称 (如 spark-error-analyzer)

        Returns:
            SkillMetadata 或 None
        """
        return self._metadata.get(skill_name)

    def get_all_skills(self) -> Dict[str, SkillMetadata]:
        """
        获取所有 Skill 元数据

        Returns:
            Dict[skill_name, SkillMetadata]
        """
        return self._metadata.copy()

    def match_skill_for_task_type(self, task_type: str) -> Optional[str]:
        """
        根据 task_type 匹配 skill_name

        Args:
            task_type: 任务类型

        Returns:
            skill_name 或 None
        """
        return self.task_skill_map.get(task_type.upper())

    def get_skill_scripts_dir(self, task_type: str) -> Optional[Path]:
        """
        获取 Skill scripts 目录路径

        Args:
            task_type: 任务类型

        Returns:
            scripts 目录路径，如果不存在则返回 None
        """
        skill_name = self.match_skill_for_task_type(task_type)
        if not skill_name:
            return None

        # 从元数据获取 path
        metadata = self._metadata.get(skill_name)
        if metadata and metadata.path:
            scripts_path = metadata.path / "scripts"
            if scripts_path.exists():
                return scripts_path

        # 直接查找目录
        skill_dir = self._skills_dir / skill_name
        if skill_dir.exists():
            scripts_path = skill_dir / "scripts"
            if scripts_path.exists():
                return scripts_path

        return None

    def get_skill_patterns_file(self, task_type: str) -> Optional[Path]:
        """
        获取 Skill patterns 文件路径

        Args:
            task_type: 任务类型

        Returns:
            patterns 文件路径，如果不存在则返回 None
        """
        scripts_dir = self.get_skill_scripts_dir(task_type)
        if not scripts_dir:
            return None

        # 查找 patterns 文件
        patterns_file = scripts_dir.parent / f"{task_type.lower()}_patterns.md"
        if patterns_file.exists():
            return patterns_file

        # 尝试其他命名
        for name in ["patterns.md", "error_patterns.md"]:
            patterns_file = scripts_dir.parent / name
            if patterns_file.exists():
                return patterns_file

        return None

    def register_skill(self, task_types: List[str], skill: BaseSkill) -> None:
        """
        注册新 Skill

        Args:
            task_types: 支持的任务类型列表
            skill: BaseSkill 实例
        """
        for task_type in task_types:
            self._skills[task_type.upper()] = skill

    def list_supported_task_types(self) -> List[str]:
        """
        列出所有支持的任务类型

        Returns:
            任务类型列表
        """
        return list(self._skills.keys())


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
        """默认分析 - 返回 UNKNOWN，触发 LLM 分析"""
        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            category=ErrorCategory.UNKNOWN,
            original_log_error=log_content[:300],
            analysis_process="无匹配 Skill，交给 LLM 分析",
            reasoning="任务类型未匹配到预定义 Skill，需要 LLM 进行深度分析",
        )


# 全局注册表
skill_registry = SkillRegistry()


__all__ = ["SkillRegistry", "SkillMetadata", "skill_registry"]