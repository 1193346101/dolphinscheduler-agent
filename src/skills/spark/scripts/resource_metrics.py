"""
Spark 资源 Metrics 获取工具

整合 YARN ResourceManager 和 Spark History Server 数据，
为 Skill 分析提供真实资源使用信息。

数据来源：
1. YARN ResourceManager API - 获取容器资源使用、诊断信息
2. Spark History Server API - 获取 Executor metrics、内存溢出、Shuffle 数据量

DolphinScheduler 支持的资源参数：
- Driver核心数、Driver内存数
- Executor数量、Executor内存数、Executor核心数
"""

import re
import json
import requests
from typing import Dict, Any, Optional
from pathlib import Path

# 动态导入配置
_settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.py"


def _get_settings():
    """获取配置实例"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("settings", _settings_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.settings


def fetch_yarn_app_info(application_id: str) -> Dict[str, Any]:
    """
    从 YARN ResourceManager 获取应用资源信息

    Args:
        application_id: YARN 应用 ID (如 application_1234567890_0001)

    Returns:
        资源信息字典：
        - allocated_vcores: 分配的虚拟核心数
        - allocated_memory_mb: 分配的内存（MB）
        - running_containers: 运行中的容器数
        - diagnostics: 诊断信息（错误原因）
        - state: 应用状态
        - elapsed_time: 运行时长（ms）
    """
    settings = _get_settings()

    if not settings.YARN_RM_URL:
        return {}

    # YARN API URL
    url = f"{settings.YARN_RM_URL}/ws/v1/cluster/apps/{application_id}"

    try:
        # 如果配置了 LDAP 认证，使用 Basic Auth
        auth = None
        if settings.YARN_USERNAME and settings.YARN_PASSWORD:
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(settings.YARN_USERNAME, settings.YARN_PASSWORD)

        response = requests.get(
            url,
            auth=auth,
            timeout=settings.YARN_RM_TIMEOUT or 30,
            verify=False  # Knox Gateway 可能使用自签名证书
        )

        if response.status_code != 200:
            return {"error": f"YARN API HTTP {response.status_code}"}

        app_data = response.json().get("app", {})

        return {
            "app_id": app_data.get("id", ""),
            "app_name": app_data.get("name", ""),
            "state": app_data.get("state", ""),
            "final_status": app_data.get("finalStatus", ""),
            "user": app_data.get("user", ""),
            # 资源使用（关键数据）
            "allocated_vcores": app_data.get("allocatedVCores", 0),
            "allocated_memory_mb": app_data.get("allocatedMB", 0),
            "running_containers": app_data.get("runningContainers", 0),
            # 时间信息
            "started_time": app_data.get("startedTime", 0),
            "finished_time": app_data.get("finishedTime", 0),
            "elapsed_time_ms": app_data.get("elapsedTime", 0),
            # 诊断信息（错误原因）
            "diagnostics": app_data.get("diagnostics", ""),
            # 资源请求
            "resource_requests": app_data.get("resourceRequests", []),
        }

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_spark_history_metrics(application_id: str) -> Dict[str, Any]:
    """
    从 Spark History Server 获取应用 metrics

    Args:
        application_id: Spark 应用 ID (如 application_1234567890_0001)

    Returns:
        Metrics 字典：
        - executor_count: Executor 数量
        - executor_memory_used: Executor 内存使用
        - driver_memory_used: Driver 内存使用
        - memory_spilled_mb: 内存溢出量（MB）
        - shuffle_read_mb: Shuffle 读取量（MB）
        - shuffle_write_mb: Shuffle 写入量（MB）
        - input_bytes_mb: 输入数据量（MB）
        - peak_memory_mb: 峰值内存使用（MB）
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")

    try:
        # 1. 获取应用基本信息
        app_url = f"{base_url}/api/v1/applications/{application_id}"
        app_response = requests.get(app_url, timeout=settings.SPARK_HISTORY_TIMEOUT or 30)

        if app_response.status_code != 200:
            return {"error": f"Spark History API HTTP {app_response.status_code}"}

        app_data = app_response.json()
        metrics = {
            "app_name": app_data.get("name", ""),
            "attempt_count": len(app_data.get("attempts", [])),
        }

        # 2. 获取 Executor 信息
        executors_url = f"{base_url}/api/v1/applications/{application_id}/executors"
        executors_response = requests.get(executors_url, timeout=30)

        if executors_response.status_code == 200:
            executors_data = executors_response.json()

            # 统计活跃 Executor
            active_executors = [e for e in executors_data if not e.get("isBlacklisted", False)]
            metrics["executor_count"] = len(active_executors)

            # 计算总内存使用
            total_memory_used = 0
            max_memory_used = 0

            for executor in active_executors:
                mem_used = executor.get("memoryUsed", 0)
                total_memory_used += mem_used
                max_memory_used = max(max_memory_used, mem_used)

                # 检查是否有内存溢出
                if executor.get("memorySpilled", 0) > 0:
                    metrics["memory_spilled_mb"] = executor.get("memorySpilled", 0) // (1024 * 1024)

            metrics["total_executor_memory_used_mb"] = total_memory_used // (1024 * 1024)
            metrics["peak_executor_memory_mb"] = max_memory_used // (1024 * 1024)

        # 3. 获取 Stage 信息（Shuffle 数据量）
        stages_url = f"{base_url}/api/v1/applications/{application_id}/stages"
        stages_response = requests.get(stages_url, timeout=30)

        if stages_response.status_code == 200:
            stages_data = stages_response.json()

            total_shuffle_read = 0
            total_shuffle_write = 0
            total_input_bytes = 0

            for stage in stages_data:
                # Shuffle 数据量
                input_metrics = stage.get("inputMetrics", {})
                total_input_bytes += input_metrics.get("bytesRead", 0)

                shuffle_read_metrics = stage.get("shuffleReadMetrics", {})
                total_shuffle_read += shuffle_read_metrics.get("remoteBytesRead", 0)

                shuffle_write_metrics = stage.get("shuffleWriteMetrics", {})
                total_shuffle_write += shuffle_write_metrics.get("shuffleBytesWritten", 0)

            metrics["input_bytes_mb"] = total_input_bytes // (1024 * 1024)
            metrics["shuffle_read_mb"] = total_shuffle_read // (1024 * 1024)
            metrics["shuffle_write_mb"] = total_shuffle_write // (1024 * 1024)

        # 4. 获取 Driver 信息
        # 通过尝试获取第一个 executor（通常是 driver）或单独的 API
        # Spark History Server 在 executors 列表中包含 driver
        if executors_response.status_code == 200:
            for executor in executors_data:
                if executor.get("id", "").startswith("driver"):
                    metrics["driver_memory_used_mb"] = executor.get("memoryUsed", 0) // (1024 * 1024)
                    metrics["driver_cores"] = executor.get("totalCores", 0)
                    break

        # 5. 获取配置信息（从环境变量或尝试解析 event log）
        # 从 application attempt 的 AppSparkEnv 获取配置
        attempts = app_data.get("attempts", [])
        if attempts:
            last_attempt = attempts[-1]
            metrics["app_duration_ms"] = last_attempt.get("duration", 0)
            metrics["spark_user"] = last_attempt.get("sparkUser", "")

        return metrics

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_spark_event_log(application_id: str) -> Optional[str]:
    """
    从 Spark History Server 获取完整的 event log（JSON 格式）

    Event log 包含详细的 Spark 配置和任务执行信息。

    Args:
        application_id: Spark 应用 ID

    Returns:
        Event log 文本（每行一个 JSON）或 None
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return None

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")

    try:
        # 获取 event log（ZIP 格式）
        logs_url = f"{base_url}/api/v1/applications/{application_id}/logs"
        response = requests.get(logs_url, timeout=60)

        if response.status_code != 200:
            return None

        # 尝试解压 ZIP
        import zipfile
        import io

        try:
            zip_buffer = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_buffer, 'r') as z:
                for name in z.namelist():
                    content = z.read(name)
                    return content.decode('utf-8', errors='ignore')
        except zipfile.BadZipFile:
            # 不是 ZIP，直接返回文本
            return response.text

    except requests.RequestException:
        return None


def parse_event_log_for_config(event_log: str) -> Dict[str, str]:
    """
    从 event log 解析 Spark 配置

    Args:
        event_log: Event log 文本（每行一个 JSON）

    Returns:
        Spark 配置字典（映射到 DolphinScheduler UI 参数）
    """
    config = {}

    if not event_log:
        return config

    for line in event_log.splitlines():
        if not line.strip() or not line.startswith('{'):
            continue

        try:
            event = json.loads(line)
            event_type = event.get("Event", "")

            # SparkListenerEnvironmentUpdate 包含所有配置
            if event_type == "SparkListenerEnvironmentUpdate":
                env_details = event.get("Environment Details", {})

                # Spark Properties
                spark_props = env_details.get("Spark Properties", {})

                # 映射到 DolphinScheduler UI 参数
                config_mapping = {
                    "spark.driver.memory": "driver_memory",
                    "spark.driver.cores": "driver_cores",
                    "spark.executor.memory": "executor_memory",
                    "spark.executor.cores": "executor_cores",
                    "spark.executor.instances": "executor_instances",
                }

                for spark_key, ds_key in config_mapping.items():
                    if spark_key in spark_props:
                        config[ds_key] = spark_props[spark_key]

                break  # 通常只在第一个 EnvironmentUpdate 事件中有完整配置

        except json.JSONDecodeError:
            continue

    return config


def parse_event_log_for_metrics(event_log: str) -> Dict[str, int]:
    """
    从 event log 解析资源 metrics（聚合所有 TaskEnd 事件）

    Args:
        event_log: Event log 文本

    Returns:
        Metrics 字典：
        - input_bytes: 输入数据量（字节）
        - shuffle_read_bytes: Shuffle 读取量（字节）
        - shuffle_write_bytes: Shuffle 写入量（字节）
        - memory_spilled_bytes: 内存溢出量（字节）
    """
    metrics = {
        "input_bytes": 0,
        "shuffle_read_bytes": 0,
        "shuffle_write_bytes": 0,
        "memory_spilled_bytes": 0,
    }

    if not event_log:
        return metrics

    for line in event_log.splitlines():
        if not line.strip() or not line.startswith('{'):
            continue

        try:
            event = json.loads(line)

            if event.get("Event") == "SparkListenerTaskEnd":
                task_metrics = event.get("Task Metrics", {})

                metrics["input_bytes"] += task_metrics.get("Input Metrics", {}).get("Bytes Read", 0)
                metrics["shuffle_read_bytes"] += task_metrics.get("Shuffle Read Metrics", {}).get("Remote Bytes Read", 0)
                metrics["shuffle_write_bytes"] += task_metrics.get("Shuffle Write Metrics", {}).get("Shuffle Bytes Written", 0)
                metrics["memory_spilled_bytes"] += task_metrics.get("Memory Bytes Spilled", 0)

        except json.JSONDecodeError:
            continue

    return metrics


def get_comprehensive_metrics(application_id: str) -> Dict[str, Any]:
    """
    综合获取 Spark 应用资源 metrics（整合所有数据源）

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

    # 1. 从 YARN 获取容器资源使用
    yarn_info = fetch_yarn_app_info(application_id)
    if yarn_info and not yarn_info.get("error"):
        result["yarn_info"] = yarn_info

        # YARN diagnostics 可能包含错误原因
        if yarn_info.get("diagnostics"):
            result["diagnostics"] = yarn_info["diagnostics"]

    # 2. 从 Spark History 获取 metrics
    spark_metrics = fetch_spark_history_metrics(application_id)
    if spark_metrics and not spark_metrics.get("error"):
        result["spark_metrics"] = spark_metrics

        # 映射到 data_metrics（供 calculate_resource.py 使用）
        result["data_metrics"] = {
            "memory_spilled": spark_metrics.get("memory_spilled_mb", 0),
            "peak_memory": spark_metrics.get("peak_executor_memory_mb", 0),
            "shuffle_read": spark_metrics.get("shuffle_read_mb", 0),
            "shuffle_write": spark_metrics.get("shuffle_write_mb", 0),
            "input_bytes": spark_metrics.get("input_bytes_mb", 0),
        }

    # 3. 从 Event Log 获取详细配置和 metrics
    event_log = fetch_spark_event_log(application_id)
    if event_log:
        # 解析配置
        config = parse_event_log_for_config(event_log)
        if config:
            result["current_config"] = config

        # 如果 Spark History API 没返回 metrics，从 event log 解析
        if not result["data_metrics"].get("memory_spilled"):
            log_metrics = parse_event_log_for_metrics(event_log)
            result["data_metrics"]["memory_spilled"] = log_metrics["memory_spilled_bytes"] // (1024 * 1024)
            result["data_metrics"]["shuffle_read"] = log_metrics["shuffle_read_bytes"] // (1024 * 1024)
            result["data_metrics"]["shuffle_write"] = log_metrics["shuffle_write_bytes"] // (1024 * 1024)

    return result


