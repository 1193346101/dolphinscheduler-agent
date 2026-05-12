"""
Project Resolver - 项目名称解析工具

通过项目名称查找项目 code，使用全局 API Token（所有项目读权限）
"""

import json
from typing import Optional, Tuple
from dataclasses import dataclass

from .dsctl_wrapper import DSCLIClient, CLIResult
from ..config import settings


@dataclass
class ProjectInfo:
    """项目信息"""
    code: int
    name: str
    description: Optional[str] = None


class ProjectResolver:
    """
    项目解析器

    使用全局 API Token 查找项目信息，不依赖配置文件
    """

    def __init__(self):
        # 使用全局 settings 的 API 配置
        self.client = DSCLIClient(
            api_url=settings.DS_API_URL,
            api_token=settings.DS_API_TOKEN,
            version=settings.DS_VERSION,
        )
        # 项目缓存（避免重复查询）
        self._cache: dict = {}

    def resolve_by_name(self, project_name: str) -> Optional[ProjectInfo]:
        """
        通过项目名查找项目 code

        Args:
            project_name: 项目名称

        Returns:
            ProjectInfo 或 None（如果找不到）
        """
        if not project_name or not project_name.strip():
            return None

        project_name = project_name.strip()

        # 检查缓存
        if project_name in self._cache:
            return self._cache[project_name]

        # 先尝试使用 project get 命令（直接查询）
        result = self.client.get_project(project_name)

        if result.success:
            try:
                data = json.loads(result.stdout)
                # dsctl project get 返回格式: {"action": "project.get", "data": {...}}
                if isinstance(data, dict):
                    proj_data = data.get("data", data)
                    code = proj_data.get("code")
                    name = proj_data.get("name", project_name)
                    if code:
                        info = ProjectInfo(
                            code=int(code),
                            name=name,
                            description=proj_data.get("description"),
                        )
                        self._cache[project_name] = info
                        return info
            except json.JSONDecodeError:
                pass

        # 如果 project get 失败，尝试从项目列表中查找
        result = self.client.list_projects(page_size=200)

        if not result.success:
            print(f"[ProjectResolver] 查询项目列表失败: {result.stderr}")
            return None

        try:
            data = json.loads(result.stdout)
            # dsctl 返回格式：{"action": "project.list", "data": [...]} 或 {"data": {"totalList": [...}}
            if isinstance(data, dict):
                projects = data.get("data", [])
                if isinstance(projects, dict):
                    projects = projects.get("totalList", [])
            elif isinstance(data, list):
                projects = data
            else:
                projects = []

            # 查找匹配的项目名
            for proj in projects:
                if isinstance(proj, dict):
                    name = proj.get("name", "")
                    if name == project_name or name.lower() == project_name.lower():
                        code = proj.get("code")
                        if code:
                            info = ProjectInfo(
                                code=int(code),
                                name=name,
                                description=proj.get("description"),
                            )
                            # 缓存结果
                            self._cache[project_name] = info
                            return info

        except json.JSONDecodeError:
            print(f"[ProjectResolver] 解析项目列表失败")

        return None

    def resolve(self, project_input: str) -> Tuple[Optional[int], Optional[str]]:
        """
        解析项目输入（名称或代码）

        Args:
            project_input: 项目名称或项目代码（数字字符串）

        Returns:
            (project_code, project_name) 元组
        """
        if not project_input:
            return None, None

        # 尝试作为数字代码
        try:
            code = int(project_input)
            # 如果是数字，假设就是代码
            return code, None
        except (ValueError, TypeError):
            pass

        # 尝试通过名称查找
        info = self.resolve_by_name(project_input)
        if info:
            return info.code, info.name

        return None, None

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()


# 全局单例
project_resolver = ProjectResolver()


__all__ = ["ProjectResolver", "ProjectInfo", "project_resolver"]