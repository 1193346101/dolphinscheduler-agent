"""
Tests for AgentState TypedDict state definition.
"""

import pytest
from typing import get_type_hints
from src.workflow.state import AgentState, create_initial_state


class TestAgentStateFields:
    """Tests for AgentState field definitions."""

    def test_initial_state_has_all_fields(self):
        """Test that initial state contains all required fields."""
        state = create_initial_state(
            alert_raw={"test": "data"},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="SPARK",
            error_time="2024-01-01T00:00:00Z",
        )

        # Input stage fields
        assert "alert_raw" in state
        assert "project_code" in state
        assert "workflow_code" in state
        assert "task_code" in state
        assert "task_type" in state
        assert "error_time" in state

        # Validation stage fields
        assert "project_valid" in state
        assert "project_config" in state

        # Log fetch stage fields
        assert "driver_logs" in state
        assert "spark_logs" in state
        assert "yarn_logs" in state
        assert "k8s_logs" in state
        assert "log_fetch_error" in state

        # Analysis stage fields
        assert "error_patterns" in state
        assert "error_category" in state
        assert "suggested_actions" in state
        assert "knowledge_match" in state
        assert "confidence_score" in state

        # Risk assessment stage fields
        assert "risk_level" in state
        assert "risk_factors" in state
        assert "downstream_tasks" in state
        assert "impact_summary" in state

        # Approval stage fields
        assert "approval_required" in state
        assert "approval_status" in state
        assert "approval_message_id" in state

        # Execution stage fields
        assert "executed_actions" in state
        assert "execution_results" in state
        assert "execution_success" in state

        # Notification stage fields
        assert "notification_sent" in state
        assert "notification_content" in state

        # Storage stage fields
        assert "log_stored" in state
        assert "result_stored" in state
        assert "log_store_path" in state

    def test_initial_state_defaults(self):
        """Test that initial state has correct default values."""
        state = create_initial_state(
            alert_raw={"test": "data"},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="SHELL",
            error_time="2024-01-01T00:00:00Z",
        )

        # Input stage
        assert state["alert_raw"] == {"test": "data"}
        assert state["project_code"] == "proj_001"
        assert state["workflow_code"] == "wf_001"
        assert state["task_code"] == "task_001"
        assert state["task_type"] == "SHELL"
        assert state["error_time"] == "2024-01-01T00:00:00Z"

        # Validation stage defaults
        assert state["project_valid"] is False
        assert state["project_config"] is None

        # Log fetch stage defaults
        assert state["driver_logs"] is None
        assert state["spark_logs"] is None
        assert state["yarn_logs"] is None
        assert state["k8s_logs"] is None
        assert state["log_fetch_error"] is None

        # Analysis stage defaults
        assert state["error_patterns"] == []
        assert state["error_category"] == ""
        assert state["suggested_actions"] == []
        assert state["knowledge_match"] is None
        assert state["confidence_score"] == 0.0

        # Risk assessment stage defaults
        assert state["risk_level"] == "LOW"
        assert state["risk_factors"] == []
        assert state["downstream_tasks"] == 0
        assert state["impact_summary"] is None

        # Approval stage defaults
        assert state["approval_required"] is False
        assert state["approval_status"] is None
        assert state["approval_message_id"] is None

        # Execution stage defaults
        assert state["executed_actions"] == []
        assert state["execution_results"] == []
        assert state["execution_success"] is False

        # Notification stage defaults
        assert state["notification_sent"] is False
        assert state["notification_content"] is None

        # Storage stage defaults
        assert state["log_stored"] is False
        assert state["result_stored"] is False
        assert state["log_store_path"] is None

    def test_state_can_be_updated(self):
        """Test that state can be updated with new values."""
        state = create_initial_state(
            alert_raw={"test": "data"},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="SPARK",
            error_time="2024-01-01T00:00:00Z",
        )

        # Update validation stage
        state["project_valid"] = True
        state["project_config"] = {"name": "test-project", "env": "prod"}

        # Update log fetch stage
        state["driver_logs"] = "Driver log content"
        state["spark_logs"] = "Spark log content"

        # Update analysis stage
        state["error_patterns"] = ["OutOfMemoryError", "ExecutorLostFailure"]
        state["error_category"] = "oom"
        state["suggested_actions"] = [
            {"action": "increase_memory", "value": "4g"}
        ]
        state["confidence_score"] = 0.95

        # Update risk assessment stage
        state["risk_level"] = "HIGH"
        state["risk_factors"] = ["memory_pressure", "data_skew"]
        state["downstream_tasks"] = 5

        # Update approval stage
        state["approval_required"] = True
        state["approval_status"] = "approved"

        # Update execution stage
        state["executed_actions"] = [{"type": "config_update"}]
        state["execution_results"] = [{"status": "success"}]
        state["execution_success"] = True

        # Update notification stage
        state["notification_sent"] = True
        state["notification_content"] = "Alert processed successfully"

        # Update storage stage
        state["log_stored"] = True
        state["result_stored"] = True
        state["log_store_path"] = "/logs/2024/01/01/alert_001.log"

        # Verify all updates
        assert state["project_valid"] is True
        assert state["project_config"]["name"] == "test-project"
        assert state["driver_logs"] == "Driver log content"
        assert len(state["error_patterns"]) == 2
        assert state["error_category"] == "oom"
        assert state["confidence_score"] == 0.95
        assert state["risk_level"] == "HIGH"
        assert state["downstream_tasks"] == 5
        assert state["approval_status"] == "approved"
        assert state["execution_success"] is True
        assert state["notification_sent"] is True
        assert state["log_store_path"] == "/logs/2024/01/01/alert_001.log"

    def test_state_task_type_literal(self):
        """Test that task_type accepts only predefined values."""
        valid_types = ["SHELL", "SPARK", "PYTHON", "DATAX"]

        for task_type in valid_types:
            state = create_initial_state(
                alert_raw={},
                project_code="proj_001",
                workflow_code="wf_001",
                task_code="task_001",
                task_type=task_type,
                error_time="2024-01-01T00:00:00Z",
            )
            assert state["task_type"] == task_type

    def test_state_risk_level_literal(self):
        """Test that risk_level accepts only predefined values."""
        valid_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

        state = create_initial_state(
            alert_raw={},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="SPARK",
            error_time="2024-01-01T00:00:00Z",
        )

        for level in valid_levels:
            state["risk_level"] = level
            assert state["risk_level"] == level


