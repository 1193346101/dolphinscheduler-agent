# Timeout Error Patterns

超时原因模式表，用于快速识别和分类工作流超时告警。

## AUTO_FIXABLE

可直接调整配置解决的问题。

| error_type | pattern | fix_action |
|------------|---------|------------|
| timeout_config_too_short | `workflow_timeout < sum(task_avg_duration) * 1.5` | {"action_type": "modify_config", "config_changes": {"timeout": "增加超时阈值"}} |
| retry_config_too_aggressive | `retry_interval < 30s AND retry_count > 3` | {"action_type": "modify_config", "config_changes": {"retry_interval": "增加到60s"}} |

## RESOURCE_SUGGESTED

资源类问题，Skill智能计算初步建议 + LLM验证补充。

| error_type | pattern | hint |
|------------|---------|------|
| cluster_overloaded | `cluster_utilization > 85% OR pending_containers > 100` | 集群资源过载，建议检查YARN队列配置或降低并发任务数 |
| queue_congested | `queue_used_capacity > 90% OR pending_apps > 10` | YARN队列拥堵，建议调整队列容量或错峰调度 |
| memory_pressure | `memory_utilization > 90%` | 集群内存紧张，建议检查大内存任务或增加节点 |
| vcore_pressure | `vcore_utilization > 90%` | 集群VCore紧张，建议检查CPU密集型任务 |

## KNOWN_NEEDS_LLM

已知超时类型，需要 LLM 进一步分析上下文。

| error_type | pattern | llm_hint |
|------------|---------|----------|
| task_retry_timeout | `retry_count >= 3 AND task_status == FAILED` | 任务多次重试导致超时，请分析任务错误日志确定失败原因 |
| task_retry_long | `retry_count >= 2 AND retry_duration > workflow_timeout * 0.3` | 任务重试占用过多时间，请分析重试间隔和失败原因 |
| task_execution_slow | `execution_time > historical_avg * 3` | 任务执行时间异常长，请分析日志判断是否有性能问题或数据量变化 |
| queue_wait_long | `queue_wait_time > historical_avg * 2 AND queue_wait_time > 300` | 任务排队等待时间过长，请检查集群资源状态 |
| upstream_delay | `upstream_task_duration > historical_avg * 2` | 上游任务延迟传导，请分析上游任务超时原因 |
| data_volume_spike | `data_size > historical_avg * 5` | 数据量激增导致处理时间变长，请分析数据来源变化 |
| task_chain_long | `task_count > 20 AND parallelism < 3` | 任务链过长且并行度低，请分析工作流设计优化 |

## Pattern Matching Rules

1. **优先级**: AUTO_FIXABLE > RESOURCE_SUGGESTED > KNOWN_NEEDS_LLM > UNKNOWN
2. **匹配方式**: 基于指标计算而非正则匹配（超时分析特殊性）
3. **阈值动态调整**: 可根据任务类型(Spark/Shell/DataX)调整阈值倍数
4. **置信度评分**: 每个匹配结果附带置信度(0.0-1.0)

## Timeout Analysis Metrics

### 任务指标

| 指标 | 说明 | 用于判断 |
|------|------|----------|
| retry_count | 重试次数 | task_retry_timeout, task_retry_long |
| retry_interval | 重试间隔 | retry_config_too_aggressive |
| execution_time | 执行时间(秒) | task_execution_slow |
| queue_wait_time | 排队等待时间(秒) | queue_wait_long |
| data_size | 处理数据量(MB) | data_volume_spike |
| task_status | 任务状态 | task_retry_timeout |

### 集群指标

| 指标 | 说明 | 用于判断 |
|------|------|----------|
| cluster_utilization | 集群整体利用率 | cluster_overloaded |
| memory_utilization | 内存利用率 | memory_pressure |
| vcore_utilization | VCore利用率 | vcore_pressure |
| pending_containers | 待分配容器数 | cluster_overloaded |
| queue_used_capacity | 队列容量使用率 | queue_congested |
| pending_apps | 待处理应用数 | queue_congested |

### 历史指标

| 指标 | 说明 | 用于判断 |
|------|------|----------|
| avg_execution_time | 平均执行时间 | task_execution_slow |
| avg_queue_wait_time | 平均排队时间 | queue_wait_long |
| avg_data_size | 平均数据量 | data_volume_spike |
| avg_task_count | 平均任务数 | task_chain_long |

## Threshold Configuration

```yaml
# 可在配置文件中调整阈值
thresholds:
  task_retry:
    min_retry_count: 3          # 最小重试次数才认为是重试超时
    retry_time_ratio: 0.3       # 重试时间占比超过30%才认为严重
  
  execution_time:
    slow_multiplier: 3          # 执行时间超过历史均值3倍
  
  queue_wait:
    long_multiplier: 2          # 排队时间超过历史均值2倍
    min_absolute_seconds: 300   # 排队时间绝对阈值300秒
  
  cluster:
    utilization_threshold: 85   # 集群利用率阈值85%
    pending_containers: 100     # 待分配容器阈值
  
  queue:
    capacity_threshold: 90      # 队列容量阈值90%
    pending_apps: 10            # 待处理应用阈值
```