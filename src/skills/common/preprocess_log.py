"""
Log preprocessing module for pattern-based extraction

根据任务类型匹配正则表达式，提取配置和错误信息。
"""

import re
import json
from typing import Optional, Dict, List, Any


def extract_config_lines(log_content: str, task_type: str = None) -> List[str]:
    """
    根据任务类型匹配正则表达式，提取配置行。

    支持的任务类型：
    - SPARK: spark-submit --conf, spark.executor.memory, JSON driverMemory
    - FLINK: flink.parallelism, taskmanager.memory
    - DATAX: speed.bytes, channel, reader/writer
    - SHELL/PYTHON: 脚本路径、参数
    - HTTP/API: url, timeout
    - SQL/HIVE: SQL语句、hive设置
    - SUB_PROCESS: 子工作流定义
    - DEPENDENT: 依赖配置

    Args:
        log_content: 日志内容
        task_type: 任务类型

    Returns:
        配置行列表
    """
    if not log_content:
        return []

    # Determine config patterns based on task type
    task_type_upper = (task_type or "").upper()

    config_patterns = []

    # ===== Spark Configuration =====
    if task_type_upper in ["SPARK", "SPARKSQL", "SPARK_APP"]:
        config_patterns.extend([
            # spark-submit command line
            r'--conf\s+spark\.\w+\s*=',        # --conf spark.executor.memory=4g
            r'spark-submit.*--conf',           # spark-submit command with --conf
            r'--executor-memory\s+\S+',        # --executor-memory 4G
            r'--driver-memory\s+\S+',          # --driver-memory 2G
            r'--num-executors\s+\S+',          # --num-executors 4
            r'--executor-cores\s+\S+',         # --executor-cores 2
            # JSON config format (DS task params)
            r'"executorMemory"\s*:',           # "executorMemory": "4G"
            r'"driverMemory"\s*:',             # "driverMemory": "2G"
            r'"executorCores"\s*:',            # "executorCores": 2
            r'"numExecutors"\s*:',             # "numExecutors": 4
            r'"driverCores"\s*:',              # "driverCores": 1
            r'"mainClass"\s*:',                # "mainClass": "com.example.Main"
            r'"appName"\s*:',                  # "appName": "MySparkApp"
            # Spark properties format
            r'spark\.\w+\s*=\s*\S+',           # spark.executor.memory=4g
            r'spark\.\w+\s*:\s*\S+',           # spark.executor.memory: 4g
        ])

    # ===== Flink Configuration =====
    elif task_type_upper in ["FLINK", "FLINK_SQL"]:
        config_patterns.extend([
            # Flink command line
            r'flink\s+run\s+',                 # flink run command
            r'-p\s+\d+',                       # -p 4 (parallelism)
            r'-yjm\s+\S+',                     # -yjm 1024 (jobManagerMemory)
            r'-ytm\s+\S+',                     # -ytm 4096 (taskManagerMemory)
            r'-yn\s+\d+',                      # -yn 2 (numberTaskManagers)
            r'-ys\s+\d+',                      # -ys 2 (slotsPerTaskManager)
            # Flink config keys (支持多级属性名如 taskmanager.memory.process.size)
            r'flink\.parallelism\s*[=:]',      # flink.parallelism: 4
            r'pipeline\.name\s*[=:]',          # pipeline.name: MyJob
            r'taskmanager\.memory\.[\w.]+\s*[=:]', # taskmanager.memory.process.size: 4096
            r'taskmanager\.[\w.]+\s*[=:]',      # taskmanager.* 通用
            r'state\.backend\s*[=:]',          # state.backend: rocksdb
            r'checkpoint\.[\w.]+\s*[=:]',      # checkpoint.interval: 60000
            # JSON config (DS Flink task)
            r'"jobManagerMemory"\s*:',        # "jobManagerMemory": "1024"
            r'"taskManagerMemory"\s*:',       # "taskManagerMemory": "4096"
            r'"parallelism"\s*:',             # "parallelism": 4
            r'"slots"\s*:',                   # "slots": 2
            r'"mainClass"\s*:',               # Flink main class
        ])

    # ===== DataX Configuration =====
    elif task_type_upper in ["DATAX", "DATAX_SYNC"]:
        config_patterns.extend([
            # DataX job config JSON
            r'"speed"\s*:',                    # "speed": {"bytes": -1, "records": 1000}
            r'"bytes"\s*:',                    # speed.bytes setting
            r'"records"\s*:',                  # speed.records setting
            r'"channel"\s*:',                  # "channel": 3
            r'"job"\s*:',                      # "job": {...}
            r'"content"\s*:',                  # "content": [reader/writer]
            r'"reader"\s*:',                   # "reader": {"name": "mysqlreader"}
            r'"writer"\s*:',                   # "writer": {"name": "hdfswriter"}
            # DataX parameters
            r'--job\s+',                       # --job /path/to/job.json
            r'--mode\s+',                      # --mode standalone
            # MySQL reader config
            r'"connection"\s*:',               # MySQL connection
            r'"jdbcUrl"\s*:',                  # jdbcUrl
            r'"querySql"\s*:',                 # querySql
            # HDFS writer config
            r'"path"\s*:',                     # HDFS path
            r'"fileName"\s*:',                 # fileName
            r'"fileFormat"\s*:',               # fileFormat
        ])

    # ===== Shell/Python Configuration =====
    elif task_type_upper in ["SHELL", "PYTHON", "PYTHON_SCRIPT"]:
        config_patterns.extend([
            # Script path/command
            r'^python\s+',                     # python /path/to/script.py
            r'^bash\s+',                       # bash /path/to/script.sh
            r'^sh\s+',                         # sh script.sh
            r'^\./\S+',                        # ./script.sh
            r'^/[\w/]+\.\w+',                  # /path/to/script.py (script path)
            # Script arguments
            r'--\w+\s+\S+',                    # --arg value
            r'-\w\s+\S+',                      # -a value
            # Python imports (detect libraries used)
            r'^import\s+\w+',                  # import pandas
            r'^from\s+\w+\s+import',           # from pyspark import SparkContext
            # Environment variables
            r'^export\s+\w+=',                 # export JAVA_HOME=/path
            r'^set\s+\w+=',                    # set VAR=value (Windows)
        ])

    # ===== HTTP/API Configuration =====
    elif task_type_upper in ["HTTP", "API", "REST"]:
        config_patterns.extend([
            # URL/endpoint
            r'https?://[^\s\'"]+',             # http://api.example.com
            r'"url"\s*:',                      # "url": "http://..."
            r'"endpoint"\s*:',                 # "endpoint": "/api/v1"
            # Timeout/retry
            r'"timeout"\s*:',                  # "timeout": 30
            r'"retry"\s*:',                    # "retry": 3
            r'"method"\s*:',                   # "method": "POST"
            # Headers
            r'"headers"\s*:',                  # headers config
        ])

    # ===== SQL Query Configuration =====
    elif task_type_upper in ["SQL", "HIVE", "HIVESQL"]:
        config_patterns.extend([
            # SQL statement markers
            r'^SELECT\s+',                     # SELECT ... FROM ...
            r'^INSERT\s+',                      # INSERT INTO ...
            r'^CREATE\s+',                      # CREATE TABLE ...
            r'^UPDATE\s+',                      # UPDATE ...
            r'^DELETE\s+',                      # DELETE FROM ...
            r'^DROP\s+',                        # DROP TABLE ...
            # Hive settings
            r'SET\s+hive\.\w+\s*=',            # SET hive.exec.parallel=true
            r'"database"\s*:',                 # "database": "default"
            r'"table"\s*:',                    # "table": "my_table"
        ])

    # ===== SUB_PROCESS Configuration =====
    elif task_type_upper in ["SUB_PROCESS", "SUBPROCESS"]:
        config_patterns.extend([
            # Sub workflow definition
            r'"workflowDefinitionCode"\s*:',   # "workflowDefinitionCode": 123456789
            r'"workflowDefinitionName"\s*:',   # "workflowDefinitionName": "child_workflow"
            r'"definitionCode"\s*:',           # "definitionCode": 123456789
            r'"definitionName"\s*:',           # "definitionName": "child_workflow"
            # Sub workflow instance info
            r'"subWorkflowInstanceId"\s*:',    # "subWorkflowInstanceId": 987654321
            r'"processInstanceId"\s*:',        # parent workflow instance
            # Worker group/tenant
            r'"workerGroup"\s*:',              # "workerGroup": "default"
            r'"tenantCode"\s*:',               # "tenantCode": "tenant1"
        ])

    # ===== DEPENDENT Configuration =====
    elif task_type_upper in ["DEPENDENT", "DEPENDENT_TASK"]:
        config_patterns.extend([
            # Dependent workflow/task definition
            r'"dependence"\s*:',               # "dependence": {...}
            r'"definitionCode"\s*:',           # "definitionCode": 123456789
            r'"taskDefinitionCode"\s*:',       # "taskDefinitionCode": 456789
            r'"relation"\s*:',                 # "relation": "AND" / "OR"
            r'"projectId"\s*:',                # "projectId": 1
            r'"depTaskCode"\s*:',              # "depTaskCode": 789012
            # Dependency condition
            r'"status"\s*:',                   # "status": "SUCCESS"
            r'"dateValue"\s*:',                # "dateValue": "today" / "last1Days"
            r'"cycle"\s*:',                    # "cycle": "day"
            r'"dayHours"\s*:',                 # "dayHours": "00:00"
        ])

    # ===== Default/Generic Configuration =====
    else:
        # When task_type unknown, use generic patterns for all types
        config_patterns.extend([
            # Generic spark
            r'--conf\s+spark\.\w+\s*=',
            r'"executorMemory"\s*:',
            r'"driverMemory"\s*:',
            # Generic Flink
            r'flink\.parallelism\s*[=:]',
            r'taskmanager\.memory\.\w+\s*[=:]',
            # Generic DataX
            r'"speed"\s*:',
            r'"channel"\s*:',
            # Generic Shell/Python
            r'^python\s+',
            r'^bash\s+',
            r'^import\s+\w+',
            # Generic HTTP
            r'"url"\s*:',
            r'"timeout"\s*:',
            # Generic Hadoop/YARN
            r'hadoop\.\w+\s*=',                # hadoop.fs.defaultFS=hdfs://
            r'yarn\.\w+\s*=',                  # yarn.resourcemanager.address=
        ])

    # Patterns to exclude (stack traces, error messages)
    exclude_patterns = [
        r'spark\.scheduler\.',             # spark.scheduler.DAGScheduler
        r'spark\.executor\.\w+Executor',   # spark.executor.Executor
        r'spark\.deploy\.',                # spark.deploy.yarn.Client
        r'spark\.sql\.\w+\$',              # spark.sql.DataFrame$$anon
        r'spark\.rdd\.',                   # spark.rdd.RDD
        r'flink\.runtime\.',               # flink.runtime.TaskExecutor
        r'flink\.execution\.',             # flink.execution.graph
        r'\.scala:\d+',                    # Scala file line reference
        r'\.\w+\(',                        # Method call pattern
        r'\bException\b',                  # Exception lines
        r'\bError\b',                      # Error lines (unless config)
    ]

    config_lines = []
    lines = log_content.split('\n')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip stack trace lines
        if re.search(r'\.\w+\(', stripped):
            continue
        if re.search(r'\.scala:\d+', stripped):
            continue

        # Skip exception/error lines (but keep config)
        if re.search(r'\bException\b', stripped) and 'spark-submit' not in stripped and 'flink run' not in stripped:
            continue
        if re.search(r'\bSparkException\b', stripped):
            continue
        if re.search(r'\bFlinkException\b', stripped):
            continue

        # Skip lines that match exclude patterns
        if any(re.search(p, stripped) for p in exclude_patterns):
            continue

        # Check if line contains actual config pattern
        for pattern in config_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                config_lines.append(stripped)
                break

    return config_lines


