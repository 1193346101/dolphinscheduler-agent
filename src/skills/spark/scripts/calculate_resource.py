"""
Spark 资源智能计算脚本

基于历史成功数据预测 + 规则引擎兜底，计算资源调整建议。

核心逻辑：
1. 历史预测：分析历史数据量与内存使用关系，预测当前任务需要的配置（最准确）
2. Driver 处理：单独计算 driver_memory（Driver OOM 时）
3. Executor 内存：基于溢出量或预测峰值
4. Executor 数量：基于 Shuffle 数据量计算并行度
5. 规则兜底：无数据时保守翻倍

DolphinScheduler Spark 任务支持的参数：
- Driver核心数 (spark.driver.cores) - 固定，不调整
- Driver内存数 (spark.driver.memory) - 需调整
- Executor数量 (spark.executor.instances) - 需调整
- Executor内存数 (spark.executor.memory) - 需调整
- Executor核心数 (spark.executor.cores) - 固定为1，不调整
"""

from typing import Dict, Any, Optional, List
import re
import statistics


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

    memory_str = str(memory_str).strip().lower()

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


def predict_config_from_history(
    historical_instances: List[Dict],
    current_data_size_mb: int,
) -> Dict[str, Any]:
    """
    基于历史成功数据预测当前任务需要的配置

    分析历史数据量与内存使用的关系，预测当前任务峰值内存。

    Args:
        historical_instances: 历史成功任务的 metrics 列表
            [{date, input_bytes_mb, peak_memory_mb, shuffle_read_mb, shuffle_write_mb,
              executor_memory, executor_instances, success}]
        current_data_size_mb: 当前任务数据量

    Returns:
        预测结果 {
            executor_memory: 建议内存,
            executor_instances: 建议 Executor 数量,
            predicted_peak_mb: 预测峰值内存,
            memory_per_data_ratio: 数据量到内存的转换系数,
            confidence: HIGH/MEDIUM/LOW,
            reasoning: 说明,
        }
    """
    # 过滤成功案例
    success_cases = [h for h in historical_instances if h.get("success") and h.get("peak_memory_mb")]

    if len(success_cases) < 3:
        return {
            "confidence": "LOW",
            "reasoning": f"历史成功案例不足（{len(success_cases)}个），无法预测",
        }

    # ========== 分析数据量与内存的关系 ==========

    data_sizes = [h.get("input_bytes_mb", 0) for h in success_cases]
    peak_memories = [h.get("peak_memory_mb", 0) for h in success_cases]

    # 基础计算：平均值比例
    avg_data = statistics.mean(data_sizes) if data_sizes else 0
    avg_peak = statistics.mean(peak_memories) if peak_memories else 0

    if avg_data <= 0:
        return {"confidence": "LOW", "reasoning": "历史数据量无效"}

    base_ratio = avg_peak / avg_data

    # 进阶计算：斜率（数据量变化对内存的影响）
    memory_per_data = base_ratio

    if len(success_cases) >= 5:
        # 按数据量排序，分大小组
        sorted_cases = sorted(success_cases, key=lambda x: x.get("input_bytes_mb", 0))

        mid = len(sorted_cases) // 2
        small_cases = sorted_cases[:mid]
        large_cases = sorted_cases[mid:]

        avg_small_data = statistics.mean([c.get("input_bytes_mb", 0) for c in small_cases])
        avg_small_peak = statistics.mean([c.get("peak_memory_mb", 0) for c in small_cases])
        avg_large_data = statistics.mean([c.get("input_bytes_mb", 0) for c in large_cases])
        avg_large_peak = statistics.mean([c.get("peak_memory_mb", 0) for c in large_cases])

        data_diff = avg_large_data - avg_small_data
        peak_diff = avg_large_peak - avg_small_peak

        if data_diff > 0:
            # 斜率：每增加 1MB 数据，内存增加多少 MB
            memory_per_data = peak_diff / data_diff

    # ========== 预测当前任务峰值内存 ==========

    predicted_peak_mb = current_data_size_mb * memory_per_data

    # 加安全余量（30%，确保能执行完成）
    suggested_memory_mb = int(predicted_peak_mb * 1.3)

    # 确保不低于历史最小配置
    historical_memories = [
        parse_memory_to_mb(h.get("executor_memory", "2g"))
        for h in success_cases
        if h.get("executor_memory")
    ]
    if historical_memories:
        min_memory_mb = min(historical_memories)
        suggested_memory_mb = max(suggested_memory_mb, min_memory_mb)

    # ========== 预测 Executor 数量（基于 Shuffle） ==========

    # 计算历史 Shuffle 与数据量的关系
    shuffle_totals = [
        h.get("shuffle_read_mb", 0) + h.get("shuffle_write_mb", 0)
        for h in success_cases
    ]

    avg_shuffle_per_data = statistics.mean(shuffle_totals) / avg_data if avg_data > 0 and statistics.mean(shuffle_totals) > 0 else 0

    predicted_shuffle_mb = current_data_size_mb * avg_shuffle_per_data

    # 每个 Executor 处理 2GB Shuffle 数据
    suggested_instances = max(2, int(predicted_shuffle_mb / 2048))

    # 基于历史 Executor 数量范围调整
    historical_instances_list = [
        h.get("executor_instances", 10)
        for h in success_cases
        if h.get("executor_instances")
    ]
    if historical_instances_list:
        min_instances = min(historical_instances_list)
        max_instances = max(historical_instances_list)
        suggested_instances = max(min_instances, min(suggested_instances, max_instances * 2))

    # ========== 构建结果 ==========

    confidence = "HIGH" if len(success_cases) >= 5 else "MEDIUM"

    reasoning = (
        f"基于{len(success_cases)}个历史成功案例，"
        f"数据量{current_data_size_mb // 1024}GB预估峰值{predicted_peak_mb // 1024}GB "
        f"(比例1:{memory_per_data:.2f})，建议内存{format_memory_from_mb(suggested_memory_mb)}"
    )

    if predicted_shuffle_mb > 2048:
        reasoning += f"，Shuffle预估{predicted_shuffle_mb // 1024}GB建议{ suggested_instances}个Executor"

    return {
        "executor_memory": format_memory_from_mb(suggested_memory_mb),
        "executor_instances": suggested_instances,
        "predicted_peak_mb": predicted_peak_mb,
        "memory_per_data_ratio": memory_per_data,
        "confidence": confidence,
        "method": "history_prediction",
        "reasoning": reasoning,
        "sample_count": len(success_cases),
    }


