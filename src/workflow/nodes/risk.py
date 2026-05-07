"""
risk.py - 风险评估节点
"""

from typing import Dict
from ..state import AgentState
from ...tools.risk_assess import RiskAssessTool
from ...tools.impact import ImpactTool


def assess_risk(state: AgentState) -> AgentState:
    """评估风险等级"""
    tool = RiskAssessTool()

    result = tool.assess(
        suggested_actions=state.get("suggested_actions", []),
        downstream_count=state.get("downstream_tasks", 0),
    )

    return {
        **state,
        "risk_level": result["risk_level"],
        "risk_factors": result["risk_factors"],
        "approval_required": result["approval_required"],
    }


def impact_analysis(state: AgentState) -> AgentState:
    """分析下游影响"""
    impact_tool = ImpactTool()

    # 获取工作流 DAG - 这里暂时使用空列表，后续集成 DSCLIClient
    task_relations = state.get("task_relations", None)
    task_code = state["task_code"]

    # task_relations 为 None 表示无法获取，返回默认值
    # task_relations 为 [] 表示可以获取但没有下游依赖
    if task_relations is None:
        return {
            **state,
            "downstream_tasks": 0,
            "downstream_list": [],
            "impact_summary": "无法分析下游影响",
        }

    impact = impact_tool.analyze_downstream(task_relations, task_code)
    return {
        **state,
        "downstream_tasks": impact["downstream_tasks"],
        "downstream_list": impact["downstream_list"],
        "impact_summary": impact["impact_summary"],
    }


__all__ = ["assess_risk", "impact_analysis"]