def extract_error_blocks(log_content: str) -> List[str]:
    """
    Extract complete error blocks from log content.

    Identifies error blocks starting with ERROR/FATAL/Exception markers
    and includes following stack trace lines and exception type lines.
    Supports:
    - Java exceptions (java.lang.*, org.apache.*, etc.)
    - Python traceback (Traceback + File + Error)
    - Shell errors (line X: syntax error, Permission denied, etc.)
    - DataX errors (ERROR + Exception)

    Args:
        log_content: The raw log content to process

    Returns:
        List of error blocks found in the log
    """
    if not log_content:
        return []

    # Patterns that start an error block
    error_start_patterns = [
        r'\bERROR\b',
        r'\bFATAL\b',
        r'\bException\b',
        r'^FetchFailedException',           # Spark shuffle fetch failed
        r'^Traceback \(most recent call last\)',  # Python traceback
        r'^java\.[a-z]+\.[A-Z]',           # Java exception at line start
        r'^org\.[a-z]+\.[A-Z]',             # org.apache.* exception
        r'^com\.[a-z]+\.[A-Z]',             # com.* exception
        r'^\w+Error:',                       # Python error: KeyError:, ValueError:, etc.
        r'^\w+Exception:',                   # Python/Java exception at line start
        r'^[A-Z][a-zA-Z]+Error',             # ModuleNotFoundError, IndexError
        # Shell error patterns
        r'/bin/bash:.*error',               # Shell syntax error
        r'\bPermission denied\b',           # Shell permission error
        r'\bConnection refused\b',          # Network connection error
        r'\bno space left\b',               # Disk full error
        r'\bCannot connect\b',              # Connection connection
        r'\bFailed to connect\b',           # curl/wget connection error
        r'\bCommunications link failure\b', # DataX/MySQL connection error
        # DataX/MySQL/Database error patterns
        r'\bDuplicate entry.*for key\b',    # MySQL duplicate key error
        r'\bAccess denied for user\b',      # MySQL authentication error
        r"\bTable.*doesn'?t exist\b",       # MySQL table not found (apostrophe optional)
        r'\bORA-\d+',                       # Oracle error code (ORA-12154, ORA-12514)
        # Spark/YARN error patterns
        r'\bContainer killed\b',             # YARN container killed
        r'\bPath.*does not exist\b',         # Spark/HDFS path not found
        # DolphinScheduler Worker failure patterns（需要非零退出码）
        r'process has exited.*exitStatusCode\s*[=:]\s*[1-9]',  # DS Worker 进程退出且失败
        r'\bexitStatusCode\s*[=:]\s*[1-9]',  # Non-zero exit code (failure)
        r'\bSend task execute status: FAILURE\b', # DS failure notification
        r'\bFinalize task instance\b.*FAILURE',       # DS task finalization with FAILURE
        # Additional Shell/Linux error patterns
        r'^ls:.*No such file',              # ls file not found
        r'^cat:.*No such file',             # cat file not found
        r'^rm:.*No such file',              # rm file not found
        r'^mkdir:.*cannot create',          # mkdir error
        r'^cp:.*cannot',                    # cp error
        r'^mv:.*cannot',                    # mv error
        r'^chmod:.*cannot',                 # chmod error
        r'^chown:.*cannot',                 # chown error
        r'^grep:.*',                        # grep error
        r'^find:.*',                        # find error
        r'^sed:.*',                         # sed error
        r'^awk:.*',                         # awk error
        r'^curl:.*',                        # curl error
        r'^wget:.*',                        # wget error
        r'^ssh:.*',                         # ssh error
        r'^scp:.*',                         # scp error
        r'^tar:.*',                         # tar error
        r'^unzip:.*',                       # unzip error
        r'^python:.*',                      # python command error
        r'^pip:.*',                         # pip error
        r'^docker:.*',                      # docker error
        r'^kubectl:.*',                     # kubectl error
        r'\bNo such file or directory\b',   # Generic file not found
        r'\bcommand not found\b',           # Command not found
        r'\bsyntax error\b',                # Generic syntax error
        r'\bsegmentation fault\b',          # Segfault
        r'\bcore dumped\b',                 # Core dump
    ]

    # Patterns that continue an error block
    continuation_patterns = [
        # Java stack trace
        r'^\s+at\s+',                    # at com.example.Class.method(File.java:10)
        r'^\s+\.\.\.\s+\d+\s+more',      # ... N more
        r'Caused by:',                    # Caused by: exception chain
        r'^\s+\[?:',                      # [CIRCULAR REFERENCE:]
        # Java exception continuation
        r'^The last packet',              # MySQL/DataX error continuation
        r'^\s+at java\.',                 # Java stack trace
        r'^\s+at org\.',                  # Apache stack trace
        # Python traceback
        r'^\s+File "',                   # Python: File "path", line N
        r'^\s+import\s+',                 # Python import line in traceback
        r'^\s+[A-Z][a-zA-Z]+Error:',      # Python error line continuation
        r'^During handling',              # Python exception handling
        # Shell continuation
        r'^\s+[a-zA-Z_]+:',               # Shell error continuation (script.sh:)
        # DataX/Database error continuation (critical lines after ERROR)
        r'^Duplicate entry',              # MySQL duplicate key
        r'^Access denied',                # MySQL access denied
        r'^Table.*doesn',                 # MySQL table not found
        r'^Connection refused',           # Connection error
        r'^Timeout',                      # Timeout error
        r'^Invalid',                      # Invalid value
        r'^Out of range',                 # Out of range
        r'^Data truncation',              # Data truncation
        r'^com\.mysql',                   # MySQL exception class
        r'^java\.\w+',                    # Java exception class continuation
        r'^org\.\w+',                     # Apache exception class
    ]

    error_blocks = []
    lines = log_content.split('\n')
    current_block = []
    in_error_block = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_error_block:
                # End block on empty line (for most cases)
                if current_block:
                    error_blocks.append('\n'.join(current_block))
                current_block = []
                in_error_block = False
            continue

        # 优先检查 Caused by（例外链延续），即使匹配 error_start 也作为延续处理
        is_caused_by = stripped.startswith('Caused by:') or re.search(r'^Caused by:', stripped)

        # Check if this line starts a new error block
        is_error_start = any(
            re.search(pattern, stripped, re.IGNORECASE)
            for pattern in error_start_patterns
        )

        # Check if this line continues a block
        is_continuation = any(
            re.search(pattern, stripped)
            for pattern in continuation_patterns
        )

        # Exception type line (java.lang.*, etc.) - should continue or start
        is_exception_type = re.match(r'^[a-z]+\.[a-z]+\.[A-Z]', stripped) or \
                           re.match(r'^[A-Z][a-zA-Z]+Error:', stripped) or \
                           re.match(r'^[A-Z][a-zA-Z]+Exception', stripped)

        # Caused by 优先作为延续（例外链），不开启新块
        if is_caused_by and in_error_block:
            current_block.append(line)
        elif is_error_start:
            # Save previous block if exists
            if current_block:
                error_blocks.append('\n'.join(current_block))
            # Start new block
            current_block = [line]
            in_error_block = True
        elif in_error_block and (is_continuation or is_exception_type):
            # Continue current block
            current_block.append(line)
        elif in_error_block and len(current_block) < 30:
            # Allow up to 30 lines per block for unknown continuation
            # Check if it looks like it could be related
            if stripped.startswith(('at', 'Caused', 'File', 'import', 'The', 'More', 'Error', 'Exception')):
                current_block.append(line)
            else:
                # End block
                if current_block:
                    error_blocks.append('\n'.join(current_block))
                current_block = []
                in_error_block = False

    # Don't forget the last block
    if current_block:
        error_blocks.append('\n'.join(current_block))

    return error_blocks


