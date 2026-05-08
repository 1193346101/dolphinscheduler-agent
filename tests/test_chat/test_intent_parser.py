"""Tests for IntentParser intent parsing functionality."""

import pytest

from src.chat.tools.intent_parser import IntentParser


class TestIntentParser:
    """IntentParser 测试类"""

    @pytest.fixture
    def parser(self):
        """创建 IntentParser 实例"""
        return IntentParser()

    def test_parse_scan_graph_intent(self, parser):
        """测试扫描图谱意图解析"""
        # 测试 "扫描项目 X 图谱" 格式
        result = parser.parse("扫描项目 my_project 图谱")
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "my_project"

        # 测试 "更新 X 图谱" 格式
        result = parser.parse("更新 my_project 图谱")
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "my_project"

        # 测试带空格的情况
        result = parser.parse("扫描项目  test_proj  图谱")
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "test_proj"

    def test_parse_lineage_query_intent_downstream(self, parser):
        """测试下游血缘查询意图解析"""
        # 测试 "工作流 Y 的下游" 格式
        result = parser.parse("工作流 wf_123 的下游")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "wf_123"

        # 测试 "工作流 Y 下游" 格式
        result = parser.parse("工作流 wf_456 下游")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "wf_456"

    def test_parse_table_consumer_intent(self, parser):
        """测试表消费者查询意图解析"""
        # 测试 "表 T 被谁消费" 格式
        result = parser.parse("表 hive.db.table1 被谁消费")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_consumer"
        assert result["table_name"] == "hive.db.table1"

        # 测试 "表 T 的消费" 格式
        result = parser.parse("表 hive.db.table2 的消费")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_consumer"
        assert result["table_name"] == "hive.db.table2"

    def test_parse_workflow_nodes_intent(self, parser):
        """测试工作流节点查询意图解析"""
        # 测试 "工作流 Y 有哪些节点" 格式
        result = parser.parse("工作流 wf_001 有哪些节点")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "workflow_nodes"
        assert result["workflow_code"] == "wf_001"

        # 测试 "工作流 Y 的节点" 格式
        result = parser.parse("工作流 wf_002 的节点")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "workflow_nodes"
        assert result["workflow_code"] == "wf_002"

    def test_parse_upstream_intent(self, parser):
        """测试上游血缘查询意图解析"""
        # 测试 "工作流 Y 的上游" 格式
        result = parser.parse("工作流 wf_789 的上游")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "upstream"
        assert result["workflow_code"] == "wf_789"

        # 测试 "工作流 Y 上游依赖" 格式
        result = parser.parse("工作流 wf_999 上游依赖")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "upstream"
        assert result["workflow_code"] == "wf_999"

    def test_parse_table_producer_intent(self, parser):
        """测试表生产者查询意图解析"""
        # 测试 "表 T 被谁产出" 格式
        result = parser.parse("表 hive.db.source_table 被谁产出")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_producer"
        assert result["table_name"] == "hive.db.source_table"

        # 测试 "表 T 的生产" 格式
        result = parser.parse("表 hive.db.target_table 的生产")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_producer"
        assert result["table_name"] == "hive.db.target_table"

    def test_parse_visualize_lineage_intent(self, parser):
        """测试可视化血缘意图解析"""
        # 测试 "展示 Y 的影响链路" 格式
        result = parser.parse("展示 wf_visual 的影响链路")
        assert result["intent_type"] == "visualize_lineage"
        assert result["workflow_code"] == "wf_visual"

        # 测试 "可视化 Y 的下游" 格式
        result = parser.parse("可视化 wf_down 的下游")
        assert result["intent_type"] == "visualize_lineage"
        assert result["workflow_code"] == "wf_down"

    def test_parse_help_intent(self, parser):
        """测试帮助意图解析"""
        # 测试 "帮助"
        result = parser.parse("帮助")
        assert result["intent_type"] == "help"

        # 测试 "help"
        result = parser.parse("help")
        assert result["intent_type"] == "help"

        # 测试 "HELP" (大小写不敏感)
        result = parser.parse("HELP")
        assert result["intent_type"] == "help"

    def test_parse_unknown_intent(self, parser):
        """测试未知意图解析"""
        # 测试随机文本
        result = parser.parse("这是一条随机消息")
        assert result["intent_type"] == "unknown"

        # 测试空字符串
        result = parser.parse("")
        assert result["intent_type"] == "unknown"

        # 测试只有空格
        result = parser.parse("   ")
        assert result["intent_type"] == "unknown"

        # 测试不匹配的文本
        result = parser.parse("今天天气怎么样")
        assert result["intent_type"] == "unknown"

        # 测试部分匹配但不完整的文本
        result = parser.parse("扫描图谱")  # 缺少项目名
        assert result["intent_type"] == "unknown"

    def test_parse_with_extra_text(self, parser):
        """测试带额外文本的意图解析"""
        # 测试消息开头有意图
        result = parser.parse("请扫描项目 my_proj 图谱")
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "my_proj"

        # 测试消息中间有意图
        result = parser.parse("我想查询工作流 wf_001 的下游是什么")
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "wf_001"