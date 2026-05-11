# Spark Error Patterns

This file defines error patterns for Spark task log analysis.

## Pattern Table

| error_type | pattern | category | fix_action | llm_hint |
|------------|---------|----------|------------|----------|
| oom_executor | `java.lang.OutOfMemoryError: Java heap space` | AUTO_FIXABLE | increase executor memory to 4g and memoryOverhead to 1g | |
| oom_driver | `OutOfMemoryError: unable to create new native thread` | AUTO_FIXABLE | increase driver memory to 2g and maxResultSize to 2g | |
| oom_driver_direct | `OutOfMemoryError: Container memory exceeded` | AUTO_FIXABLE | increase driver maxResultSize to 2g | |
| oom_offheap | `OutOfMemoryError: offheap` | AUTO_FIXABLE | enable offHeap with size 2g | |
| oom_storage | `OutOfMemoryError: Storage memory` | AUTO_FIXABLE | adjust storageFraction to 0.3 | |
| driver_memory_insufficient | `System memory.*must be at least.*increase heap size.*driver-memory` | AUTO_FIXABLE | increase driver-memory to 512m | |
| executor_memory_insufficient | `Executor memory.*must be at least` | AUTO_FIXABLE | increase executor-memory to 1g | |
| broadcast_timeout | `BroadcastHashJoin.*timeout\|broadcast.*timeout` | AUTO_FIXABLE | disable autoBroadcastJoinThreshold | |
| shuffle_timeout | `shuffle.*timeout` | AUTO_FIXABLE | increase shuffle.io.timeout to 120s | |
| network_timeout | `spark.network.timeout` | AUTO_FIXABLE | increase network.timeout to 300s | |
| rpc_timeout | `RPC timeout` | AUTO_FIXABLE | increase rpc.timeout to 300s | |
| executor_lost_heartbeat | `Executor heartbeat timeout` | AUTO_FIXABLE | increase heartbeatInterval to 60s and network.timeout to 300s | |
| gc_overhead | `GC overhead limit exceeded` | AUTO_FIXABLE | increase executor memory to 8g and memoryOverhead to 2g | |
| container_killed_memory | `Container killed due to memory\|exceeding memory limits\|memory limits` | AUTO_FIXABLE | increase executor memory to 4g and memoryOverhead to 1g | |
| class_not_found | `ClassNotFoundException` | KNOWN_NEEDS_LLM | | Check missing class and required dependencies |
| no_class_def | `NoClassDefFoundError` | KNOWN_NEEDS_LLM | | Check class definition and dependency loading |
| jar_not_found | `jar not found\|could not find jar` | KNOWN_NEEDS_LLM | | Check jar path and upload to resource center |
| main_class_not_found | `Main class not found` | KNOWN_NEEDS_LLM | | Check Main Class name configuration |
| spark_version_mismatch | `Spark version mismatch` | KNOWN_NEEDS_LLM | | Check version compatibility |
| shuffle_failed | `FetchFailedException` | KNOWN_NEEDS_LLM | | Analyze Shuffle Service status and network issues |
| shuffle_connection | `shuffle.*connection failed` | KNOWN_NEEDS_LLM | | Check Shuffle Service availability |
| connection_refused | `Connection refused\|ConnectException` | KNOWN_NEEDS_LLM | | Check if target service is running |
| connection_timeout | `Connection timed out\|SocketTimeoutException` | KNOWN_NEEDS_LLM | | Check network status |
| driver_disconnected | `Driver disconnected\|Driver closed` | KNOWN_NEEDS_LLM | | Analyze Driver status |
| block_manager_lost | `BlockManager.*lost\|BlockManagerId.*lost` | KNOWN_NEEDS_LLM | | Check storage status |
| hdfs_not_found | `does not exist\|FileNotFound\|InvalidInputException.*path` | KNOWN_NEEDS_LLM | | Check input path exists |
| file_not_found | `FileNotFoundException\|file not found` | KNOWN_NEEDS_LLM | | Check file path |
| hdfs_permission | `Permission denied.*hdfs\|access denied` | KNOWN_NEEDS_LLM | | Check file permissions |
| schema_mismatch | `Schema mismatch\|cannot resolve` | KNOWN_NEEDS_LLM | | Analyze data structure |
| partition_not_found | `Partition not found\|partition.*does not exist` | KNOWN_NEEDS_LLM | | Check partition configuration |
| corrupt_data | `Corrupt block\|corrupt data` | KNOWN_NEEDS_LLM | | Check data files |
| null_value | `Null value\|NullPointerException` | KNOWN_NEEDS_LLM | | Analyze null value handling |
| datetime_parse | `DateTimeParseException\|cannot parse date` | KNOWN_NEEDS_LLM | | Check date format |
| spark_sql_error | `SparkSQLException\|AnalysisException` | KNOWN_NEEDS_LLM | | Analyze SQL syntax and semantics |
| job_aborted | `SparkException: Job aborted` | KNOWN_NEEDS_LLM | | Analyze specific abort reason |
| stage_failed | `Stage \d+ failed` | KNOWN_NEEDS_LLM | | Analyze failed Stage and reason |
| task_failed | `Task failed\|TaskSetManager.*failed` | KNOWN_NEEDS_LLM | | Analyze task failure reason |
| app_submission_failed | `Application submission failed` | KNOWN_NEEDS_LLM | | Check submission configuration |
| sql_syntax | `SQL syntax error\|parse exception` | KNOWN_NEEDS_LLM | | Analyze SQL syntax |
| sql_column_not_found | `Column.*not found\|cannot resolve column` | KNOWN_NEEDS_LLM | | Check column name |
| sql_table_not_found | `Table.*not found\|table does not exist` | KNOWN_NEEDS_LLM | | Check table name |
| container_killed | `Container killed by YARN\|Container killed` | KNOWN_NEEDS_LLM | | Analyze resource usage |
| executor_lost | `Executor lost` | KNOWN_NEEDS_LLM | | Analyze Executor status |
| executor_crash | `Executor crashed` | KNOWN_NEEDS_LLM | | Analyze crash reason |
| yarn_resource | `YARN.*resource.*insufficient` | KNOWN_NEEDS_LLM | | Check resource quota |
| yarn_container_exit | `Container.*exit.*code` | KNOWN_NEEDS_LLM | | Analyze exit reason |
| queue_full | `Queue.*full\|queue capacity` | KNOWN_NEEDS_LLM | | Check queue status |
| killed_by_user | `Killed by user` | KNOWN_NEEDS_LLM | | No auto fix needed |

## Categories

- **AUTO_FIXABLE**: Errors that can be automatically fixed by adjusting Spark configuration
- **KNOWN_NEEDS_LLM**: Errors that are recognized but require LLM analysis to determine the specific fix
- **UNKNOWN**: Errors that don't match any known pattern (not in this table)