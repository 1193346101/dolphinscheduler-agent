"""
query_knowledge 节点

查询知识库，匹配历史案例
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...knowledge.manager import knowledge_manager, KnowledgeEntry


def query_knowledge(state: AgentState) -> AgentState:
    """
    查询知识库

    根据错误分析结果，查询历史已确认的知识

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (knowledge_match)
    """
    # 获取错误分析结果
    error_analysis = state.get("error_analysis", {})
    error_type = error_analysis.get("error_type", "")
    error_message = error_analysis.get("error_message", "")

    # 获取任务类型
    task_type = state.get("task_type", "UNKNOWN")

    # 查询知识库
    match: Optional[KnowledgeEntry] = None

    if error_message:
        # 优先匹配错误消息
        match = knowledge_manager.match_error(task_type, error_message)

    if match:
        # 找到匹配，更新状态
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

    # 未找到匹配
    return {
        **state,
        "knowledge_match": None,
    }


__all__ = ["query_knowledge"]