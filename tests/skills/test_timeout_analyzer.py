"""
Tests for timeout-analyzer skill
"""

import pytest

from src.skills.timeout_analyzer.scripts.analyze_timeout import (
    analyze_timeout_alert,
    get_timeout_summary
)
from src.skills.timeout_analyzer.scripts.check_cluster import (
    get_cluster_resource_status,
    check_queue_status
)


class TestAnalyzeTimeoutAlert:
    """Test analyze_timeout_alert function"""

    def test_task_error_retry(self):
        """Test detection of task error retry timeout cause"""
        tasks = [
            {"name": "extract_task", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 60},
            {"name": "transform_task", "status": "FAILED", "retry_count": 3, "queue_wait_time": 30},
            {"name": "load_task", "status": "PENDING", "retry_count": 0, "queue_wait_time": 0}
        ]
        historical_metrics = {"avg_queue_wait_time": 120}

        result = analyze_timeout_alert(tasks, historical_metrics)

        assert result["root_cause"]["type"] == "task_error_retry"
        assert result["root_cause"]["task_name"] == "transform_task"
        assert result["root_cause"]["retry_count"] == 3
        assert len(result["analysis"]) >= 2
        assert "transform_task" in result["llm_hint"]

    def test_resource_waiting(self):
        """Test detection of resource waiting timeout cause"""
        tasks = [
            {"name": "spark_job", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 600}
        ]
        historical_metrics = {"avg_queue_wait_time": 120}

        result = analyze_timeout_alert(tasks, historical_metrics)

        assert result["root_cause"]["type"] == "resource_waiting"
        assert result["root_cause"]["task_name"] == "spark_job"
        assert result["root_cause"]["queue_wait_time"] == 600
        assert result["root_cause"]["historical_avg"] == 120
        assert "排队等待" in result["analysis"][0]
        assert "YARN" in result["llm_hint"] or "资源" in result["llm_hint"]

    def test_unknown_cause(self):
        """Test detection of unknown timeout cause"""
        tasks = [
            {"name": "task1", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 100},
            {"name": "task2", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 150}
        ]
        historical_metrics = {"avg_queue_wait_time": 120}

        result = analyze_timeout_alert(tasks, historical_metrics)

        assert result["root_cause"]["type"] == "unknown"
        assert result["root_cause"]["task_name"] is None
        assert "无法确定" in result["analysis"][0] or "未知" in result["llm_hint"]

    def test_empty_tasks(self):
        """Test with empty task list"""
        result = analyze_timeout_alert([], {})

        assert result["root_cause"]["type"] == "unknown"
        assert len(result["analysis"]) >= 1
        assert "缺少" in result["analysis"][0] or "没有" in result["analysis"][0]

    def test_no_historical_metrics(self):
        """Test without historical metrics (can't detect resource_waiting)"""
        tasks = [
            {"name": "task1", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 600}
        ]

        result = analyze_timeout_alert(tasks, None)

        # Should be unknown since we can't compare queue_wait_time
        assert result["root_cause"]["type"] == "unknown"

    def test_retry_priority_over_resource_waiting(self):
        """Test that task_error_retry has priority over resource_waiting"""
        tasks = [
            {
                "name": "failed_task",
                "status": "FAILED",
                "retry_count": 2,
                "queue_wait_time": 600  # Also high queue wait
            }
        ]
        historical_metrics = {"avg_queue_wait_time": 100}

        result = analyze_timeout_alert(tasks, historical_metrics)

        # Should detect retry first, not resource_waiting
        assert result["root_cause"]["type"] == "task_error_retry"
        assert result["root_cause"]["retry_count"] == 2

    def test_multiple_retry_tasks(self):
        """Test with multiple retry tasks - should pick the one with most retries"""
        tasks = [
            {"name": "task1", "status": "FAILED", "retry_count": 1, "queue_wait_time": 10},
            {"name": "task2", "status": "FAILED", "retry_count": 5, "queue_wait_time": 10},
            {"name": "task3", "status": "FAILED", "retry_count": 2, "queue_wait_time": 10}
        ]
        historical_metrics = {"avg_queue_wait_time": 100}

        result = analyze_timeout_alert(tasks, historical_metrics)

        assert result["root_cause"]["type"] == "task_error_retry"
        assert result["root_cause"]["task_name"] == "task2"
        assert result["root_cause"]["retry_count"] == 5

    def test_multiple_resource_waiting_tasks(self):
        """Test with multiple resource waiting tasks - should pick the one with highest ratio"""
        tasks = [
            {"name": "task1", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 300},
            {"name": "task2", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 900},
            {"name": "task3", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 450}
        ]
        historical_metrics = {"avg_queue_wait_time": 100}

        result = analyze_timeout_alert(tasks, historical_metrics)

        assert result["root_cause"]["type"] == "resource_waiting"
        assert result["root_cause"]["task_name"] == "task2"
        assert result["root_cause"]["queue_wait_time"] == 900


