"""
parse_alert node

Extract key info from webhook JSON: project_code, workflow_code, task_code, task_type
Support identifying sub-workflows and querying parent workflow info
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...graph.storage import GraphStorage
from ...graph.models import Graph
from ...config import settings
from ...tools.dingtalk_progress import get_notifier_from_settings


def parse_alert(state: AgentState) -> AgentState:
    """
    Parse alert data
    """
    print("\n" + "="*50)
    print("[1/10] parse_alert - Parse alert")
    print("="*50)

    alert_raw = state["alert_raw"]

    # Extract project code
    project_code = str(alert_raw.get("projectCode", 0))
    print(f"  >> Project code: {project_code}")

    # Extract workflow code (DS 3.2.0 uses processDefinitionCode)
    workflow_code = str(alert_raw.get("processDefinitionCode", 0))
    print(f"  >> Workflow code: {workflow_code}")

    # Extract task code
    task_code = str(alert_raw.get("taskCode", 0))
    print(f"  >> Task code: {task_code}")

    # Extract task type
    task_type = alert_raw.get("taskType", "UNKNOWN").upper()
    task_name = alert_raw.get("taskName", "") or ""
    workflow_name = alert_raw.get("processName", "") or ""
    project_name = alert_raw.get("projectName", "") or ""
    print(f"  >> Task type: {task_type}")
    print(f"  >> Task name: {task_name or '(empty)'}")
    print(f"  >> Workflow name: {workflow_name or '(empty)'}")

    # Extract workflow instance ID
    process_instance_id = alert_raw.get("processId") or alert_raw.get("processInstanceId") or 0
    print(f"  >> Instance ID: {process_instance_id}")

    # If names are empty, fetch them from workflow-instance digest
    if (not task_name or not workflow_name) and process_instance_id:
        from ...integrations.dsctl_wrapper import DSCLIClient
        try:
            dsctl = DSCLIClient()
            digest_result = dsctl.workflow_instance_digest(process_instance_id)
            if digest_result.success:
                import json
                digest_data = json.loads(digest_result.stdout)
                failed_tasks = digest_data.get("data", {}).get("failedTasks", [])
                wf_instance = digest_data.get("data", {}).get("workflowInstance", {})

                if failed_tasks:
                    # Get the most recent failed task
                    task_name = failed_tasks[0].get("name", "")
                    task_code = str(failed_tasks[0].get("taskCode", task_code))
                    task_type = failed_tasks[0].get("taskType", task_type).upper()
                    print(f"  >> [digest] Found failed task: {task_name}")

                if not workflow_name and wf_instance:
                    # Extract workflow name from instance name (format: workflow_name-version-timestamp)
                    instance_name = wf_instance.get("name", "")
                    if instance_name:
                        # Remove version and timestamp suffix
                        parts = instance_name.split("-")
                        if len(parts) > 2:
                            workflow_name = "-".join(parts[:-2])
                        else:
                            workflow_name = instance_name
                        print(f"  >> [digest] Found workflow name: {workflow_name}")
        except Exception as e:
            print(f"  [WARN] Failed to get names from digest: {e}")

    if not task_name:
        task_name = "N/A"
    if not workflow_name:
        workflow_name = "N/A"
    if not project_name:
        project_name = "N/A"

    # Send DingTalk notification - alert received (basic info)
    notifier = get_notifier_from_settings()
    notifier.send_markdown(
        title=f"告警接收 - {task_name}",
        text=f"## 🚨 DolphinScheduler 任务告警\n\n"
             f"| 项目 | 工作流实例 | 任务节点名称 | 任务类型 |\n"
             f"| --- | --- | --- | --- |\n"
             f"| {project_name} | {workflow_name} | {task_name} | {task_type} |\n\n"
             f"**告警时间:** {alert_raw.get('taskEndTime', 'N/A')}\n\n"
             f"**实例 ID:** {process_instance_id}\n\n"
             f"---\n\n"
             f"🤖 **Agent 正在分析错误...**"
    )

    # Normalize task type
    if task_type not in ["SHELL", "SPARK", "PYTHON", "DATAX"]:
        task_type = "SHELL"  # Default

    # Extract error time
    error_time = alert_raw.get("endTime") or alert_raw.get("taskEndTime") or ""

    # Extract parent workflow instance ID (if sub-workflow)
    parent_process_instance_id = alert_raw.get("rootProcessInstanceId") or alert_raw.get("parentProcessInstanceId") or None

    # Check if sub-workflow: has parent instance ID and not equal to current instance ID
    is_sub_workflow = parent_process_instance_id is not None and parent_process_instance_id != process_instance_id

    # Sub-workflow scenario: parent workflow code and node code are empty for now
    # Can be queried via workflow-instance parent API if needed
    parent_workflow_code: Optional[str] = None
    sub_workflow_node_code: Optional[str] = None

    print(f"  >> Sub-workflow: {is_sub_workflow}")
    if is_sub_workflow:
        print(f"  >> Parent workflow instance ID: {parent_process_instance_id}")

    # Update state
    print("[OK] Parse complete")
    return {
        **state,
        "project_code": project_code,
        "project_name": project_name,
        "workflow_code": workflow_code,
        "workflow_name": workflow_name,
        "task_code": task_code,
        "task_name": task_name,
        "task_type": task_type,
        "error_time": error_time,
        "is_sub_workflow": is_sub_workflow,
        "parent_workflow_code": parent_workflow_code,
        "process_instance_id": process_instance_id,
        "parent_process_instance_id": parent_process_instance_id,
        "sub_workflow_node_code": sub_workflow_node_code,
    }


__all__ = ["parse_alert"]