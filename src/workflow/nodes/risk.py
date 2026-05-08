"""
risk.py - 风险评估节点

支持子工作流影响分析
"""

from typing import Dict
from ..state import AgentState
from ...tools.risk_assess import RiskAssessTool
from ...tools.impact import ImpactTool
from ...tools.graph_impact import GraphImpactTool
from ...graph.querier import GraphQuerier
from ...graph.storage import GraphStorage
from ...config import settings


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
    """
    分析下游影响

    支持子工作流的影响分析：
    - 子工作流内任务的下游
    - 父工作流中子工作流之后的下游
    - 父工作流的下游工作流

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (downstream_tasks, downstream_list, impact_summary)
    """
    project_code = state.get("project_code")
    workflow_code = state.get("workflow_code")
    task_code = state.get("task_code")
    is_sub_workflow = state.get("is_sub_workflow", False)

    # 使用图谱分析
    graph_storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    querier = GraphQuerier(graph_storage)

    # 检查图谱是否存在
    graph_available = graph_storage.graph_exists(project_code)

    # 如果图谱存在且是子工作流，使用完整的影响分析
    if graph_available and is_sub_workflow:
        sub_impact = querier.query_subworkflow_impact(
            project_code,
            workflow_code,
            task_code
        )

        if sub_impact["found"]:
            # 构建完整的影响摘要
            impact_summary = _build_subworkflow_impact_summary(sub_impact)

            return {
                **state,
                "downstream_tasks": sub_impact["total_impact_count"],
                "downstream_list": (
                    sub_impact["task_downstream_in_subworkflow"] +
                    sub_impact["downstream_in_parent"] +
                    sub_impact["parent_downstream_workflows"]
                ),
                "impact_summary": impact_summary,
                "impact_source": "sub_workflow_analysis",
                "sub_workflow_info": sub_impact.get("sub_workflow"),
                "parent_workflow_info": sub_impact.get("parent_workflow"),
            }

    # 图谱存在且是普通工作流，使用标准下游分析
    if graph_available:
        graph_impact = GraphImpactTool(graph_storage)

        # 分析工作流下游
        workflow_result = graph_impact.analyze_workflow_downstream(
            str(project_code),
            str(workflow_code),
        )

        if workflow_result.get("graph_available"):
            # 同时分析任务级下游
            task_result = graph_impact.analyze_task_downstream(
                str(project_code),
                str(workflow_code),
                str(task_code)
            )

            total_downstream = (
                workflow_result["downstream_count"] +
                task_result.get("downstream_count", 0)
            )

            combined_list = (
                workflow_result["downstream_workflows"] +
                task_result.get("downstream_tasks", [])
            )

            impact_summary = graph_impact.build_impact_summary(
                str(workflow_code),
                workflow_result["downstream_workflows"],
                task_result.get("downstream_tasks", []),
                workflow_result["workflow_names"],
            )

            return {
                **state,
                "downstream_tasks": total_downstream,
                "downstream_list": combined_list,
                "impact_summary": impact_summary,
                "impact_source": "graph",
            }

    # 降级：图谱不存在时使用 task_relations 分析
    impact_tool = ImpactTool()
    task_relations = state.get("task_relations")

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


def _build_subworkflow_impact_summary(sub_impact: Dict) -> str:
    """
    构建子工作流影响摘要

    Args:
        sub_impact: 子工作流影响分析结果

    Returns:
        Markdown 格式的摘要
    """
    lines = ["## 子工作流失败影响分析\n"]

    # 子工作流信息
    sub_wf = sub_impact.get("sub_workflow", {})
    if sub_wf:
        lines.append(f"**子工作流**: {sub_wf.get('name', sub_wf.get('code'))}\n")

    # 子工作流内影响
    task_downstream = sub_impact.get("task_downstream_in_subworkflow", [])
    if task_downstream:
        lines.append(f"**子工作流内下游任务**: {len(task_downstream)} 个\n")

    # 父工作流信息
    parent_wf = sub_impact.get("parent_workflow", {})
    if parent_wf:
        lines.append(f"**父工作流**: {parent_wf.get('name', parent_wf.get('code'))}\n")

    # 父工作流内影响
    downstream_in_parent = sub_impact.get("downstream_in_parent", [])
    if downstream_in_parent:
        lines.append(f"**父工作流内下游任务**: {len(downstream_in_parent)} 个\n")

    # 父工作流下游工作流
    parent_downstream_wf = sub_impact.get("parent_downstream_workflows", [])
    if parent_downstream_wf:
        lines.append(f"**父工作流下游工作流**: {len(parent_downstream_wf)} 个\n")

    # 总影响
    total = sub_impact.get("total_impact_count", 0)
    lines.append(f"\n**总影响范围**: {total} 个节点\n")

    return "\n".join(lines)


__all__ = ["assess_risk", "impact_analysis"]