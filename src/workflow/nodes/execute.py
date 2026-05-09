"""
execute_action node

Execute fix actions - using dsctl CLI
"""

from typing import Dict, List, Optional
from ..state import AgentState
from ...integrations.dsctl_wrapper import DSCLIClient, CLIResult
from ...config import settings
from ...tools.dingtalk_progress import get_notifier_from_settings


def execute_action(state: AgentState) -> AgentState:
    """
    Execute actions

    Sub-workflow scenario:
    - Alert points to sub-workflow B instance and failed task c
    - process_instance_id is B instance ID
    - Execute recover-failed on B, B recovers from c
    - After B succeeds, parent workflow A auto detects and continues
    - No need to manually handle parent workflow
    """
    print("\n" + "="*50)
    print("[7/10] execute_action - Execute fix")
    print("="*50)

    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    knowledge_match = state.get("knowledge_match")
    is_sub_workflow = state.get("is_sub_workflow", False)

    # Show sub-workflow info
    if is_sub_workflow:
        print("  >> [Sub-workflow scenario] Directly recover sub-workflow instance, parent workflow will auto continue")

    if not actions:
        print("[WARN] No suggested actions, skip execution")
        # Send result notification even without actions
        notifier = get_notifier_from_settings()
        project_name = state.get("project_name", state.get("project_code", "N/A"))
        workflow_name = state.get("workflow_name", state.get("workflow_code", "N/A"))
        task_name = state.get("task_name", "N/A")
        notifier.send_execution_result(
            project_name=str(project_name),
            workflow_name=str(workflow_name),
            task_name=str(task_name),
            success=False,
            message="No suggested actions, not executed"
        )
        return {
            **state,
            "executed_actions": [],
            "execution_results": [],
            "execution_success": False,
        }

    print(f"  >> Action count: {len(actions)}")
    for i, action in enumerate(actions):
        print(f"  >> Action{i+1}: {action.get('action_type', 'unknown')} (risk: {action.get('risk_level', 'N/A')})")

    # Use dsctl CLI
    dsctl = DSCLIClient()

    executed = []
    results = []

    # Get necessary info from state
    project_code = int(state.get("project_code", 0) or 0)
    workflow_code = int(state.get("workflow_code", 0) or 0)
    process_instance_id = state.get("process_instance_id", 0)
    task_code = int(state.get("task_code", 0) or 0)  # Failed task_code in sub-workflow B
    parent_workflow_code = int(state.get("parent_workflow_code", 0) or 0)
    parent_process_instance_id = state.get("parent_process_instance_id", 0)
    sub_workflow_node_code = int(state.get("sub_workflow_node_code", 0) or 0)  # Sub-workflow node task_code in A

    for action in actions:
        action_type = action.get("action_type", "")
        risk_level = action.get("risk_level", "LOW")

        # Check approval
        if risk_level in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                results.append({
                    "action": action,
                    "status": "skipped",
                    "reason": f"Needs approval, current status: {approval_status}"
                })
                continue

        # Execute action
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
                    "reason": "Unknown action type"
                })
        except Exception as e:
            results.append({
                "action": action,
                "status": "error",
                "reason": str(e)
            })

    # Determine overall success
    success = any(
        r.get("status") == "success"
        for r in results
        if r.get("status") != "skipped"
    ) if executed else False

    # Send execution result notification
    notifier = get_notifier_from_settings()
    project_name = state.get("project_name", state.get("project_code", "N/A"))
    workflow_name = state.get("workflow_name", state.get("workflow_code", "N/A"))
    task_name = state.get("task_name", "N/A")

    # Get additional info for enhanced notification
    error_type = state.get("error_type") or state.get("skill_result", {}).get("error_type")
    confidence = state.get("confidence_score") or state.get("skill_result", {}).get("confidence")

    # Get script_changes from executed actions
    script_changes = None
    action_type = None
    knowledge_entry_id = None

    if executed:
        first_action = executed[0]
        action_type = first_action.get("action_type")
        if action_type in ["modify_script", "script-fix"]:
            script_changes = first_action.get("script_changes")

        # Create knowledge entry for successful fix
        if success and script_changes and error_type:
            try:
                from ...knowledge.manager import knowledge_manager

                # Build analysis summary
                analysis = f"Error: {error_type}"
                suggestion = f"Script fix: {script_changes}"

                # Add to pending knowledge base
                entry = knowledge_manager.add_pending(
                    task_type=state.get("task_type", "SHELL").lower(),
                    error_type=error_type,
                    pattern=error_type,  # Use error_type as pattern for now
                    analysis=analysis,
                    suggestion=suggestion,
                )
                knowledge_entry_id = entry.id
                print(f"  >> Created knowledge entry: {knowledge_entry_id}")
            except Exception as e:
                print(f"  [WARN] Failed to create knowledge entry: {e}")

    # Build result message
    result_msg = ""
    for r in results:
        action_type_msg = r.get("action", {}).get("action_type", "unknown")
        status = r.get("status", "unknown")
        result_msg += f"- {action_type_msg}: {status}\n"

    notifier.send_execution_result(
        project_name=str(project_name),
        workflow_name=str(workflow_name),
        task_name=str(task_name),
        success=success,
        message=result_msg or "No executed actions",
        error_type=error_type,
        script_changes=script_changes,
        confidence=confidence,
        action_type=action_type,
        knowledge_entry_id=knowledge_entry_id
    )

    if success:
        print("[OK] Execution success")
    else:
        print("[FAIL] Execution failed or skipped")

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
    Execute single action

    Supported actions:
    - recover-failed: Recover failed workflow instance
    - modify_script: Modify script content and recover instance
    - script-fix: Same as modify_script
    - rerun: Rerun workflow instance
    - notify-only: Only notify
    """

    # Get task name
    task_name = state.get("task_name", "")

    if action_type == "recover-failed":
        # Recover failed workflow instance
        print(f"  >> Execute: workflow-instance recover-failed {process_instance_id}")
        return dsctl.workflow_instance_recover_failed(process_instance_id)

    elif action_type in ["modify_script", "script-fix"]:
        # Modify script and recover instance
        # Get script_changes from action
        action = None
        for a in state.get("suggested_actions", []):
            if a.get("action_type") in ["modify_script", "script-fix"]:
                action = a
                break

        script_changes = action.get("script_changes", {}) if action else {}

        if not script_changes:
            return CLIResult(success=False, stdout="", stderr="No script modification content", returncode=1)

        print(f"  >> Script modification: {script_changes}")

        # 1. Export workflow instance
        export_result = dsctl.workflow_instance_export(process_instance_id)
        if not export_result.success:
            return CLIResult(
                success=False,
                stdout="",
                stderr=f"Export instance failed: {export_result.stderr}",
                returncode=1
            )

        # 2. Parse YAML, find script, apply modifications
        import yaml
        try:
            data = yaml.safe_load(export_result.stdout)
            for task in data.get('tasks', []):
                if task.get('name') == task_name:
                    original_script = task.get('task_params', {}).get('rawScript', '')
                    # Apply modifications
                    modified_script = original_script
                    for wrong_cmd, correct_cmd in script_changes.items():
                        modified_script = modified_script.replace(wrong_cmd, correct_cmd)
                    print(f"  >> Modified script: {modified_script[:100]}...")

                    # 3. Use patch to edit instance (sync to definition)
                    edit_result = dsctl.workflow_instance_edit_task_script(
                        process_instance_id,
                        task_name,
                        modified_script,
                        sync_definition=True
                    )

                    if not edit_result.success:
                        return edit_result

                    # 4. Recover instance
                    recover_result = dsctl.workflow_instance_recover_failed(process_instance_id)
                    recover_result.stdout = f"Script fixed ({script_changes})\n" + recover_result.stdout
                    return recover_result

            return CLIResult(success=False, stdout="", stderr="Task definition not found", returncode=1)

        except Exception as e:
            return CLIResult(success=False, stdout="", stderr=f"YAML parse failed: {e}", returncode=1)

    elif action_type == "modify_config":
        # Modify Spark config and recover instance
        action = None
        for a in state.get("suggested_actions", []):
            if a.get("action_type") == "modify_config":
                action = a
                break

        config_changes = action.get("config_changes", {}) if action else {}

        if not config_changes:
            return CLIResult(success=False, stdout="", stderr="No config modification content", returncode=1)

        print(f"  >> Config modification: {config_changes}")

        # 1. Export workflow instance
        export_result = dsctl.workflow_instance_export(process_instance_id)
        if not export_result.success:
            return CLIResult(
                success=False,
                stdout="",
                stderr=f"Export instance failed: {export_result.stderr}",
                returncode=1
            )

        # 2. Parse YAML, find task, apply config modifications
        import yaml
        try:
            data = yaml.safe_load(export_result.stdout)
            for task in data.get('tasks', []):
                if task.get('name') == task_name:
                    task_params = task.get('task_params', {})
                    # Apply config modifications
                    for config_key, config_value in config_changes.items():
                        # Map Spark config names to DS parameter names
                        if config_key == "spark.driver.memory":
                            task_params['driverMemory'] = config_value
                        elif config_key == "spark.driver.memoryOverhead":
                            # DS 3.2.0 has no separate memoryOverhead parameter, need to adjust driverMemory
                            pass
                        elif config_key == "spark.executor.memory":
                            task_params['executorMemory'] = config_value
                        elif config_key == "spark.executor.memoryOverhead":
                            task_params['executorMemoryOverhead'] = config_value
                        elif config_key == "spark.executor.instances":
                            task_params['numExecutors'] = config_value

                    print(f"  >> Modified config: driverMemory={task_params.get('driverMemory')}")

                    # 3. Use full file method to modify instance (preserve execution params)
                    import tempfile
                    import subprocess
                    import os

                    # Use allow_unicode=True to ensure Chinese encoding correct
                    full_yaml = yaml.dump(data, default_flow_style=False, allow_unicode=True)

                    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
                        f.write(full_yaml)
                        file_path = f.name

                    # Call dsctl workflow-instance edit --file --sync-definition
                    # This modifies instance and syncs to workflow definition
                    env = os.environ.copy()
                    env['DS_API_URL'] = dsctl.api_url
                    env['DS_API_TOKEN'] = dsctl.api_token
                    env['DS_VERSION'] = dsctl.version

                    result = subprocess.run(
                        ['python', '-m', 'dsctl', 'workflow-instance', 'edit',
                         str(process_instance_id), '--file', file_path, '--sync-definition'],
                        capture_output=True, text=True, env=env
                    )

                    os.unlink(file_path)

                    if result.returncode != 0:
                        return CLIResult(
                            success=False,
                            stdout=result.stdout,
                            stderr=result.stderr,
                            returncode=result.returncode
                        )

                    print("  >> Instance config modified, synced to workflow definition")

                    # 4. Recover instance from failed task (preserve execution params: worker_group, tenant etc)
                    # recover-failed only executes failed tasks, not rerun successful tasks
                    print(f"  >> Recover instance from failed task: {process_instance_id}")
                    recover_result = dsctl.workflow_instance_recover_failed(process_instance_id)
                    recover_result.stdout = f"Config fixed and synced ({config_changes})\n" + recover_result.stdout
                    return recover_result

            return CLIResult(success=False, stdout="", stderr="Task definition not found", returncode=1)

        except Exception as e:
            return CLIResult(success=False, stdout="", stderr=f"YAML parse failed: {e}", returncode=1)

    elif action_type == "rerun":
        # Rerun workflow instance
        print(f"  >> Execute: workflow-instance rerun {process_instance_id}")
        return dsctl.workflow_instance_rerun(process_instance_id)

    elif action_type == "notify-only":
        # Only notify, no execution
        print(f"  >> Only notify, no execution")
        return CLIResult(success=True, stdout="Only notify, not executed", stderr="", returncode=0)

    return None


__all__ = ["execute_action"]