# ============================================================================
# 深度分析新增 API 函数
# ============================================================================

def fetch_stage_tasks(
    application_id: str,
    stage_id: int,
    attempt_id: int = 0
) -> Dict[str, Any]:
    """
    获取 Stage 的 Task 级别详情

    用于数据倾斜诊断、定位执行异常的 Task。

    API: /api/v1/applications/{app_id}/stages/{stage_id}/{attempt_id}/taskList

    Args:
        application_id: Spark 应用 ID
        stage_id: Stage ID
        attempt_id: Attempt ID（默认 0）

    Returns:
        {
            tasks: Task 列表 [{task_id, duration, input_bytes, status, executor_id}]
            straggler_tasks: 执行时间异常的 Task（超过 median * 3）
            skew_tasks: 数据量异常的 Task
            skew_ratio: max_duration / median_duration
            is_skewed: 是否存在倾斜
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/stages/{stage_id}/{attempt_id}/taskList"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "url": url}

        tasks = response.json()
        return analyze_task_distribution(tasks)

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_task_summary(
    application_id: str,
    stage_id: int,
    attempt_id: int = 0
) -> Dict[str, Any]:
    """
    获取 Task 时间分布统计

    用于快速判断是否存在数据倾斜。

    API: /api/v1/applications/{app_id}/stages/{stage_id}/{attempt_id}/taskSummary

    Args:
        application_id: Spark 应用 ID
        stage_id: Stage ID
        attempt_id: Attempt ID（默认 0）

    Returns:
        {
            percentiles: {25%, 50%, 75%, 95%, 99%} 执行时间
            median_duration_ms: 中位数时间
            max_duration_ms: 最大时间
            skew_ratio: max/median
            is_skewed: 是否倾斜（ratio > 3）
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/stages/{stage_id}/{attempt_id}/taskSummary"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "url": url}

        summary = response.json()

        # 计算倾斜比例
        median = summary.get("median", 0) or summary.get("50%", 0)
        max_val = summary.get("max", 0) or summary.get("99%", 0)

        skew_ratio = max_val / median if median > 0 else 0

        return {
            "percentiles": {
                "25%": summary.get("25%", 0),
                "50%": summary.get("50%", 0) or median,
                "75%": summary.get("75%", 0),
                "95%": summary.get("95%", 0),
                "99%": summary.get("99%", 0),
            },
            "median_duration_ms": median,
            "max_duration_ms": max_val,
            "skew_ratio": skew_ratio,
            "is_skewed": skew_ratio > 3,
        }

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_sql_execution(
    application_id: str,
    execution_id: int
) -> Dict[str, Any]:
    """
    获取 SQL 执行计划

    用于分析 Join 策略、执行计划变化。

    API: /api/v1/applications/{app_id}/sql/execution/{execution_id}

    Args:
        application_id: Spark 应用 ID
        execution_id: SQL Execution ID

    Returns:
        {
            sql_text: SQL 文本
            physical_plan: 物理执行计划
            join_strategies: Join 策略列表
            scan_info: 表扫描信息
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/sql/execution/{execution_id}"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "url": url}

        data = response.json()
        return parse_sql_execution_plan(data)

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_sql_executions_list(application_id: str) -> List[Dict[str, Any]]:
    """
    获取 SQL Execution 列表

    API: /api/v1/applications/{app_id}/sql/executions

    Args:
        application_id: Spark 应用 ID

    Returns:
        SQL Execution 列表 [{id, status, description}]
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return []

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/sql/executions"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            return response.json()
        return []

    except requests.RequestException:
        return []


def fetch_jobs(application_id: str) -> List[Dict[str, Any]]:
    """
    获取 Job 列表

    用于 Stage-Job 映射，定位哪个 Action 触发了问题 Stage。

    API: /api/v1/applications/{app_id}/jobs

    Args:
        application_id: Spark 应用 ID

    Returns:
        [{job_id, status, stage_ids, duration, description}]
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return []

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/jobs"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            return response.json()
        return []

    except requests.RequestException:
        return []


def fetch_stages_detail(application_id: str) -> List[Dict[str, Any]]:
    """
    获取 Stage 详情列表

    API: /api/v1/applications/{app_id}/stages

    Args:
        application_id: Spark 应用 ID

    Returns:
        [{stageId, status, duration, inputBytes, shuffleReadBytes, shuffleWriteBytes}]
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return []

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/stages"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            stages = response.json()
            # 提取关键信息
            result = []
            for stage in stages:
                result.append({
                    "stageId": stage.get("stageId"),
                    "attemptId": stage.get("attemptId", 0),
                    "name": stage.get("name", ""),
                    "status": stage.get("status", ""),
                    "duration": stage.get("duration", 0),
                    "inputBytes": stage.get("inputBytes", 0),
                    "shuffleReadBytes": stage.get("shuffleReadBytes", 0),
                    "shuffleWriteBytes": stage.get("shuffleWriteBytes", 0),
                    "memoryBytesSpilled": stage.get("memoryBytesSpilled", 0),
                    "task_count": stage.get("numTasks", 0),
                    "failed_tasks": stage.get("numFailedTasks", 0),
                })
            return result
        return []

    except requests.RequestException:
        return []


def analyze_task_distribution(tasks: List[Dict]) -> Dict[str, Any]:
    """
    分析 Task 分布，识别倾斜和 Straggler

    Args:
        tasks: Task 列表（从 API 返回）

    Returns:
        {
            tasks: 原始 Task 列表
            median_duration_ms: 中位数执行时间
            max_duration_ms: 最大执行时间
            skew_ratio: 倾斜比例
            is_skewed: 是否倾斜
            straggler_tasks: 执行时间异常的 Task
            skew_tasks_by_input: 输入数据量异常的 Task
        }
    """
    if not tasks:
        return {
            "tasks": [],
            "median_duration_ms": 0,
            "max_duration_ms": 0,
            "skew_ratio": 0,
            "is_skewed": False,
            "straggler_tasks": [],
            "skew_tasks_by_input": [],
        }

    # 提取执行时间
    durations = [t.get("duration", 0) for t in tasks if t.get("duration")]
    if not durations:
        durations = [0]

    # 计算中位数
    sorted_durations = sorted(durations)
    n = len(sorted_durations)
    median = sorted_durations[n // 2] if n % 2 == 1 else \
             (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) / 2

    max_duration = max(durations)
    skew_ratio = max_duration / median if median > 0 else 0

    # 找出 Straggler（执行时间超过 median * 3）
    straggler_threshold = median * 3
    straggler_tasks = [
        {
            "task_id": t.get("taskId"),
            "index": t.get("index"),
            "duration": t.get("duration"),
            "attempt": t.get("attempt"),
            "executor_id": t.get("executorId"),
            "host": t.get("host"),
            "status": t.get("status"),
        }
        for t in tasks
        if t.get("duration", 0) > straggler_threshold
    ]

    # 找出输入数据量异常的 Task
    input_sizes = [t.get("inputBytesRead", 0) or t.get("bytesRead", 0) for t in tasks]
    if input_sizes:
        sorted_inputs = sorted(input_sizes)
        median_input = sorted_inputs[len(sorted_inputs) // 2]
        input_threshold = median_input * 3

        skew_tasks_by_input = [
            {
                "task_id": t.get("taskId"),
                "index": t.get("index"),
                "input_bytes": t.get("inputBytesRead", 0) or t.get("bytesRead", 0),
                "duration": t.get("duration"),
            }
            for t in tasks
            if (t.get("inputBytesRead", 0) or t.get("bytesRead", 0)) > input_threshold
        ]
    else:
        skew_tasks_by_input = []

    return {
        "tasks": tasks,
        "median_duration_ms": median,
        "max_duration_ms": max_duration,
        "skew_ratio": skew_ratio,
        "is_skewed": skew_ratio > 3,
        "straggler_tasks": straggler_tasks,
        "skew_tasks_by_input": skew_tasks_by_input,
        "task_count": len(tasks),
    }


def parse_sql_execution_plan(data: Dict) -> Dict[str, Any]:
    """
    解析 SQL 执行计划，提取 Join 策略等信息

    Args:
        data: API 返回的 SQL Execution 数据

    Returns:
        {
            sql_text: SQL 文本
            physical_plan: 物理执行计划
            join_strategies: Join 策略列表
            scan_info: 表扫描信息
        }
    """
    result = {
        "sql_text": "",
        "physical_plan": "",
        "join_strategies": [],
        "scan_info": [],
    }

    # SQL 文本
    result["sql_text"] = data.get("description", "") or data.get("sql", "")

    # 物理执行计划
    plan = data.get("physicalPlan", "")
    result["physical_plan"] = plan

    # 从执行计划中提取 Join 策略
    if plan:
        # BroadcastHashJoin
        if "BroadcastHashJoin" in plan:
            result["join_strategies"].append({
                "type": "BroadcastHashJoin",
                "count": plan.count("BroadcastHashJoin"),
            })

        # SortMergeJoin
        if "SortMergeJoin" in plan:
            result["join_strategies"].append({
                "type": "SortMergeJoin",
                "count": plan.count("SortMergeJoin"),
            })

        # ShuffleHashJoin
        if "ShuffleHashJoin" in plan:
            result["join_strategies"].append({
                "type": "ShuffleHashJoin",
                "count": plan.count("ShuffleHashJoin"),
            })

        # CartesianProduct
        if "CartesianProduct" in plan:
            result["join_strategies"].append({
                "type": "CartesianProduct",
                "count": plan.count("CartesianProduct"),
            })

        # 提取 Scan 信息
        scan_patterns = [
            r'Scan\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
            r'FileScan\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
        ]

        import re
        for pattern in scan_patterns:
            for match in re.finditer(pattern, plan):
                table_name = match.group(1)
                if table_name not in [s.get("table") for s in result["scan_info"]]:
                    result["scan_info"].append({
                        "table": table_name,
                        "type": "Scan",
                    })

    return result


def get_deep_analysis_metrics(application_id: str) -> Dict[str, Any]:
    """
    获取深度分析所需的所有 metrics

    整合:
    - 基础 metrics（已有）
    - Task 级别分析（新增）
    - SQL 执行计划（新增）
    - Job 信息（新增）
    - Stage 详情（新增）

    Args:
        application_id: Spark 应用 ID

    Returns:
        {
            basic_metrics: 基础资源 metrics
            stages: Stage 详情列表
            stage_tasks: {stage_id: Task 分析结果}
            task_summaries: {stage_id: Task 时间分布}
            sql_executions: SQL 执行计划列表
            jobs: Job 列表
            skew_analysis: 数据倾斜诊断结果
        }
    """
    # 1. 获取基础 metrics
    result = get_comprehensive_metrics(application_id)

    # 2. 获取 Stage 详情
    stages = fetch_stages_detail(application_id)
    result["stages"] = stages

    # 3. 对每个 Stage 获取 Task 级别分析
    result["stage_tasks"] = {}
    result["task_summaries"] = {}

    for stage in stages:
        stage_id = stage.get("stageId")
        attempt_id = stage.get("attemptId", 0)

        # 获取 Task 详情
        if stage_id:
            tasks_data = fetch_stage_tasks(application_id, stage_id, attempt_id)
            if tasks_data and not tasks_data.get("error"):
                result["stage_tasks"][stage_id] = tasks_data

            # 获取 Task 摘要
            summary_data = fetch_task_summary(application_id, stage_id, attempt_id)
            if summary_data and not summary_data.get("error"):
                result["task_summaries"][stage_id] = summary_data

    # 4. 获取 Jobs
    result["jobs"] = fetch_jobs(application_id)

    # 5. 获取 SQL Executions
    sql_executions_list = fetch_sql_executions_list(application_id)
    result["sql_executions"] = []

    for sql_exec in sql_executions_list[:5]:  # 最多分析 5 个 SQL
        exec_id = sql_exec.get("id")
        if exec_id:
            exec_detail = fetch_sql_execution(application_id, exec_id)
            if exec_detail and not exec_detail.get("error"):
                result["sql_executions"].append(exec_detail)

    # 6. 数据倾斜诊断结果
    result["skew_analysis"] = analyze_skew(result)

    return result


def analyze_skew(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    综合分析数据倾斜情况

    Args:
        metrics: get_deep_analysis_metrics 返回的数据

    Returns:
        {
            has_skew: 是否存在倾斜
            skewed_stages: 倾斜的 Stage 列表
            max_skew_ratio: 最大倾斜比例
            recommendation: 建议修复方式
        }
    """
    result = {
        "has_skew": False,
        "skewed_stages": [],
        "max_skew_ratio": 0,
        "recommendation": None,
    }

    stage_tasks = metrics.get("stage_tasks", {})
    task_summaries = metrics.get("task_summaries", {})

    for stage_id, tasks_data in stage_tasks.items():
        if tasks_data.get("is_skewed"):
            result["has_skew"] = True
            result["skewed_stages"].append({
                "stage_id": stage_id,
                "skew_ratio": tasks_data.get("skew_ratio"),
                "straggler_count": len(tasks_data.get("straggler_tasks", [])),
                "skew_by_input_count": len(tasks_data.get("skew_tasks_by_input", [])),
            })

            # 更新最大倾斜比例
            skew_ratio = tasks_data.get("skew_ratio", 0)
            if skew_ratio > result["max_skew_ratio"]:
                result["max_skew_ratio"] = skew_ratio

    # 根据倾斜类型生成建议
    if result["has_skew"]:
        # 检查是否是输入数据倾斜
        has_input_skew = False
        for stage in result["skewed_stages"]:
            tasks_data = stage_tasks.get(stage["stage_id"], {})
            if tasks_data.get("skew_tasks_by_input"):
                has_input_skew = True
                break

        if has_input_skew:
            result["recommendation"] = {
                "type": "salting",
                "description": "Key 分布不均导致数据倾斜，建议对 Join Key 加盐",
                "example": "key = concat(key, floor(rand() * 10))",
            }
        else:
            result["recommendation"] = {
                "type": "increase_parallelism",
                "description": "部分 Task 执行时间过长，建议增加 Executor 数量",
            }

    return result


# ============ Environment/Storage API（新增） ============

def fetch_spark_environment(application_id: str) -> Dict[str, Any]:
    """
    从 Spark History Server 获取 Environment 配置

    API: /api/v1/applications/{app_id}/environment

    替代 Event Log 解析，直接获取完整 Spark 配置。

    Args:
        application_id: Spark 应用 ID

    Returns:
        {
            spark_properties: {spark.executor.memory, spark.driver.memory, ...}
            hadoop_properties: {hadoop.fs.defaultFS, ...}
            classpath_entries: [依赖路径列表]
            ds_config: {executor_memory, driver_memory, ...}  # 映射到 DolphinScheduler UI
            runtime: {spark_version, java_version}
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")

    # 获取 attemptId（默认 1）
    try:
        app_url = f"{base_url}/api/v1/applications/{application_id}"
        app_resp = requests.get(app_url, timeout=10)
        if app_resp.status_code == 200:
            app_data = app_resp.json()
            attempts = app_data.get("attempts", [])
            if attempts:
                attempt_id = attempts[0].get("attemptId", "1")
            else:
                attempt_id = "1"
        else:
            attempt_id = "1"
    except:
        attempt_id = "1"

    url = f"{base_url}/api/v1/applications/{application_id}/{attempt_id}/environment"

    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}"}

        env_data = response.json()
        spark_props_raw = env_data.get("sparkProperties", [])

        # 解析嵌套 list 格式 [["key", "value"], ...]
        spark_props = {}
        if isinstance(spark_props_raw, list):
            for item in spark_props_raw:
                if isinstance(item, list) and len(item) == 2:
                    spark_props[item[0]] = item[1]
                elif isinstance(item, dict) and 'key' in item and 'value' in item:
                    spark_props[item['key']] = item['value']
        elif isinstance(spark_props_raw, dict):
            spark_props = spark_props_raw

        # 映射到 DolphinScheduler UI 配置
        config_mapping = {
            "spark.driver.memory": "driver_memory",
            "spark.driver.cores": "driver_cores",
            "spark.executor.memory": "executor_memory",
            "spark.executor.cores": "executor_cores",
            "spark.executor.instances": "executor_instances",
            "spark.sql.shuffle.partitions": "shuffle_partitions",
            "spark.default.parallelism": "default_parallelism",
        }

        ds_config = {}
        for spark_key, ds_key in config_mapping.items():
            if spark_key in spark_props:
                ds_config[ds_key] = spark_props[spark_key]

        # 提取 Runtime 信息
        runtime_data = env_data.get("runtime", {})
        runtime = {
            "java_version": runtime_data.get("javaVersion", ""),
            "scala_version": runtime_data.get("scalaVersion", ""),
        }

        return {
            "spark_properties": spark_props,
            "hadoop_properties": env_data.get("hadoopProperties", {}),
            "classpath_entries": list(env_data.get("classpathEntries", {}).keys()) if isinstance(env_data.get("classpathEntries"), dict) else [],
            "ds_config": ds_config,
            "runtime": runtime,
        }

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_spark_storage_rdds(application_id: str) -> Dict[str, Any]:
    """
    获取 RDD 缓存信息

    API: /api/v1/applications/{app_id}/storage/rdd

    用于 OOM 诊断、缓存优化分析。

    Args:
        application_id: Spark 应用 ID

    Returns:
        {
            rdd_list: [{id, name, memory_used_mb, disk_used_mb, level, num_cached_partitions}]
            total_memory_used_mb: 总内存使用
            total_disk_used_mb: 总磁盘使用（溢出）
            has_disk_spill: 是否有数据溢出到磁盘
            oom_risk: {level, reason, recommendation} 或 None
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/storage/rdd"

    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}"}

        rdds = response.json()
        if not isinstance(rdds, list):
            rdds = []

        total_memory_bytes = 0
        total_disk_bytes = 0
        rdd_list = []

        for rdd in rdds:
            memory_used = rdd.get("memoryUsed", 0)
            disk_used = rdd.get("diskUsed", 0)
            total_memory_bytes += memory_used
            total_disk_bytes += disk_used

            rdd_list.append({
                "id": rdd.get("id"),
                "name": rdd.get("name", ""),
                "memory_used_mb": memory_used // (1024 * 1024),
                "disk_used_mb": disk_used // (1024 * 1024),
                "level": rdd.get("level", ""),
                "num_cached_partitions": rdd.get("numCachedPartitions", 0),
            })

        total_memory_mb = total_memory_bytes // (1024 * 1024)
        total_disk_mb = total_disk_bytes // (1024 * 1024)

        # OOM 风险评估
        oom_risk = None
        if total_memory_mb > 4096:  # > 4GB
            oom_risk = {
                "level": "HIGH",
                "reason": f"RDD缓存占用 {total_memory_mb}MB，可能导致内存溢出",
                "recommendation": "建议调低缓存级别或增加 executor_memory",
            }
        elif total_memory_mb > 2048:
            oom_risk = {
                "level": "MEDIUM",
                "reason": f"RDD缓存占用 {total_memory_mb}MB",
            }

        return {
            "rdd_list": rdd_list,
            "total_memory_used_mb": total_memory_mb,
            "total_disk_used_mb": total_disk_mb,
            "has_disk_spill": total_disk_mb > 0,
            "oom_risk": oom_risk,
        }

    except requests.RequestException as e:
        return {"error": str(e)}


def fetch_rdd_distribution(application_id: str, rdd_id: int) -> Dict[str, Any]:
    """
    获取 RDD 数据分布（Executor 级别）

    API: /api/v1/applications/{app_id}/storage/rdd/{rdd_id}

    用于数据分布不均衡诊断、热点 Partition 分析。

    Args:
        application_id: Spark 应用 ID
        rdd_id: RDD ID

    Returns:
        {
            rdd_id: rdd_id
            rdd_name: RDD 名称
            data_distribution: [{executor_id, memory_used_mb, disk_used_mb, num_partitions}]
            skew_detected: 是否存在数据倾斜
            skew_ratio: max_memory / median_memory
            skew_executors: 倾斜的 Executor 列表
        }
    """
    settings = _get_settings()

    if not settings.SPARK_HISTORY_URL:
        return {"error": "SPARK_HISTORY_URL not configured"}

    base_url = settings.SPARK_HISTORY_URL.rstrip("/")
    url = f"{base_url}/api/v1/applications/{application_id}/storage/rdd/{rdd_id}"

    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}"}

        rdd_data = response.json()

        # 解析 dataDistribution
        distributions = rdd_data.get("dataDistribution", [])
        dist_list = []
        memory_values = []

        for dist in distributions:
            memory_used = dist.get("memoryUsed", 0)
            memory_values.append(memory_used)
            dist_list.append({
                "executor_id": dist.get("executorId", ""),
                "memory_used_mb": memory_used // (1024 * 1024),
                "disk_used_mb": dist.get("diskUsed", 0) // (1024 * 1024),
                "on_heap_memory_mb": dist.get("onHeapMemoryUsed", 0) // (1024 * 1024),
                "off_heap_memory_mb": dist.get("offHeapMemoryUsed", 0) // (1024 * 1024),
            })

        # 检测数据倾斜
        skew_detected = False
        skew_ratio = 0
        skew_executors = []

        if memory_values and len(memory_values) >= 2:
            sorted_memory = sorted(memory_values)
            n = len(sorted_memory)
            median = sorted_memory[n // 2] if n % 2 == 1 else \
                     (sorted_memory[n // 2 - 1] + sorted_memory[n // 2]) / 2
            max_memory = max(memory_values)

            if median > 0:
                skew_ratio = max_memory / median
                skew_detected = skew_ratio > 3

                # 找出倾斜 Executor
                skew_threshold = median * 3
                skew_executors = [
                    d for d in dist_list
                    if d["memory_used_mb"] * 1024 * 1024 > skew_threshold
                ]

        return {
            "rdd_id": rdd_id,
            "rdd_name": rdd_data.get("name", ""),
            "data_distribution": dist_list,
            "skew_detected": skew_detected,
            "skew_ratio": round(skew_ratio, 2),
            "skew_executors": skew_executors,
        }

    except requests.RequestException as e:
        return {"error": str(e)}


def get_comprehensive_metrics_with_env(application_id: str) -> Dict[str, Any]:
    """
    综合获取 Spark 应用资源 metrics（增强版）

    整合:
    - YARN 应用信息
    - Spark History Metrics（Executor、Shuffle）
    - Environment API（完整配置）
    - Storage API（RDD 缓存）

    Args:
        application_id: Spark 应用 ID

    Returns:
        {
            yarn_info: {...}
            spark_metrics: {...}
            spark_environment: {...}  # 新增
            spark_storage: {...}      # 新增
            current_config: {...}     # 从 Environment API 提取
            data_metrics: {...}
        }
    """
    result = get_comprehensive_metrics(application_id)  # 已有函数

    # 新增: Environment API
    env_data = fetch_spark_environment(application_id)
    if env_data and not env_data.get("error"):
        result["spark_environment"] = env_data
        # 从 Environment API 提取配置（优先）
        result["current_config"] = env_data.get("ds_config", {})
    else:
        result["spark_environment"] = env_data

    # 新增: Storage API
    storage_data = fetch_spark_storage_rdds(application_id)
    if storage_data and not storage_data.get("error"):
        result["spark_storage"] = storage_data

        # OOM 风险信息补充
        if storage_data.get("oom_risk"):
            result["storage_oom_risk"] = storage_data["oom_risk"]

        # 数据 metrics 补充
        if "data_metrics" not in result:
            result["data_metrics"] = {}
        result["data_metrics"]["rdd_cache_memory_mb"] = storage_data.get("total_memory_used_mb", 0)
        result["data_metrics"]["rdd_disk_spill_mb"] = storage_data.get("total_disk_used_mb", 0)
        result["data_metrics"]["has_disk_spill"] = storage_data.get("has_disk_spill", False)
    else:
        result["spark_storage"] = storage_data

    return result


__all__ = [
    "fetch_yarn_app_info",
    "fetch_spark_history_metrics",
    "fetch_spark_event_log",
    "parse_event_log_for_config",
    "parse_event_log_for_metrics",
    "get_comprehensive_metrics",
    # 新增深度分析函数
    "fetch_stage_tasks",
    "fetch_task_summary",
    "fetch_sql_execution",
    "fetch_sql_executions_list",
    "fetch_jobs",
    "fetch_stages_detail",
    "analyze_task_distribution",
    "parse_sql_execution_plan",
    "get_deep_analysis_metrics",
    "analyze_skew",
    # 新增 Environment/Storage API
    "fetch_spark_environment",
    "fetch_spark_storage_rdds",
    "fetch_rdd_distribution",
    "get_comprehensive_metrics_with_env",
]