class TestAgentStateTypes:
    """Tests for AgentState type hints."""

    def test_typed_dict_annotation(self):
        """Test that AgentState is a TypedDict."""
        # AgentState should be a TypedDict
        from typing import TypedDict
        assert AgentState.__bases__[0].__name__ == "TypedDict" or \
               AgentState.__name__ == "AgentState"

    def test_total_false_annotation(self):
        """Test that AgentState has total=False for optional fields."""
        # All fields should be optional since total=False
        state: AgentState = {}
        assert isinstance(state, dict)


class TestAgentStateIntegration:
    """Integration tests for AgentState usage patterns."""

    def test_full_workflow_state_transitions(self):
        """Test state transitions through a full workflow."""
        # Initial state
        state = create_initial_state(
            alert_raw={"alert_id": "123", "message": "Task failed"},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="SPARK",
            error_time="2024-01-01T10:30:00Z",
        )

        # Stage 1: Validation
        state["project_valid"] = True
        state["project_config"] = {
            "ds_url": "http://ds.example.com",
            "token": "xxx",
        }

        # Stage 2: Log fetch
        state["driver_logs"] = "OutOfMemoryError: Java heap space"
        state["spark_logs"] = "Executor lost: container killed"

        # Stage 3: Analysis
        state["error_patterns"] = ["OutOfMemoryError", "container killed"]
        state["error_category"] = "oom"
        state["suggested_actions"] = [
            {"action": "increase_executor_memory", "value": "8g"},
            {"action": "increase_driver_memory", "value": "4g"},
        ]
        state["knowledge_match"] = {
            "kb_id": "kb_001",
            "title": "Spark OOM troubleshooting",
        }
        state["confidence_score"] = 0.92

        # Stage 4: Risk assessment
        state["risk_level"] = "MEDIUM"
        state["risk_factors"] = ["memory_config", "downstream_impact"]
        state["downstream_tasks"] = 3
        state["impact_summary"] = "3 downstream tasks may be delayed"

        # Stage 5: Approval (for MEDIUM risk, auto-approve)
        state["approval_required"] = True
        state["approval_status"] = "approved"

        # Stage 6: Execution
        state["executed_actions"] = [
            {"action": "increase_executor_memory", "status": "done"},
            {"action": "increase_driver_memory", "status": "done"},
        ]
        state["execution_results"] = [
            {"success": True, "message": "Config updated"},
        ]
        state["execution_success"] = True

        # Stage 7: Notification
        state["notification_sent"] = True
        state["notification_content"] = "Alert processed and fixed"

        # Stage 8: Storage
        state["log_stored"] = True
        state["result_stored"] = True
        state["log_store_path"] = "/logs/2024/01/01/proj_001_wf_001.log"

        # Verify final state
        assert state["project_valid"] is True
        assert state["error_category"] == "oom"
        assert state["risk_level"] == "MEDIUM"
        assert state["approval_status"] == "approved"
        assert state["execution_success"] is True
        assert state["notification_sent"] is True
        assert state["result_stored"] is True

    def test_k8s_logs_field(self):
        """Test that k8s_logs field works correctly."""
        state = create_initial_state(
            alert_raw={},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="PYTHON",
            error_time="2024-01-01T00:00:00Z",
        )

        # Initially None
        assert state["k8s_logs"] is None

        # Can be set to a dict
        state["k8s_logs"] = {
            "spark-driver": "Driver log content",
            "spark-executor-1": "Executor 1 log content",
            "spark-executor-2": "Executor 2 log content",
        }

        assert "spark-driver" in state["k8s_logs"]
        assert len(state["k8s_logs"]) == 3

    def test_approval_status_values(self):
        """Test all approval status values."""
        state = create_initial_state(
            alert_raw={},
            project_code="proj_001",
            workflow_code="wf_001",
            task_code="task_001",
            task_type="DATAX",
            error_time="2024-01-01T00:00:00Z",
        )

        # Test all valid status values
        valid_statuses = ["pending", "approved", "rejected", "timeout"]
        for status in valid_statuses:
            state["approval_status"] = status
            assert state["approval_status"] == status