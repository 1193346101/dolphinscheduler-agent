"""
Spark 资源建议计算脚本

根据错误类型、数据指标、当前配置和集群限制计算资源调整建议。
"""

from typing import Dict, Any, Optional
import re


def parse_memory_to_mb(memory_str: str) -> int:
    """
    将内存字符串转换为 MB 单位。

    Args:
        memory_str: 内存字符串，如 "4g", "2048m", "2g"

    Returns:
        内存大小（MB）
    """
    if not memory_str:
        return 0

    memory_str = memory_str.strip().lower()

    # 提取数字和单位
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([gmkt]?)$', memory_str)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2)

    # 转换为 MB
    multipliers = {
        '': 1,      # 默认为 MB
        'k': 1 / 1024,
        'm': 1,
        'g': 1024,
        't': 1024 * 1024,
    }

    return int(value * multipliers.get(unit, 1))


def format_memory_from_mb(memory_mb: int) -> str:
    """
    将 MB 单位的内存转换为易读格式。

    Args:
        memory_mb: 内存大小（MB）

    Returns:
        格式化的内存字符串，如 "4g", "512m"
    """
    if memory_mb >= 1024:
        gb = memory_mb / 1024
        if gb == int(gb):
            return f"{int(gb)}g"
        return f"{gb:.1f}g"
    else:
        return f"{memory_mb}m"