def extract_app_id(log_content: str) -> Optional[str]:
    """
    Extract Application ID from log content.

    Supports multiple formats:
    - application_1234567890_0001 (YARN standard format)
    - app-20240101-0001 (Spark standalone format)
    - application_1234567890 (partial format)

    Args:
        log_content: The raw log content to process

    Returns:
        The first Application ID found, or None if not found
    """
    if not log_content:
        return None

    patterns = [
        r'application_\d+_\d+',      # application_1234567890_0001
        r'app-\d+-\d+',              # app-20240101-0001
        r'application_\d+',          # application_1234567890 (partial)
    ]

    for pattern in patterns:
        match = re.search(pattern, log_content)
        if match:
            return match.group(0)

    return None


def _extract_spark_metrics(log_content: str) -> Dict[str, int]:
    """
    Extract data metrics from Spark Event Log JSON entries.

    Extracts and aggregates:
    - input_bytes: Total bytes read from input
    - shuffle_read_bytes: Total bytes read during shuffle
    - shuffle_write_bytes: Total bytes written during shuffle
    - memory_spilled: Total memory bytes spilled to disk

    Args:
        log_content: The raw log content to process (may contain JSON lines)

    Returns:
        Dictionary with aggregated metrics (zeros if not found)
    """
    metrics = {
        "input_bytes": 0,
        "shuffle_read_bytes": 0,
        "shuffle_write_bytes": 0,
        "memory_spilled": 0
    }

    if not log_content:
        return metrics

    # Find all JSON lines that look like Spark Event Log entries
    lines = log_content.split('\n')

    for line in lines:
        line = line.strip()
        if not line.startswith('{'):
            continue

        try:
            data = json.loads(line)

            # Only process task end events with metrics
            if data.get("Event") != "SparkListenerTaskEnd":
                continue

            task_metrics = data.get("Task Metrics", {})

            # Input metrics
            input_metrics = task_metrics.get("Input Metrics", {})
            metrics["input_bytes"] += input_metrics.get("Bytes Read", 0)

            # Shuffle read metrics
            shuffle_read = task_metrics.get("Shuffle Read Metrics", {})
            metrics["shuffle_read_bytes"] += shuffle_read.get("Remote Bytes Read", 0)

            # Shuffle write metrics
            shuffle_write = task_metrics.get("Shuffle Write Metrics", {})
            metrics["shuffle_write_bytes"] += shuffle_write.get("Shuffle Bytes Written", 0)

            # Memory spilled
            metrics["memory_spilled"] += task_metrics.get("Memory Bytes Spilled", 0)

        except json.JSONDecodeError:
            continue

    return metrics


