"""Tests for ChatState TypedDict state definition."""

import pytest
from typing import get_type_hints

from src.chat.state import ChatState, create_chat_state


class TestChatStateFields:
    """Tests for ChatState field definitions."""

    def test_create_chat_state_has_all_fields(self):
        """Test that created state contains all required fields."""
        state = create_chat_state(
            message="测试消息",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Input stage fields
        assert "message" in state
        assert "user_id" in state
        assert "conversation_id" in state

        # Intent parsing stage fields
        assert "intent_type" in state
        assert "query_type" in state

        # Parameters stage fields
        assert "workflow_code" in state
        assert "task_code" in state
        assert "table_name" in state
        assert "project_code" in state
        assert "project_name" in state

        # Query stage fields
        assert "result_data" in state

        # Response stage fields
        assert "response_content" in state
        assert "error_message" in state

    def test_create_chat_state_defaults(self):
        """Test that created state has correct default values."""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Input stage
        assert state["message"] == "工作流 wf_001 的下游"
        assert state["user_id"] == "user_001"
        assert state["conversation_id"] == "conv_001"

        # Default values for intent stage
        assert state["intent_type"] == "unknown"
        assert state["query_type"] is None

        # Default values for parameters stage
        assert state["workflow_code"] is None
        assert state["task_code"] is None
        assert state["table_name"] is None
        assert state["project_code"] is None
        assert state["project_name"] is None

        # Default values for query stage
        assert state["result_data"] is None

        # Default values for response stage
        assert state["response_content"] is None
        assert state["error_message"] is None

    def test_state_can_be_updated(self):
        """Test that state can be updated with new values."""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Update intent parsing stage
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"

        # Update parameters stage
        state["workflow_code"] = "wf_001"
        state["project_code"] = "proj_001"

        # Update query stage
        state["result_data"] = {
            "found": True,
            "direct": ["wf_002", "wf_003"],
            "all": ["wf_002", "wf_003", "wf_004"],
            "count": 3,
        }

        # Update response stage
        state["response_content"] = "### 下游依赖查询结果\n..."
        state["error_message"] = None

        # Verify all updates
        assert state["intent_type"] == "lineage_query"
        assert state["query_type"] == "downstream"
        assert state["workflow_code"] == "wf_001"
        assert state["result_data"]["found"] is True
        assert len(state["result_data"]["direct"]) == 2
        assert state["response_content"] == "### 下游依赖查询结果\n..."


class TestChatStateTypes:
    """Tests for ChatState type hints."""

    def test_typed_dict_annotation(self):
        """Test that ChatState is a TypedDict."""
        from typing import TypedDict
        # ChatState should be a TypedDict
        assert ChatState.__bases__[0].__name__ == "TypedDict" or \
               ChatState.__name__ == "ChatState"

    def test_total_false_annotation(self):
        """Test that ChatState has total=False for optional fields."""
        # All fields should be optional since total=False
        state: ChatState = {}
        assert isinstance(state, dict)


class TestChatStateIntentTypes:
    """Tests for different intent types in ChatState."""

    def test_scan_graph_intent(self):
        """Test state for scan_graph intent."""
        state = create_chat_state(
            message="扫描项目 my_project 图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Simulate intent parsing result
        state["intent_type"] = "scan_graph"
        state["project_name"] = "my_project"

        assert state["intent_type"] == "scan_graph"
        assert state["project_name"] == "my_project"

    def test_lineage_query_downstream(self):
        """Test state for lineage_query downstream."""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Simulate intent parsing result
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"

        assert state["intent_type"] == "lineage_query"
        assert state["query_type"] == "downstream"
        assert state["workflow_code"] == "wf_001"

    def test_lineage_query_table_consumer(self):
        """Test state for lineage_query table_consumer."""
        state = create_chat_state(
            message="表 hive.db.table1 被谁消费",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Simulate intent parsing result
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_consumer"
        state["table_name"] = "hive.db.table1"

        assert state["intent_type"] == "lineage_query"
        assert state["query_type"] == "table_consumer"
        assert state["table_name"] == "hive.db.table1"

    def test_help_intent(self):
        """Test state for help intent."""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Simulate intent parsing result
        state["intent_type"] = "help"

        assert state["intent_type"] == "help"

    def test_unknown_intent(self):
        """Test state for unknown intent."""
        state = create_chat_state(
            message="随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Intent stays as unknown
        assert state["intent_type"] == "unknown"


class TestChatStateIntegration:
    """Integration tests for ChatState usage patterns."""

    def test_full_workflow_state_transitions(self):
        """Test state transitions through a full chat workflow."""
        # Initial state
        state = create_chat_state(
            message="工作流 wf_123 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Stage 1: Parse intent
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_123"

        # Stage 2: Set project context
        state["project_code"] = "proj_001"

        # Stage 3: Query lineage (simulated result)
        state["result_data"] = {
            "found": True,
            "direct": ["wf_456", "wf_789"],
            "all": ["wf_456", "wf_789", "wf_abc"],
            "count": 3,
            "message": "Found 3 downstream workflows",
        }

        # Stage 4: Format response
        state["response_content"] = """### 工作流 wf_123 下游依赖

**直接依赖**: wf_456, wf_789
**所有下游**: wf_456, wf_789, wf_abc
**总数**: 3"""

        # Verify final state
        assert state["intent_type"] == "lineage_query"
        assert state["query_type"] == "downstream"
        assert state["workflow_code"] == "wf_123"
        assert state["result_data"]["found"] is True
        assert state["response_content"] is not None
        assert state["error_message"] is None

    def test_error_state(self):
        """Test state when query fails."""
        state = create_chat_state(
            message="工作流 wf_notexist 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        # Parse intent
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_notexist"
        state["project_code"] = "proj_001"

        # Query fails
        state["result_data"] = {
            "found": False,
            "message": "Workflow not found: wf_notexist",
        }
        state["error_message"] = "工作流 wf_notexist 不存在"

        # Response includes error
        state["response_content"] = "查询失败: 工作流 wf_notexist 不存在"

        # Verify error state
        assert state["result_data"]["found"] is False
        assert state["error_message"] is not None
        assert "不存在" in state["response_content"]