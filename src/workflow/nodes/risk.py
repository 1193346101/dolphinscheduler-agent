"""
risk.py - Risk assessment node

Support sub-workflow impact analysis
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
    """Assess risk level"""
    print("\n" + "="*50)
    print("[6/10] assess_risk - Risk assessment")
    print("="*50)

    tool = RiskAssessTool()

    suggested_actions = state.get("suggested_actions", [])
    downstream_count = state.get("downstream_tasks", 0)

    print(f"  >> Suggested action count: {len(suggested_actions)}")
    print(f"  >> Downstream task count: {downstream_count}")

    result = tool.assess(
        suggested_actions=suggested_actions,
        downstream_count=downstream_count,
    )

    print(f"  >> Risk level: {result['risk_level']}")
    print(f"  >> Approval required: {result['approval_required']}")

    if result['risk_level'] == 'LOW':
        print("[OK] Low risk, auto execute")
    elif result['risk_level'] == 'MEDIUM':
        print("[OK] Medium risk, auto execute")
    else:
        print("[INFO] High risk, waiting for approval")

    return {
        **state,
        "risk_level": result["risk_level"],
        "risk_factors": result["risk_factors"],
        "approval_required": result["approval_required"],
    }


def impact_analysis(state: AgentState) -> AgentState:
    """
    Analyze downstream impact

    Support sub-workflow impact analysis:
    - Downstream tasks within sub-workflow
    - Downstream in parent workflow after sub-workflow
    - Parent workflow downstream workflows

    Args:
        state: Current state

    Returns:
        Updated state (downstream_tasks, downstream_list, impact_summary)
    """
    project_code = state.get("project_code")
    workflow_code = state.get("workflow_code")
    task_code = state.get("task_code")
    is_sub_workflow = state.get("is_sub_workflow", False)

    # Use graph analysis
    graph_storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    querier = GraphQuerier(graph_storage)

    # Check if graph exists
    graph_available = graph_storage.graph_exists(project_code)

    # If graph exists and is sub-workflow, use full impact analysis
    if graph_available and is_sub_workflow:
        sub_impact = querier.query_subworkflow_impact(
            project_code,
            workflow_code,
            task_code
        )

        if sub_impact["found"]:
            # Build full impact summary
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

    # Graph exists and is normal workflow, use standard downstream analysis
    if graph_available:
        graph_impact = GraphImpactTool(graph_storage)

        # Analyze workflow downstream
        workflow_result = graph_impact.analyze_workflow_downstream(
            str(project_code),
            str(workflow_code),
        )

        if workflow_result.get("graph_available"):
            # Also analyze task-level downstream
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

    # Fallback: Use task_relations analysis when graph not exists
    impact_tool = ImpactTool()
    task_relations = state.get("task_relations")

    # task_relations None means cannot get, return default
    # task_relations [] means can get but no downstream dependency
    if task_relations is None:
        return {
            **state,
            "downstream_tasks": 0,
            "downstream_list": [],
            "impact_summary": "Cannot analyze downstream impact",
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
    Build sub-workflow impact summary

    Args:
        sub_impact: Sub-workflow impact analysis result

    Returns:
        Markdown format summary
    """
    lines = ["## Sub-workflow failure impact analysis\n"]

    # Sub-workflow info
    sub_wf = sub_impact.get("sub_workflow", {})
    if sub_wf:
        lines.append(f"**Sub-workflow**: {sub_wf.get('name', sub_wf.get('code'))}\n")

    # Impact within sub-workflow
    task_downstream = sub_impact.get("task_downstream_in_subworkflow", [])
    if task_downstream:
        lines.append(f"**Downstream tasks in sub-workflow**: {len(task_downstream)}\n")

    # Parent workflow info
    parent_wf = sub_impact.get("parent_workflow", {})
    if parent_wf:
        lines.append(f"**Parent workflow**: {parent_wf.get('name', parent_wf.get('code'))}\n")

    # Impact in parent workflow
    downstream_in_parent = sub_impact.get("downstream_in_parent", [])
    if downstream_in_parent:
        lines.append(f"**Downstream in parent workflow**: {len(downstream_in_parent)}\n")

    # Parent workflow downstream workflows
    parent_downstream_wf = sub_impact.get("parent_downstream_workflows", [])
    if parent_downstream_wf:
        lines.append(f"**Parent workflow downstream workflows**: {len(parent_downstream_wf)}\n")

    # Total impact
    total = sub_impact.get("total_impact_count", 0)
    lines.append(f"\n**Total impact range**: {total} nodes\n")

    return "\n".join(lines)


__all__ = ["assess_risk", "impact_analysis"]