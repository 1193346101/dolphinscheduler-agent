"""Tests for query_lineage_node functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.chat.state import ChatState, create_chat_state
from src.chat.nodes.query_lineage import query_lineage_node


class TestQueryLineageNode:
    """query_lineage_node 测试类"""

    @pytest.fixture
    def mock_querier(self):
        """创建 Mock GraphQuerier"""
        querier = Mock()
        querier.query_workflow_downstream = Mock(return_value={
            "found": True,
            "direct": ["wf_002", "wf_003"],
            "all": ["wf_002", "wf_003", "wf_004"],
            "count": 3,
            "message": "Found 3 downstream workflows",
        })
        querier.query_workflow_upstream = Mock(return_value={
            "found": True,
            "upstream": ["wf_parent1", "wf_parent2"],
            "message": "Found 2 upstream workflows",
        })
        querier.query_workflow_nodes = Mock(return_value={
            "found": True,
            "tasks": ["task_001", "task_002"],
            "task_names": {"task_001": "数据抽取", "task_002": "数据转换"},
            "task_types": {"task_001": "DATAX", "task_002": "SPARK"},
            "spark_classes": {"task_002": "com.example.DataProcessor"},
            "message": "Found 2 tasks in workflow",
        })
        querier.query_table_consumers = Mock(return_value={
            "found": True,
            "workflows": ["wf_001", "wf_002"],
            "tasks": ["task_001", "task_002"],
            "classes": ["com.example.Consumer1"],
            "message": "Found 2 tasks consuming this table",
        })
        querier.query_table_producers = Mock(return_value={
            "found": True,
            "workflows": ["wf_source"],
            "tasks": ["task_source"],
            "classes": ["com.example.Producer"],
            "message": "Found 1 task producing this table",
        })
        return querier

    def test_query_downstream_success(self, mock_querier):
        """测试下游查询成功"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_001 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is True
            assert result["result_data"]["count"] == 3
            assert len(result["result_data"]["direct"]) == 2
            assert result["error_message"] is None

    def test_query_upstream_success(self, mock_querier):
        """测试上游查询成功"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_001 的上游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "upstream"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is True
            assert len(result["result_data"]["upstream"]) == 2
            assert result["error_message"] is None

    def test_query_workflow_nodes_success(self, mock_querier):
        """测试工作流节点查询成功"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_001 有哪些节点",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "workflow_nodes"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is True
            assert len(result["result_data"]["tasks"]) == 2
            assert "task_001" in result["result_data"]["task_names"]
            assert result["error_message"] is None

    def test_query_table_consumers_success(self, mock_querier):
        """测试表消费者查询成功"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="表 hive.db.table1 被谁消费",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "table_consumer"
            state["table_name"] = "hive.db.table1"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is True
            assert len(result["result_data"]["tasks"]) == 2
            assert result["error_message"] is None

    def test_query_table_producers_success(self, mock_querier):
        """测试表生产者查询成功"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="表 hive.db.table1 被谁产出",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "table_producer"
            state["table_name"] = "hive.db.table1"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is True
            assert len(result["result_data"]["tasks"]) == 1
            assert result["error_message"] is None

    def test_query_not_found(self, mock_querier):
        """测试查询未找到结果"""
        mock_querier.query_workflow_downstream = Mock(return_value={
            "found": False,
            "direct": [],
            "all": [],
            "count": 0,
            "message": "Workflow not found: wf_notexist",
        })
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_notexist 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            state["workflow_code"] = "wf_notexist"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"]["found"] is False
            assert result["error_message"] == "Workflow not found: wf_notexist"

    def test_query_missing_project_code(self):
        """测试缺少项目代码"""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "wf_001"
        # No project_code

        result = query_lineage_node(state)

        assert result["result_data"] is None
        assert "缺少项目代码" in result["error_message"]

    def test_query_missing_workflow_code(self, mock_querier):
        """测试缺少工作流代码"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 ? 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            # No workflow_code
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"] is None
            assert "缺少工作流代码" in result["error_message"]

    def test_query_missing_table_name(self, mock_querier):
        """测试缺少表名"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="表 ? 被谁消费",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "table_consumer"
            # No table_name
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"] is None
            assert "缺少表名" in result["error_message"]

    def test_non_lineage_query_intent(self):
        """测试非血缘查询意图"""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "help"

        result = query_lineage_node(state)

        # Should not execute any query
        assert result["result_data"] is None
        assert result["error_message"] is None

    def test_unknown_query_type(self, mock_querier):
        """测试未知的查询类型"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="未知查询",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "unknown_type"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"] is None
            assert "未知的查询类型" in result["error_message"]

    def test_state_preserves_input_fields(self, mock_querier):
        """测试状态保留输入字段"""
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_001 的下游",
                user_id="user_xyz",
                conversation_id="conv_abc",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            # Input fields should be preserved
            assert result["message"] == "工作流 wf_001 的下游"
            assert result["user_id"] == "user_xyz"
            assert result["conversation_id"] == "conv_abc"

    def test_query_exception_handling(self, mock_querier):
        """测试查询异常处理"""
        mock_querier.query_workflow_downstream = Mock(
            side_effect=Exception("Database connection failed")
        )
        with patch('src.chat.nodes.query_lineage.GraphStorage'), \
             patch('src.chat.nodes.query_lineage.GraphQuerier', return_value=mock_querier):
            state = create_chat_state(
                message="工作流 wf_001 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = query_lineage_node(state)

            assert result["result_data"] is None
            assert "查询异常" in result["error_message"]