def validate_extraction(original: str, extracted: Dict[str, Any]) -> bool:
    """
    Validate extraction completeness and quality.

    Checks:
    - Whether config lines were found
    - Whether error blocks were found
    - Whether app ID was found
    - Whether data metrics were found

    Args:
        original: The original log content
        extracted: Dictionary containing extraction results

    Returns:
        True if extraction is usable (at least one piece of useful info found),
        False otherwise
    """
    if not extracted:
        return False

    app_info = extracted.get("app_info", {})
    data_metrics = extracted.get("data_metrics", {})
    total_metrics = sum(data_metrics.values()) if data_metrics else 0

    # Extraction is valid if at least one piece of useful info was found
    return bool(
        extracted.get("config_lines") or
        extracted.get("error_blocks") or
        app_info.get("app_id") or
        total_metrics > 0
    )


def preprocess_log(log_content: str, task_type: str = None) -> Dict[str, Any]:
    """
    日志预处理：根据任务类型提取配置和错误信息。

    提取内容：
    - config_lines: 配置行（按 task_type 匹配正则）
    - error_blocks: 错误块（排序、去重、摘要）
    - warn_critical: 关键 WARN 信息（OOM 前兆等）
    - root_cause: 根本原因
    - app_info: Application ID
    - oss_paths: OSS/HDFS 路径
    - executor_events: Executor 生命周期事件
    - stage_timing: Stage 时间信息
    - join_strategies: Join 策略选择
    - broadcast_info: Broadcast 大小

    Args:
        log_content: 日志内容
        task_type: 任务类型（SPARK, FLINK, DATAX, SHELL 等）

    Returns:
        提取结果字典
    """
    # 使用改进的错误提取
    errors_summary = extract_errors_summary(log_content)

    return {
        "config_lines": extract_config_lines(log_content, task_type),
        # 改进后的错误提取
        "error_blocks": errors_summary["error_blocks"],
        "warn_critical": errors_summary["warn_critical"],
        "root_cause": errors_summary["root_cause"],
        "error_stats": {
            "raw_count": errors_summary["error_count"],
            "unique_count": errors_summary["unique_count"],
        },
        # 原有字段
        "app_info": {"app_id": extract_app_id(log_content)},
        "data_metrics": _extract_spark_metrics(log_content),
        "oss_paths": extract_oss_paths(log_content),
        # 深度分析字段
        "broadcast_info": extract_broadcast_info(log_content),
        "join_strategies": extract_join_strategy(log_content),
        "stage_timing": extract_stage_timing(log_content),
        "timestamp_analysis": analyze_log_timestamps(log_content),
        "executor_events": extract_executor_events(log_content),
    }


def fetch_real_spark_metrics(application_id: str) -> Dict[str, Any]:
    """
    按需获取 Spark 应用真实资源 metrics（只在资源类问题时调用）

    整合 YARN ResourceManager 和 Spark History Server 数据。

    Args:
        application_id: Spark 应用 ID

    Returns:
        综合 Metrics 字典，包含：
        - yarn_info: YARN ResourceManager 信息
        - spark_metrics: Spark History Server metrics
        - current_config: 当前 Spark 配置（映射到 DolphinScheduler UI）
        - data_metrics: 数据量 metrics（用于资源计算）
    """
    result = {
        "yarn_info": {},
        "spark_metrics": {},
        "current_config": {},
        "data_metrics": {},
    }

    if not application_id:
        return result

    try:
        from pathlib import Path
        import importlib.util

        # 动态导入 resource_metrics
        metrics_path = Path(__file__).parent.parent / "spark" / "scripts" / "resource_metrics.py"
        if metrics_path.exists():
            spec = importlib.util.spec_from_file_location("resource_metrics", metrics_path)
            metrics_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(metrics_module)

            # 获取综合 metrics
            comprehensive = metrics_module.get_comprehensive_metrics(application_id)

            # 合并到结果
            if comprehensive.get("yarn_info"):
                result["yarn_info"] = comprehensive["yarn_info"]

            if comprehensive.get("spark_metrics"):
                result["spark_metrics"] = comprehensive["spark_metrics"]

            if comprehensive.get("current_config"):
                result["current_config"] = comprehensive["current_config"]

            if comprehensive.get("data_metrics"):
                result["data_metrics"] = comprehensive["data_metrics"]

    except Exception as e:
        print(f"[fetch_real_spark_metrics] Failed: {e}", file=__import__('sys').stderr)

    return result


def extract_oss_paths(log_content: str) -> List[str]:
    """
    Extract OSS/HDFS paths from log content.

    匹配多种路径格式：
    - oss://bucket/path/file.parquet
    - hdfs://namenode/path/file
    - /user/hive/warehouse/table/partition=xxx
    - file:///path/to/file

    Args:
        log_content: The raw log content to process

    Returns:
        List of paths found in log (最多 5 个)
    """
    if not log_content:
        return []

    paths = []

    # OSS 路径: oss://bucket/path
    oss_pattern = r'oss://[a-zA-Z0-9\-_.]+(?:/[a-zA-Z0-9\-_.//]+)?'
    for match in re.finditer(oss_pattern, log_content):
        paths.append(match.group(0))

    # HDFS 路径: hdfs://namenode/path 或 hdfs:///path
    hdfs_pattern = r'hdfs://(?:[a-zA-Z0-9\-_.:]+)?(?:/[a-zA-Z0-9\-_.//]+)?'
    for match in re.finditer(hdfs_pattern, log_content):
        path = match.group(0)
        if path not in paths:
            paths.append(path)

    # 本地/HDFS 路径（无协议）: /user/hive/warehouse/xxx 或 /path/to/file
    # 只匹配看起来像数据路径的（包含 warehouse、data、partition 等）
    local_path_pattern = r'/(?:user|data|warehouse|hive|tmp|output)[/[a-zA-Z0-9\-_.=/]+'
    for match in re.finditer(local_path_pattern, log_content):
        path = match.group(0)
        if path not in paths and len(path) > 10:  # 避免太短的路径
            paths.append(path)

    # 带分区的路径: partition=xxx 或 /dt=xxx/
    partition_pattern = r'[a-zA-Z_]+=[a-zA-Z0-9\-_.]+'
    partition_matches = re.findall(partition_pattern, log_content)
    # 如果找到分区，尝试构建完整路径
    if partition_matches:
        # 在分区前面找可能的父路径
        for part in partition_matches[:3]:
            # 找包含这个分区的路径
            part_pattern = rf'[^\s\'"]*{re.escape(part)}[^\s\'"]*'
            for match in re.finditer(part_pattern, log_content):
                path = match.group(0).strip()
                if path.startswith('/') or path.startswith('oss://') or path.startswith('hdfs://'):
                    if path not in paths:
                        paths.append(path)

    # 去重并限制数量
    unique_paths = list(set(paths))
    # 按长度排序，优先保留完整路径
    unique_paths.sort(key=lambda x: len(x), reverse=True)

    return unique_paths[:5]


