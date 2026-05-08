"""Tests for visualize_node functionality."""

import pytest
from unittest.mock import Mock, patch

from src.chat.state import ChatState, create_chat_state
from src.chat.nodes.visualize import visualize_node


class TestVisualizeNode:
    """visualize_node 测试类"""

    @pytest.fixture
    def mock_generator(self):
        """创建 Mock MermaidGenerator"""
        generator = Mock()
        generator.generate_downstream_graph = Mock(return_value="""
graph TD
  wf_001[数据导入]
  wf_001 --> wf_002[数据清洗]
  wf_002 --> wf_003[数据分析]
""")
        return generator

    @pytest.fixture
    def mock_storage(self):
        """创建 Mock GraphStorage"""
        storage = Mock()
        storage.load_graph = Mock(return_value={
            "nodes": {
                "workflows": [
                    {"code": "wf_001", "name": "数据导入"},
                    {"code": "wf_002", "name": "数据清洗"},
                ]
            }
        })
        storage.load_index = Mock(return_value={
            "workflow_downstream": {
                "wf_001": {
                    "direct": ["wf_002"],
                    "all": ["wf_002", "wf_003"],
                    "count": 2,
                }
            }
        })
        return storage

    def test_visualize_downstream(self, mock_generator, mock_storage):
        """测试下游可视化成功"""
        with patch('src.chat.nodes.visualize.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.visualize.MermaidGenerator', return_value=mock_generator):
            state = create_chat_state(
                message="展示 wf_001 的影响链路",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "visualize_lineage"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = visualize_node(state)

            assert result["result_data"]["mermaid_code"] is not None
            assert result["result_data"]["is_empty"] is False
            assert "graph TD" in result["result_data"]["mermaid_code"]
            assert result["error_message"] is None

    def test_visualize_no_workflow(self):
        """测试缺少工作流代码"""
        state = create_chat_state(
            message="展示 ? 的影响链路",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "visualize_lineage"
        state["project_code"] = "proj_001"
        # No workflow_code

        result = visualize_node(state)

        assert result["result_data"] is None
        assert "缺少工作流代码" in result["error_message"]

    def test_visualize_no_project(self):
        """测试缺少项目代码"""
        state = create_chat_state(
            message="展示 wf_001 的影响链路",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "visualize_lineage"
        state["workflow_code"] = "wf_001"
        # No project_code

        result = visualize_node(state)

        assert result["result_data"] is None
        assert "缺少项目代码" in result["error_message"]

    def test_visualize_empty_graph(self):
        """测试空图谱"""
        mock_generator = Mock()
        mock_generator.generate_downstream_graph = Mock(
            return_value="graph TD\n  empty[Workflow not found: wf_notexist]"
        )
        mock_storage = Mock()

        with patch('src.chat.nodes.visualize.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.visualize.MermaidGenerator', return_value=mock_generator):
            state = create_chat_state(
                message="展示 wf_notexist 的影响链路",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "visualize_lineage"
            state["workflow_code"] = "wf_notexist"
            state["project_code"] = "proj_001"

            result = visualize_node(state)

            assert result["result_data"]["is_empty"] is True
            assert "Workflow not found" in result["error_message"]

    def test_visualize_exception_handling(self):
        """测试可视化异常处理"""
        mock_generator = Mock()
        mock_generator.generate_downstream_graph = Mock(
            side_effect=Exception("Storage error")
        )
        mock_storage = Mock()

        with patch('src.chat.nodes.visualize.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.visualize.MermaidGenerator', return_value=mock_generator):
            state = create_chat_state(
                message="展示 wf_001 的影响链路",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "visualize_lineage"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = visualize_node(state)

            assert result["result_data"] is None
            assert "可视化异常" in result["error_message"]

    def test_non_visualize_intent(self):
        """测试非可视化意图"""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "help"

        result = visualize_node(state)

        # Should not execute any visualization
        assert result["result_data"] is None
        assert result["error_message"] is None

    def test_state_preserves_input_fields(self, mock_generator, mock_storage):
        """测试状态保留输入字段"""
        with patch('src.chat.nodes.visualize.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.visualize.MermaidGenerator', return_value=mock_generator):
            state = create_chat_state(
                message="展示 wf_001 的影响链路",
                user_id="user_xyz",
                conversation_id="conv_abc",
            )
            state["intent_type"] = "visualize_lineage"
            state["workflow_code"] = "wf_001"
            state["project_code"] = "proj_001"

            result = visualize_node(state)

            # Input fields should be preserved
            assert result["message"] == "展示 wf_001 的影响链路"
            assert result["user_id"] == "user_xyz"
            assert result["conversation_id"] == "conv_abc"