def calculate_resource_suggestion(
    error_type: str,
    data_metrics: Dict[str, Any],
    current_config: Dict[str, str],
    cluster_limit: Dict[str, str]
) -> Dict[str, Any]:
    """
    计算 Spark 资源建议。

    Args:
        error_type: 错误类型，如 "oom_executor", "container_killed_memory" 等
        data_metrics: 数据指标，包含:
            - memory_spilled: 内存溢出量（MB 或字符串如 "2g"）
            - peak_memory: 峰值内存使用
            - shuffle_read: Shuffle 读取量
            - shuffle_write: Shuffle 写入量
        current_config: 当前配置，包含:
            - executor_memory: Executor 内存
            - executor_memory_overhead: Executor 内存开销
            - driver_memory: Driver 内存
            - driver_memory_overhead: Driver 内存开销
        cluster_limit: 集群限制，包含:
            - max_executor_memory: 最大 Executor 内存
            - max_driver_memory: 最大 Driver 内存
            - max_executors_per_app: 每个 App 最大 Executor 数

    Returns:
        资源建议字典，包含:
        - suggested_memory: str - 建议的内存配置
        - reason: str - 建议原因
        - current_memory: str - 当前内存配置
        - max_limit: str - 集群限制
        - warning: str - 警告信息（如果达到限制）
    """
    # 确定是 executor 还是 driver 相关的错误
    is_driver_error = error_type in [
        "oom_driver",
        "oom_driver_direct",
        "driver_memory_insufficient"
    ]

    # 获取当前内存配置
    if is_driver_error:
        current_memory_str = current_config.get("driver_memory", "1g")
        overhead_str = current_config.get("driver_memory_overhead", "256m")
        max_limit_str = cluster_limit.get("max_driver_memory", "8g")
        resource_type = "driver"
    else:
        current_memory_str = current_config.get("executor_memory", "2g")
        overhead_str = current_config.get("executor_memory_overhead", "512m")
        max_limit_str = cluster_limit.get("max_executor_memory", "16g")
        resource_type = "executor"

    # 转换为 MB
    current_memory_mb = parse_memory_to_mb(current_memory_str)
    overhead_mb = parse_memory_to_mb(overhead_str)
    max_limit_mb = parse_memory_to_mb(max_limit_str)

    # 获取溢出内存
    memory_spilled_raw = data_metrics.get("memory_spilled", 0)
    if isinstance(memory_spilled_raw, str):
        memory_spilled_mb = parse_memory_to_mb(memory_spilled_raw)
    else:
        memory_spilled_mb = int(memory_spilled_raw)

    # 获取峰值内存（如果有）
    peak_memory_raw = data_metrics.get("peak_memory", 0)
    if isinstance(peak_memory_raw, str):
        peak_memory_mb = parse_memory_to_mb(peak_memory_raw)
    else:
        peak_memory_mb = int(peak_memory_raw)

    # 计算建议内存
    suggested_memory_mb = 0
    reason = ""

    if memory_spilled_mb > 0:
        # 情况1: 有内存溢出，添加溢出量到当前配置
        suggested_memory_mb = current_memory_mb + memory_spilled_mb + overhead_mb
        reason = (
            f"检测到内存溢出 {format_memory_from_mb(memory_spilled_mb)}，"
            f"建议在当前 {format_memory_from_mb(current_memory_mb)} 基础上增加溢出量"
        )
    elif peak_memory_mb > 0:
        # 情况2: 有峰值内存数据，基于峰值计算
        # 预留 20% 的安全余量
        suggested_memory_mb = int(peak_memory_mb * 1.2)
        reason = (
            f"基于峰值内存使用 {format_memory_from_mb(peak_memory_mb)}，"
            f"预留 20% 安全余量"
        )
    else:
        # 情况3: 无溢出数据，加倍当前配置（最大2倍）
        suggested_memory_mb = current_memory_mb * 2
        reason = (
            f"未检测到内存溢出数据，建议将 {resource_type} 内存从 "
            f"{format_memory_from_mb(current_memory_mb)} 加倍"
        )

    # 确保最小值
    min_memory_mb = 512  # 最小 512MB
    suggested_memory_mb = max(suggested_memory_mb, min_memory_mb)

    # 检查是否超过集群限制
    warning = None
    if suggested_memory_mb > max_limit_mb:
        warning = (
            f"建议内存 {format_memory_from_mb(suggested_memory_mb)} 超过集群限制 "
            f"{format_memory_from_mb(max_limit_mb)}，已调整为最大限制"
        )
        suggested_memory_mb = max_limit_mb

    # 检查是否已达到限制
    if suggested_memory_mb == max_limit_mb:
        warning = (
            f"警告: {resource_type} 内存已达集群最大限制 "
            f"{format_memory_from_mb(max_limit_mb)}，可能需要优化任务或申请更多资源配额"
        )

    # 根据错误类型调整建议
    config_changes = {}
    if error_type == "oom_executor":
        config_changes = {
            "spark.executor.memory": format_memory_from_mb(suggested_memory_mb),
            "spark.executor.memoryOverhead": format_memory_from_mb(overhead_mb),
        }
    elif error_type == "oom_driver":
        config_changes = {
            "spark.driver.memory": format_memory_from_mb(suggested_memory_mb),
            "spark.driver.memoryOverhead": format_memory_from_mb(overhead_mb),
        }
    elif error_type == "oom_offheap":
        # 对于 offheap OOM，额外建议开启 offheap
        config_changes = {
            "spark.memory.offHeap.enabled": "true",
            "spark.memory.offHeap.size": format_memory_from_mb(suggested_memory_mb // 2),
        }
        reason += "，并建议开启 offHeap 内存"
    elif error_type == "container_killed_memory":
        config_changes = {
            "spark.executor.memory": format_memory_from_mb(suggested_memory_mb),
            "spark.executor.memoryOverhead": format_memory_from_mb(overhead_mb + 256),  # 额外增加开销
        }
        reason += "，同时增加 memoryOverhead 以避免容器被终止"
    elif error_type == "gc_overhead":
        # GC overhead 通常需要更多内存和调整内存比例
        config_changes = {
            "spark.executor.memory": format_memory_from_mb(suggested_memory_mb),
            "spark.executor.memoryOverhead": format_memory_from_mb(suggested_memory_mb // 4),
            "spark.memory.fraction": "0.6",
            "spark.memory.storageFraction": "0.3",
        }
        reason += "，并建议调整内存比例以减少 GC 压力"
    else:
        # 默认配置
        if is_driver_error:
            config_changes = {
                "spark.driver.memory": format_memory_from_mb(suggested_memory_mb),
            }
        else:
            config_changes = {
                "spark.executor.memory": format_memory_from_mb(suggested_memory_mb),
            }

    return {
        "suggested_memory": format_memory_from_mb(suggested_memory_mb),
        "reason": reason,
        "current_memory": format_memory_from_mb(current_memory_mb),
        "max_limit": format_memory_from_mb(max_limit_mb),
        "warning": warning,
        "config_changes": config_changes,
        "resource_type": resource_type,
    }


def calculate_executor_count_suggestion(
    data_metrics: Dict[str, Any],
    current_config: Dict[str, Any],
    cluster_limit: Dict[str, str]
) -> Dict[str, Any]:
    """
    计算 Executor 数量建议。

    Args:
        data_metrics: 数据指标
        current_config: 当前配置
        cluster_limit: 集群限制

    Returns:
        Executor 数量建议
    """
    current_executors = current_config.get("executor_count", 2)
    max_executors = int(cluster_limit.get("max_executors_per_app", 100))

    # 基于数据量或并行度计算
    shuffle_read_mb = 0
    shuffle_read_raw = data_metrics.get("shuffle_read", 0)
    if isinstance(shuffle_read_raw, str):
        shuffle_read_mb = parse_memory_to_mb(shuffle_read_raw)
    else:
        shuffle_read_mb = int(shuffle_read_raw)

    # 每个 executor 处理 2GB 数据
    suggested_executors = max(2, (shuffle_read_mb + 2047) // 2048)
    suggested_executors = min(suggested_executors, max_executors)

    warning = None
    if suggested_executors > current_executors * 2:
        warning = (
            f"建议 Executor 数量 {suggested_executors} 远大于当前 {current_executors}，"
            f"请确认是否需要如此高的并行度"
        )

    return {
        "suggested_executors": suggested_executors,
        "current_executors": current_executors,
        "max_limit": max_executors,
        "warning": warning,
        "reason": f"基于 Shuffle 数据量 {format_memory_from_mb(shuffle_read_mb)} 计算"
    }


# 便捷函数：综合资源建议
def get_comprehensive_suggestion(
    error_type: str,
    data_metrics: Dict[str, Any],
    current_config: Dict[str, str],
    cluster_limit: Dict[str, str]
) -> Dict[str, Any]:
    """
    获取综合资源建议。

    Args:
        error_type: 错误类型
        data_metrics: 数据指标
        current_config: 当前配置
        cluster_limit: 集群限制

    Returns:
        综合资源建议
    """
    memory_suggestion = calculate_resource_suggestion(
        error_type, data_metrics, current_config, cluster_limit
    )

    executor_suggestion = calculate_executor_count_suggestion(
        data_metrics, current_config, cluster_limit
    )

    return {
        "memory": memory_suggestion,
        "executors": executor_suggestion,
        "recommended_configs": memory_suggestion.get("config_changes", {}),
    }


__all__ = [
    "parse_memory_to_mb",
    "format_memory_from_mb",
    "calculate_resource_suggestion",
    "calculate_executor_count_suggestion",
    "get_comprehensive_suggestion",
]