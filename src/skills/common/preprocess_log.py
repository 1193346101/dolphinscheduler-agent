"""
Log preprocessing module for noise reduction

This module provides intelligent log preprocessing to extract key information
from Spark/Hadoop logs, replacing fixed line extraction with targeted extraction.
"""

import re
import json
from typing import Optional, Dict, List, Any


def extract_config_lines(log_content: str) -> List[str]:
    """
    Extract Spark/Hadoop configuration lines from log content.

    Identifies lines containing configuration keys like:
    - spark.*
    - hadoop.*
    - yarn.*
    - dfs.*

    Args:
        log_content: The raw log content to process

    Returns:
        List of configuration lines found in the log
    """
    if not log_content:
        return []

    config_patterns = [
        r'\bspark\.',       # spark.driver.memory, spark.executor.memory, etc.
        r'\bhadoop\.',      # hadoop.fs.defaultFS, etc.
        r'\byarn\.',        # yarn.resourcemanager.address, etc.
        r'\bdfs\.',         # dfs.replication, etc.
    ]

    config_lines = []
    lines = log_content.split('\n')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if line contains any config pattern
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
        r'\bCannot connect\b',              # Connection error
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

        if is_error_start:
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
    Preprocess log content to extract key information.

    This is the main entry point that performs all extractions:
    1. Extract configuration lines
    2. Extract error blocks
    3. Extract application ID
    4. Extract data metrics
    5. Extract OSS/HDFS paths (用于 ossutil 验证)

    Args:
        log_content: The raw log content to process
        task_type: Optional task type (e.g., 'spark', 'flink') for specialized processing

    Returns:
        Dictionary containing:
        - config_lines: List of configuration lines
        - error_blocks: List of error blocks
        - app_info: Dict containing app_id (Application ID or None)
        - data_metrics: Dictionary with input_bytes, shuffle_read_bytes,
                       shuffle_write_bytes, memory_spilled
        - resource_stats: List of resource statistics (empty for now)
        - oss_paths: List of OSS/HDFS paths found in log
    """
    return {
        "config_lines": extract_config_lines(log_content),
        "error_blocks": extract_error_blocks(log_content),
        "app_info": {"app_id": extract_app_id(log_content)},
        "data_metrics": _extract_spark_metrics(log_content),
        "resource_stats": [],
        "oss_paths": extract_oss_paths(log_content),
    }


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
]