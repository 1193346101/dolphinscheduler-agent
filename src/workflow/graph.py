"""
graph.py - LangGraph 状态机定义

定义告警处理的状态流转:
parse_alert -> validate_project -> fetch_logs -> analyze_error
-> query_knowledge -> impact_analysis -> assess_risk
-> [approval分支] request_approval -> check_approval -> [execute/end]
-> [auto_execute分支] execute_action
-> notify_dingtalk -> store_results -> END
"""

from langgraph.graph import StateGraph, END
from .state import AgentState, create_initial_state
from .nodes import (
    parse_alert,
    validate_project,
    fetch_logs,
    analyze_error,
    query_knowledge,
    impact_analysis,
    assess_risk,
    request_approval,
    check_approval,
    execute_action,
    notify_dingtalk,
    store_results,
)


def should_continue(state: AgentState) -> str:
    """
    判断是否继续处理

    Args:
        state: 当前状态

    Returns:
        "continue" 或 "end"
    """
    if not state.get("project_valid"):
        return "end"
    return "continue"


def route_by_risk(state: AgentState) -> str:
    """
    根据风险等级路由

    Args:
        state: 当前状态

    Returns:
        "approval" 或 "auto_execute"
    """
    if state.get("approval_required"):
        return "approval"
    return "auto_execute"


def check_approval_status(state: AgentState) -> str:
    """
    检查审批状态

    Args:
        state: 当前状态

    Returns:
        "execute", "notify_reject", "notify_timeout", 或 "wait"
    """
    status = state.get("approval_status")
    if status == "approved":
        return "execute"
    elif status == "rejected":
        return "notify_reject"
    elif status == "timeout":
        return "notify_timeout"
    return "wait"


def build_alert_graph() -> StateGraph:
    """
    构建告警处理状态机

    流程:
    1. parse_alert -> validate_project
    2. validate_project -> [继续/结束]
    3. fetch_logs -> analyze_error -> query_knowledge
    4. impact_analysis -> assess_risk
    5. assess_risk -> [审批分支/自动执行分支]
    6. 审批分支: request_approval -> check_approval -> [执行/通知/等待]
    7. 执行分支: execute_action -> notify_dingtalk -> store_results -> END

    Returns:
        StateGraph 实例
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("parse_alert", parse_alert)
    graph.add_node("validate_project", validate_project)
    graph.add_node("fetch_logs", fetch_logs)
    graph.add_node("analyze_error", analyze_error)
    graph.add_node("query_knowledge", query_knowledge)
    graph.add_node("impact_analysis", impact_analysis)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("request_approval", request_approval)
    graph.add_node("check_approval", check_approval)
    graph.add_node("execute_action", execute_action)
    graph.add_node("notify_dingtalk", notify_dingtalk)
    graph.add_node("store_results", store_results)

    # 设置入口
    graph.set_entry_point("parse_alert")

    # 添加边 - 主流程
    graph.add_edge("parse_alert", "validate_project")

    # 验证失败直接结束
    graph.add_conditional_edges(
        "validate_project",
        should_continue,
        {
            "continue": "fetch_logs",
            "end": END,
        },
    )

    graph.add_edge("fetch_logs", "analyze_error")
    graph.add_edge("analyze_error", "query_knowledge")
    graph.add_edge("query_knowledge", "impact_analysis")
    graph.add_edge("impact_analysis", "assess_risk")

    # 根据风险等级路由
    graph.add_conditional_edges(
        "assess_risk",
        route_by_risk,
        {
            "approval": "request_approval",
            "auto_execute": "execute_action",
        },
    )

    # 审批分支
    graph.add_edge("request_approval", "check_approval")
    graph.add_conditional_edges(
        "check_approval",
        check_approval_status,
        {
            "execute": "execute_action",
            "notify_reject": "notify_dingtalk",
            "notify_timeout": "notify_dingtalk",
            "wait": END,  # 等待审批回调
        },
    )

    # 执行后通知
    graph.add_edge("execute_action", "notify_dingtalk")
    graph.add_edge("notify_dingtalk", "store_results")
    graph.add_edge("store_results", END)

    return graph


class AlertWorkflowGraph:
    """
    告警处理工作流

    封装 LangGraph 状态机，提供简单的执行接口
    """

    def __init__(self):
        self.graph = build_alert_graph()
        self.app = self.graph.compile()

    def run(self, alert_raw: dict) -> AgentState:
        """
        执行工作流

        Args:
            alert_raw: 原始告警数据

        Returns:
            最终状态
        """
        initial_state = create_initial_state(alert_raw=alert_raw)
        return self.app.invoke(initial_state)

    def continue_from_approval(self, state: AgentState, approval_status: str) -> AgentState:
        """
        从审批状态继续

        Args:
            state: 当前状态
            approval_status: approved / rejected / timeout

        Returns:
            更新后的状态
        """
        state["approval_status"] = approval_status
        return self.app.invoke(state)


__all__ = ["AlertWorkflowGraph", "build_alert_graph", "should_continue", "route_by_risk", "check_approval_status"]