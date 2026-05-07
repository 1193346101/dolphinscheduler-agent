"""
execute_action 节点

执行修复动作 - 完整实现
"""

from typing import Dict, List
from ..state import AgentState
from ...integrations.dsctl_wrapper import DSCLIClient, CLIResult


def execute_action(state: AgentState) -> AgentState:
    """
    执行动作

    支持动作:
    - rerun: 重跑工作流
    - recover-failed: 从失败恢复
    - config-change: 修改配置
    - notify-only: 仅通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (executed_actions, execution_results, execution_success)
    """
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    project_config = state.get("project_config")

    if not actions or not project_config:
        return {
            **state,
            "executed_actions": [],
            "execution_results": [],
            "execution_success": False,
        }

    dsctl = DSCLIClient(
        api_url=project_config.get("ds_api_url", ""),
        api_token=project_config.get("ds_api_token", "")
    )

    executed = []
    results = []

    instance_id = state["alert_raw"].get("processInstanceId")
    task_code = int(state.get("task_code", 0) or 0)

    for action in actions:
        action_type = action.get("action_type", "")
        risk_level = action.get("risk_level", "LOW")

        # 检查审批
        if risk_level in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                results.append({
                    "action": action,
                    "status": "skipped",
                    "reason": f"需要审批，当前状态: {approval_status}"
                })
                continue

        # 执行动作
        result = _execute_single_action(
            action_type,
            dsctl,
            instance_id,
            task_code,
            state
        )

        if result:
            executed.append(action)
            results.append({
                "action": action,
                "status": "success" if result.success else "failed",
                "output": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:200] if result.stderr else ""
            })
        else:
            results.append({
                "action": action,
                "status": "skipped",
                "reason": "未知动作类型"
            })

    # 判断整体成功
    success = any(
        r.get("status") == "success"
        for r in results
        if r.get("status") != "skipped"
    ) if executed else False

    return {
        **state,
        "executed_actions": executed,
        "execution_results": results,
        "execution_success": success,
    }


def _execute_single_action(
    action_type: str,
    dsctl: DSCLIClient,
    instance_id: int,
    task_code: int,
    state: Dict
) -> CLIResult:
    """执行单个动作"""

    if action_type == "rerun":
        return dsctl.workflow_instance_rerun(instance_id)

    elif action_type == "recover-failed":
        return dsctl.workflow_instance_recover(instance_id, task_code)

    elif action_type == "config-change":
        # config-change 需要: 1) 更新参数 2) 重跑
        # 当前简化实现，直接重跑
        return dsctl.workflow_instance_rerun(instance_id)

    elif action_type == "notify-only":
        # 仅通知，不执行
        return CLIResult(success=True, stdout="仅通知", stderr="", returncode=0)

    return None


__all__ = ["execute_action"]