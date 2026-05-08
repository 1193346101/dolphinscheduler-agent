"""Tests for parse_intent_node functionality."""

import pytest

from src.chat.state import ChatState, create_chat_state
from src.chat.nodes.parse_intent import parse_intent_node


class TestParseIntentNode:
    """parse_intent_node 测试类"""

    def test_parse_downstream_intent(self):
        """测试解析下游查询意图"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "wf_001"
        assert result["user_id"] == "user_001"
        assert result["conversation_id"] == "conv_001"

    def test_parse_upstream_intent(self):
        """测试解析上游查询意图"""
        state = create_chat_state(
            message="工作流 wf_002 的上游",
            user_id="user_002",
            conversation_id="conv_002",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "upstream"
        assert result["workflow_code"] == "wf_002"

    def test_parse_workflow_nodes_intent(self):
        """测试解析工作流节点查询意图"""
        state = create_chat_state(
            message="工作流 wf_003 有哪些节点",
            user_id="user_003",
            conversation_id="conv_003",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "workflow_nodes"
        assert result["workflow_code"] == "wf_003"

    def test_parse_table_consumer_intent(self):
        """测试解析表消费者查询意图"""
        state = create_chat_state(
            message="表 hive.db.table1 被谁消费",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_consumer"
        assert result["table_name"] == "hive.db.table1"

    def test_parse_table_producer_intent(self):
        """测试解析表生产者查询意图"""
        state = create_chat_state(
            message="表 hive.db.source_table 被谁产出",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_producer"
        assert result["table_name"] == "hive.db.source_table"

    def test_parse_scan_graph_intent(self):
        """测试解析扫描图谱意图"""
        state = create_chat_state(
            message="扫描项目 my_project 图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "my_project"

    def test_parse_visualize_lineage_intent(self):
        """测试解析可视化血缘意图"""
        state = create_chat_state(
            message="展示 wf_visual 的影响链路",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "visualize_lineage"
        assert result["workflow_code"] == "wf_visual"

    def test_parse_help_intent(self):
        """测试解析帮助意图"""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "help"

    def test_parse_help_intent_case_insensitive(self):
        """测试帮助意图大小写不敏感"""
        state = create_chat_state(
            message="HELP",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "help"

    def test_parse_unknown_intent(self):
        """测试解析未知意图"""
        state = create_chat_state(
            message="这是一条随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "unknown"
        assert result["query_type"] is None
        assert result["workflow_code"] is None
        assert result["table_name"] is None

    def test_parse_empty_message(self):
        """测试空消息"""
        state = create_chat_state(
            message="",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "unknown"
        assert result["query_type"] is None

    def test_parse_whitespace_message(self):
        """测试只有空格的消息"""
        state = create_chat_state(
            message="   ",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "unknown"

    def test_state_preserves_input_fields(self):
        """测试状态保留输入字段"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_abc",
            conversation_id="conv_xyz",
        )

        result = parse_intent_node(state)

        # Input fields should be preserved
        assert result["message"] == "工作流 wf_001 的下游"
        assert result["user_id"] == "user_abc"
        assert result["conversation_id"] == "conv_xyz"

    def test_parse_with_extra_text(self):
        """测试带额外文本的意图解析"""
        state = create_chat_state(
            message="请扫描项目 my_proj 图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = parse_intent_node(state)

        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "my_proj"


class TestParseIntentNodeIntegration:
    """Integration tests for parse_intent_node."""

    def test_multiple_queries_sequentially(self):
        """测试连续处理多个查询"""
        # Query 1: downstream
        state1 = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        result1 = parse_intent_node(state1)
        assert result1["intent_type"] == "lineage_query"

        # Query 2: table consumer
        state2 = create_chat_state(
            message="表 hive.db.table1 被谁消费",
            user_id="user_002",
            conversation_id="conv_002",
        )
        result2 = parse_intent_node(state2)
        assert result2["intent_type"] == "lineage_query"
        assert result2["query_type"] == "table_consumer"

        # Query 3: help
        state3 = create_chat_state(
            message="帮助",
            user_id="user_003",
            conversation_id="conv_003",
        )
        result3 = parse_intent_node(state3)
        assert result3["intent_type"] == "help"