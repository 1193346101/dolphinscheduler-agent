"""
RiskAssessTool 测试
"""

import pytest
from src.tools.risk_assess import RiskAssessTool


def test_assess_low_risk_single_config():
    """测试 LOW 风险 - 单配置变更"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "config_key": "spark.executor.memory"}],
        downstream_count=0,
    )

    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False


def test_assess_low_risk_rerun_transient():
    """测试 LOW 风险 - 临时重试"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "rerun", "transient": True, "retry_count": 1}],
        downstream_count=0,
    )

    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False


def test_assess_medium_risk_multiple_config():
    """测试 MEDIUM 风险 - 多配置变更"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "multi_param": True}],
        downstream_count=0,
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["approval_required"] is False


def test_assess_medium_risk_recover_small_downstream():
    """测试 MEDIUM 风险 - 下游少于 5 的恢复"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=3,
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["approval_required"] is False


def test_assess_high_risk_recover_many_downstream():
    """测试 HIGH 风险 - 下游超过 5 的恢复"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=12,
    )

    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_high_risk_structural_change():
    """测试 HIGH 风险 - 结构性变更"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "structural": True}],
        downstream_count=0,
    )

    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_critical_risk_delete():
    """测试 CRITICAL 风险 - 删除操作"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "delete"}],
        downstream_count=0,
    )

    assert result["risk_level"] == "CRITICAL"
    assert result["approval_required"] is True


def test_assess_critical_risk_cross_project():
    """测试 CRITICAL 风险 - 跨项目操作"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "cross_project"}],
        downstream_count=0,
    )

    assert result["risk_level"] == "CRITICAL"
    assert result["approval_required"] is True


def test_assess_multiple_actions_max_risk():
    """测试多个动作取最大风险"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[
            {"action_type": "config-change", "config_key": "spark.executor.memory"},
            {"action_type": "recover-failed"},
        ],
        downstream_count=10,
    )

    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_empty_actions():
    """测试空动作列表"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[],
        downstream_count=0,
    )

    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False


def test_assess_medium_risk_retry_count_over_3():
    """测试 MEDIUM 风险 - 重试次数超过 3"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "rerun", "retry_count": 4}],
        downstream_count=0,
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["approval_required"] is False


def test_assess_medium_risk_downstream_exactly_5():
    """测试 MEDIUM 风险 - 下游正好 5"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=5,
    )

    assert result["risk_level"] == "MEDIUM"


def test_assess_high_risk_downstream_exactly_6():
    """测试 HIGH 风险 - 下游正好 6"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=6,
    )

    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True