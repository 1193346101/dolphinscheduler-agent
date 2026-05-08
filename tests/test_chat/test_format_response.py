"""Tests for format_response_node functionality."""

import pytest

from src.chat.state import ChatState, create_chat_state
from src.chat.nodes.format_response import format_response_node


class TestFormatResponseNode:
    """format_response_node 测试类"""

    def test_format_downstream_response(self):
        """测试格式化下游查询响应"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"
        state["result_data"] = {
            "found": True,
            "direct": ["wf_002", "wf_003"],
            "all": ["wf_002", "wf_003", "wf_004"],
            "count": 3,
        }

        result = format_response_node(state)

        assert result["response_content"] is not None
        assert "wf_001" in result["response_content"]
        assert "下游依赖" in result["response_content"]
        assert "wf_002" in result["response_content"]
        assert "**总数**: 3" in result["response_content"]

    def test_format_downstream_not_found(self):
        """测试格式化下游查询未找到"""
        state = create_chat_state(
            message="工作流 wf_notexist 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_notexist"
        state["result_data"] = {
            "found": False,
            "direct": [],
            "all": [],
            "count": 0,
        }

        result = format_response_node(state)

        assert "未找到下游依赖" in result["response_content"]

    def test_format_upstream_response(self):
        """测试格式化上游查询响应"""
        state = create_chat_state(
            message="工作流 wf_001 的上游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "upstream"
        state["workflow_code"] = "wf_001"
        state["result_data"] = {
            "found": True,
            "upstream": ["wf_parent1", "wf_parent2"],
        }

        result = format_response_node(state)

        assert result["response_content"] is not None
        assert "上游依赖" in result["response_content"]
        assert "wf_parent1" in result["response_content"]
        assert "**总数**: 2" in result["response_content"]

    def test_format_workflow_nodes_response(self):
        """测试格式化工作流节点查询响应"""
        state = create_chat_state(
            message="工作流 wf_001 有哪些节点",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "workflow_nodes"
        state["workflow_code"] = "wf_001"
        state["result_data"] = {
            "found": True,
            "tasks": ["task_001", "task_002"],
            "task_names": {"task_001": "数据抽取", "task_002": "数据转换"},
            "task_types": {"task_001": "DATAX", "task_002": "SPARK"},
            "spark_classes": {"task_002": "com.example.DataProcessor"},
        }

        result = format_response_node(state)

        assert result["response_content"] is not None
        assert "任务节点" in result["response_content"]
        assert "数据抽取" in result["response_content"]
        assert "数据转换" in result["response_content"]
        assert "com.example.DataProcessor" in result["response_content"]

    def test_format_table_consumer_response(self):
        """测试格式化表消费者查询响应"""
        state = create_chat_state(
            message="表 hive.db.table1 被谁消费",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_consumer"
        state["table_name"] = "hive.db.table1"
        state["result_data"] = {
            "found": True,
            "workflows": ["wf_001", "wf_002"],
            "tasks": ["task_001", "task_002"],
            "classes": ["com.example.Consumer1"],
        }

        result = format_response_node(state)

        assert result["response_content"] is not None
        assert "消费者" in result["response_content"]
        assert "hive.db.table1" in result["response_content"]
        assert "wf_001" in result["response_content"]
        assert "com.example.Consumer1" in result["response_content"]

    def test_format_table_producer_response(self):
        """测试格式化表生产者查询响应"""
        state = create_chat_state(
            message="表 hive.db.table1 被谁产出",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_producer"
        state["table_name"] = "hive.db.table1"
        state["result_data"] = {
            "found": True,
            "workflows": ["wf_source"],
            "tasks": ["task_source"],
            "classes": ["com.example.Producer"],
        }

        result = format_response_node(state)

        assert result["response_content"] is not None
        assert "生产者" in result["response_content"]
        assert "hive.db.table1" in result["response_content"]
        assert "com.example.Producer" in result["response_content"]

    def test_format_error_response_workflow(self):
        """测试格式化工作流错误响应"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"
        state["error_message"] = "工作流不存在"

        result = format_response_node(state)

        assert "查询失败" in result["response_content"]
        assert "wf_001" in result["response_content"]
        assert "工作流不存在" in result["response_content"]

    def test_format_error_response_table(self):
        """测试格式化表错误响应"""
        state = create_chat_state(
            message="表 hive.db.table1 被谁消费",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_consumer"
        state["table_name"] = "hive.db.table1"
        state["error_message"] = "表不存在"

        result = format_response_node(state)

        assert "查询失败" in result["response_content"]
        assert "hive.db.table1" in result["response_content"]

    def test_format_help_intent(self):
        """测试格式化帮助意图"""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "help"

        result = format_response_node(state)

        assert "帮助" in result["response_content"]
        assert "支持的命令" in result["response_content"]
        assert "血缘查询" in result["response_content"]

    def test_format_unknown_intent(self):
        """测试格式化未知意图"""
        state = create_chat_state(
            message="随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "unknown"

        result = format_response_node(state)

        assert "不理解" in result["response_content"]
        assert "帮助" in result["response_content"]

    def test_format_scan_graph_intent(self):
        """测试格式化扫描图谱意图"""
        state = create_chat_state(
            message="扫描项目 my_project 图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "scan_graph"
        state["project_name"] = "my_project"

        result = format_response_node(state)

        assert "扫描图谱" in result["response_content"]
        assert "my_project" in result["response_content"]

    def test_format_visualize_lineage_intent(self):
        """测试格式化可视化血缘意图"""
        state = create_chat_state(
            message="展示 wf_001 的影响链路",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "visualize_lineage"
        state["workflow_code"] = "wf_001"

        result = format_response_node(state)

        assert "血缘可视化" in result["response_content"]
        assert "wf_001" in result["response_content"]

    def test_format_empty_result_data(self):
        """测试格式化空结果数据"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["result_data"] = None

        result = format_response_node(state)

        assert "查询无结果" in result["response_content"]

    def test_state_preserves_input_fields(self):
        """测试状态保留输入字段"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_xyz",
            conversation_id="conv_abc",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"
        state["result_data"] = {
            "found": True,
            "direct": ["wf_002"],
            "all": ["wf_002"],
            "count": 1,
        }

        result = format_response_node(state)

        assert result["message"] == "工作流 wf_001 的下游"
        assert result["user_id"] == "user_xyz"
        assert result["conversation_id"] == "conv_abc"

    def test_format_markdown_structure(self):
        """测试 Markdown 结构格式"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"
        state["result_data"] = {
            "found": True,
            "direct": ["wf_002"],
            "all": ["wf_002"],
            "count": 1,
        }

        result = format_response_node(state)

        # Should have proper Markdown headers
        assert result["response_content"].startswith("###")

        # Should have bold text
        assert "**总数**" in result["response_content"]
        assert "**直接依赖**" in result["response_content"]


class TestFormatResponseNodeIntegration:
    """Integration tests for format_response_node."""

    def test_full_workflow_format(self):
        """测试完整流程格式化"""
        # Simulate full workflow state
        state = create_chat_state(
            message="工作流 wf_123 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_123"
        state["project_code"] = "proj_001"
        state["result_data"] = {
            "found": True,
            "direct": ["wf_456", "wf_789"],
            "all": ["wf_456", "wf_789", "wf_abc"],
            "count": 3,
        }

        result = format_response_node(state)

        # Should be complete Markdown response
        assert result["response_content"] is not None
        assert "### 工作流 wf_123 下游依赖" in result["response_content"]
        assert "**总数**: 3" in result["response_content"]
        assert "wf_456" in result["response_content"]
        assert "wf_abc" in result["response_content"]