"""
risk.py 节点测试
"""

import pytest
from src.workflow.state import create_initial_state, INITIAL_STATE
from src.workflow.nodes.risk import assess_risk, impact_analysis
from src.tools.impact import ImpactTool


# ==================== ImpactTool Tests ====================


class TestImpactTool:
    """ImpactTool 测试类"""

    def test_analyze_downstream_no_downstream(self):
        """测试没有下游任务的情况"""
        tool = ImpactTool()
        task_relations = []
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 0
        assert result["downstream_list"] == []
        assert "没有下游依赖" in result["impact_summary"]

    def test_analyze_downstream_single_downstream(self):
        """测试单个下游任务"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
        ]
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 1
        assert "task_2" in result["downstream_list"]
        assert "影响 1 个下游任务" in result["impact_summary"]

    def test_analyze_downstream_multiple_downstream(self):
        """测试多个下游任务"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
            {"preTaskCode": "task_1", "postTaskCode": "task_3"},
            {"preTaskCode": "task_2", "postTaskCode": "task_4"},
        ]
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 3
        assert set(result["downstream_list"]) == {"task_2", "task_3", "task_4"}

    def test_analyze_downstream_chain(self):
        """测试链式依赖"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
            {"preTaskCode": "task_2", "postTaskCode": "task_3"},
            {"preTaskCode": "task_3", "postTaskCode": "task_4"},
        ]
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 3
        assert set(result["downstream_list"]) == {"task_2", "task_3", "task_4"}

    def test_analyze_downstream_diamond_dependency(self):
        """测试菱形依赖"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
            {"preTaskCode": "task_1", "postTaskCode": "task_3"},
            {"preTaskCode": "task_2", "postTaskCode": "task_4"},
            {"preTaskCode": "task_3", "postTaskCode": "task_4"},
        ]
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 3
        assert set(result["downstream_list"]) == {"task_2", "task_3", "task_4"}

    def test_analyze_downstream_many_tasks(self):
        """测试超过10个下游任务的摘要"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": f"task_{i}"} for i in range(2, 15)
        ]
        result = tool.analyze_downstream(task_relations, "task_1")

        assert result["downstream_tasks"] == 13
        assert "另外 3 个" in result["impact_summary"]

    def test_analyze_downstream_integer_codes(self):
        """测试整数类型的任务编码"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": 123, "postTaskCode": 456},
            {"preTaskCode": 456, "postTaskCode": 789},
        ]
        result = tool.analyze_downstream(task_relations, "123")

        assert result["downstream_tasks"] == 2
        assert set(result["downstream_list"]) == {"456", "789"}

    def test_analyze_downstream_no_matching_task(self):
        """测试查询的任务不在关系中"""
        tool = ImpactTool()
        task_relations = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
        ]
        result = tool.analyze_downstream(task_relations, "task_999")

        assert result["downstream_tasks"] == 0
        assert result["downstream_list"] == []


# ==================== assess_risk Tests ====================


class TestAssessRisk:
    """assess_risk 节点测试"""

    def test_assess_risk_low_risk(self):
        """测试低风险场景"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "rerun"}]
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "LOW"
        assert result["approval_required"] is False

    def test_assess_risk_medium_risk_retry_count(self):
        """测试中等风险场景 - 重试次数多"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "rerun", "retry_count": 5}]
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "MEDIUM"
        assert result["approval_required"] is False

    def test_assess_risk_medium_risk_downstream(self):
        """测试中等风险场景 - 有下游任务"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed"}]
        state["downstream_tasks"] = 3

        result = assess_risk(state)

        assert result["risk_level"] == "MEDIUM"
        assert result["approval_required"] is False

    def test_assess_risk_high_risk(self):
        """测试高风险场景"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed"}]
        state["downstream_tasks"] = 10

        result = assess_risk(state)

        assert result["risk_level"] == "HIGH"
        assert result["approval_required"] is True

    def test_assess_risk_critical_risk_delete(self):
        """测试严重风险场景 - 删除操作"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "delete"}]
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "CRITICAL"
        assert result["approval_required"] is True

    def test_assess_risk_critical_risk_cross_project(self):
        """测试严重风险场景 - 跨项目操作"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "cross_project"}]
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "CRITICAL"
        assert result["approval_required"] is True

    def test_assess_risk_multiple_actions(self):
        """测试多个动作的风险评估"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = [
            {"action_type": "rerun"},
            {"action_type": "config-change", "multi_param": True},
        ]
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "MEDIUM"
        assert len(result["risk_factors"]) == 2

    def test_assess_risk_empty_actions(self):
        """测试空动作列表"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["suggested_actions"] = []
        state["downstream_tasks"] = 0

        result = assess_risk(state)

        assert result["risk_level"] == "LOW"
        assert result["approval_required"] is False


# ==================== impact_analysis Tests ====================


class TestImpactAnalysis:
    """impact_analysis 节点测试"""

    def test_impact_analysis_with_relations(self):
        """测试有任务关系的分析"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "task_1"
        state["task_relations"] = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
            {"preTaskCode": "task_2", "postTaskCode": "task_3"},
        ]

        result = impact_analysis(state)

        assert result["downstream_tasks"] == 2
        assert set(result["downstream_list"]) == {"task_2", "task_3"}
        assert "影响 2 个下游任务" in result["impact_summary"]

    def test_impact_analysis_no_relations(self):
        """测试没有任务关系的分析"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "task_1"
        state["task_relations"] = []

        result = impact_analysis(state)

        assert result["downstream_tasks"] == 0
        assert "没有下游依赖" in result["impact_summary"]

    def test_impact_analysis_missing_relations_key(self):
        """测试缺少 task_relations 键"""
        state = create_initial_state(alert_raw={})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "task_1"
        # 不设置 task_relations

        result = impact_analysis(state)

        assert result["downstream_tasks"] == 0
        assert "无法分析下游影响" in result["impact_summary"]

    def test_impact_analysis_preserves_other_state(self):
        """测试分析保留其他状态"""
        state = create_initial_state(alert_raw={"test": "data"})
        state["project_code"] = "123"
        state["workflow_code"] = "456"
        state["task_code"] = "task_1"
        state["task_type"] = "SPARK"
        state["error_time"] = "2025-05-07 14:30:00"
        state["project_valid"] = True
        state["error_patterns"] = ["error1", "error2"]
        state["task_relations"] = [
            {"preTaskCode": "task_1", "postTaskCode": "task_2"},
        ]

        result = impact_analysis(state)

        # 确保其他状态被保留
        assert result["project_code"] == "123"
        assert result["workflow_code"] == "456"
        assert result["task_code"] == "task_1"
        assert result["task_type"] == "SPARK"
        assert result["project_valid"] is True
        assert result["error_patterns"] == ["error1", "error2"]
        # 新的分析结果
        assert result["downstream_tasks"] == 1