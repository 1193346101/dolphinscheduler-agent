#!/usr/bin/env python3
"""
Cluster Resource Status Checker

Checks YARN cluster resource status to determine if the cluster is overloaded.
"""

from typing import Dict, Any, Optional


def get_cluster_resource_status(yarn_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get cluster resource utilization and check if overloaded.

    Args:
        yarn_metrics: YARN metrics containing:
            - total_memory_mb: int - Total cluster memory in MB
            - used_memory_mb: int - Used cluster memory in MB
            - total_vcores: int - Total cluster vcores
            - used_vcores: int - Used cluster vcores
            - active_nodes: int - Number of active nodes
            - unhealthy_nodes: int - Number of unhealthy nodes
            - pending_containers: int - Number of pending containers
            - running_applications: int - Number of running applications

    Returns:
        Dict containing:
            - utilization: {memory_percent, vcore_percent, node_health_percent}
            - is_overloaded: bool - Whether the cluster is overloaded
            - analysis: list of analysis messages
    """
    result = {
        "utilization": {
            "memory_percent": 0.0,
            "vcore_percent": 0.0,
            "node_health_percent": 100.0
        },
        "is_overloaded": False,
        "analysis": []
    }

    if not yarn_metrics:
        result["analysis"].append("缺少 YARN 集群指标")
        return result

    # Calculate memory utilization
    total_memory = yarn_metrics.get("total_memory_mb", 0)
    used_memory = yarn_metrics.get("used_memory_mb", 0)
    memory_percent = 0.0
    if total_memory > 0:
        memory_percent = (used_memory / total_memory) * 100
    result["utilization"]["memory_percent"] = round(memory_percent, 2)

    # Calculate vcore utilization
    total_vcores = yarn_metrics.get("total_vcores", 0)
    used_vcores = yarn_metrics.get("used_vcores", 0)
    vcore_percent = 0.0
    if total_vcores > 0:
        vcore_percent = (used_vcores / total_vcores) * 100
    result["utilization"]["vcore_percent"] = round(vcore_percent, 2)

    # Calculate node health
    active_nodes = yarn_metrics.get("active_nodes", 0)
    unhealthy_nodes = yarn_metrics.get("unhealthy_nodes", 0)
    node_health_percent = 100.0
    if active_nodes + unhealthy_nodes > 0:
        node_health_percent = (active_nodes / (active_nodes + unhealthy_nodes)) * 100
    result["utilization"]["node_health_percent"] = round(node_health_percent, 2)

    # Get pending containers and running applications
    pending_containers = yarn_metrics.get("pending_containers", 0)
    running_applications = yarn_metrics.get("running_applications", 0)

    # Determine if cluster is overloaded
    # Criteria for overload:
    # 1. Memory utilization > 85%
    # 2. VCore utilization > 85%
    # 3. Node health < 80%
    # 4. Large number of pending containers (> 100)
    overload_reasons = []

    if memory_percent > 85:
        overload_reasons.append(f"内存利用率过高: {memory_percent:.1f}%")

    if vcore_percent > 85:
        overload_reasons.append(f"VCore 利用率过高: {vcore_percent:.1f}%")

    if node_health_percent < 80:
        overload_reasons.append(f"节点健康率低: {node_health_percent:.1f}%")

    if pending_containers > 100:
        overload_reasons.append(f"待分配容器过多: {pending_containers}")

    # Set overload status
    result["is_overloaded"] = len(overload_reasons) > 0

    # Generate analysis messages
    result["analysis"].append(f"内存利用率: {memory_percent:.1f}% ({used_memory}/{total_memory} MB)")
    result["analysis"].append(f"VCore 利用率: {vcore_percent:.1f}% ({used_vcores}/{total_vcores})")
    result["analysis"].append(f"节点健康率: {node_health_percent:.1f}% ({active_nodes}/{active_nodes + unhealthy_nodes})")
    result["analysis"].append(f"运行中应用: {running_applications}")
    result["analysis"].append(f"待分配容器: {pending_containers}")

    if overload_reasons:
        result["analysis"].append("---")
        result["analysis"].append("集群状态: 过载")
        for reason in overload_reasons:
            result["analysis"].append(f"  - {reason}")
    else:
        result["analysis"].append("---")
        result["analysis"].append("集群状态: 正常")

    return result


def check_queue_status(queue_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check the status of a specific YARN queue.

    Args:
        queue_metrics: Queue metrics containing:
            - queue_name: str - Name of the queue
            - used_capacity: float - Used capacity percentage
            - max_capacity: float - Maximum capacity percentage
            - num_applications: int - Number of applications in queue
            - num_pending_applications: int - Number of pending applications

    Returns:
        Dict containing:
            - queue_name: str
            - used_capacity: float
            - is_congested: bool
            - analysis: list of analysis messages
    """
    result = {
        "queue_name": queue_metrics.get("queue_name", "unknown"),
        "used_capacity": queue_metrics.get("used_capacity", 0),
        "is_congested": False,
        "analysis": []
    }

    used_capacity = queue_metrics.get("used_capacity", 0)
    pending_applications = queue_metrics.get("num_pending_applications", 0)

    # Queue is congested if usage > 90% or many pending applications
    if used_capacity > 90:
        result["is_congested"] = True
        result["analysis"].append(f"队列容量使用率过高: {used_capacity:.1f}%")

    if pending_applications > 10:
        result["is_congested"] = True
        result["analysis"].append(f"待处理应用过多: {pending_applications}")

    if not result["is_congested"]:
        result["analysis"].append("队列状态正常")

    return result


if __name__ == "__main__":
    import json
    import sys

    def main():
        """CLI entry point for cluster status check."""
        # Sample YARN metrics
        sample_metrics = {
            "total_memory_mb": 102400,
            "used_memory_mb": 87040,
            "total_vcores": 200,
            "used_vcores": 170,
            "active_nodes": 10,
            "unhealthy_nodes": 0,
            "pending_containers": 50,
            "running_applications": 25
        }

        # Parse command line arguments if provided
        if len(sys.argv) > 1:
            try:
                with open(sys.argv[1], 'r') as f:
                    yarn_metrics = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Error reading input file: {sys.argv[1]}")
                sys.exit(1)
        else:
            yarn_metrics = sample_metrics

        # Run cluster status check
        result = get_cluster_resource_status(yarn_metrics)

        # Output results
        print("=== Cluster Resource Status ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    main()