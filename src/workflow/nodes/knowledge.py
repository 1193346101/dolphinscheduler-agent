"""
query_knowledge node

Query knowledge base, match historical cases
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...knowledge.manager import knowledge_manager, KnowledgeEntry


def query_knowledge(state: AgentState) -> AgentState:
    """
    Query knowledge base

    Based on error analysis result, query historical confirmed knowledge

    Args:
        state: Current state

    Returns:
        Updated state (knowledge_match)
    """
    # Get error analysis result
    error_analysis = state.get("error_analysis", {})
    error_type = error_analysis.get("error_type", "")
    error_message = error_analysis.get("error_message", "")

    # Get task type
    task_type = state.get("task_type", "UNKNOWN")

    # Query knowledge base
    match: Optional[KnowledgeEntry] = None

    if error_message:
        # Prefer matching error message
        match = knowledge_manager.match_error(task_type, error_message)

    if match:
        # Found match, update state
        return {
            **state,
            "knowledge_match": {
                "id": match.id,
                "error_type": match.error_type,
                "pattern": match.pattern,
                "analysis": match.analysis,
                "suggestion": match.suggestion,
                "config_fix": match.config_fix,
                "script_fix": match.script_fix,
                "confirmed_at": match.confirmed_at,
            },
        }

    # No match found
    return {
        **state,
        "knowledge_match": None,
    }


__all__ = ["query_knowledge"]