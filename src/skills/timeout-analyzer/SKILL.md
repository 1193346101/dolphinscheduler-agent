---
name: timeout-analyzer
description: 分析工作流超时告警并定位根因。当工作流执行超时时触发，识别任务重试或资源等待导致的超时。
task_types:
  - WORKFLOW
  - TASK_TIMEOUT
version: "1.0.0"
---

# Timeout Analyzer Skill

分析工作流超时告警并定位根因，区分任务错误重试和资源等待两类超时原因。

## Processing Steps

### 1. 收集超时任务信息

获取超时工作流的任务列表和执行状态：

```python
tasks = [
    {
        "name": "task_name",
        "status": "FAILED" | "SUCCESS" | "RUNNING",
        "retry_count": 0,
        "start_time": "2024-01-15 10:00:00",
        "end_time": "2024-01-15 10:30:00",
        "queue_wait_time": 120,  # seconds
    },
    ...
]
```

### 2. 分析超时根因

调用 `scripts/analyze_timeout.py` 进行根因分析（使用动态导入）：

```python
import importlib.util
spec = importlib.util.spec_from_file_location("analyze_timeout", scripts_dir / "analyze_timeout.py")
analyze_timeout_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_timeout_module)

result = analyze_timeout_module.analyze_timeout_alert(tasks, historical_metrics)
```

### 3. 判断超时类型

**只有两类超时原因：**

| 类型 | 判定条件 | 根因 |
|------|----------|------|
| task_error_retry | `retry_count > 0` | 任务执行失败后重试导致超时 |
| resource_waiting | `queue_wait_time > historical_avg × 2` | 资源排队等待导致超时 |

### 4. 检查集群资源状态

对于 `resource_waiting` 类型，检查集群状态（使用动态导入）：

```python
import importlib.util
spec = importlib.util.spec_from_file_location("check_cluster", scripts_dir / "check_cluster.py")
check_cluster_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_cluster_module)

status = check_cluster_module.get_cluster_resource_status(yarn_metrics)
```

## Output Format

```json
{
  "root_cause": {
    "type": "task_error_retry",
    "task_name": "data_transform_task",
    "retry_count": 3
  },
  "analysis": [
    "任务 data_transform_task 执行失败并重试 3 次",
    "每次重试增加约 10 分钟执行时间",
    "总重试时间: 30 分钟，超过工作流超时阈值"
  ],
  "llm_hint": "请分析任务 data_transform_task 的执行错误日志，确定失败原因"
}
```

```json
{
  "root_cause": {
    "type": "resource_waiting",
    "task_name": "spark_etl_task",
    "queue_wait_time": 1800,
    "historical_avg": 300
  },
  "analysis": [
    "任务 spark_etl_task 排队等待 1800 秒",
    "历史平均排队时间: 300 秒",
    "排队时间是历史均值的 6 倍，表明集群资源紧张"
  ],
  "llm_hint": "集群资源不足，建议检查 YARN 队列配置或降低并发任务数"
}
```

## Dependencies

- `skills/timeout-analyzer/scripts/analyze_timeout.py` - 超时分析核心逻辑
- `skills/timeout-analyzer/scripts/check_cluster.py` - 集群资源状态检查

## Examples

### Example 1: 任务重试超时

**Input:**
```python
tasks = [
    {"name": "extract_task", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 60},
    {"name": "transform_task", "status": "FAILED", "retry_count": 3, "queue_wait_time": 30},
    {"name": "load_task", "status": "PENDING", "retry_count": 0, "queue_wait_time": 0}
]
historical_metrics = {"avg_queue_wait_time": 120}
```

**Output:**
```json
{
  "root_cause": {
    "type": "task_error_retry",
    "task_name": "transform_task",
    "retry_count": 3
  },
  "analysis": [
    "任务 transform_task 执行失败并重试 3 次",
    "重试导致执行时间延长"
  ],
  "llm_hint": "请分析任务 transform_task 的执行错误日志"
}
```

### Example 2: 资源等待超时

**Input:**
```python
tasks = [
    {"name": "spark_job", "status": "SUCCESS", "retry_count": 0, "queue_wait_time": 600}
]
historical_metrics = {"avg_queue_wait_time": 120}
```

**Output:**
```json
{
  "root_cause": {
    "type": "resource_waiting",
    "task_name": "spark_job",
    "queue_wait_time": 600,
    "historical_avg": 120
  },
  "analysis": [
    "任务 spark_job 排队等待 600 秒",
    "历史平均排队时间: 120 秒",
    "排队时间是历史均值的 5 倍"
  ],
  "llm_hint": "集群资源紧张，建议检查 YARN 队列配置"
}
```