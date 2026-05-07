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
    # Task code
    task_code: str
    # Task type (limited to specific values)
    task_type: Literal["SHELL", "SPARK", "PYTHON", "DATAX"]
    # Alert timestamp
    error_time: str

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


def create_initial_state(
    alert_raw: Dict[str, Any],
    project_code: str,
    workflow_code: str,
    task_code: str,
    task_type: Literal["SHELL", "SPARK", "PYTHON", "DATAX"],
    error_time: str,
) -> AgentState:
    """
    Create an initial AgentState with default values.

    Args:
        alert_raw: Raw webhook JSON data
        project_code: Project code
        workflow_code: Workflow code
        task_code: Task code
        task_type: Task type (SHELL, SPARK, PYTHON, or DATAX)
        error_time: Alert timestamp

    Returns:
        Initial AgentState with all fields populated
    """
    return AgentState(
        # Input stage
        alert_raw=alert_raw,
        project_code=project_code,
        workflow_code=workflow_code,
        task_code=task_code,
        task_type=task_type,
        error_time=error_time,

        # Validation stage
        project_valid=False,
        project_config=None,

        # Log fetch stage
        driver_logs=None,
        spark_logs=None,
        yarn_logs=None,
        k8s_logs=None,
        log_fetch_error=None,

        # Analysis stage
        error_patterns=[],
        error_category="",
        suggested_actions=[],
        knowledge_match=None,
        confidence_score=0.0,

        # Risk assessment stage
        risk_level="LOW",
        risk_factors=[],
        downstream_tasks=0,
        impact_summary=None,

        # Approval stage
        approval_required=False,
        approval_status=None,
        approval_message_id=None,

        # Execution stage
        executed_actions=[],
        execution_results=[],
        execution_success=False,

        # Notification stage
        notification_sent=False,
        notification_content=None,

        # Storage stage
        log_stored=False,
        result_stored=False,
        log_store_path=None,
    )


__all__ = ["AgentState", "create_initial_state"]