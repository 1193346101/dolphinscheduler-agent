---
name: spark-error-analyzer
description: 分析 Spark/Spark Streaming 任务执行错误
task_types:
  - SPARK
  - SPARK_STREAMING
version: "1.0.0"
---

# Spark Error Analyzer Skill

分析 Spark/Spark Streaming 任务执行错误，提供错误分类、修复建议和 LLM 提示。

## Processing Steps

### 1. 日志预处理

调用 `preprocess_log.py` 提取关键信息：

```python
from skills.common.preprocess_log import preprocess_log

result = preprocess_log(log_content, task_type="spark")
# 返回: config_lines, error_blocks, app_info, data_metrics, resource_stats
```

提取内容：
- **config_lines**: Spark/Hadoop 配置行 (spark.*, hadoop.*, yarn.*)
- **error_blocks**: 完整的错误堆栈块
- **app_info**: Application ID
- **data_metrics**: 数据量指标 (input_bytes, shuffle_read/write, memory_spilled)

### 2. 匹配错误模式

调用 `scripts/match_error.py` 匹配已知错误模式：

```python
from skills.spark_error_analyzer.scripts.match_error import match_error

match = match_error(error_blocks, patterns_file="spark_patterns.md")
# 返回: error_type, category, pattern, fix_action
```

模式分类：
- **AUTO_FIXABLE**: 可自动修复（配置调整）
- **KNOWN_NEEDS_LLM**: 已知类型，需 LLM 分析
- **UNKNOWN**: 未知错误，完全交给 LLM

### 3. 增强上下文

对于连接/服务错误，补充环境上下文：

```python
if error_type in ["connection_refused", "shuffle_failed", "hdfs_not_found"]:
    context = enrich_context(error_type, app_info)
    # 补充: 集群状态、服务健康检查结果
```

### 4. 构建修复方案

对于 AUTO_FIXABLE 类型，构建配置修复方案：

```python
if category == "AUTO_FIXABLE":
    fix = build_fix_action(error_type, data_metrics)
    # 返回: action_type, config_changes, reasoning
```

### 5. 分析数据量指标

对于 OOM/性能问题，分析数据量：

```python
if error_type.startswith("oom_") or error_type in ["gc_overhead", "container_killed_memory"]:
    metrics_analysis = analyze_data_metrics(data_metrics)
    # 分析: 数据量是否超预期、shuffle 数据倾斜
```

### 6. 匹配知识库

查询历史相似案例：

```python
kb_match = match_knowledge_base(error_type, error_message)
# 返回: similar_cases, solutions
```

### 7. 安全检查

验证修复方案的安全性：

```python
if fix:
    safety = check_safety(fix)
    # 检查: 配置值范围、资源限制、环境兼容性
```

## Output Format

```json
{
  "error_type": "oom_executor",
  "category": "AUTO_FIXABLE",
  "error_message": "java.lang.OutOfMemoryError: Java heap space\n\tat...",
  "targets": {
    "spark_app_id": "application_1234567890_0001",
    "executor_id": "executor-1"
  },
  "data_metrics": {
    "input_bytes": 10737418240,
    "shuffle_read_bytes": 5368709120,
    "shuffle_write_bytes": 2147483648,
    "memory_spilled": 1073741824
  },
  "fix": {
    "action_type": "modify_config",
    "config_changes": {
      "spark.executor.memory": "4g",
      "spark.executor.memoryOverhead": "1g"
    },
    "reasoning": "Executor OOM detected with 10GB input data. Increasing executor memory."
  },
  "llm_hint": null,
  "confidence": 0.95
}
```

## Error Categories

### AUTO_FIXABLE

错误类型可通过配置调整自动修复：

| 错误类型 | 典型模式 | 修复动作 |
|---------|---------|---------|
| oom_executor | `OutOfMemoryError: Java heap space` | 增加 executor.memory |
| oom_driver | `OutOfMemoryError: unable to create new native thread` | 增加 driver.memory |
| container_killed_memory | `Container killed due to memory` | 增加 memory + memoryOverhead |
| gc_overhead | `GC overhead limit exceeded` | 增加内存 + 调整 GC |
| broadcast_timeout | `BroadcastHashJoin.*timeout` | 禁用广播或增加阈值 |
| shuffle_timeout | `shuffle.*timeout` | 增加 shuffle.io.timeout |
| network_timeout | `spark.network.timeout` | 增加 network.timeout |

### KNOWN_NEEDS_LLM

已知错误类型，需要 LLM 进一步分析：

| 错误类型 | 典型模式 | LLM 提示 |
|---------|---------|---------|
| class_not_found | `ClassNotFoundException` | 分析缺失的类名和依赖包 |
| shuffle_failed | `FetchFailedException` | 分析 Shuffle Service 状态 |
| connection_refused | `Connection refused` | 检查目标服务运行状态 |
| hdfs_not_found | `does not exist\|FileNotFound` | 检查输入路径是否正确 |
| schema_mismatch | `Schema mismatch\|cannot resolve` | 分析数据结构问题 |

完整模式定义见 [spark_patterns.md](./spark_patterns.md)

## Dependencies

- `skills/common/preprocess_log.py` - 日志预处理
- `skills/spark-error-analyzer/scripts/match_error.py` - 模式匹配
- `skills/spark-error-analyzer/spark_patterns.md` - 错误模式表

## Examples

### Example 1: Executor OOM

**Input Log:**
```
ERROR Executor: Exception in task 0.0 in stage 1.0 (TID 1)
java.lang.OutOfMemoryError: Java heap space
    at org.apache.spark.shuffle.sort.ShuffleExternalSorter...
```

**Output:**
```json
{
  "error_type": "oom_executor",
  "category": "AUTO_FIXABLE",
  "error_message": "java.lang.OutOfMemoryError: Java heap space",
  "targets": {"spark_app_id": "application_1704067200000_0001"},
  "data_metrics": {"input_bytes": 10737418240},
  "fix": {
    "action_type": "modify_config",
    "config_changes": {
      "spark.executor.memory": "4g",
      "spark.executor.memoryOverhead": "1g"
    }
  }
}
```

### Example 2: Class Not Found

**Input Log:**
```
ERROR SparkContext: Error initializing SparkContext.
java.lang.ClassNotFoundException: com.example.MyCustomClass
    at java.net.URLClassLoader.findClass(URLClassLoader.java:382)
```

**Output:**
```json
{
  "error_type": "class_not_found",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "java.lang.ClassNotFoundException: com.example.MyCustomClass",
  "targets": {"spark_app_id": null},
  "data_metrics": {},
  "fix": null,
  "llm_hint": "Spark 类找不到，请分析缺失的类名和需要的依赖包"
}
```