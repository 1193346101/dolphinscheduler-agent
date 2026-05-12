"""
Intent Context - 对话上下文管理

管理多轮对话的上下文，支持：
- 记忆最近提到的项目、工作流、表
- 参数补全（从上下文推断缺失参数）
- 多轮对话意图理解
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import json


@dataclass
class ConversationMemory:
    """对话记忆"""

    # 最近提到的实体
    last_project: Optional[str] = None
    last_workflow_code: Optional[str] = None
    last_workflow_name: Optional[str] = None
    last_table_name: Optional[str] = None
    last_instance_id: Optional[str] = None

    # 最近意图类型
    last_intent_type: Optional[str] = None
    last_query_type: Optional[str] = None

    # 时间戳
    updated_at: Optional[str] = None

    # 历史对话（最多保留5轮）
    history: List[Dict[str, Any]] = field(default_factory=list)


class IntentContext:
    """
    意图上下文管理器

    功能：
    1. 记忆对话实体（项目、工作流、表）
    2. 参数补全（从历史上下文推断）
    3. 多轮对话支持
    """

    # 会话存储（单例）
    _sessions: Dict[str, ConversationMemory] = {}

    def __init__(self):
        """初始化"""
        pass

    def get_memory(self, conversation_id: str) -> ConversationMemory:
        """获取会话记忆"""
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = ConversationMemory()
        return self._sessions[conversation_id]

    def update_memory(
        self,
        conversation_id: str,
        intent_result: Dict[str, Any],
        message: str
    ) -> ConversationMemory:
        """更新会话记忆"""
        memory = self.get_memory(conversation_id)

        # 更新实体
        if intent_result.get("project_name"):
            memory.last_project = intent_result["project_name"]
        if intent_result.get("workflow_code"):
            memory.last_workflow_code = intent_result["workflow_code"]
        if intent_result.get("workflow_name"):
            memory.last_workflow_name = intent_result["workflow_name"]
        if intent_result.get("table_name"):
            memory.last_table_name = intent_result["table_name"]
        if intent_result.get("workflow_instance_id"):
            memory.last_instance_id = intent_result["workflow_instance_id"]

        # 更新意图
        memory.last_intent_type = intent_result.get("intent_type")
        memory.last_query_type = intent_result.get("query_type")

        # 更新时间
        memory.updated_at = datetime.now().isoformat()

        # 记录历史
        memory.history.append({
            "message": message,
            "intent": intent_result,
            "timestamp": memory.updated_at,
        })

        # 限制历史长度
        if len(memory.history) > 5:
            memory.history = memory.history[-5:]

        return memory

    def complete_parameters(
        self,
        conversation_id: str,
        intent_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        参数补全

        从历史上下文推断缺失的参数：
        - 如果缺少project_name但最近提到过项目，使用last_project
        - 如果缺少workflow_code但最近提到过工作流，使用last_workflow_code
        - 等等
        """
        memory = self.get_memory(conversation_id)

        result = intent_result.copy()

        # 智能补全逻辑
        intent_type = result.get("intent_type", "unknown")

        # 需要project_name的意图
        if intent_type in ["query_workflow", "query_workflow_instances", "scan_graph"]:
            if not result.get("project_name") and memory.last_project:
                result["project_name"] = memory.last_project
                result["parameter_source"] = "context_memory"

        # 需要workflow_code的意图
        if intent_type in ["query_status", "query_logs", "recover_failure",
                          "run_workflow", "lineage_query", "visualize_lineage"]:
            if not result.get("workflow_code") and memory.last_workflow_code:
                result["workflow_code"] = memory.last_workflow_code
                result["parameter_source"] = "context_memory"

        # 需要table_name的意图
        if intent_type == "lineage_query" and result.get("query_type") in ["table_consumer", "table_producer"]:
            if not result.get("table_name") and memory.last_table_name:
                result["table_name"] = memory.last_table_name
                result["parameter_source"] = "context_memory"

        return result

    def can_complete_from_context(
        self,
        conversation_id: str,
        intent_type: str
    ) -> bool:
        """检查是否可以从上下文补全"""
        memory = self.get_memory(conversation_id)

        if intent_type in ["query_workflow", "query_workflow_instances", "scan_graph"]:
            return memory.last_project is not None
        elif intent_type in ["query_status", "query_logs", "recover_failure",
                             "run_workflow", "lineage_query"]:
            return memory.last_workflow_code is not None
        elif intent_type == "lineage_query":
            return memory.last_table_name is not None or memory.last_workflow_code is not None

        return False

    def clear_memory(self, conversation_id: str):
        """清除会话记忆"""
        if conversation_id in self._sessions:
            del self._sessions[conversation_id]

    def get_context_summary(self, conversation_id: str) -> str:
        """获取上下文摘要（用于LLM提示）"""
        memory = self.get_memory(conversation_id)

        parts = []
        if memory.last_project:
            parts.append(f"最近项目: {memory.last_project}")
        if memory.last_workflow_code:
            parts.append(f"最近工作流: {memory.last_workflow_code}")
        if memory.last_workflow_name:
            parts.append(f"工作流名: {memory.last_workflow_name}")
        if memory.last_table_name:
            parts.append(f"最近表: {memory.last_table_name}")

        if parts:
            return "对话上下文: " + ", ".join(parts)
        return "无上下文"


# 全局单例
intent_context = IntentContext()


__all__ = ["IntentContext", "ConversationMemory", "intent_context"]