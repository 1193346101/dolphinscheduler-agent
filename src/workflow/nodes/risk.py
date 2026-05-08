"""
risk.py - 风险评估节点
"""

from typing import Dict
from ..state import AgentState
from ...tools.risk_assess import RiskAssessTool
from ...tools.impact import ImpactTool
from ...tools.graph_impact import GraphImpactTool


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
    # 优先使用图谱分析
    graph_impact = GraphImpactTool()

    project_code = state.get("project_code")
    workflow_code = state.get("process_definition_code")
    task_code = state.get("task_code")

    # 尝试使用图谱分析工作流下游
    graph_result = graph_impact.analyze_workflow_downstream(
        str(project_code),
        str(workflow_code),
    )

    if graph_result.get("graph_available"):
        # 图谱可用，使用图谱结果
        return {
            **state,
            "downstream_tasks": graph_result["downstream_count"],
            "downstream_list": graph_result["downstream_workflows"],
            "impact_summary": graph_impact.build_impact_summary(
                str(workflow_code),
                graph_result["downstream_workflows"],
                [],
                graph_result["workflow_names"],
            ),
            "impact_source": "graph",
        }

    # 降级：使用 ImpactTool（基于任务关系）
    impact_tool = ImpactTool()

    # 获取工作流 DAG - 这里暂时使用空列表，后续集成 DSCLIClient
    task_relations = state.get("task_relations", None)

    # task_relations 为 None 表示无法获取，返回默认值
    # task_relations 为 [] 表示可以获取但没有下游依赖
    if task_relations is None:
        return {
            **state,
            "downstream_tasks": 0,
            "downstream_list": [],
            "impact_summary": "无法分析下游影响",
            "impact_source": "fallback_none",
        }

    impact = impact_tool.analyze_downstream(task_relations, str(task_code))
    return {
        **state,
        "downstream_tasks": impact["downstream_tasks"],
        "downstream_list": impact["downstream_list"],
        "impact_summary": impact["impact_summary"],
        "impact_source": "fallback_impact_tool",
    }


__all__ = ["assess_risk", "impact_analysis"]