class TestGetTimeoutSummary:
    """Test get_timeout_summary function"""

    def test_summary_task_error_retry(self):
        """Test summary for task error retry"""
        result = {
            "root_cause": {
                "type": "task_error_retry",
                "task_name": "transform_task",
                "retry_count": 3
            },
            "analysis": [],
            "llm_hint": ""
        }

        summary = get_timeout_summary(result)

        assert "transform_task" in summary
        assert "重试" in summary
        assert "3" in summary

    def test_summary_resource_waiting(self):
        """Test summary for resource waiting"""
        result = {
            "root_cause": {
                "type": "resource_waiting",
                "task_name": "spark_job",
                "queue_wait_time": 600,
                "historical_avg": 120
            },
            "analysis": [],
            "llm_hint": ""
        }

        summary = get_timeout_summary(result)

        assert "spark_job" in summary
        assert "资源排队" in summary
        assert "600" in summary
        assert "120" in summary

    def test_summary_unknown(self):
        """Test summary for unknown cause"""
        result = {
            "root_cause": {
                "type": "unknown",
                "task_name": None
            },
            "analysis": [],
            "llm_hint": ""
        }

        summary = get_timeout_summary(result)

        assert "未知" in summary


class TestGetClusterResourceStatus:
    """Test get_cluster_resource_status function"""

    def test_normal_cluster(self):
        """Test with normal cluster metrics"""
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 51200,
            "total_vcores": 200,
            "used_vcores": 100,
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 20,
            "running_applications": 15
        }

        result = get_cluster_resource_status(yarn_metrics)

        assert result["utilization"]["memory_percent"] == 50.0
        assert result["utilization"]["vcore_percent"] == 50.0
        assert result["utilization"]["node_health_percent"] == 100.0
        assert result["is_overloaded"] is False

    def test_overloaded_cluster_memory(self):
        """Test detection of overloaded cluster due to memory"""
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 92160,  # 90%
            "total_vcores": 200,
            "used_vcores": 100,
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 20,
            "running_applications": 15
        }

        result = get_cluster_resource_status(yarn_metrics)

        assert result["is_overloaded"] is True
        assert any("内存" in msg for msg in result["analysis"])

    def test_overloaded_cluster_vcores(self):
        """Test detection of overloaded cluster due to vcores"""
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 51200,
            "total_vcores": 200,
            "used_vcores": 180,  # 90%
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 20,
            "running_applications": 15
        }

        result = get_cluster_resource_status(yarn_metrics)

        assert result["is_overloaded"] is True
        assert any("VCore" in msg for msg in result["analysis"])

    def test_overloaded_cluster_unhealthy_nodes(self):
        """Test detection of overloaded cluster due to unhealthy nodes"""
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 51200,
            "total_vcores": 200,
            "used_vcores": 100,
            "active_nodes": 5,
            "unhealthy_nodes": 5,  # 50% unhealthy
            "pending_containers": 20,
            "running_applications": 15
        }

        result = get_cluster_resource_status(yarn_metrics)

        assert result["is_overloaded"] is True
        assert any("节点健康" in msg for msg in result["analysis"])

    def test_overloaded_cluster_pending_containers(self):
        """Test detection of overloaded cluster due to pending containers"""
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 51200,
            "total_vcores": 200,
            "used_vcores": 100,
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 200,  # > 100
            "running_applications": 15
        }

        result = get_cluster_resource_status(yarn_metrics)

        assert result["is_overloaded"] is True
        assert any("待分配容器" in msg for msg in result["analysis"])

    def test_empty_metrics(self):
        """Test with empty metrics"""
        result = get_cluster_resource_status({})

        assert result["utilization"]["memory_percent"] == 0.0
        assert result["utilization"]["vcore_percent"] == 0.0
        assert result["is_overloaded"] is False
        assert any("缺少" in msg for msg in result["analysis"])

    def test_none_metrics(self):
        """Test with None metrics"""
        result = get_cluster_resource_status(None)

        assert result["is_overloaded"] is False
        assert any("缺少" in msg for msg in result["analysis"])


