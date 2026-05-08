"""
execute_action 节点

执行修复动作 - 使用 dsctl CLI
"""

from typing import Dict, List, Optional
from ..state import AgentState
from ...integrations.dsctl_wrapper import DSCLIClient, CLIResult


def execute_action(state: AgentState) -> AgentState:
    """
    执行动作

    支持动作:
    - recover-failed: 从失败恢复（保持 process_instance_id）
    - script-fix: 修改实例中的任务脚本并恢复
    - config-change: 修改工作流定义配置
    - rerun: 重跑工作流（新实例）
    - notify-only: 仅通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (executed_actions, execution_results, execution_success)
    """
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    knowledge_match = state.get("knowledge_match")

    if not actions:
        return {
            **state,
            "executed_actions": [],
            "execution_results": [],
            "execution_success": False,
        }

    # 使用 dsctl CLI
    dsctl = DSCLIClient()

    executed = []
    results = []

    # 从 alert_raw 获取必要信息
    alert_raw = state.get("alert_raw", {})
    project_code = int(state.get("project_code", 0) or 0)
    workflow_code = int(state.get("workflow_code", 0) or 0)
    process_instance_id = alert_raw.get("processId") or alert_raw.get("processInstanceId") or 0
    task_code = int(state.get("task_code", 0) or 0)
    task_instance_id = alert_raw.get("taskInstanceId", 0)

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
        try:
            result = _execute_single_action(
                action_type,
                dsctl,
                project_code,
                workflow_code,
                process_instance_id,
                task_code,
                task_instance_id,
                knowledge_match,
                state
            )

            if result:
                executed.append(action)
                results.append({
                    "action": action,
                    "status": "success" if result.success else "failed",
                    "output": result.stdout[:500] if result.stdout else "",
                    "error": result.stderr[:200] if result.stderr else "",
                })
            else:
                results.append({
                    "action": action,
                    "status": "skipped",
                    "reason": "未知动作类型"
                })
        except Exception as e:
            results.append({
                "action": action,
                "status": "error",
                "reason": str(e)
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
    project_code: int,
    workflow_code: int,
    process_instance_id: int,
    task_code: int,
    task_instance_id: int,
    knowledge_match: Optional[Dict],
    state: Dict
) -> Optional[CLIResult]:
    """执行单个动作"""

    if action_type == "recover-failed":
        # 恢复失败任务（保持 process_instance_id）
        return dsctl.workflow_instance_recover(process_instance_id, task_code)

    elif action_type == "script-fix":
        # 修改实例中的任务脚本并恢复
        script_changes = knowledge_match.get("script_fix", {}) if knowledge_match else {}
        if script_changes:
            return dsctl.workflow_instance_edit_and_recover(
                process_instance_id,
                task_code,
                script_changes
            )
        return CLIResult(success=False, stdout="", stderr="无脚本修改方案", returncode=1)

    elif action_type == "config-change":
        # 修改工作流定义配置后启动新实例
        config_changes = knowledge_match.get("config_fix", {}) if knowledge_match else {}
        if config_changes:
            # 先更新工作流定义
            update_result = dsctl.workflow_update_config(
                project_code,
                workflow_code,
                task_code,
                config_changes
            )
            if update_result.success:
                # 启动新实例
                return dsctl.workflow_run(project_code, workflow_code)
            return update_result
        return CLIResult(success=False, stdout="", stderr="无配置修改方案", returncode=1)

    elif action_type == "rerun":
        # 重跑工作流实例
        return dsctl.workflow_instance_rerun(process_instance_id)

    elif action_type == "notify-only":
        # 仅通知，不执行
        return CLIResult(success=True, stdout="仅通知，未执行操作", stderr="", returncode=0)

    return None


__all__ = ["execute_action"]