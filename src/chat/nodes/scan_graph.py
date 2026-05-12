"""
Scan Graph Node - 图谱扫描节点

重构版：使用全局 Token，通过项目名自动查找项目 code
"""

from typing import Dict, Any, Optional
import os

from ..state import ChatState
from src.graph import GraphScanner, GraphStorage, GraphIndexer
from ...integrations import project_resolver
from ...config import settings


def scan_graph_node(state: ChatState) -> ChatState:
    """
    Execute graph scan based on project_name.

    通过项目名自动查找项目 code，使用全局 API Token

    Args:
        state: Current ChatState with project_name populated

    Returns:
        Updated ChatState with result_data containing scan statistics
    """
    intent_type = state.get("intent_type")

    # Only process scan_graph intents
    if intent_type != "scan_graph":
        return {
            **state,
            "result_data": None,
            "error_message": None,
        }

    # Get project name
    project_name = state.get("project_name")

    if not project_name:
        return {
            **state,
            "result_data": None,
            "error_message": "请提供项目名称，例如：扫描项目 ad_monitor 图谱",
        }

    # 通过项目名查找项目 code（使用全局 Token）
    project_code, resolved_name = project_resolver.resolve(project_name)

    if not project_code:
        return {
            **state,
            "result_data": None,
            "error_message": f"未找到项目: {project_name}",
        }

    # 使用解析后的项目名
    display_name = resolved_name or project_name

    # 使用全局 API 配置
    ds_api_url = settings.DS_API_URL
    ds_api_token = settings.DS_API_TOKEN

    # Get code_root from environment or default
    code_root = os.getenv("CODE_ROOT", "")

    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    try:
        # Initialize storage and scanner
        storage = GraphStorage()
        scanner = GraphScanner(storage=storage, code_root=code_root)

        # Execute scan
        scan_result = scanner.scan_project(
            project_code=str(project_code),
            project_name=display_name,
            ds_api_url=ds_api_url,
            ds_api_token=ds_api_token,
        )

        # Generate indexes after scan
        indexer = GraphIndexer(storage)
        indexer.generate_all_indexes(str(project_code))

        # Count classes from graph
        graph_data = storage.load_graph(str(project_code))
        classes_count = 0
        if graph_data:
            nodes = graph_data.get("nodes", {})
            classes = nodes.get("classes", [])
            classes_count = len(classes)

        # Build result_data
        result_data = {
            "workflows_count": scan_result.get("workflows_count", 0),
            "tasks_count": scan_result.get("tasks_count", 0),
            "tables_count": scan_result.get("tables_count", 0),
            "classes_count": classes_count,
            "project_code": project_code,
            "project_name": display_name,
        }

    except Exception as e:
        error_message = f"扫描异常: {str(e)}"
        result_data = None

    return {
        **state,
        "result_data": result_data,
        "error_message": error_message,
        "project_name": display_name,
    }


__all__ = ["scan_graph_node"]