__all__ = [
    "extract_config_lines",
    "extract_error_blocks",
    "extract_app_id",
    "validate_extraction",
    "preprocess_log",
    "extract_oss_paths",
    "fetch_real_spark_metrics",
    # 深度分析函数
    "extract_broadcast_info",
    "extract_join_strategy",
    "extract_stage_timing",
    "analyze_log_timestamps",
    "extract_executor_events",
    "fetch_historical_logs",
    # 错误提取改进函数
    "extract_warn_critical",
    "extract_exception_type",
    "deduplicate_errors",
    "rank_error_blocks",
    "summarize_error_block",
    "extract_root_cause",
    "extract_errors_summary",
]


# ============================================================================
# 深度分析新增函数
# ============================================================================

def extract_broadcast_info(log_content: str) -> Dict[str, Any]:
    """
    提取 Broadcast 信息

    从 Driver 日志提取广播变量的大小信息，用于分析广播超时原因。

    支持的日志格式：
    - BroadcastExchange: broadcast size = 256.0 MB
    - broadcast size exceeds threshold (10485760 bytes)
    - Build relation size: 15.2 MB

    Args:
        log_content: Driver 日志内容

    Returns:
        {
            broadcast_size_mb: 广播数据量（MB）
            exceeds_threshold: 是否超阈值
            threshold_bytes: 阈值设置
            broadcast_tables: 广播的表名列表
        }
    """
    result = {
        "broadcast_size_mb": 0,
        "exceeds_threshold": False,
        "threshold_bytes": 0,
        "broadcast_tables": [],
        "broadcast_events": [],
    }

    if not log_content:
        return result

    # Broadcast size 信息
    broadcast_size_pattern = r'BroadcastExchange.*broadcast size\s*[=:]\s*([\d.]+)\s*(MB|KB|bytes)?'
    for match in re.finditer(broadcast_size_pattern, log_content, re.IGNORECASE):
        size_value = float(match.group(1))
        unit = match.group(2) or "bytes"

        # 转换为 MB
        if unit.lower() == "kb":
            size_mb = size_value / 1024
        elif unit.lower() == "bytes":
            size_mb = size_value / (1024 * 1024)
        else:
            size_mb = size_value

        result["broadcast_size_mb"] = max(result["broadcast_size_mb"], size_mb)
        result["broadcast_events"].append({
            "size_mb": size_mb,
            "line": match.group(0)[:100],
        })

    # 超阈值警告
    exceeds_pattern = r'broadcast.*exceeds threshold.*\(?(\d+)\s*bytes\)?'
    match = re.search(exceeds_pattern, log_content, re.IGNORECASE)
    if match:
        result["exceeds_threshold"] = True
        result["threshold_bytes"] = int(match.group(1))

    # Build relation size（BroadcastHashJoin 的广播表大小）
    relation_pattern = r'Build relation size\s*[=:]\s*([\d.]+)\s*(MB|KB|GB)?'
    for match in re.finditer(relation_pattern, log_content, re.IGNORECASE):
        size_value = float(match.group(1))
        unit = match.group(2) or "bytes"

        if unit.lower() == "kb":
            size_mb = size_value / 1024
        elif unit.lower() == "gb":
            size_mb = size_value * 1024
        elif unit.lower() == "mb":
            size_mb = size_value
        else:
            size_mb = size_value / (1024 * 1024)

        result["broadcast_size_mb"] = max(result["broadcast_size_mb"], size_mb)

    # 广播表名提取
    table_pattern = r'BroadcastHashJoin.*\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*){0,2})\b'
    for match in re.finditer(table_pattern, log_content, re.IGNORECASE):
        table_name = match.group(1)
        if table_name not in result["broadcast_tables"]:
            result["broadcast_tables"].append(table_name)

    return result


def extract_join_strategy(log_content: str) -> List[Dict[str, Any]]:
    """
    提取 Join Strategy 选择信息

    从 Driver 日志提取 Spark 选择的 Join 策略，用于分析执行计划变化。

    支持的日志格式：
    - Choosing join strategy: BroadcastHashJoin (build = left)
    - Choosing join strategy: SortMergeJoin
    - Choosing join strategy: ShuffleHashJoin

    Args:
        log_content: Driver 日志内容

    Returns:
        [{strategy, build_side, line}] 列表
    """
    strategies = []

    if not log_content:
        return strategies

    # Join Strategy 选择
    join_pattern = r'Choosing join strategy\s*[=:]\s*(BroadcastHashJoin|SortMergeJoin|ShuffleHashJoin|CartesianProduct)\s*(?:\(build\s*[=:]\s*(left|right)\))?'

    for match in re.finditer(join_pattern, log_content, re.IGNORECASE):
        strategy_info = {
            "strategy": match.group(1),
            "build_side": match.group(2) if match.group(2) else "unknown",
            "line": match.group(0),
        }
        strategies.append(strategy_info)

    # 如果没找到 Choosing join strategy，尝试从执行计划推断
    if not strategies:
        # BroadcastHashJoin 标识
        bhj_pattern = r'\bBroadcastHashJoin\b'
        if re.search(bhj_pattern, log_content):
            strategies.append({
                "strategy": "BroadcastHashJoin",
                "build_side": "unknown",
                "line": "推断：日志中包含 BroadcastHashJoin",
            })

        # SortMergeJoin 标识
        smj_pattern = r'\bSortMergeJoin\b'
        if re.search(smj_pattern, log_content):
            strategies.append({
                "strategy": "SortMergeJoin",
                "build_side": "unknown",
                "line": "推断：日志中包含 SortMergeJoin",
            })

    return strategies