class TestCheckQueueStatus:
    """Test check_queue_status function"""

    def test_normal_queue(self):
        """Test with normal queue status"""
        queue_metrics = {
            "queue_name": "default",
            "used_capacity": 50.0,
            "max_capacity": 100.0,
            "num_applications": 10,
            "num_pending_applications": 2
        }

        result = check_queue_status(queue_metrics)

        assert result["queue_name"] == "default"
        assert result["used_capacity"] == 50.0
        assert result["is_congested"] is False

    def test_congested_queue_capacity(self):
        """Test detection of congested queue due to capacity"""
        queue_metrics = {
            "queue_name": "production",
            "used_capacity": 95.0,
            "max_capacity": 100.0,
            "num_applications": 50,
            "num_pending_applications": 5
        }

        result = check_queue_status(queue_metrics)

        assert result["is_congested"] is True
        assert any("容量" in msg for msg in result["analysis"])

    def test_congested_queue_pending_apps(self):
        """Test detection of congested queue due to pending applications"""
        queue_metrics = {
            "queue_name": "production",
            "used_capacity": 70.0,
            "max_capacity": 100.0,
            "num_applications": 50,
            "num_pending_applications": 20
        }

        result = check_queue_status(queue_metrics)

        assert result["is_congested"] is True
        assert any("待处理" in msg for msg in result["analysis"])


class TestIntegration:
    """Integration tests for timeout analyzer"""

    def test_full_analysis_workflow_retry(self):
        """Test full analysis workflow for retry timeout"""
        tasks = [
            {"name": "data_extract", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 30},
            {"name": "data_transform", "status": "FAILED", "retry_count": 4, "queue_wait_time": 15},
            {"name": "data_load", "status": "PENDING", "retry_count": 0, "queue_wait_time": 0}
        ]
        historical_metrics = {"avg_queue_wait_time": 60}

        # Run analysis
        result = analyze_timeout_alert(tasks, historical_metrics)

        # Verify
        assert result["root_cause"]["type"] == "task_error_retry"
        assert result["root_cause"]["task_name"] == "data_transform"

        # Get summary
        summary = get_timeout_summary(result)
        assert "data_transform" in summary

    def test_full_analysis_workflow_resource_waiting(self):
        """Test full analysis workflow for resource waiting timeout"""
        tasks = [
            {"name": "spark_etl", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 1200}
        ]
        historical_metrics = {"avg_queue_wait_time": 200}

        # Run analysis
        result = analyze_timeout_alert(tasks, historical_metrics)

        # Verify
        assert result["root_cause"]["type"] == "resource_waiting"
        assert result["root_cause"]["queue_wait_time"] == 1200

        # Check cluster status
        yarn_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 94208,  # 92%
            "total_vcores": 200,
            "used_vcores": 180,  # 90%
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 150,
            "running_applications": 30
        }
        cluster_status = get_cluster_resource_status(yarn_metrics)
        assert cluster_status["is_overloaded"] is True