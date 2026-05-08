"""Tests for scan_graph_node functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.chat.state import ChatState, create_chat_state
from src.chat.nodes.scan_graph import scan_graph_node
from src.config.projects import ProjectConfig


class TestScanGraphNode:
    """scan_graph_node 测试类"""

    @pytest.fixture
    def mock_project_config(self):
        """创建 Mock ProjectConfig"""
        return ProjectConfig(
            name="test_project",
            code=12345,
            ds_api_url="http://ds-api.example.com",
            ds_api_token="test_token",
        )

    @pytest.fixture
    def mock_scanner(self):
        """创建 Mock GraphScanner"""
        scanner = Mock()
        scanner.scan_project = Mock(return_value={
            "workflows_count": 10,
            "tasks_count": 50,
            "tables_count": 25,
        })
        return scanner

    @pytest.fixture
    def mock_storage(self):
        """创建 Mock GraphStorage"""
        storage = Mock()
        storage.load_graph = Mock(return_value={
            "nodes": {
                "classes": [
                    {"name": "com.example.Class1"},
                    {"name": "com.example.Class2"},
                    {"name": "com.example.Class3"},
                ]
            }
        })
        storage.save_graph = Mock()
        return storage

    @pytest.fixture
    def mock_indexer(self):
        """创建 Mock GraphIndexer"""
        indexer = Mock()
        indexer.generate_all_indexes = Mock(return_value={
            "downstream": {},
            "table_consumer": {},
            "workflow_nodes": {},
        })
        return indexer

    def test_scan_graph_success(
        self, mock_project_config, mock_scanner, mock_storage, mock_indexer
    ):
        """测试扫描成功"""
        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry, \
             patch('src.chat.nodes.scan_graph.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.scan_graph.GraphScanner', return_value=mock_scanner), \
             patch('src.chat.nodes.scan_graph.GraphIndexer', return_value=mock_indexer):
            # Setup registry mock
            mock_registry.get_by_code = Mock(return_value=mock_project_config)
            mock_registry.get_by_name = Mock(return_value=mock_project_config)

            state = create_chat_state(
                message="扫描项目 test_project 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "scan_graph"
            state["project_name"] = "test_project"
            state["project_code"] = "12345"

            result = scan_graph_node(state)

            assert result["result_data"]["workflows_count"] == 10
            assert result["result_data"]["tasks_count"] == 50
            assert result["result_data"]["tables_count"] == 25
            assert result["result_data"]["classes_count"] == 3
            assert result["error_message"] is None

    def test_scan_graph_no_project(self):
        """测试缺少项目"""
        state = create_chat_state(
            message="扫描图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "scan_graph"
        # No project_name or project_code

        result = scan_graph_node(state)

        assert result["result_data"] is None
        assert "缺少项目名称或项目代码" in result["error_message"]

    def test_scan_graph_with_code_only(
        self, mock_project_config, mock_scanner, mock_storage, mock_indexer
    ):
        """测试只用项目代码扫描"""
        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry, \
             patch('src.chat.nodes.scan_graph.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.scan_graph.GraphScanner', return_value=mock_scanner), \
             patch('src.chat.nodes.scan_graph.GraphIndexer', return_value=mock_indexer):
            # Setup registry mock - only get_by_code returns config
            mock_registry.get_by_code = Mock(return_value=mock_project_config)
            mock_registry.get_by_name = Mock(return_value=None)

            state = create_chat_state(
                message="扫描项目 12345 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "scan_graph"
            state["project_code"] = "12345"
            # No project_name

            result = scan_graph_node(state)

            assert result["result_data"]["workflows_count"] == 10
            assert result["result_data"]["project_name"] == "test_project"
            assert result["error_message"] is None

    def test_scan_graph_with_name_only(
        self, mock_project_config, mock_scanner, mock_storage, mock_indexer
    ):
        """测试只用项目名称扫描"""
        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry, \
             patch('src.chat.nodes.scan_graph.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.scan_graph.GraphScanner', return_value=mock_scanner), \
             patch('src.chat.nodes.scan_graph.GraphIndexer', return_value=mock_indexer):
            # Setup registry mock - only get_by_name returns config
            mock_registry.get_by_name = Mock(return_value=mock_project_config)
            mock_registry.get_by_code = Mock(return_value=mock_project_config)

            state = create_chat_state(
                message="扫描项目 test_project 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "scan_graph"
            state["project_name"] = "test_project"
            # No project_code initially

            result = scan_graph_node(state)

            assert result["result_data"]["workflows_count"] == 10
            assert result["result_data"]["project_code"] == "12345"
            assert result["error_message"] is None

    def test_scan_graph_project_not_found(self):
        """测试项目未找到"""
        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry:
            mock_registry.get_by_name = Mock(return_value=None)
            mock_registry.get_by_code = Mock(return_value=None)

            state = create_chat_state(
                message="扫描项目 nonexistent 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "scan_graph"
            state["project_name"] = "nonexistent"

            result = scan_graph_node(state)

            assert result["result_data"] is None
            assert "未找到项目配置" in result["error_message"]

    def test_scan_graph_exception_handling(
        self, mock_project_config
    ):
        """测试扫描异常处理"""
        mock_storage = Mock()
        mock_scanner = Mock()
        mock_scanner.scan_project = Mock(side_effect=Exception("API connection failed"))

        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry, \
             patch('src.chat.nodes.scan_graph.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.scan_graph.GraphScanner', return_value=mock_scanner):
            mock_registry.get_by_code = Mock(return_value=mock_project_config)
            mock_registry.get_by_name = Mock(return_value=mock_project_config)

            state = create_chat_state(
                message="扫描项目 test_project 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )
            state["intent_type"] = "scan_graph"
            state["project_code"] = "12345"

            result = scan_graph_node(state)

            assert result["result_data"] is None
            assert "扫描异常" in result["error_message"]

    def test_non_scan_graph_intent(self):
        """测试非扫描图谱意图"""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "help"

        result = scan_graph_node(state)

        # Should not execute any scan
        assert result["result_data"] is None
        assert result["error_message"] is None

    def test_state_preserves_input_fields(
        self, mock_project_config, mock_scanner, mock_storage, mock_indexer
    ):
        """测试状态保留输入字段"""
        with patch('src.chat.nodes.scan_graph.projects_registry') as mock_registry, \
             patch('src.chat.nodes.scan_graph.GraphStorage', return_value=mock_storage), \
             patch('src.chat.nodes.scan_graph.GraphScanner', return_value=mock_scanner), \
             patch('src.chat.nodes.scan_graph.GraphIndexer', return_value=mock_indexer):
            mock_registry.get_by_code = Mock(return_value=mock_project_config)
            mock_registry.get_by_name = Mock(return_value=mock_project_config)

            state = create_chat_state(
                message="扫描项目 test_project 图谱",
                user_id="user_xyz",
                conversation_id="conv_abc",
            )
            state["intent_type"] = "scan_graph"
            state["project_code"] = "12345"

            result = scan_graph_node(state)

            # Input fields should be preserved
            assert result["message"] == "扫描项目 test_project 图谱"
            assert result["user_id"] == "user_xyz"
            assert result["conversation_id"] == "conv_abc"