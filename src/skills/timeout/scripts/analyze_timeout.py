#!/usr/bin/env python3
"""
Timeout Alert Analyzer

Analyzes workflow timeout alerts and identifies root causes.
Only two timeout causes are considered:
1. task_error_retry: retry_count > 0
2. resource_waiting: queue_wait_time > historical_avg * 2
"""

from typing import Dict, List, Any, Optional


def analyze_timeout_alert(
    tasks: List[Dict[str, Any]],
    historical_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Analyze timeout alert and identify root cause.

    Args:
        tasks: List of task execution information, each containing:
            - name: str - Task name
            - status: str - Task status (SUCCESS, FAILED, RUNNING, PENDING)
            - retry_count: int - Number of retry attempts
            - queue_wait_time: int - Queue wait time in seconds
            - start_time: str - Task start time (optional)
            - end_time: str - Task end time (optional)
        historical_metrics: Historical metrics containing:
            - avg_queue_wait_time: float - Average queue wait time

    Returns:
        Dict containing:
            - root_cause: {type, task_name, retry_count/queue_wait_time}
            - analysis: list of analysis messages
            - llm_hint: str - Hint for LLM analysis
    """
    result = {
        "root_cause": {},
        "analysis": [],
        "llm_hint": ""
    }

    if not tasks:
        result["root_cause"] = {
            "type": "unknown",
            "task_name": None
        }
        result["analysis"].append("没有任务信息")
        result["llm_hint"] = "无法分析超时原因：缺少任务信息"
        return result

    # Get historical average queue wait time
    historical_avg = 0
    if historical_metrics:
        historical_avg = historical_metrics.get("avg_queue_wait_time", 0)

    # First check for task_error_retry (priority over resource_waiting)
    retry_tasks = []
    for task in tasks:
        retry_count = task.get("retry_count", 0)
        if retry_count > 0:
            retry_tasks.append(task)

    if retry_tasks:
        # Find task with most retries
        retry_task = max(retry_tasks, key=lambda t: t.get("retry_count", 0))
        task_name = retry_task.get("name", "unknown")
        retry_count = retry_task.get("retry_count", 0)

        result["root_cause"] = {
            "type": "task_error_retry",
            "task_name": task_name,
            "retry_count": retry_count
        }
        result["analysis"] = [
            f"任务 {task_name} 执行失败并重试 {retry_count} 次",
            f"重试导致执行时间延长"
        ]
        result["llm_hint"] = f"请分析任务 {task_name} 的执行错误日志，确定失败原因"
        return result

    # Check for resource_waiting
    resource_waiting_tasks = []
    threshold_multiplier = 2.0

    for task in tasks:
        queue_wait_time = task.get("queue_wait_time", 0)
        if queue_wait_time > 0 and historical_avg > 0:
            if queue_wait_time > historical_avg * threshold_multiplier:
                resource_waiting_tasks.append(task)

    if resource_waiting_tasks:
        # Find task with longest relative queue wait time
        wait_task = max(
            resource_waiting_tasks,
            key=lambda t: t.get("queue_wait_time", 0) / max(historical_avg, 1)
        )
        task_name = wait_task.get("name", "unknown")
        queue_wait_time = wait_task.get("queue_wait_time", 0)
        ratio = queue_wait_time / max(historical_avg, 1)

        result["root_cause"] = {
            "type": "resource_waiting",
            "task_name": task_name,
            "queue_wait_time": queue_wait_time,
            "historical_avg": historical_avg
        }
        result["analysis"] = [
            f"任务 {task_name} 排队等待 {queue_wait_time} 秒",
            f"历史平均排队时间: {historical_avg} 秒",
            f"排队时间是历史均值的 {ratio:.1f} 倍"
        ]
        result["llm_hint"] = "集群资源不足，建议检查 YARN 队列配置或降低并发任务数"
        return result

    # No specific cause found
    result["root_cause"] = {
        "type": "unknown",
        "task_name": None
    }
    result["analysis"] = [
        "无法确定具体的超时原因",
        f"检查了 {len(tasks)} 个任务",
        "未发现重试任务或异常排队时间"
    ]
    result["llm_hint"] = "超时原因未知，建议检查任务执行日志和网络状态"

    return result


def get_timeout_summary(result: Dict[str, Any]) -> str:
    """
    Generate a human-readable summary of the timeout analysis.

    Args:
        result: The result from analyze_timeout_alert

    Returns:
        Human-readable summary string
    """
    root_cause = result.get("root_cause", {})
    cause_type = root_cause.get("type", "unknown")
    task_name = root_cause.get("task_name", "unknown")

    if cause_type == "task_error_retry":
        retry_count = root_cause.get("retry_count", 0)
        return f"超时原因: 任务 {task_name} 重试 {retry_count} 次"

    elif cause_type == "resource_waiting":
        queue_wait_time = root_cause.get("queue_wait_time", 0)
        historical_avg = root_cause.get("historical_avg", 0)
        return f"超时原因: 任务 {task_name} 资源排队等待 {queue_wait_time} 秒 (历史均值: {historical_avg} 秒)"

    else:
        return "超时原因: 未知"


if __name__ == "__main__":
    import json
    import sys

    def main():
        """CLI entry point for timeout analysis."""
        # Sample data for testing
        sample_tasks = [
            {
                "name": "extract_task",
                "status": "SUCCESS",
                "retry_count": 0,
                "queue_wait_time": 60
            },
            {
                "name": "transform_task",
                "status": "FAILED",
                "retry_count": 3,
                "queue_wait_time": 30
            }
        ]

        sample_metrics = {
            "avg_queue_wait_time": 120
        }

        # Parse command line arguments if provided
        if len(sys.argv) > 1:
            try:
                with open(sys.argv[1], 'r') as f:
                    data = json.load(f)
                tasks = data.get("tasks", [])
                historical_metrics = data.get("historical_metrics", {})
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Error reading input file: {sys.argv[1]}")
                sys.exit(1)
        else:
            tasks = sample_tasks
            historical_metrics = sample_metrics

        # Run analysis
        result = analyze_timeout_alert(tasks, historical_metrics)

        # Output results
        print("=== Timeout Analysis Result ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        print("\n=== Summary ===")
        print(get_timeout_summary(result))

    main()