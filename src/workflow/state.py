"""
AgentState TypedDict definition for DolphinScheduler alert automation.

This module defines the state structure used throughout the alert processing
workflow, containing all fields for each stage of processing.
"""

from typing import Dict, List, Any, Optional, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """
    State definition for the alert automation workflow.

    The state tracks all information through the following stages:
    1. Input stage - Raw alert data
    2. Validation stage - Project validation
    3. Log fetch stage - Log retrieval
    4. Analysis stage - Error analysis
    5. Risk assessment stage - Risk evaluation
    6. Approval stage - Approval workflow
    7. Execution stage - Action execution
    8. Notification stage - Alert notification
    9. Storage stage - Result persistence
    """

    # ==================== Input Stage ====================
    # Raw webhook JSON data
    alert_raw: Dict[str, Any]
    # Project code
    project_code: str
    # Workflow code
    workflow_code: str
    # Workflow name
    workflow_name: str
    # Task code (failed task code in current workflow)
    task_code: str
    # Task type (limited to specific values)
    task_type: Literal["SHELL", "SPARK", "PYTHON", "DATAX"]
    # Alert timestamp
    error_time: str
    # Whether this is a sub-workflow
    is_sub_workflow: bool
    # Parent workflow code (if this is a sub-workflow)
    parent_workflow_code: Optional[str]
    # Parent workflow instance ID (if this is a sub-workflow)
    parent_process_instance_id: Optional[int]
    # Sub-workflow node code in parent workflow (if this is a sub-workflow)
    # This is the task code of the SUB_PROCESS task in the parent workflow
    sub_workflow_node_code: Optional[str]

    # ==================== Validation Stage ====================
    # Whether the project is valid
    project_valid: bool
    # Project configuration if valid
    project_config: Optional[Dict[str, Any]]

    # ==================== Log Fetch Stage ====================
    # Driver logs
    driver_logs: Optional[str]
    # Spark application logs
    spark_logs: Optional[str]
    # YARN logs
    yarn_logs: Optional[str]
    # Kubernetes logs (pod name -> log content)
    k8s_logs: Optional[Dict[str, str]]
    # Error message if log fetch failed
    log_fetch_error: Optional[str]

    # ==================== Analysis Stage ====================
    # List of error patterns found
    error_patterns: List[str]
    # Error category (e.g., "oom", "class_not_found", "syntax_error")
    error_category: str
    # Suggested actions with details
    suggested_actions: List[Dict[str, Any]]
    # Matched knowledge base entry
    knowledge_match: Optional[Dict[str, Any]]
    # Confidence score for the analysis (0.0 - 1.0)
    confidence_score: float

    # ==================== Risk Assessment Stage ====================
    # Risk level
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    # List of risk factors identified
    risk_factors: List[str]
    # Number of affected downstream tasks
    downstream_tasks: int
    # List of downstream task codes
    downstream_list: List[str]
    # Summary of impact
    impact_summary: Optional[str]

    # ==================== Approval Stage ====================
    # Whether approval is required for the action
    approval_required: bool
    # Approval status
    approval_status: Optional[Literal["pending", "approved", "rejected", "timeout"]]
    # Message ID for approval notification
    approval_message_id: Optional[str]

    # ==================== Execution Stage ====================
    # List of actions that were executed
    executed_actions: List[Dict[str, Any]]
    # Results of each action execution
    execution_results: List[Dict[str, Any]]
    # Whether all actions executed successfully
    execution_success: bool

    # ==================== Notification Stage ====================
    # Whether notification was sent
    notification_sent: bool
    # Content of the notification
    notification_content: Optional[str]

    # ==================== Storage Stage ====================
    # Whether logs were stored
    log_stored: bool
    # Whether results were stored
    result_stored: bool
    # Path where logs are stored
    log_store_path: Optional[str]


# Initial state template with default values
INITIAL_STATE: Dict[str, Any] = {
    # Input stage - defaults
    "alert_raw": {},
    "project_code": "",
    "workflow_code": "",
    "workflow_name": "",
    "task_code": "",
    "task_type": "SHELL",
    "error_time": "",
    "is_sub_workflow": False,
    "parent_workflow_code": None,
    "parent_process_instance_id": None,
    "sub_workflow_node_code": None,

    # Validation stage - defaults
    "project_valid": False,
    "project_config": None,

    # Log fetch stage - defaults
    "driver_logs": None,
    "spark_logs": None,
    "yarn_logs": None,
    "k8s_logs": None,
    "log_fetch_error": None,

    # Analysis stage - defaults
    "error_patterns": [],
    "error_category": "",
    "suggested_actions": [],
    "knowledge_match": None,
    "confidence_score": 0.0,

    # Risk assessment stage - defaults
    "risk_level": "LOW",
    "risk_factors": [],
    "downstream_tasks": 0,
    "downstream_list": [],
    "impact_summary": None,

    # Approval stage - defaults
    "approval_required": False,
    "approval_status": None,
    "approval_message_id": None,

    # Execution stage - defaults
    "executed_actions": [],
    "execution_results": [],
    "execution_success": False,

    # Notification stage - defaults
    "notification_sent": False,
    "notification_content": None,

    # Storage stage - defaults
    "log_stored": False,
    "result_stored": False,
    "log_store_path": None,
}


def create_initial_state(alert_raw: Dict[str, Any] = None) -> AgentState:
    """
    Create an initial AgentState with default values.

    Args:
        alert_raw: Raw webhook JSON data (optional)

    Returns:
        Initial AgentState with all fields populated
    """
    state = dict(INITIAL_STATE)
    if alert_raw:
        state["alert_raw"] = alert_raw
    return state


__all__ = ["AgentState", "create_initial_state", "INITIAL_STATE"]