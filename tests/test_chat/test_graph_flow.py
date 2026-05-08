"""Tests for LangGraph flow definition functionality."""

import pytest
from unittest.mock import patch, Mock

from src.chat.state import ChatState, create_chat_state
from src.chat.graph import create_chat_graph, get_chat_graph, route_intent


class TestRouteIntent:
    """Tests for route_intent function."""

    def test_route_scan_graph(self):
        """Test routing for scan_graph intent."""
        state = create_chat_state(
            message="扫描项目 my_project 图谱",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "scan_graph"

        result = route_intent(state)
        assert result == "scan_graph"

    def test_route_lineage_query(self):
        """Test routing for lineage_query intent."""
        state = create_chat_state(
            message="工作流 wf_001 的下游",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "lineage_query"

        result = route_intent(state)
        assert result == "lineage_query"

    def test_route_visualize(self):
        """Test routing for visualize_lineage intent."""
        state = create_chat_state(
            message="展示 wf_001 的影响链路",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "visualize_lineage"

        result = route_intent(state)
        assert result == "visualize"

    def test_route_help(self):
        """Test routing for help intent."""
        state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "help"

        result = route_intent(state)
        assert result == "help"

    def test_route_unknown(self):
        """Test routing for unknown intent."""
        state = create_chat_state(
            message="随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = "unknown"

        result = route_intent(state)
        assert result == "unknown"

    def test_route_missing_intent_type(self):
        """Test routing when intent_type is missing."""
        state = create_chat_state(
            message="随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )
        del state["intent_type"]

        result = route_intent(state)
        assert result == "unknown"

    def test_route_empty_intent_type(self):
        """Test routing when intent_type is empty string."""
        state = create_chat_state(
            message="随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )
        state["intent_type"] = ""

        result = route_intent(state)
        assert result == "unknown"


class TestCreateChatGraph:
    """Tests for create_chat_graph function."""

    def test_create_graph_returns_compiled_graph(self):
        """Test that create_chat_graph returns a compiled graph."""
        graph = create_chat_graph()

        # Graph should have invoke method (CompiledStateGraph)
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "stream")
        """Test that graph has all required nodes."""
        graph = create_chat_graph()

        # Check that graph can be invoked with a state
        assert hasattr(graph, "invoke")

    def test_graph_singleton(self):
        """Test get_chat_graph returns singleton."""
        graph1 = get_chat_graph()
        graph2 = get_chat_graph()

        # Should return the same instance
        assert graph1 is graph2


class TestGraphFlowLineageQuery:
    """Tests for lineage_query flow through the graph."""

    @patch("src.chat.graph.query_lineage_node")
    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_lineage_query_downstream(
        self, mock_format, mock_query
    ):
        """Test graph flow for lineage_query downstream."""
        # Setup mocks
        mock_query.return_value = {
            **create_chat_state(
                message="工作流 wf_001 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "lineage_query",
            "query_type": "downstream",
            "workflow_code": "wf_001",
            "project_code": "proj_001",
            "result_data": {
                "found": True,
                "direct": ["wf_002"],
                "all": ["wf_002"],
                "count": 1,
            },
        }
        mock_format.return_value = {
            **mock_query.return_value,
            "response_content": "### 工作流 wf_001 下游依赖\n...",
        }

        # Create graph and invoke
        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="工作流 wf_001 的下游",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "lineage_query",
                "query_type": "downstream",
                "workflow_code": "wf_001",
            }

            initial_state = create_chat_state(
                message="工作流 wf_001 的下游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            initial_state["project_code"] = "proj_001"

            result = graph.invoke(initial_state)

        # Verify query was called
        mock_query.assert_called_once()
        mock_format.assert_called_once()

        # Verify result has response_content
        assert "response_content" in result

    @patch("src.chat.graph.query_lineage_node")
    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_lineage_query_upstream(
        self, mock_format, mock_query
    ):
        """Test graph flow for lineage_query upstream."""
        # Setup mocks
        mock_query.return_value = {
            **create_chat_state(
                message="工作流 wf_002 的上游",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "lineage_query",
            "query_type": "upstream",
            "workflow_code": "wf_002",
            "project_code": "proj_001",
            "result_data": {
                "found": True,
                "upstream": ["wf_001"],
            },
        }
        mock_format.return_value = {
            **mock_query.return_value,
            "response_content": "### 工作流 wf_002 上游依赖\n...",
        }

        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="工作流 wf_002 的上游",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "lineage_query",
                "query_type": "upstream",
                "workflow_code": "wf_002",
            }

            initial_state = create_chat_state(
                message="工作流 wf_002 的上游",
                user_id="user_001",
                conversation_id="conv_001",
            )
            initial_state["project_code"] = "proj_001"

            result = graph.invoke(initial_state)

        assert "response_content" in result


class TestGraphFlowScanGraph:
    """Tests for scan_graph flow through the graph."""

    @patch("src.chat.graph.scan_graph_node")
    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_scan_graph(self, mock_format, mock_scan):
        """Test graph flow for scan_graph intent."""
        # Setup mocks
        mock_scan.return_value = {
            **create_chat_state(
                message="扫描项目 my_project 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "scan_graph",
            "project_name": "my_project",
            "project_code": "proj_001",
            "result_data": {
                "workflows_count": 10,
                "tasks_count": 50,
                "tables_count": 20,
                "classes_count": 5,
            },
        }
        mock_format.return_value = {
            **mock_scan.return_value,
            "response_content": "### 扫描图谱\n...",
        }

        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="扫描项目 my_project 图谱",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "scan_graph",
                "project_name": "my_project",
            }

            initial_state = create_chat_state(
                message="扫描项目 my_project 图谱",
                user_id="user_001",
                conversation_id="conv_001",
            )

            result = graph.invoke(initial_state)

        mock_scan.assert_called_once()
        mock_format.assert_called_once()
        assert "response_content" in result


class TestGraphFlowUnknown:
    """Tests for unknown intent flow through the graph."""

    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_unknown(self, mock_format):
        """Test graph flow for unknown intent."""
        mock_format.return_value = {
            **create_chat_state(
                message="随机消息",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "unknown",
            "response_content": "抱歉，我不理解您的消息...",
        }

        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="随机消息",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "unknown",
            }

            initial_state = create_chat_state(
                message="随机消息",
                user_id="user_001",
                conversation_id="conv_001",
            )

            result = graph.invoke(initial_state)

        mock_format.assert_called_once()
        assert "response_content" in result


class TestGraphFlowHelp:
    """Tests for help intent flow through the graph."""

    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_help(self, mock_format):
        """Test graph flow for help intent."""
        mock_format.return_value = {
            **create_chat_state(
                message="帮助",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "help",
            "response_content": "### 帮助\n...",
        }

        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="帮助",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "help",
            }

            initial_state = create_chat_state(
                message="帮助",
                user_id="user_001",
                conversation_id="conv_001",
            )

            result = graph.invoke(initial_state)

        mock_format.assert_called_once()
        assert "response_content" in result


class TestGraphFlowVisualize:
    """Tests for visualize_lineage flow through the graph."""

    @patch("src.chat.graph.visualize_node")
    @patch("src.chat.graph.format_response_node")
    def test_graph_flow_visualize(self, mock_format, mock_visualize):
        """Test graph flow for visualize_lineage intent."""
        mock_visualize.return_value = {
            **create_chat_state(
                message="展示 wf_001 的影响链路",
                user_id="user_001",
                conversation_id="conv_001",
            ),
            "intent_type": "visualize_lineage",
            "workflow_code": "wf_001",
            "project_code": "proj_001",
            "result_data": {
                "mermaid_code": "graph TD\n...",
                "is_empty": False,
            },
        }
        mock_format.return_value = {
            **mock_visualize.return_value,
            "response_content": "### 血缘可视化\n...",
        }

        graph = create_chat_graph()

        with patch("src.chat.graph.parse_intent_node") as mock_parse:
            mock_parse.return_value = {
                **create_chat_state(
                    message="展示 wf_001 的影响链路",
                    user_id="user_001",
                    conversation_id="conv_001",
                ),
                "intent_type": "visualize_lineage",
                "workflow_code": "wf_001",
            }

            initial_state = create_chat_state(
                message="展示 wf_001 的影响链路",
                user_id="user_001",
                conversation_id="conv_001",
            )
            initial_state["project_code"] = "proj_001"

            result = graph.invoke(initial_state)

        mock_visualize.assert_called_once()
        mock_format.assert_called_once()
        assert "response_content" in result


class TestGraphFlowIntegration:
    """Integration tests for complete graph flow."""

    def test_full_flow_with_real_nodes(self):
        """Test full flow with real nodes (no mocking of nodes)."""
        # This test uses real parse_intent_node and format_response_node
        # but mocks the external dependencies
        graph = create_chat_graph()

        initial_state = create_chat_state(
            message="帮助",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = graph.invoke(initial_state)

        # Should have help response
        assert "response_content" in result
        assert "帮助" in result["response_content"]

    def test_full_flow_unknown_with_real_nodes(self):
        """Test full flow with unknown intent using real nodes."""
        graph = create_chat_graph()

        initial_state = create_chat_state(
            message="这是一条随机消息",
            user_id="user_001",
            conversation_id="conv_001",
        )

        result = graph.invoke(initial_state)

        # Should have unknown response
        assert "response_content" in result
        assert "不理解" in result["response_content"] or "帮助" in result["response_content"]