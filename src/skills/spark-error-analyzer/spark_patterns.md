# Spark Error Patterns

错误模式表，用于快速匹配和分类 Spark 任务错误。

## AUTO_FIXABLE

可自动修复的错误，通过配置调整即可解决。

| error_type | pattern | fix_action |
|------------|---------|------------|
| oom_executor | `java\.lang\.OutOfMemoryError:\s*Java heap space` | `{"spark.executor.memory": "4g", "spark.executor.memoryOverhead": "1g"}` |
| oom_driver | `OutOfMemoryError:\s*unable to create new native thread` | `{"spark.driver.memory": "2g", "spark.driver.maxResultSize": "2g"}` |
| oom_driver_direct | `OutOfMemoryError:\s*Container memory exceeded` | `{"spark.driver.maxResultSize": "2g"}` |
| oom_offheap | `OutOfMemoryError:\s*offheap` | `{"spark.memory.offHeap.enabled": "true", "spark.memory.offHeap.size": "2g"}` |
| oom_storage | `OutOfMemoryError:\s*Storage memory` | `{"spark.memory.storageFraction": "0.3"}` |
| container_killed_memory | `Container killed due to memory\|exceeding memory limits\|memory limits` | `{"spark.executor.memory": "4g", "spark.executor.memoryOverhead": "1g", "spark.driver.memory": "2g"}` |
| gc_overhead | `GC overhead limit exceeded` | `{"spark.executor.memory": "8g", "spark.executor.memoryOverhead": "2g", "spark.driver.memory": "4g"}` |
| broadcast_timeout | `BroadcastHashJoin.*timeout\|broadcast.*timeout` | `{"spark.sql.autoBroadcastJoinThreshold": "-1"}` |
| shuffle_timeout | `shuffle.*timeout` | `{"spark.shuffle.io.timeout": "120s"}` |
| network_timeout | `spark\.network\.timeout` | `{"spark.network.timeout": "300s"}` |
| rpc_timeout | `RPC timeout` | `{"spark.rpc.timeout": "300s"}` |
| executor_lost_heartbeat | `Executor heartbeat timeout` | `{"spark.executor.heartbeatInterval": "60s", "spark.network.timeout": "300s"}` |
| driver_memory_insufficient | `System memory.*must be at least.*increase heap size.*driver-memory` | `{"spark.driver.memory": "512m", "spark.driver.memoryOverhead": "128m"}` |
| executor_memory_insufficient | `Executor memory.*must be at least` | `{"spark.executor.memory": "1g", "spark.executor.memoryOverhead": "256m"}` |

## KNOWN_NEEDS_LLM

已知错误类型，需要 LLM 进一步分析上下文。

