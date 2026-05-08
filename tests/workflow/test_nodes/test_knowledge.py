"""
query_knowledge 节点测试
"""

import pytest
import tempfile
import json
import os
from unittest.mock import patch, MagicMock

from src.workflow.nodes.knowledge import query_knowledge
from src.workflow.state import AgentState, create_initial_state
from src.knowledge.manager import KnowledgeEntry, KnowledgeManager


class TestQueryKnowledgeNode:
    """知识库查询节点测试"""

    def test_query_knowledge_no_error_analysis(self):
        """测试无错误分析时的查询"""
        state = create_initial_state(alert_raw={"projectCode": "123"})
        state["error_analysis"] = {}

        result = query_knowledge(state)

        assert result["knowledge_match"] is None

    def test_query_knowledge_with_match(self):
        """测试找到匹配的知识"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试知识库
            task_type = "spark"
            knowledge_dir = os.path.join(tmpdir, task_type, "confirmed.json")
            os.makedirs(os.path.dirname(knowledge_dir), exist_ok=True)

            entry = KnowledgeEntry(
                id="spark-001",
                task_type="SPARK",
                error_type="oom_executor",
                pattern="ExecutorOutOfMemory",
                analysis="Executor 内存不足",
                suggestion="增加 executor 内存",
                config_fix={"spark.executor.memory": "4g"},
                script_fix=None,
                status="confirmed",
                confirmed_at="2026-05-08T10:00:00",
            )

            with open(knowledge_dir, "w", encoding="utf-8") as f:
                json.dump([entry.__dict__], f, ensure_ascii=False, indent=2)

            # 创建状态
            state = create_initial_state(alert_raw={"projectCode": "123"})
            state["task_type"] = "SPARK"
            state["error_analysis"] = {
                "error_type": "oom_executor",
                "error_message": "ExecutorOutOfMemory error occurred",
            }

            # Mock 知识库管理器
            with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
                mock_manager.match_error.return_value = entry

                result = query_knowledge(state)

                assert result["knowledge_match"] is not None
                assert result["knowledge_match"]["id"] == "spark-001"
                assert result["knowledge_match"]["error_type"] == "oom_executor"
                assert result["knowledge_match"]["config_fix"] == {"spark.executor.memory": "4g"}

    def test_query_knowledge_no_match(self):
        """测试未找到匹配的知识"""
        state = create_initial_state(alert_raw={"projectCode": "123"})
        state["task_type"] = "SPARK"
        state["error_analysis"] = {
            "error_type": "unknown_error",
            "error_message": "Some unknown error",
        }

        with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
            mock_manager.match_error.return_value = None

            result = query_knowledge(state)

            assert result["knowledge_match"] is None

    def test_query_knowledge_preserves_state(self):
        """测试状态字段保留"""
        state = create_initial_state(alert_raw={"projectCode": "12345"})
        # 设置 project_code（parse_alert 节点会提取）
        state["project_code"] = "12345"
        state["task_type"] = "SHELL"
        state["error_analysis"] = {
            "error_type": "syntax_error",
            "error_message": "Syntax error in script",
        }
        state["log_content"] = "some log"

        with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
            mock_manager.match_error.return_value = None

            result = query_knowledge(state)

            # 确保其他字段保留
            assert result["project_code"] == "12345"
            assert result["task_type"] == "SHELL"
            assert result["log_content"] == "some log"
            assert result["error_analysis"]["error_type"] == "syntax_error"

    def test_query_knowledge_with_script_fix(self):
        """测试匹配到脚本修复方案"""
        entry = KnowledgeEntry(
            id="shell-001",
            task_type="SHELL",
            error_type="command_not_found",
            pattern="command not found: pyton",
            analysis="命令拼写错误",
            suggestion="修正命令拼写",
            config_fix=None,
            script_fix={"pyton": "python"},
            status="confirmed",
            confirmed_at="2026-05-08T10:00:00",
        )

        state = create_initial_state(alert_raw={"projectCode": "123"})
        state["task_type"] = "SHELL"
        state["error_analysis"] = {
            "error_type": "command_not_found",
            "error_message": "command not found: pyton",
        }

        with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
            mock_manager.match_error.return_value = entry

            result = query_knowledge(state)

            assert result["knowledge_match"]["script_fix"] == {"pyton": "python"}

    def test_query_knowledge_empty_error_message(self):
        """测试空错误消息"""
        state = create_initial_state(alert_raw={"projectCode": "123"})
        state["task_type"] = "SPARK"
        state["error_analysis"] = {
            "error_type": "oom_executor",
            "error_message": "",
        }

        with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
            mock_manager.match_error.return_value = None

            result = query_knowledge(state)

            assert result["knowledge_match"] is None

    def test_query_knowledge_unknown_task_type(self):
        """测试未知任务类型"""
        state = create_initial_state(alert_raw={"projectCode": "123"})
        state["task_type"] = "UNKNOWN"
        state["error_analysis"] = {
            "error_type": "some_error",
            "error_message": "Some error message",
        }

        with patch("src.workflow.nodes.knowledge.knowledge_manager") as mock_manager:
            mock_manager.match_error.return_value = None

            result = query_knowledge(state)

            assert result["knowledge_match"] is None