def calculate_driver_suggestion(
    error_type: str,
    current_config: Dict[str, str],
    data_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """
    计算 Driver 内存建议（单独处理 Driver 相关错误）

    Args:
        error_type: 错误类型 (oom_driver, oom_driver_direct 等)
        current_config: 当前配置
        data_metrics: 数据指标

    Returns:
        Driver 内存建议
    """
    current_driver_mem = parse_memory_to_mb(current_config.get("driver_memory", "1g"))

    # 获取溢出量
    spilled_mb = data_metrics.get("memory_spilled_mb", 0)

    if spilled_mb > 0:
        # 有溢出数据：当前 + 溢出量
        suggested_driver_mb = current_driver_mem + spilled_mb
        reasoning = f"Driver溢出{spilled_mb}MB，内存从{format_memory_from_mb(current_driver_mem)}增至{format_memory_from_mb(suggested_driver_mb)}"
    else:
        # 无数据：保守翻倍
        suggested_driver_mb = current_driver_mem * 2
        reasoning = f"Driver内存问题，建议从{format_memory_from_mb(current_driver_mem)}翻倍至{format_memory_from_mb(suggested_driver_mb)}"

    # 限制最大值（通常 Driver 不需要太大）
    max_driver_mb = 8 * 1024  # 8GB
    if suggested_driver_mb > max_driver_mb:
        suggested_driver_mb = max_driver_mb
        reasoning += f"，已达上限{format_memory_from_mb(max_driver_mb)}"

    return {
        "driver_memory": format_memory_from_mb(suggested_driver_mb),
        "reasoning": reasoning,
        "method": "driver_oom",
    }


def calculate_memory_utilization_ratio(
    current_config: Dict[str, str],
    shuffle_write_mb: float,
) -> Dict[str, Any]:
    """
    计算内存利用率（总内存池 / Shuffle总量）

    这是 resource_optimizer.py 的核心指标，用于判断：
    - < 1.0x: 风险配置，无余量应对数据波动
    - 1.5x - 2.0x: 推荐范围，留50%-100%余量
    - > 3.0x: 过剩配置，资源浪费

    Args:
        current_config: 当前配置
        shuffle_write_mb: Shuffle写入量（MB）

    Returns:
        {
            ratio: 内存利用率比值
            total_memory_mb: 总内存池（MB）
            shuffle_write_mb: Shuffle总量
            status: "risky" | "need_increase" | "optimal" | "over_configured"
            reason: 说明
        }
    """
    if shuffle_write_mb <= 0:
        return {
            "ratio": 0,
            "total_memory_mb": 0,
            "shuffle_write_mb": 0,
            "status": "unknown",
            "reason": "无 Shuffle 数据",
        }

    # 计算总内存池
    executor_mem_mb = parse_memory_to_mb(current_config.get("executor_memory", "4g"))
    executor_instances = int(current_config.get("executor_instances", "2") or 2)

    total_memory_mb = executor_mem_mb * executor_instances

    # 计算利用率
    ratio = total_memory_mb / shuffle_write_mb

    # 判断状态
    # 推荐范围: 1.5x - 2.0x
    risky_threshold = 1.0
    optimal_min = 1.5
    optimal_max = 2.0
    over_configured_threshold = 3.0

    if ratio < risky_threshold:
        status = "risky"
        reason = f"内存利用率 {ratio:.1f}x 过低，无余量应对数据波动"
    elif ratio < optimal_min:
        status = "need_increase"
        reason = f"内存利用率 {ratio:.1f}x 低于推荐范围 ({optimal_min}-{optimal_max}x)"
    elif ratio <= optimal_max:
        status = "optimal"
        reason = f"内存利用率 {ratio:.1f}x 在推荐范围内"
    elif ratio <= over_configured_threshold:
        status = "slightly_over"
        reason = f"内存利用率 {ratio:.1f}x 略高于推荐范围"
    else:
        status = "over_configured"
        reason = f"内存利用率 {ratio:.1f}x 过高，资源配置过剩"

    return {
        "ratio": ratio,
        "total_memory_mb": total_memory_mb,
        "shuffle_write_mb": shuffle_write_mb,
        "executor_mem_mb": executor_mem_mb,
        "executor_instances": executor_instances,
        "status": status,
        "reason": reason,
        "optimal_range": f"{optimal_min}-{optimal_max}x",
    }


def calculate_balanced_config(
    shuffle_write_mb: float,
    target_ratio: float = 1.5,
    current_config: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    计算均衡配置（避免极端配置）

    借鉴 resource_optimizer.py 的均衡逻辑：
    - executor_memory 范围: 512m - 8G
    - executor_instances 范围: 2 - 20
    - 避免: 512m×50 (内存太小) 或 16G×1 (内存太大)

    Args:
        shuffle_write_mb: Shuffle写入量（MB）
        target_ratio: 目标内存利用率（默认 1.5x）
        current_config: 当前配置（用于限制调整幅度）

    Returns:
        {
            executor_memory: 建议内存
            executor_instances: 建议数量
            total_memory_mb: 总内存池
            actual_ratio: 实际利用率
            reasoning: 说明
        }
    """
    # 目标总内存池
    target_total_mb = shuffle_write_mb * target_ratio

    # Executor 内存选项
    memory_options = [512, 1024, 2048, 3072, 4096, 6144, 8192]  # MB

    min_instances = 2
    max_instances = 20

    best_config = None
    best_score = float('inf')

    for mem_mb in memory_options:
        # 计算能达到目标的 instances 范围
        for instances in range(min_instances, max_instances + 1):
            actual_total_mb = mem_mb * instances
            actual_ratio = actual_total_mb / shuffle_write_mb if shuffle_write_mb > 0 else 0

            # 条件1: 利用在推荐范围 (1.5x - 2.5x)
            if actual_ratio < 1.5:
                continue
            if actual_ratio > 2.5:
                continue

            # 条件2: 避免极端配置
            is_extreme = False

            # 512m 且 instances > 8: 极端（内存太小）
            if mem_mb <= 512 and instances > 8:
                is_extreme = True

            # 6G+ 且 instances < 4: 极端（内存太大）
            if mem_mb >= 6144 and instances < 4:
                is_extreme = True

            # 8G 且 instances <= 2: 极端
            if mem_mb >= 8192 and instances <= 2:
                is_extreme = True

            if is_extreme:
                continue

            # 评分: 越接近目标 ratio 越好
            ratio_diff = abs(actual_ratio - target_ratio)

            # 均衡加分: instances 在合理范围 (4-12) 更好
            balance_bonus = 0
            if 4 <= instances <= 12:
                balance_bonus = -0.1

            total_score = ratio_diff + balance_bonus

            if total_score < best_score:
                best_score = total_score
                best_config = {
                    "executor_memory": format_memory_from_mb(mem_mb),
                    "executor_instances": instances,
                    "total_memory_mb": actual_total_mb,
                    "actual_ratio": actual_ratio,
                    "reasoning": f"Shuffle {int(shuffle_write_mb)}MB，总内存池 {int(actual_total_mb)}MB，利用率 {actual_ratio:.1f}x",
                }

    # 如果没找到合适的，放宽限制
    if not best_config:
        # 简单计算：目标总内存 / 合理单Executor内存
        reasonable_mem_mb = 4096  # 4G
        instances = max(min_instances, min(max_instances, int(target_total_mb / reasonable_mem_mb) + 1))
        actual_total_mb = reasonable_mem_mb * instances
        actual_ratio = actual_total_mb / shuffle_write_mb if shuffle_write_mb > 0 else 0

        best_config = {
            "executor_memory": format_memory_from_mb(reasonable_mem_mb),
            "executor_instances": instances,
            "total_memory_mb": actual_total_mb,
            "actual_ratio": actual_ratio,
            "reasoning": f"无法找到均衡配置，使用保守建议",
        }

    return best_config


def calculate_executor_memory_suggestion(
    current_config: Dict[str, str],
    data_metrics: Dict[str, Any],
    prediction_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    计算 Executor 内存建议

    优先级：
    1. 历史预测结果
    2. 溢出量
    3. 峰值内存
    4. Shuffle 数据量（估算单 Task 数据）
    5. 翻倍兜底

    Args:
        current_config: 当前配置
        data_metrics: 数据指标
        prediction_result: 历史预测结果（如果有）

    Returns:
        Executor 内存建议
    """
    current_mem = parse_memory_to_mb(current_config.get("executor_memory", "4g"))

    # 优先使用历史预测
    if prediction_result and prediction_result.get("executor_memory"):
        return {
            "executor_memory": prediction_result["executor_memory"],
            "reasoning": prediction_result.get("reasoning", "历史预测"),
            "method": prediction_result.get("method", "history_prediction"),
            "confidence": prediction_result.get("confidence", "MEDIUM"),
        }

    # 溢出量计算
    spilled_mb = data_metrics.get("memory_spilled_mb", 0) or data_metrics.get("memory_spilled", 0) / 1024 / 1024
    if spilled_mb > 0:
        suggested_mb = current_mem + int(spilled_mb)
        return {
            "executor_memory": format_memory_from_mb(suggested_mb),
            "reasoning": f"溢出{int(spilled_mb)}MB，内存增至{format_memory_from_mb(suggested_mb)}",
            "method": "oom_spill",
            "confidence": "HIGH",
        }

    # 峰值内存计算
    peak_mb = data_metrics.get("peak_memory_mb", 0) or data_metrics.get("peak_memory", 0)
    if peak_mb > 0:
        # 峰值 + 30% 余量
        suggested_mb = int(peak_mb * 1.3)
        return {
            "executor_memory": format_memory_from_mb(suggested_mb),
            "reasoning": f"峰值{peak_mb}MB，预留30%余量",
            "method": "peak_memory",
            "confidence": "MEDIUM",
        }

    # Shuffle 数据量计算（估算）
    # 支持多种 key 格式：shuffle_write, shuffle_write_mb, shuffle_write_bytes
    shuffle_write_mb = data_metrics.get("shuffle_write_mb", 0)
    if not shuffle_write_mb:
        shuffle_write_mb = data_metrics.get("shuffle_write", 0)
    if not shuffle_write_mb:
        shuffle_write_bytes = data_metrics.get("shuffle_write_bytes", 0)
        if shuffle_write_bytes > 0:
            shuffle_write_mb = shuffle_write_bytes / 1024 / 1024

    executor_instances = int(current_config.get("executor_instances", "2") or 2)

    if shuffle_write_mb > 0:
        # 估算单 Task 数据量（假设每个 Executor 有 2 个 Task 并行）
        # executor_cores 默认为 1，每个 core 可并行 1 个 task
        executor_cores = int(current_config.get("executor_cores", "1") or 1)
        parallel_tasks = executor_cores  # 每个 core 一个 task
        total_tasks = executor_instances * parallel_tasks

        per_task_data_mb = shuffle_write_mb / total_tasks if total_tasks > 0 else shuffle_write_mb

        # 建议：Executor Memory = 1.5x 单 Task 数据（留余量）
        suggested_mb = max(int(per_task_data_mb * 1.5), current_mem * 2)

        return {
            "executor_memory": format_memory_from_mb(suggested_mb),
            "reasoning": f"Shuffle数据{int(shuffle_write_mb)}MB，单Task约{int(per_task_data_mb)}MB，建议{format_memory_from_mb(suggested_mb)}（1.5x）",
            "method": "shuffle_based",
            "confidence": "MEDIUM",
        }

    # 翻倍兜底
    suggested_mb = current_mem * 2
    return {
        "executor_memory": format_memory_from_mb(suggested_mb),
        "reasoning": f"无数据支撑，保守翻倍至{format_memory_from_mb(suggested_mb)}",
        "method": "fallback_double",
        "confidence": "LOW",
    }


def calculate_executor_instances_suggestion(
    current_config: Dict[str, str],
    data_metrics: Dict[str, Any],
    prediction_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    计算 Executor 数量建议（基于 Shuffle 数据量）

    Args:
        current_config: 当前配置
        data_metrics: 数据指标
        prediction_result: 历史预测结果（如果有）

    Returns:
        Executor 数量建议
    """
    current_instances = int(current_config.get("executor_instances", 10))

    # 优先使用历史预测
    if prediction_result and prediction_result.get("executor_instances"):
        predicted_instances = prediction_result["executor_instances"]
        if predicted_instances > current_instances:
            return {
                "executor_instances": predicted_instances,
                "reasoning": f"历史预测建议{predicted_instances}个Executor",
                "method": "history_prediction",
            }

    # Shuffle 数据量计算
    shuffle_mb = data_metrics.get("shuffle_read_mb", 0) + data_metrics.get("shuffle_write_mb", 0)

    if shuffle_mb < 2048:  # < 2GB，不需要调整
        return {}

    # 每个 Executor 处理 2GB Shuffle
    suggested_instances = max(2, shuffle_mb // 2048)

    # 不超过当前配置的2倍（避免过度调整）
    max_instances = current_instances * 2
    suggested_instances = min(suggested_instances, max_instances)

    # 限制集群上限
    cluster_max_instances = 100
    suggested_instances = min(suggested_instances, cluster_max_instances)

    if suggested_instances > current_instances:
        return {
            "executor_instances": suggested_instances,
            "reasoning": f"Shuffle {shuffle_mb // 1024}GB，建议{ suggested_instances}个Executor（每Executor处理2GB）",
            "method": "shuffle_parallelism",
        }

    return {}


def build_smart_resource_suggestion(
    error_type: str,
    current_config: Dict[str, str],
    data_metrics: Dict[str, Any],
    historical_logs: Optional[List[Dict]] = None,
    current_data_size_mb: int = 0,
) -> Dict[str, Any]:
    """
    构建智能资源建议（主入口函数）

    Args:
        error_type: 错误类型
        current_config: 当前配置
            - driver_memory: Driver 内存
            - executor_memory: Executor 内存
            - executor_instances: Executor 数量
        data_metrics: 数据指标
            - memory_spilled_mb: 内存溢出量
            - peak_memory_mb: 峰值内存
            - shuffle_read_mb: Shuffle 读取量
            - shuffle_write_mb: Shuffle 写入量
            - input_bytes_mb: 输入数据量
        historical_logs: 历史成功日志的 metrics（最近7天）
        current_data_size_mb: 当前任务数据量

    Returns:
        {
            suggested_config: {driver_memory, executor_memory, executor_instances},
            reasoning: 说明,
            method: history_prediction/rule_engine/fallback,
            confidence: HIGH/MEDIUM/LOW,
            executor_cores: 1,  # 固定值
        }
    """
    suggested_config = {}
    reasoning_parts = []
    method = "rule_engine"
    confidence = "LOW"

    # ========== 1. Driver 相关错误（单独处理）==========
    driver_errors = ["oom_driver", "oom_driver_direct", "driver_memory_insufficient"]
    is_driver_error = error_type in driver_errors

    if is_driver_error:
        driver_suggestion = calculate_driver_suggestion(error_type, current_config, data_metrics)
        suggested_config["driver_memory"] = driver_suggestion["driver_memory"]
        reasoning_parts.append(driver_suggestion["reasoning"])
        method = driver_suggestion.get("method", "driver_oom")
        confidence = driver_suggestion.get("confidence", "MEDIUM")

    # ========== 2. Executor 相关错误（主流程）==========
    executor_errors = [
        "oom_executor", "oom_offheap", "container_killed_memory", "gc_overhead",
        "shuffle_timeout", "shuffle_failed", "executor_lost_heartbeat",
        "executor_memory_insufficient"
    ]
    is_executor_error = error_type in executor_errors

    if is_executor_error or not is_driver_error:
        # 尝试历史预测
        prediction_result = None

        if historical_logs and len(historical_logs) >= 3 and current_data_size_mb > 0:
            prediction_result = predict_config_from_history(historical_logs, current_data_size_mb)

            if prediction_result.get("confidence") in ["HIGH", "MEDIUM"]:
                # 历史预测成功
                suggested_config["executor_memory"] = prediction_result["executor_memory"]

                if prediction_result.get("executor_instances"):
                    suggested_config["executor_instances"] = prediction_result["executor_instances"]

                reasoning_parts.append(prediction_result["reasoning"])
                method = "history_prediction"
                confidence = prediction_result["confidence"]

        # 如果历史预测失败，使用规则引擎
        if not suggested_config.get("executor_memory"):
            mem_suggestion = calculate_executor_memory_suggestion(
                current_config, data_metrics, prediction_result
            )
            suggested_config["executor_memory"] = mem_suggestion["executor_memory"]
            reasoning_parts.append(mem_suggestion["reasoning"])
            method = mem_suggestion.get("method", "rule_engine")
            confidence = mem_suggestion.get("confidence", "LOW")

        # Executor 数量建议
        if not suggested_config.get("executor_instances"):
            instances_suggestion = calculate_executor_instances_suggestion(
                current_config, data_metrics, prediction_result
            )
            if instances_suggestion:
                suggested_config["executor_instances"] = instances_suggestion["executor_instances"]
                reasoning_parts.append(instances_suggestion["reasoning"])

    # ========== 3. 集群限制检查 ==========
    max_executor_memory_mb = 16 * 1024  # 16GB
    max_driver_memory_mb = 8 * 1024     # 8GB

    if suggested_config.get("executor_memory"):
        suggested_mem_mb = parse_memory_to_mb(suggested_config["executor_memory"])
        if suggested_mem_mb > max_executor_memory_mb:
            suggested_config["executor_memory"] = format_memory_from_mb(max_executor_memory_mb)
            reasoning_parts.append(f"Executor内存已达上限{format_memory_from_mb(max_executor_memory_mb)}")

    if suggested_config.get("driver_memory"):
        suggested_driver_mb = parse_memory_to_mb(suggested_config["driver_memory"])
        if suggested_driver_mb > max_driver_memory_mb:
            suggested_config["driver_memory"] = format_memory_from_mb(max_driver_memory_mb)
            reasoning_parts.append(f"Driver内存已达上限{format_memory_from_mb(max_driver_memory_mb)}")

    # ========== 4. 构建最终结果 ==========

    return {
        "suggested_config": suggested_config,
        "reasoning": " | ".join(reasoning_parts) if reasoning_parts else "无建议",
        "method": method,
        "confidence": confidence,
        "executor_cores": 1,  # 固定值，不调整
        "driver_cores": 1,    # 固定值，不调整
        "current_config": current_config,
    }


# ========== 兼容旧接口（保持向后兼容） ==========

def calculate_resource_suggestion(
    error_type: str,
    data_metrics: Dict[str, Any],
    current_config: Dict[str, str],
    cluster_limit: Dict[str, str]
) -> Dict[str, Any]:
    """
    计算资源建议（兼容旧接口）

    已废弃，建议使用 build_smart_resource_suggestion
    """
    return build_smart_resource_suggestion(
        error_type=error_type,
        current_config=current_config,
        data_metrics=data_metrics,
        historical_logs=None,
        current_data_size_mb=data_metrics.get("input_bytes_mb", 0),
    )


def build_resource_suggestion(
    error_type: str,
    current_config: Dict[str, str],
    data_metrics: Dict[str, Any],
    app_info: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    构建 Spark 资源建议（整合 memory_utilization_ratio 计算）

    Args:
        error_type: 错误类型
        current_config: 当前 Spark 配置
        data_metrics: 数据量指标
        app_info: App 信息

    Returns:
        资源建议字典或 None
    """
    # 非资源类错误不返回建议
    resource_errors = [
        "oom_executor", "oom_driver", "oom_driver_direct", "oom_offheap",
        "container_killed_memory", "gc_overhead",
        "shuffle_timeout", "shuffle_failed", "executor_lost_heartbeat",
        "driver_memory_insufficient", "executor_memory_insufficient"
    ]

    if error_type not in resource_errors:
        return None

    # ========== 1. 计算内存利用率（科学方法）==========
    # 支持多种 key 格式
    shuffle_write_mb = data_metrics.get("shuffle_write_mb", 0)
    if not shuffle_write_mb:
        shuffle_write_mb = data_metrics.get("shuffle_write", 0)
    if not shuffle_write_mb:
        shuffle_write_bytes = data_metrics.get("shuffle_write_bytes", 0)
        if shuffle_write_bytes > 0:
            shuffle_write_mb = shuffle_write_bytes / 1024 / 1024

    # 计算当前配置的内存利用率
    utilization = calculate_memory_utilization_ratio(current_config, shuffle_write_mb)

    reasoning_parts = []
    method = "rule_engine"
    confidence = "LOW"

    # ========== 2. 根据状态决定建议策略 ==========
    suggested_config = {}

    status = utilization.get("status", "unknown")

    if status == "risky":
        # 风险配置：无余量，必须增加
        reasoning_parts.append(f"内存利用率 {utilization['ratio']:.1f}x 过低，无余量应对数据波动")
        confidence = "HIGH"
    elif status == "need_increase":
        # 需要调整：低于推荐范围
        reasoning_parts.append(f"内存利用率 {utilization['ratio']:.1f}x 低于推荐范围 (1.5-2.0x)")
        confidence = "MEDIUM"
    elif status == "optimal":
        # 配置合理，但如果是 OOM 错误，仍需要调整
        if error_type in ["oom_executor", "container_killed_memory", "gc_overhead"]:
            reasoning_parts.append(f"内存利用率 {utilization['ratio']:.1f}x 在推荐范围内，但发生了 OOM")
            confidence = "MEDIUM"
        else:
            # 配置合理，无需调整
            return None
    elif status in ["slightly_over", "over_configured"]:
        # 过剩配置：但如果是 OOM，说明利用率计算有问题（可能单Task数据过大）
        if error_type in ["oom_executor", "container_killed_memory"]:
            reasoning_parts.append(f"内存利用率显示过剩，但发生了 OOM（可能是单Task数据过大）")
            confidence = "MEDIUM"
        else:
            # 真正过剩，建议降低
            reasoning_parts.append(f"内存利用率 {utilization['ratio']:.1f}x 过高，资源配置过剩")
            confidence = "LOW"

    # ========== 3. 使用均衡配置计算建议 ==========
    if shuffle_write_mb > 0:
        # 使用均衡配置计算
        balanced = calculate_balanced_config(shuffle_write_mb, target_ratio=1.5, current_config=current_config)

        suggested_config["executor_memory"] = balanced["executor_memory"]
        suggested_config["executor_instances"] = balanced["executor_instances"]

        reasoning_parts.append(balanced["reasoning"])
        method = "balanced_config"

        # 添加利用率信息
        reasoning_parts.append(f"推荐利用率 {balanced['actual_ratio']:.1f}x")
    else:
        # 无 Shuffle 数据，使用传统方法
        result = build_smart_resource_suggestion(
            error_type=error_type,
            current_config=current_config,
            data_metrics=data_metrics,
            historical_logs=None,
            current_data_size_mb=data_metrics.get("input_bytes_mb", 0),
        )

        suggested_config = result.get("suggested_config", {})
        reasoning_parts.append(result.get("reasoning", ""))
        method = result.get("method", "rule_engine")
        confidence = result.get("confidence", "LOW")

    if not suggested_config:
        return None

    return {
        "suggested_config": suggested_config,
        "reasoning": " | ".join(reasoning_parts),
        "current_config": current_config,
        "method": method,
        "confidence": confidence,
        "utilization": utilization,  # 返回利用率详情
    }


__all__ = [
    # 工具函数
    "parse_memory_to_mb",
    "format_memory_from_mb",
    # 核心计算函数
    "predict_config_from_history",
    "calculate_driver_suggestion",
    "calculate_executor_memory_suggestion",
    "calculate_executor_instances_suggestion",
    # 新增：科学计算方法
    "calculate_memory_utilization_ratio",
    "calculate_balanced_config",
    # 主入口函数
    "build_smart_resource_suggestion",
    # 兼容旧接口
    "calculate_resource_suggestion",
    "build_resource_suggestion",
]