def extract_stage_timing(log_content: str) -> List[Dict[str, Any]]:
    """
    提取 Stage 开始/结束时间和执行时长

    从 Driver 日志提取 Stage 时间信息，用于性能分析和历史对比。

    支持的日志格式：
    - Stage 0 started: 2024-01-01 10:00:00
    - Stage 0 finished: 2024-01-01 10:05:00
    - Stage 0 completed: 2024-01-01 10:05:00, duration: 5min
    - Stage 15 failed: Task 0 failed 4 times

    Args:
        log_content: Driver 日志内容

    Returns:
        [{stage_id, start_time, end_time, duration_seconds, status}] 列表
    """
    stages = {}

    if not log_content:
        return []

    # Stage 开始
    started_pattern = r'Stage\s+(\d+)\s+started\s*[=:]\s*([\d\-:]+\s+[\d:]+|[\d]+ms)'
    for match in re.finditer(started_pattern, log_content, re.IGNORECASE):
        stage_id = int(match.group(1))
        time_str = match.group(2)

        if stage_id not in stages:
            stages[stage_id] = {"stage_id": stage_id}
        stages[stage_id]["start_time"] = time_str
        stages[stage_id]["status"] = "running"

    # Stage 完成（带时长）
    completed_pattern = r'Stage\s+(\d+)\s+(?:completed|finished)\s*[=:]\s*([\d\-:]+\s+[\d:]+),?\s*(?:duration\s*[=:]\s*)?([\d]+)\s*(ms|s|min|h)?'
    for match in re.finditer(completed_pattern, log_content, re.IGNORECASE):
        stage_id = int(match.group(1))
        time_str = match.group(2)
        duration_value = int(match.group(3))
        duration_unit = match.group(4) or "ms"

        # 转换为秒
        if duration_unit.lower() == "min":
            duration_seconds = duration_value * 60
        elif duration_unit.lower() == "h":
            duration_seconds = duration_value * 3600
        elif duration_unit.lower() == "s":
            duration_seconds = duration_value
        else:
            duration_seconds = duration_value / 1000

        if stage_id not in stages:
            stages[stage_id] = {"stage_id": stage_id}
        stages[stage_id]["end_time"] = time_str
        stages[stage_id]["duration_seconds"] = duration_seconds
        stages[stage_id]["status"] = "completed"

    # Stage 失败
    failed_pattern = r'Stage\s+(\d+)\s+failed\s*[,:]\s*(.*)'
    for match in re.finditer(failed_pattern, log_content, re.IGNORECASE):
        stage_id = int(match.group(1))
        reason = match.group(2)[:100]  # 截取原因

        if stage_id not in stages:
            stages[stage_id] = {"stage_id": stage_id}
        stages[stage_id]["status"] = "failed"
        stages[stage_id]["failure_reason"] = reason

    # 简化格式：Stage X finished in Y ms
    simple_pattern = r'Stage\s+(\d+)\s+finished\s+in\s+([\d]+)\s*ms'
    for match in re.finditer(simple_pattern, log_content, re.IGNORECASE):
        stage_id = int(match.group(1))
        duration_ms = int(match.group(2))

        if stage_id not in stages:
            stages[stage_id] = {"stage_id": stage_id}
        stages[stage_id]["duration_seconds"] = duration_ms / 1000
        stages[stage_id]["status"] = "completed"

    return list(stages.values())


