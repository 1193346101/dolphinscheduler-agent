"""
execute_action 节点

执行修复动作 - 使用 dsctl CLI

关键设计：
- 子工作流任务失败时，优先在子工作流实例内恢复（不重复执行成功任务）
- 恢复子工作流后，主工作流的子工作流节点会自动变为成功
- 然后需要从主工作流继续执行后续节点

恢复策略（最优方案）：
| 场景 | 操作步骤 | 是否重复执行 |
|-----|---------|-------------|
| 临时故障 | 1. 子工作流recover-failed | ❌ 不重复 |
| 脚本错误 | 1. 子工作流script-fix+recover | ❌ 不重复 |
| 配置问题 | 1. 修改定义 2. 主工作流从子节点恢复 | ⚠️ 重新执行整个子工作流 |

注意：recover-failed 和 script-fix 只恢复子工作流实例
      主工作流需要额外步骤继续执行后续节点
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
    - rerun: 重跑工作流（新实例）- 不建议用于子工作流
    - notify-only: 仅通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (executed_actions, execution_results, execution_success)
    """
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    knowledge_match = state.get("knowledge_match")
    is_sub_workflow = state.get("is_sub_workflow", False)

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

    # 从 state 获取必要信息
    project_code = int(state.get("project_code", 0) or 0)
    workflow_code = int(state.get("workflow_code", 0) or 0)
    process_instance_id = state.get("process_instance_id", 0)
    task_code = int(state.get("task_code", 0) or 0)  # 子工作流B中失败的task_code
    parent_workflow_code = int(state.get("parent_workflow_code", 0) or 0)
    parent_process_instance_id = state.get("parent_process_instance_id", 0)
    sub_workflow_node_code = int(state.get("sub_workflow_node_code", 0) or 0)  # 子工作流节点在A中的task_code

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
                knowledge_match,
                state,
                is_sub_workflow,
                parent_workflow_code,
                parent_process_instance_id,
                sub_workflow_node_code
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
    knowledge_match: Optional[Dict],
    state: Dict,
    is_sub_workflow: bool,
    parent_workflow_code: int,
    parent_process_instance_id: int,
    sub_workflow_node_code: int
) -> Optional[CLIResult]:
    """
    执行单个动作

    子工作流场景处理：
    - recover-failed: 在子工作流实例中恢复（保持同一实例）
    - script-fix: 在子工作流实例中修改脚本并恢复（保持同一实例）
    - config-change: 修改子工作流定义后，从父工作流恢复子工作流节点
    """

    if action_type == "recover-failed":
        # 恢复失败任务
        # 子工作流场景：先恢复子工作流实例，不重复执行成功任务
        result = dsctl.workflow_instance_recover(process_instance_id, task_code)

        # 如果是子工作流且恢复成功，需要通知用户手动恢复主工作流后续节点
        # 或者添加一个后续动作
        if is_sub_workflow and result.success and parent_process_instance_id:
            # 子工作流恢复成功后，建议从主工作流继续
            # 可以在这里添加自动恢复主工作流的逻辑
            # 或者将信息返回给用户
            result.stdout += f"\n子工作流恢复成功。请从主工作流实例 {parent_process_instance_id} 继续执行后续节点。"

        return result

    elif action_type == "script-fix":
        # 修改实例中的任务脚本并恢复（保持同一实例）
        script_changes = knowledge_match.get("script_fix", {}) if knowledge_match else {}
        if script_changes:
            return dsctl.workflow_instance_edit_and_recover(
                process_instance_id,
                task_code,
                script_changes
            )
        return CLIResult(success=False, stdout="", stderr="无脚本修改方案", returncode=1)

    elif action_type == "config-change":
        # 修改工作流定义配置
        config_changes = knowledge_match.get("config_fix", {}) if knowledge_match else {}
        if config_changes:
            # 1. 先更新工作流定义
            update_result = dsctl.workflow_update_config(
                project_code,
                workflow_code,
                task_code,
                config_changes
            )
            if not update_result.success:
                return update_result

            # 2. 根据是否为子工作流，决定恢复策略
            if is_sub_workflow and parent_process_instance_id and sub_workflow_node_code:
                # 子工作流配置修改后的恢复策略：
                # 从父工作流的子工作流节点恢复
                # - 保持父工作流实例ID不变
                # - 使用更新后的子工作流定义创建新子实例
                # - 新子实例属于父实例
                return dsctl.workflow_instance_recover_from_subworkflow(
                    parent_process_instance_id,
                    sub_workflow_node_code
                )
            else:
                # 非子工作流：启动新实例
                return dsctl.workflow_run(project_code, workflow_code)
        return CLIResult(success=False, stdout="", stderr="无配置修改方案", returncode=1)

    elif action_type == "rerun":
        # 重跑工作流实例
        # 注意：对于子工作流，这会生成新实例，与父工作流断开
        # 通常不建议对子工作流使用此操作
        if is_sub_workflow:
            return CLIResult(
                success=False,
                stdout="",
                stderr="子工作流不支持 rerun，请使用 recover-failed 保持同一实例，或使用 config-change 从父工作流恢复",
                returncode=1
            )
        return dsctl.workflow_instance_rerun(process_instance_id)

    elif action_type == "notify-only":
        # 仅通知，不执行
        return CLIResult(success=True, stdout="仅通知，未执行操作", stderr="", returncode=0)

    return None


__all__ = ["execute_action"]