| error_type | pattern | llm_hint |
|------------|---------|----------|
| class_not_found | `ClassNotFoundException` | Spark 类找不到，请分析缺失的类名和需要的依赖包 |
| no_class_def | `NoClassDefFoundError` | Spark 类定义找不到，请分析类名和依赖加载问题 |
| jar_not_found | `jar not found\|could not find jar` | Spark Jar 包找不到，请检查 Jar 包路径 |
| main_class_not_found | `Main class not found` | Spark 主类找不到，请检查 Main Class 名称 |
| spark_version_mismatch | `Spark version mismatch` | Spark 版本不匹配，请检查版本兼容性 |
| shuffle_failed | `FetchFailedException` | Spark Shuffle 数据拉取失败，请分析 Shuffle Service 状态和网络问题 |
| shuffle_connection | `shuffle.*connection failed` | Spark Shuffle 连接失败，请检查 Shuffle Service |
| connection_refused | `Connection refused\|ConnectException` | Spark 网络连接被拒绝，请检查目标服务是否运行 |
| connection_timeout | `Connection timed out\|SocketTimeoutException` | Spark 网络连接超时，请检查网络状态 |
| driver_disconnected | `Driver disconnected\|Driver closed` | Spark Driver 断开连接，请分析 Driver 状态 |
| block_manager_lost | `BlockManager.*lost\|BlockManagerId.*lost` | Spark BlockManager 丢失，请检查存储状态 |
| hdfs_not_found | `does not exist\|FileNotFound\|InvalidInputException.*path` | Spark HDFS 文件不存在，请检查输入路径是否正确 |
| file_not_found | `FileNotFoundException\|file not found` | Spark 文件不存在，请检查文件路径 |
| hdfs_permission | `Permission denied.*hdfs\|access denied` | Spark HDFS 权限不足，请检查文件权限 |
| schema_mismatch | `Schema mismatch\|cannot resolve` | Spark Schema 不匹配，请分析数据结构问题 |
| partition_not_found | `Partition not found\|partition.*does not exist` | Spark 分区不存在，请检查分区配置 |
| corrupt_data | `Corrupt block\|corrupt data` | Spark 数据损坏，请检查数据文件 |
| null_value | `Null value\|NullPointerException` | Spark 空值问题，请分析空值处理逻辑 |
| datetime_parse | `DateTimeParseException\|cannot parse date` | Spark 日期解析失败，请检查日期格式 |
| spark_sql_error | `SparkSQLException\|AnalysisException` | Spark SQL 错误，请分析 SQL 语法和语义问题 |
| job_aborted | `SparkException:\s*Job aborted` | Spark Job 被中止，请分析具体中止原因 |
| stage_failed | `Stage\s+\d+\s+failed` | Spark Stage 失败，请分析失败的具体 Stage 和原因 |
| task_failed | `Task failed\|TaskSetManager.*failed` | Spark Task 失败，请分析失败原因 |
| app_submission_failed | `Application submission failed` | Spark 应用提交失败，请检查提交配置 |
| sql_syntax | `SQL syntax error\|parse exception` | Spark SQL 语法错误，请分析 SQL 语法 |
| sql_column_not_found | `Column.*not found\|cannot resolve column` | Spark SQL 列不存在，请检查列名 |
| sql_table_not_found | `Table.*not found\|table does not exist` | Spark SQL 表不存在，请检查表名 |
| container_killed | `Container killed by YARN\|Container killed` | Spark 容器被 YARN 终止，请分析资源使用情况 |
| executor_lost | `Executor lost` | Spark Executor 丢失，请分析 Executor 状态 |
| executor_crash | `Executor crashed` | Spark Executor 崩溃，请分析崩溃原因 |
| yarn_resource | `YARN.*resource.*insufficient` | Spark YARN 资源不足，请检查资源配额 |
| yarn_container_exit | `Container.*exit.*code` | YARN Container 异常退出，请分析退出原因 |
| queue_full | `Queue.*full\|queue capacity` | Spark YARN 队列满，请检查队列状态 |
| killed_by_user | `Killed by user` | Spark 任务被手动终止，无需自动修复 |

## Pattern Matching Rules

1. **优先级**: AUTO_FIXABLE > KNOWN_NEEDS_LLM > UNKNOWN
2. **匹配方式**: 正则表达式，忽略大小写 (re.IGNORECASE)
3. **跨行匹配**: 使用 re.DOTALL 处理跨行日志
4. **多模式匹配**: 单个日志可能匹配多个模式，取第一个匹配

## Usage

```python
import re
from pathlib import Path

def load_patterns(file_path: str) -> dict:
    """Load patterns from spark_patterns.md"""
    patterns = {"AUTO_FIXABLE": {}, "KNOWN_NEEDS_LLM": {}}
    # Parse markdown tables and populate patterns
    return patterns

def match_error(log_content: str, patterns: dict) -> tuple:
    """Match error patterns in log content"""
    for category, error_patterns in patterns.items():
        for error_type, (pattern, hint_or_fix) in error_patterns.items():
            if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
                return error_type, category, pattern, hint_or_fix
    return "unknown", "UNKNOWN", None, None
```