def analyze_log_timestamps(log_content: str) -> Dict[str, Any]:
    """
    分析日志时间戳，检测长时间无输出

    用于检测任务"卡住"不报错的情况。

    支持的时间戳格式：
    - 2024-01-01 10:00:00 INFO ...
    - 2024/01/01 10:00:00,000 INFO ...
    - 10:00:00 INFO ...

    Args:
        log_content: Driver 日志内容

    Returns:
        {
            first_timestamp: 第一条日志时间
            last_timestamp: 最后一条日志时间
            log_count: 日志行数
            silent_periods: 无输出时段 [{start, end, duration_minutes}]
            max_gap_minutes: 最大时间间隔
            has_progress: 是否有持续输出
        }
    """
    result = {
        "first_timestamp": None,
        "last_timestamp": None,
        "log_count": 0,
        "silent_periods": [],
        "max_gap_minutes": 0,
        "has_progress": True,
    }

    if not log_content:
        return result

    timestamps = []
    lines = log_content.split('\n')

    # 时间戳格式
    timestamp_patterns = [
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',  # 2024-01-01 10:00:00
        r'^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',  # 2024/01/01 10:00:00
        r'^(\d{2}:\d{2}:\d{2})',  # 10:00:00（只有时分秒）
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        result["log_count"] += 1

        # 尝试提取时间戳
        for pattern in timestamp_patterns:
            match = re.match(pattern, stripped)
            if match:
                timestamps.append(match.group(1))
                break

    if not timestamps:
        return result

    result["first_timestamp"] = timestamps[0]
    result["last_timestamp"] = timestamps[-1]

    # 计算时间间隔（只有时分秒时无法跨天计算，跳过）
    if len(timestamps) >= 2:
        try:
            # 尝试解析完整时间戳
            from datetime import datetime

            parsed_times = []
            for ts in timestamps:
                try:
                    if '-' in ts:  # 2024-01-01 10:00:00
                        parsed_times.append(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"))
                    elif '/' in ts:  # 2024/01/01 10:00:00
                        parsed_times.append(datetime.strptime(ts, "%Y/%m/%d %H:%M:%S"))
                    else:  # 只有 10:00:00，无法跨天计算
                        continue
                except ValueError:
                    continue

            if len(parsed_times) >= 2:
                gaps = []
                for i in range(1, len(parsed_times)):
                    gap_minutes = (parsed_times[i] - parsed_times[i-1]).total_seconds() / 60

                    # 大于 5 分钟视为无输出时段
                    if gap_minutes > 5:
                        gaps.append({
                            "start": str(parsed_times[i-1]),
                            "end": str(parsed_times[i]),
                            "duration_minutes": gap_minutes,
                        })
                        result["max_gap_minutes"] = max(result["max_gap_minutes"], gap_minutes)

                result["silent_periods"] = gaps

                # 如果有大于 10 分钟的无输出时段，视为无进展
                if result["max_gap_minutes"] > 10:
                    result["has_progress"] = False

        except Exception:
            pass

    return result


def extract_executor_events(log_content: str) -> List[Dict[str, Any]]:
    """
    提取 Executor 添加/移除事件

    从 Driver 日志提取 Executor 生命周期事件，用于分析 Executor 丢失原因。

    支持的日志格式：
    - Added executor 1 on host1 with 4 cores
    - Removed executor 1: reason = heartbeat timeout
    - Executor 1 lost (removed by driver)

    Args:
        log_content: Driver 日志内容

    Returns:
        [{executor_id, event_type, timestamp, reason, host}] 列表
    """
    events = []

    if not log_content:
        return events

    # Executor 添加
    added_pattern = r'Added executor\s+(\d+)\s+on\s+(\S+)\s+with\s+(\d+)\s+cores'
    for match in re.finditer(added_pattern, log_content, re.IGNORECASE):
        events.append({
            "executor_id": int(match.group(1)),
            "event_type": "added",
            "host": match.group(2),
            "cores": int(match.group(3)),
            "reason": None,
        })

    # Executor 移除（带原因）
    removed_pattern = r'Removed executor\s+(\d+)[\s:]+(?:reason\s*[=:]\s*)?(\S+[^)]*)'
    for match in re.finditer(removed_pattern, log_content, re.IGNORECASE):
        reason = match.group(2).strip()
        if reason.endswith(')'):
            reason = reason[:-1]

        events.append({
            "executor_id": int(match.group(1)),
            "event_type": "removed",
            "host": None,
            "reason": reason,
        })

    # Executor lost
    lost_pattern = r'Executor\s+(\d+)\s+lost(?:\s+\(removed by driver\))?'
    for match in re.finditer(lost_pattern, log_content, re.IGNORECASE):
        events.append({
            "executor_id": int(match.group(1)),
            "event_type": "lost",
            "host": None,
            "reason": "executor_lost",
        })

    # Executor heartbeat timeout
    heartbeat_pattern = r'Executor\s+(\d+)\s+heartbeat timeout'
    for match in re.finditer(heartbeat_pattern, log_content, re.IGNORECASE):
        events.append({
            "executor_id": int(match.group(1)),
            "event_type": "heartbeat_timeout",
            "host": None,
            "reason": "heartbeat_timeout",
        })

    return events


def fetch_historical_logs(
    project_name: str,
    workflow_code: str,
    task_code: str,
    days: int = 7,
    client: Any = None,
) -> Dict[str, Any]:
    """
    按需拉取历史一周的成功日志，用于数据漂移和性能对比

    流程:
    1. 查询 DolphinScheduler 实例 API 获取最近 days 天的成功实例
    2. 过滤 workflow_code + task_code
    3. 按需调用 dsctl get_task_logs 拉取日志
    4. 解析 metrics 建立基线

    Args:
        project_name: 项目名称
        workflow_code: 工作流编码
        task_code: 任务编码
        days: 查询天数（默认 7 天）
        client: DSCLIClient 实例（如果已创建）

    Returns:
        {
            instances: [{instance_id, date, metrics}] 列表
            baseline_avg: 各指标的平均值
            baseline_std: 各指标的标准差
            success_count: 成功实例数量
            fetched_count: 实际拉取日志的数量
        }
    """
    result = {
        "instances": [],
        "baseline_avg": {},
        "baseline_std": {},
        "success_count": 0,
        "fetched_count": 0,
        "error": None,
    }

    try:
        # 动态导入 DSCLIClient
        from pathlib import Path
        import importlib.util

        if client is None:
            client_path = Path(__file__).parent.parent.parent / "integrations" / "dsctl_wrapper.py"
            spec = importlib.util.spec_from_file_location("dsctl_wrapper", client_path)
            client_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(client_module)

            from ...config.settings import settings
            client = client_module.DSCLIClient(
                api_url=settings.DS_API_URL,
                api_token=settings.DS_API_TOKEN,
            )

        # 1. 查询实例列表（最近 days 天）
        # 注意：list_workflow_instances 可能需要 project_code
        # 这里先用 workflow_code 查询

        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 获取实例列表
        instances_result = client.list_workflow_instances(
            workflow_code=int(workflow_code),
            state="SUCCESS",  # 只查成功实例
            page_size=50,
        )

        if not instances_result.success:
            result["error"] = instances_result.stderr
            return result

        # 解析实例列表
        instances_data = instances_result.stdout
        if isinstance(instances_data, str):
            import json as json_module
            try:
                instances_data = json_module.loads(instances_data)
            except json_module.JSONDecodeError:
                result["error"] = "无法解析实例列表"
                return result

        # 提取成功实例
        success_instances = []
        if isinstance(instances_data, list):
            for inst in instances_data:
                state = inst.get("state", "")
                if state in ["SUCCESS", "成功"]:
                    success_instances.append(inst)
        elif isinstance(instances_data, dict):
            # 可能是 {totalList: [...]}
            total_list = instances_data.get("totalList", [])
            for inst in total_list:
                state = inst.get("state", "")
                if state in ["SUCCESS", "成功"]:
                    success_instances.append(inst)

        result["success_count"] = len(success_instances)

        # 2. 按需拉取日志（最多 5 个实例）
        metrics_list = []
        fetched_count = 0

        for inst in success_instances[:5]:
            instance_id = inst.get("id") or inst.get("processInstanceId")
            if not instance_id:
                continue

            # 拉取任务日志
            logs_result = client.get_task_logs(
                task_instance_id=int(instance_id),
                limit=5000,  # 只拉取前 5000 行
            )

            if logs_result.success:
                log_content = logs_result.stdout
                if isinstance(log_content, str):
                    # 解析 metrics
                    metrics = _extract_spark_metrics(log_content)
                    metrics["instance_id"] = instance_id
                    metrics["date"] = inst.get("startTime", "")[:10]  # YYYY-MM-DD

                    metrics_list.append(metrics)
                    fetched_count += 1

        result["fetched_count"] = fetched_count

        # 3. 计算基线
        if metrics_list:
            # 计算平均值
            metric_keys = ["input_bytes", "shuffle_read_bytes", "shuffle_write_bytes", "memory_spilled"]

            for key in metric_keys:
                values = [m.get(key, 0) for m in metrics_list if m.get(key, 0) > 0]
                if values:
                    avg = sum(values) / len(values)
                    result["baseline_avg"][key] = avg

                    # 计算标准差
                    if len(values) > 1:
                        variance = sum((v - avg) ** 2 for v in values) / len(values)
                        result["baseline_std"][key] = variance ** 0.5

            result["instances"] = metrics_list

    except Exception as e:
        result["error"] = str(e)

    return result


# ============================================================================
# 错误提取改进函数
# ============================================================================

# WARN 级别但关键的模式（OOM 前兆、资源问题等）
WARN_CRITICAL_PATTERNS = [
    r'GC overhead limit exceeded',           # GC 警告（OOM 前兆）
    r'GC pause.*exceeds',                    # GC 停顿过长
    r'Shuffle fetch failed.*retry',          # Shuffle 重试
    r'Executor lost.*heartbeat',             # Executor 丢失
    r'Memory pressure detected',             # 内存压力
    r'Low memory',                           # 低内存警告
    r'Slow task detected',                   # 慢任务
    r'Skew detected',                        # 数据倾斜
    r'Connection.*retry',                    # 连接重试
    r'Retrying.*connection',                 # 重试连接
    r'Retry.*attempt.*failed',               # 重试失败
    r'Remote shuffle server unavailable',    # Shuffle 服务不可用
    r'Container memory limit exceeded',      # 容器内存超限警告
    r'BlockManager heartbeat timeout',       # BlockManager 超时
    r'Checkpoint timeout',                   # Flink checkpoint 超时
    r'Task execution timeout',               # DS 任务执行超时
    r'Task timeout',                         # 任务超时
    r'execution time exceeds',               # 执行时间超限
    r'Heartbeat timeout',                    # 心跳超时
    r'Job stuck',                            # 任务卡住
]

# 错误优先级关键词（分数越高优先级越高）
ERROR_PRIORITY_KEYWORDS = [
    ("OutOfMemoryError", 10),          # OOM 最高优先级
    ("GC overhead limit exceeded", 10),
    ("Memory limit exceeded", 9),
    ("Container killed", 9),           # 容器被杀
    ("Executor lost", 8),
    ("heartbeat timeout", 8),
    ("FetchFailedException", 8),       # Shuffle 失败
    ("SparkException: Job aborted", 7),
    ("Job aborted", 7),
    ("Task failed", 6),
    ("Stage failed", 6),
    ("Communications link failure", 6), # 数据库连接失败
    ("Access denied", 5),
    ("Permission denied", 5),
    ("Duplicate entry", 5),
    ("process has exited", 5),         # DS Worker 进程退出
    ("exitStatusCode", 5),             # DS 非零退出码
    ("Exception", 4),                  # 通用异常
    ("Error", 3),                      # 通用错误
    ("FATAL", 2),
    ("ERROR", 1),
]


def extract_warn_critical(log_content: str) -> List[str]:
    """
    提取 WARN 级别但关键的信息（OOM 前兆、资源问题）

    这些信息虽然不是 ERROR，但对诊断很重要。

    Args:
        log_content: 日志内容

    Returns:
        关键 WARN 信息列表
    """
    if not log_content:
        return []

    warn_criticals = []
    lines = log_content.split('\n')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 检查是否匹配关键 WARN 模式
        for pattern in WARN_CRITICAL_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                warn_criticals.append(stripped)
                break

    return warn_criticals


def extract_exception_type(block: str) -> str:
    """
    提取错误块的异常类型（用于去重）

    Args:
        block: 错误块

    Returns:
        异常类型字符串
    """
    # Java: java.lang.OutOfMemoryError, org.apache.spark.SparkException
    match = re.search(r'(java|org|com)\.[a-z]+\.[A-Z][a-zA-Z]*(?:Exception|Error)?', block)
    if match:
        return match.group(0)

    # Python: FileNotFoundError, ModuleNotFoundError
    match = re.search(r'[A-Z][a-zA-Z]+Error', block)
    if match:
        return match.group(0)

    # Shell/通用: Permission denied, Connection refused
    match = re.search(r'(Permission denied|Connection refused|No such file|command not found)', block, re.IGNORECASE)
    if match:
        return match.group(0).lower()

    # DS Worker: process has exited, exitStatusCode
    match = re.search(r'(process has exited|exitStatusCode)', block, re.IGNORECASE)
    if match:
        return match.group(0).lower()

    return "unknown"


def deduplicate_errors(error_blocks: List[str]) -> List[str]:
    """
    同类错误只保留第一个（去重）

    Args:
        error_blocks: 错误块列表

    Returns:
        去重后的错误块列表
    """
    if not error_blocks:
        return []

    seen_types = set()
    unique_blocks = []

    for block in error_blocks:
        exception_type = extract_exception_type(block)
        if exception_type not in seen_types:
            seen_types.add(exception_type)
            unique_blocks.append(block)

    return unique_blocks


def rank_error_blocks(error_blocks: List[str]) -> List[str]:
    """
    按严重程度排序错误块（root cause 排在前面）

    检查完整错误块（包括 Caused by），而不是只检查第一行。

    Args:
        error_blocks: 错误块列表

    Returns:
        排序后的错误块列表
    """
    if not error_blocks:
        return []

    ranked = []
    for block in error_blocks:
        score = 0
        # 检查完整错误块（包括 Caused by）
        for keyword, weight in ERROR_PRIORITY_KEYWORDS:
            if keyword.lower() in block.lower():
                score = max(score, weight)
        ranked.append((score, block))

    # 按分数降序排序
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [block for score, block in ranked]


def summarize_error_block(block: str, max_lines: int = 10) -> str:
    """
    错误块摘要：只保留关键行

    保留：
    - 第一行（错误描述）
    - 所有 Caused by 行（完整异常链）
    - 最多 max_lines 行

    Args:
        block: 错误块
        max_lines: 最大行数

    Returns:
        摘要后的错误块
    """
    lines = block.strip().split('\n')
    if len(lines) <= max_lines:
        return block

    summary_lines = [lines[0]]  # 第一行

    # 查找所有关键行
    for line in lines[1:]:
        stripped = line.strip()
        # 所有 Caused by 行都保留（root cause 在最后一个）
        if stripped.startswith('Caused by:'):
            summary_lines.append(stripped)
        # 异常类型行（独立一行）
        elif re.match(r'^[a-z]+\.[a-z]+\.[A-Z]', stripped) or re.match(r'^[A-Z][a-zA-Z]+Error', stripped):
            if len(summary_lines) < max_lines:
                summary_lines.append(stripped)

    return '\n'.join(summary_lines)


def extract_root_cause(error_blocks: List[str]) -> str:
    """
    从错误块提取根本原因（root cause）

    优先级：
    1. 最后一个 Caused by（Java 异常链的 root cause）
    2. 第一个高优先级错误块的第一行

    Args:
        error_blocks: 错误块列表（已排序）

    Returns:
        Root cause 字符串
    """
    if not error_blocks:
        return ""

    # 从已排序的第一个（最高优先级）错误块找 Caused by
    first_block = error_blocks[0]

    # 找所有 Caused by，最后一个是最根本原因
    caused_by_matches = re.findall(r'Caused by:\s*(.+)', first_block)
    if caused_by_matches:
        # 直接返回最后一个 Caused by（真正的 root cause）
        # 不再检查中间层级，因为最后一个才是最根本的原因
        return caused_by_matches[-1].strip()

    # 没有 Caused by，返回第一行
    lines = first_block.strip().split('\n')
    return lines[0] if lines else ""


def extract_errors_summary(log_content: str, max_blocks: int = 10) -> Dict[str, Any]:
    """
    综合错误提取（整合所有改进）

    流程：
    1. 提取所有 ERROR/FATAL 错误块
    2. 提取关键 WARN 信息
    3. 去重
    4. 按优先级排序
    5. 摘要（限制行数）
    6. 提取 root cause

    Args:
        log_content: 日志内容
        max_blocks: 最大返回错误块数量

    Returns:
        {
            error_blocks: 排序去重后的错误块列表
            warn_critical: 关键 WARN 信息
            root_cause: 根本原因
            error_count: 原始错误块数量
            unique_count: 去重后数量
        }
    """
    # 1. 提取原始错误块
    raw_errors = extract_error_blocks(log_content)

    # 2. 提取关键 WARN
    warn_critical = extract_warn_critical(log_content)

    # 3. 去重
    unique_errors = deduplicate_errors(raw_errors)

    # 4. 排序
    ranked_errors = rank_error_blocks(unique_errors)

    # 5. 摘要 + 限制数量
    summarized_errors = [summarize_error_block(block) for block in ranked_errors[:max_blocks]]

    # 6. 提取 root cause
    root_cause = extract_root_cause(ranked_errors)

    return {
        "error_blocks": summarized_errors,
        "warn_critical": warn_critical,
        "root_cause": root_cause,
        "error_count": len(raw_errors),
        "unique_count": len(unique_errors),
    }