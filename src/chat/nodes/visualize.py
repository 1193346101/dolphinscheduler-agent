"""
Visualize Node - 可视化节点

生成 Mermaid 可视化图
"""

from typing import Dict, Any, Optional

from ..state import ChatState
from src.graph import MermaidGenerator, GraphStorage


def visualize_node(state: ChatState) -> ChatState:
    """
    Generate Mermaid visualization for workflow lineage.

    Initializes MermaidGenerator with storage,
    calls generator.generate_downstream_graph() to create
    Mermaid diagram code.

    Args:
        state: Current ChatState with workflow_code and project_code populated

    Returns:
        Updated ChatState with result_data containing mermaid_code
    """
    intent_type = state.get("intent_type")

    # Only process visualize_lineage intents
    if intent_type != "visualize_lineage":
        return {
            **state,
            "result_data": None,
            "error_message": None,
        }

    # Get workflow_code (required)
    workflow_code = state.get("workflow_code")
    if not workflow_code:
        return {
            **state,
            "result_data": None,
            "error_message": "缺少工作流代码(workflow_code)",
        }

    # Get project_code (required for graph lookup)
    project_code = state.get("project_code")
    if not project_code:
        return {
            **state,
            "result_data": None,
            "error_message": "缺少项目代码(project_code)",
        }

    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    try:
        # Initialize storage and generator
        storage = GraphStorage()
        generator = MermaidGenerator(storage=storage)

        # Generate downstream graph
        mermaid_code = generator.generate_downstream_graph(
            project_code=project_code,
            workflow_code=workflow_code,
        )

        # Check if the result is an empty graph message
        if "empty[" in mermaid_code:
            # Extract the message from the empty graph
            error_message = mermaid_code.split("empty[")[1].split("]")[0]
            result_data = {
                "mermaid_code": mermaid_code,
                "is_empty": True,
            }
        else:
            result_data = {
                "mermaid_code": mermaid_code,
                "is_empty": False,
            }

    except Exception as e:
        error_message = f"可视化异常: {str(e)}"
        result_data = None

    return {
        **state,
        "result_data": result_data,
        "error_message": error_message,
    }


__all__ = ["visualize_node"]