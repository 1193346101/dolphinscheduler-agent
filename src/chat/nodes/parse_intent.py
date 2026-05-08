"""
Parse Intent Node - 解析用户消息意图

从用户的自然语言消息中提取意图类型和参数
"""

from typing import Dict, Any

from ..state import ChatState
from ..tools.intent_parser import IntentParser


def parse_intent_node(state: ChatState) -> ChatState:
    """
    Parse user message to extract intent and parameters.

    Uses IntentParser to analyze the message and extract:
    - intent_type: scan_graph, lineage_query, visualize_lineage, help, unknown
    - query_type: downstream, upstream, workflow_nodes, table_consumer, table_producer
    - workflow_code, table_name, project_name based on intent

    Args:
        state: Current ChatState with message field populated

    Returns:
        Updated ChatState with intent fields populated
    """
    # Get message from state
    message = state.get("message", "")

    if not message or not message.strip():
        # Return state with unknown intent if message is empty
        return {
            **state,
            "intent_type": "unknown",
            "query_type": None,
            "workflow_code": None,
            "table_name": None,
            "project_name": None,
        }

    # Initialize parser and parse the message
    parser = IntentParser()
    parsed_result = parser.parse(message)

    # Extract parsed fields
    intent_type = parsed_result.get("intent_type", "unknown")
    query_type = parsed_result.get("query_type")
    workflow_code = parsed_result.get("workflow_code")
    table_name = parsed_result.get("table_name")
    project_name = parsed_result.get("project_name")

    # Update state with parsed intent
    return {
        **state,
        "intent_type": intent_type,
        "query_type": query_type,
        "workflow_code": workflow_code,
        "table_name": table_name,
        "project_name": project_name,
    }


__all__ = ["parse_intent_node"]