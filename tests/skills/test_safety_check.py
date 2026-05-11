"""
Test safety check module for operation validation
"""

import pytest
from src.skills.common.safety_check import (
    check_cluster_safety,
    check_downstream_impact,
)


class TestCheckClusterSafety:
    """Tests for cluster safety validation"""

    def test_check_cluster_safety_safe(self):
        """Test cluster safety check when everything is normal"""
        yarn_metrics = {
            "total_mb": 100000,
            "available_mb": 50000,
            "total_virtual_cores": 100,
            "available_virtual_cores": 50,
            "pending_apps": 5,
        }
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is True
        assert result["utilization"] == 0.5
        assert result["pending_apps"] == 5
        assert result["available_mb"] == 50000
        assert result["issues"] == []

    def test_check_cluster_safety_high_utilization(self):
        """Test cluster safety check with high utilization"""
        yarn_metrics = {
            "total_mb": 100000,
            "available_mb": 15000,  # 85% utilization
            "total_virtual_cores": 100,
            "available_virtual_cores": 15,
            "pending_apps": 3,
        }
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is False
        assert result["utilization"] == 0.85
        assert result["pending_apps"] == 3
        assert result["available_mb"] == 15000
        assert "High cluster utilization: 85.0%" in result["issues"]

    def test_check_cluster_safety_queue_overload(self):
        """Test cluster safety check with queue overload"""
        yarn_metrics = {
            "total_mb": 100000,
            "available_mb": 50000,
            "total_virtual_cores": 100,
            "available_virtual_cores": 50,
            "pending_apps": 15,  # > 10
        }
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is False
        assert result["utilization"] == 0.5
        assert result["pending_apps"] == 15
        assert result["available_mb"] == 50000
        assert "Queue overload: 15 pending applications" in result["issues"]

    def test_check_cluster_safety_multiple_issues(self):
        """Test cluster safety check with multiple issues"""
        yarn_metrics = {
            "total_mb": 100000,
            "available_mb": 10000,  # 90% utilization
            "total_virtual_cores": 100,
            "available_virtual_cores": 10,
            "pending_apps": 20,  # > 10
        }
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is False
        assert result["utilization"] == 0.9
        assert result["pending_apps"] == 20
        assert result["available_mb"] == 10000
        assert len(result["issues"]) == 2
        assert "High cluster utilization: 90.0%" in result["issues"]
        assert "Queue overload: 20 pending applications" in result["issues"]

    def test_check_cluster_safety_empty_metrics(self):
        """Test cluster safety check with empty metrics"""
        yarn_metrics = {}
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is True
        assert result["utilization"] == 0.0
        assert result["pending_apps"] == 0
        assert result["available_mb"] == 0
        assert result["issues"] == []

    def test_check_cluster_safety_zero_total(self):
        """Test cluster safety check with zero total memory"""
        yarn_metrics = {
            "total_mb": 0,
            "available_mb": 0,
            "total_virtual_cores": 0,
            "available_virtual_cores": 0,
            "pending_apps": 0,
        }
        result = check_cluster_safety(yarn_metrics)

        assert result["safe"] is True
        assert result["utilization"] == 0.0
        assert result["pending_apps"] == 0
        assert result["available_mb"] == 0
        assert result["issues"] == []


class TestCheckDownstreamImpact:
    """Tests for downstream impact validation"""

    def test_check_downstream_impact_safe(self):
        """Test downstream impact check when safe (few downstream tasks)"""
        result = check_downstream_impact(downstream_count=3)

        assert result["safe"] is True
        assert result["downstream_count"] == 3
        assert result["requires_approval"] is False
        assert "Low downstream impact" in result["message"]

    def test_check_downstream_impact_needs_approval(self):
        """Test downstream impact check when approval is needed"""
        result = check_downstream_impact(downstream_count=5)

        assert result["safe"] is True  # Not unsafe, just needs approval
        assert result["downstream_count"] == 5
        assert result["requires_approval"] is True
        assert "requires approval" in result["message"]

    def test_check_downstream_impact_high_count(self):
        """Test downstream impact check with high downstream count"""
        result = check_downstream_impact(downstream_count=10)

        assert result["safe"] is True
        assert result["downstream_count"] == 10
        assert result["requires_approval"] is True
        assert "requires approval" in result["message"]

    def test_check_downstream_impact_zero_count(self):
        """Test downstream impact check with zero downstream tasks"""
        result = check_downstream_impact(downstream_count=0)

        assert result["safe"] is True
        assert result["downstream_count"] == 0
        assert result["requires_approval"] is False
        assert "Low downstream impact" in result["message"]

    def test_check_downstream_impact_negative_count(self):
        """Test downstream impact check with negative count (edge case)"""
        result = check_downstream_impact(downstream_count=-1)

        assert result["safe"] is True
        assert result["downstream_count"] == 0
        assert result["requires_approval"] is False
        assert "Low downstream impact" in result["message"]