"""
LangGraph Flow Definition - Define complete conversation flow graph.

This module defines the state machine flow for chat conversations,
orchestrating the nodes through conditional routing.
"""

from langgraph.graph import StateGraph, END

from .state import ChatState
from .nodes import (
    parse_intent_node,
    query_lineage_node,
    scan_graph_node,
    visualize_node,
    format_response_node,
    query_workflow_node,
)


def route_intent(state: ChatState) -> str:
    """
    Route function - determine which path to follow based on intent.

    Args:
        state: Current ChatState with intent_type populated

    Returns:
        Route name for the next node
    """
    intent = state.get("intent_type", "unknown")
    if intent == "scan_graph":
        return "scan_graph"
    elif intent == "lineage_query":
        return "lineage_query"
    elif intent == "visualize_lineage":
        return "visualize"
    elif intent == "query_workflow":
        return "query_workflow"
    elif intent == "query_status":
        return "query_workflow"  # 使用相同节点处理
    elif intent == "help":
        return "help"
    else:
        return "unknown"


def create_chat_graph():
    """
    Create the conversation flow graph.

    Flow:
    User message -> parse_intent -> route (branch)
      - scan_graph -> scan_graph_node -> format_response
      - lineage_query -> query_lineage_node -> format_response
      - visualize_lineage -> visualize_node -> format_response
      - query_workflow -> query_workflow_node -> format_response
      - help -> format_response (direct return)
      - unknown -> format_response (return cannot understand)

    Returns:
        Compiled LangGraph graph
    """
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("scan_graph", scan_graph_node)
    graph.add_node("lineage_query", query_lineage_node)
    graph.add_node("visualize", visualize_node)
    graph.add_node("query_workflow", query_workflow_node)
    graph.add_node("format_response", format_response_node)

    # Set entry point
    graph.set_entry_point("parse_intent")

    # Add conditional routing
    graph.add_conditional_edges(
        "parse_intent",
        route_intent,
        {
            "scan_graph": "scan_graph",
            "lineage_query": "lineage_query",
            "visualize": "visualize",
            "query_workflow": "query_workflow",
            "help": "format_response",
            "unknown": "format_response",
        },
    )

    # Add edges to END
    graph.add_edge("scan_graph", "format_response")
    graph.add_edge("lineage_query", "format_response")
    graph.add_edge("visualize", "format_response")
    graph.add_edge("query_workflow", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()


# Create singleton instance for reuse
_chat_graph = None


def get_chat_graph():
    """
    Get the singleton chat graph instance.

    Returns:
        Compiled LangGraph graph
    """
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = create_chat_graph()
    return _chat_graph


__all__ = [
    "create_chat_graph",
    "get_chat_graph",
    "route_intent",
]