"""
Scan Graph Node - 图谱扫描节点

调用 GraphScanner 执行图谱扫描
"""

from typing import Dict, Any, Optional
import os

from ..state import ChatState
from src.graph import GraphScanner, GraphStorage, GraphIndexer
from src.config.projects import projects_registry


def scan_graph_node(state: ChatState) -> ChatState:
    """
    Execute graph scan based on project_name or project_code.

    Initializes GraphScanner with storage and code_root,
    calls scanner.scan_project(), then calls indexer.generate_all_indexes()
    to generate query indexes.

    Args:
        state: Current ChatState with project_name or project_code populated

    Returns:
        Updated ChatState with result_data containing scan statistics:
        - workflows_count: number of workflows scanned
        - tasks_count: number of tasks scanned
        - tables_count: number of tables found
        - classes_count: number of classes found
    """
    intent_type = state.get("intent_type")

    # Only process scan_graph intents
    if intent_type != "scan_graph":
        return {
            **state,
            "result_data": None,
            "error_message": None,
        }

    # Get project info - need either project_name or project_code
    project_name = state.get("project_name")
    project_code = state.get("project_code")

    # If only project_name provided, look up the code
    if project_name and not project_code:
        project_config = projects_registry.get_by_name(project_name)
        if project_config:
            project_code = str(project_config.code)
        else:
            return {
                **state,
                "result_data": None,
                "error_message": f"未找到项目配置: {project_name}",
            }

    # If only project_code provided, look up the name and config
    if project_code and not project_name:
        project_config = projects_registry.get_by_code(int(project_code))
        if project_config:
            project_name = project_config.name
        else:
            return {
                **state,
                "result_data": None,
                "error_message": f"未找到项目配置: {project_code}",
            }

    # If neither provided, error
    if not project_name and not project_code:
        return {
            **state,
            "result_data": None,
            "error_message": "缺少项目名称或项目代码",
        }

    # Get project config for API credentials
    project_config = projects_registry.get_by_code(int(project_code))
    if not project_config:
        return {
            **state,
            "result_data": None,
            "error_message": f"未找到项目配置: {project_code}",
        }

    ds_api_url = project_config.ds_api_url
    ds_api_token = project_config.ds_api_token

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
            project_code=project_code,
            project_name=project_name,
            ds_api_url=ds_api_url,
            ds_api_token=ds_api_token,
        )

        # Generate indexes after scan
        indexer = GraphIndexer(storage)
        indexer.generate_all_indexes(project_code)

        # Count classes from graph
        graph_data = storage.load_graph(project_code)
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
            "project_name": project_name,
        }

    except Exception as e:
        error_message = f"扫描异常: {str(e)}"
        result_data = None

    return {
        **state,
        "result_data": result_data,
        "error_message": error_message,
    }


__all__ = ["scan_graph_node"]