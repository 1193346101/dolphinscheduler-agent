"""
ChatState TypedDict definition for DolphinScheduler chat module.

This module defines the state structure used throughout the chat
workflow, containing all fields for intent parsing, lineage query,
and response formatting.
"""

from typing import Dict, List, Any, Optional, TypedDict


class ChatState(TypedDict, total=False):
    """
    State definition for the chat workflow.

    The state tracks all information through the following stages:
    1. Input stage - User message and identifiers
    2. Intent parsing stage - Intent type and query parameters
    3. Query stage - Lineage query results
    4. Response stage - Formatted response content
    """

    # ==================== Input Stage ====================
    # User's natural language message
    message: str
    # User identifier (from DingTalk)
    user_id: str
    # Conversation identifier (from DingTalk)
    conversation_id: str

    # ==================== Intent Parsing Stage ====================
    # Intent type: scan_graph, lineage_query, visualize_lineage, help, unknown
    intent_type: str
    # Query type for lineage_query: downstream, upstream, workflow_nodes,
    #                                  table_consumer, table_producer
    query_type: Optional[str]

    # ==================== Parameters Stage ====================
    # Workflow code for workflow queries
    workflow_code: Optional[str]
    # Workflow instance id for instance queries
    workflow_instance_id: Optional[str]
    # Task code for task queries
    task_code: Optional[str]
    # Table name for table queries
    table_name: Optional[str]
    # Project code for graph operations
    project_code: Optional[str]
    # Project name for scan_graph intent
    project_name: Optional[str]
    # Date for instance queries (YYYY-MM-DD format, default today)
    query_date: Optional[str]

    # ==================== Query Stage ====================
    # Result data from lineage query
    result_data: Optional[Dict[str, Any]]

    # ==================== Response Stage ====================
    # Formatted response content (Markdown for DingTalk)
    response_content: Optional[str]
    # Error message if query failed
    error_message: Optional[str]


def create_chat_state(
    message: str,
    user_id: str,
    conversation_id: str,
) -> ChatState:
    """
    Create an initial ChatState with provided identifiers.

    Args:
        message: User's natural language message
        user_id: User identifier from DingTalk
        conversation_id: Conversation identifier from DingTalk

    Returns:
        Initial ChatState with input fields populated
    """
    return {
        "message": message,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "intent_type": "unknown",
        "query_type": None,
        "workflow_code": None,
        "workflow_instance_id": None,
        "task_code": None,
        "table_name": None,
        "project_code": None,
        "project_name": None,
        "query_date": None,
        "result_data": None,
        "response_content": None,
        "error_message": None,
    }


__all__ = ["ChatState", "create_chat_state"]