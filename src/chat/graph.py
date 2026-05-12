"""
LangGraph Flow Definition - Define complete conversation flow graph.

This module defines the state machine flow for chat conversations,
orchestrating the nodes through conditional routing.

重构版：支持所有意图类型，添加缺失节点和路由
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
    query_workflow_instances_node,
    query_status_node,
    query_logs_node,
    recover_failure_node,
    run_workflow_node,
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

    ROUTE_MAP = {
        "scan_graph": "scan_graph",
        "lineage_query": "lineage_query",
        "visualize_lineage": "visualize",
        "query_workflow": "query_workflow",
        "query_workflow_instances": "query_workflow_instances",
        "query_status": "query_status",
        "query_logs": "query_logs",
        "recover_failure": "recover_failure",
        "run_workflow": "run_workflow",
        "help": "format_response",
        "unknown": "format_response",
        "query_task_instances": "query_logs",  # 使用query_logs节点处理
    }

    return ROUTE_MAP.get(intent, "unknown")


def create_chat_graph():
    """
    Create the conversation flow graph.

    Flow:
    User message -> parse_intent -> route (branch)
      - scan_graph -> scan_graph_node -> format_response
      - lineage_query -> query_lineage_node -> format_response
      - visualize_lineage -> visualize_node -> format_response
      - query_workflow -> query_workflow_node -> format_response
      - query_workflow_instances -> query_workflow_instances_node -> format_response
      - query_status -> query_status_node -> format_response
      - query_logs -> query_logs_node -> format_response
      - recover_failure -> recover_failure_node -> format_response
      - run_workflow -> run_workflow_node -> format_response
      - help -> format_response (direct return)
      - unknown -> format_response (return cannot understand)

    Returns:
        Compiled LangGraph graph
    """
    graph = StateGraph(ChatState)

    # Add all nodes
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("scan_graph", scan_graph_node)
    graph.add_node("lineage_query", query_lineage_node)
    graph.add_node("visualize", visualize_node)
    graph.add_node("query_workflow", query_workflow_node)
    graph.add_node("query_workflow_instances", query_workflow_instances_node)
    graph.add_node("query_status", query_status_node)
    graph.add_node("query_logs", query_logs_node)
    graph.add_node("recover_failure", recover_failure_node)
    graph.add_node("run_workflow", run_workflow_node)
    graph.add_node("format_response", format_response_node)

    # Set entry point
    graph.set_entry_point("parse_intent")

    # Add conditional routing (all intents)
    graph.add_conditional_edges(
        "parse_intent",
        route_intent,
        {
            "scan_graph": "scan_graph",
            "lineage_query": "lineage_query",
            "visualize": "visualize",
            "query_workflow": "query_workflow",
            "query_workflow_instances": "query_workflow_instances",
            "query_status": "query_status",
            "query_logs": "query_logs",
            "recover_failure": "recover_failure",
            "run_workflow": "run_workflow",
            "help": "format_response",
            "unknown": "format_response",
        },
    )

    # Add edges to END (all nodes -> format_response -> END)
    graph.add_edge("scan_graph", "format_response")
    graph.add_edge("lineage_query", "format_response")
    graph.add_edge("visualize", "format_response")
    graph.add_edge("query_workflow", "format_response")
    graph.add_edge("query_workflow_instances", "format_response")
    graph.add_edge("query_status", "format_response")
    graph.add_edge("query_logs", "format_response")
    graph.add_edge("recover_failure", "format_response")
    graph.add_edge("run_workflow", "format_response")
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