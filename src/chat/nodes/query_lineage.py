"""
Query Lineage Node - 查询血缘关系

根据解析的意图类型调用 GraphQuerier 执行查询
"""

from typing import Dict, Any, Optional

from ..state import ChatState
from src.graph import GraphQuerier, GraphStorage


def query_lineage_node(state: ChatState) -> ChatState:
    """
    Execute lineage query based on parsed intent.

    Based on query_type, calls appropriate GraphQuerier method:
    - downstream → querier.query_workflow_downstream
    - upstream → querier.query_workflow_upstream
    - workflow_nodes → querier.query_workflow_nodes
    - table_consumer → querier.query_table_consumers
    - table_producer → querier.query_table_producers

    Args:
        state: Current ChatState with intent_type, query_type populated

    Returns:
        Updated ChatState with result_data or error_message
    """
    intent_type = state.get("intent_type")
    query_type = state.get("query_type")

    # Only process lineage_query intents
    if intent_type != "lineage_query":
        return {
            **state,
            "result_data": None,
            "error_message": None,
        }

    # Get project_code (required for all queries)
    project_code = state.get("project_code")
    if not project_code:
        return {
            **state,
            "result_data": None,
            "error_message": "缺少项目代码(project_code)，无法执行查询",
        }

    # Initialize querier
    storage = GraphStorage()
    querier = GraphQuerier(storage)

    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    try:
        # Execute query based on query_type
        if query_type == "downstream":
            workflow_code = state.get("workflow_code")
            if not workflow_code:
                error_message = "缺少工作流代码(workflow_code)"
            else:
                result_data = querier.query_workflow_downstream(
                    project_code=project_code,
                    workflow_code=workflow_code,
                )

        elif query_type == "upstream":
            workflow_code = state.get("workflow_code")
            if not workflow_code:
                error_message = "缺少工作流代码(workflow_code)"
            else:
                result_data = querier.query_workflow_upstream(
                    project_code=project_code,
                    workflow_code=workflow_code,
                )

        elif query_type == "workflow_nodes":
            workflow_code = state.get("workflow_code")
            if not workflow_code:
                error_message = "缺少工作流代码(workflow_code)"
            else:
                result_data = querier.query_workflow_nodes(
                    project_code=project_code,
                    workflow_code=workflow_code,
                )

        elif query_type == "table_consumer":
            table_name = state.get("table_name")
            if not table_name:
                error_message = "缺少表名(table_name)"
            else:
                result_data = querier.query_table_consumers(
                    project_code=project_code,
                    table_name=table_name,
                )

        elif query_type == "table_producer":
            table_name = state.get("table_name")
            if not table_name:
                error_message = "缺少表名(table_name)"
            else:
                result_data = querier.query_table_producers(
                    project_code=project_code,
                    table_name=table_name,
                )

        else:
            error_message = f"未知的查询类型: {query_type}"

        # Check if query returned not found
        if result_data and not result_data.get("found", False):
            error_message = result_data.get("message", "查询失败")

    except Exception as e:
        error_message = f"查询异常: {str(e)}"
        result_data = None

    return {
        **state,
        "result_data": result_data,
        "error_message": error_message,
    }


__all__ = ["query_lineage_node"]