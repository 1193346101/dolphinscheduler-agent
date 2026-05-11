"""
Safety check module for operation validation

This module provides safety validation functions to check cluster health
and downstream impact before performing operations.
"""

from typing import Dict, List, Any


def check_cluster_safety(yarn_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check cluster safety based on YARN metrics.

    Validates cluster conditions against thresholds:
    - utilization > 0.8 -> issue (high utilization)
    - pending_apps > 10 -> issue (queue overload)

    Args:
        yarn_metrics: Dictionary containing YARN metrics:
            - total_mb: Total memory in MB
            - available_mb: Available memory in MB
            - total_virtual_cores: Total virtual cores
            - available_virtual_cores: Available virtual cores
            - pending_apps: Number of pending applications

    Returns:
        Dictionary containing:
            - safe: bool - True if no issues detected
            - utilization: float - Cluster utilization ratio (0.0-1.0)
            - pending_apps: int - Number of pending applications
            - available_mb: int - Available memory in MB
            - issues: list - List of issue descriptions
    """
    # Extract metrics with defaults
    total_mb = yarn_metrics.get("total_mb", 0)
    available_mb = yarn_metrics.get("available_mb", 0)
    pending_apps = yarn_metrics.get("pending_apps", 0)

    # Calculate utilization
    utilization = 0.0
    if total_mb > 0:
        used_mb = total_mb - available_mb
        utilization = used_mb / total_mb

    # Check for issues
    issues: List[str] = []

    # High utilization threshold
    if utilization > 0.8:
        issues.append(f"High cluster utilization: {utilization * 100:.1f}%")

    # Queue overload threshold
    if pending_apps > 10:
        issues.append(f"Queue overload: {pending_apps} pending applications")

    return {
        "safe": len(issues) == 0,
        "utilization": utilization,
        "pending_apps": pending_apps,
        "available_mb": available_mb,
        "issues": issues,
    }


def check_downstream_impact(downstream_count: int) -> Dict[str, Any]:
    """
    Check downstream impact based on number of downstream tasks.

    Validates downstream task count against thresholds:
    - downstream_count >= 5 -> requires_approval

    Args:
        downstream_count: Number of downstream tasks affected

    Returns:
        Dictionary containing:
            - safe: bool - True (always safe, but may require approval)
            - downstream_count: int - Actual downstream count (min 0)
            - requires_approval: bool - True if approval is needed
            - message: str - Descriptive message
    """
    # Normalize count (no negative values)
    actual_count = max(0, downstream_count)

    # Check if approval is required
    requires_approval = actual_count >= 5

    if requires_approval:
        message = f"High downstream impact: {actual_count} downstream tasks requires approval"
    else:
        message = f"Low downstream impact: {actual_count} downstream tasks"

    return {
        "safe": True,  # Not unsafe, just may need approval
        "downstream_count": actual_count,
        "requires_approval": requires_approval,
        "message": message,
    }


__all__ = [
    "check_cluster_safety",
    "check_downstream_impact",
]