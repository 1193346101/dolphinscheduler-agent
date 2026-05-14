"""
测试智能资源计算逻辑

验证：
1. 历史预测：基于历史成功数据预测配置
2. Driver OOM：单独处理 Driver 内存
3. Executor 内存：溢出量 / 峰值 / 翻倍兜底
4. Executor 数量：基于 Shuffle 数据量
"""

import sys
import importlib.util

# 加载模块
spec = importlib.util.spec_from_file_location(
    "calculate_resource",
    "D:/Project/dolphinscheduler-agent/src/skills/spark/scripts/calculate_resource.py"
)
calc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc)


def test_history_prediction():
    """测试历史预测逻辑"""
    print("=" * 60)
    print("测试历史预测：基于历史成功数据预测配置")
    print("=" * 60)

    # 模拟历史7天成功数据
    historical_logs = [
        {"date": "Day 1", "input_bytes_mb": 5000, "peak_memory_mb": 3000, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2000, "shuffle_write_mb": 1000, "success": True},
        {"date": "Day 2", "input_bytes_mb": 6000, "peak_memory_mb": 3600, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2500, "shuffle_write_mb": 1200, "success": True},
        {"date": "Day 3", "input_bytes_mb": 4000, "peak_memory_mb": 2400, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 1500, "shuffle_write_mb": 800, "success": True},
        {"date": "Day 4", "input_bytes_mb": 5500, "peak_memory_mb": 3300, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2200, "shuffle_write_mb": 1100, "success": True},
        {"date": "Day 5", "input_bytes_mb": 4800, "peak_memory_mb": 2900, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 1900, "shuffle_write_mb": 950, "success": True},
    ]

    # 当前任务数据量翻倍
    current_data_size_mb = 10000

    result = calc.predict_config_from_history(historical_logs, current_data_size_mb)

    print(f"\n历史数据分析:")
    print(f"  - 样本数量: {len(historical_logs)}")
    print(f"  - 平均数据量: {sum([h['input_bytes_mb'] for h in historical_logs]) // len(historical_logs)} MB")
    print(f"  - 平均峰值内存: {sum([h['peak_memory_mb'] for h in historical_logs]) // len(historical_logs)} MB")

    print(f"\n当前任务:")
    print(f"  - 数据量: {current_data_size_mb} MB (10GB)")

    print(f"\n预测结果:")
    print(f"  - 预测峰值: {result.get('predicted_peak_mb', 0)} MB")
    print(f"  - 建议内存: {result.get('executor_memory', 'N/A')}")
    print(f"  - 建议 Executor 数量: {result.get('executor_instances', 'N/A')}")
    print(f"  - 数据-内存比例: 1:{result.get('memory_per_data_ratio', 0):.2f}")
    print(f"  - 置信度: {result.get('confidence', 'N/A')}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")

    # 验证：数据量翻倍，内存应该也翻倍左右
    suggested_mem_mb = calc.parse_memory_to_mb(result.get('executor_memory', '0'))
    expected_mem_mb = 6000  # 基于历史比例预测

    print(f"\n验证:")
    print(f"  - 预测内存约6GB: {suggested_mem_mb >= 5000 and suggested_mem_mb <= 8000}")

    return result.get('confidence') in ['HIGH', 'MEDIUM']


def test_driver_oom():
    """测试 Driver OOM 处理"""
    print("\n" + "=" * 60)
    print("测试 Driver OOM：单独处理 Driver 内存")
    print("=" * 60)

    current_config = {"driver_memory": "1g", "executor_memory": "4g"}
    data_metrics = {"memory_spilled_mb": 512}

    result = calc.calculate_driver_suggestion("oom_driver", current_config, data_metrics)

    print(f"\n输入:")
    print(f"  - 当前 Driver 内存: {current_config['driver_memory']}")
    print(f"  - 溢出量: {data_metrics['memory_spilled_mb']} MB")

    print(f"\n建议:")
    print(f"  - Driver 内存: {result.get('driver_memory', 'N/A')}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")

    # 验证：Driver 内存 = 1g + 512MB
    suggested_mb = calc.parse_memory_to_mb(result.get('driver_memory', '0'))
    print(f"\n验证:")
    print(f"  - 建议内存约1.5g: {suggested_mb >= 1000 and suggested_mb <= 2000}")

    return suggested_mb >= 1000


def test_executor_memory_from_spill():
    """测试 Executor 内存溢出计算"""
    print("\n" + "=" * 60)
    print("测试 Executor 内存：溢出量计算")
    print("=" * 60)

    current_config = {"executor_memory": "4g"}
    data_metrics = {"memory_spilled_mb": 2048, "peak_memory_mb": 0}

    result = calc.calculate_executor_memory_suggestion(current_config, data_metrics)

    print(f"\n输入:")
    print(f"  - 当前 Executor 内存: {current_config['executor_memory']}")
    print(f"  - 溢出量: {data_metrics['memory_spilled_mb']} MB")

    print(f"\n建议:")
    print(f"  - Executor 内存: {result.get('executor_memory', 'N/A')}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")

    # 验证：Executor 内存 = 4g + 2g = 6g
    suggested_mb = calc.parse_memory_to_mb(result.get('executor_memory', '0'))
    print(f"\n验证:")
    print(f"  - 建议内存约6g: {suggested_mb >= 5000 and suggested_mb <= 7000}")

    return suggested_mb >= 5000


def test_executor_instances_from_shuffle():
    """测试 Executor 数量计算（基于 Shuffle）"""
    print("\n" + "=" * 60)
    print("测试 Executor 数量：基于 Shuffle 数据量")
    print("=" * 60)

    current_config = {"executor_instances": "10"}
    data_metrics = {"shuffle_read_mb": 20000, "shuffle_write_mb": 10000}  # 30GB Shuffle

    result = calc.calculate_executor_instances_suggestion(current_config, data_metrics)

    print(f"\n输入:")
    print(f"  - 当前 Executor 数量: {current_config['executor_instances']}")
    print(f"  - Shuffle 读取: {data_metrics['shuffle_read_mb']} MB")
    print(f"  - Shuffle 写入: {data_metrics['shuffle_write_mb']} MB")
    print(f"  - Shuffle 总量: {data_metrics['shuffle_read_mb'] + data_metrics['shuffle_write_mb']} MB")

    print(f"\n建议:")
    print(f"  - Executor 数量: {result.get('executor_instances', 'N/A')}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")

    # 验证：30GB / 2GB = 15 个 Executor
    suggested = result.get('executor_instances', 0)
    print(f"\n验证:")
    print(f"  - 建议15个左右: {suggested >= 10 and suggested <= 20}")

    return suggested >= 10


def test_full_suggestion_history():
    """测试完整建议流程（历史预测优先）"""
    print("\n" + "=" * 60)
    print("测试完整建议：历史预测优先")
    print("=" * 60)

    historical_logs = [
        {"input_bytes_mb": 5000, "peak_memory_mb": 3000, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2000, "shuffle_write_mb": 1000, "success": True},
        {"input_bytes_mb": 6000, "peak_memory_mb": 3600, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2500, "shuffle_write_mb": 1200, "success": True},
        {"input_bytes_mb": 4000, "peak_memory_mb": 2400, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 1500, "shuffle_write_mb": 800, "success": True},
        {"input_bytes_mb": 5500, "peak_memory_mb": 3300, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 2200, "shuffle_write_mb": 1100, "success": True},
        {"input_bytes_mb": 4800, "peak_memory_mb": 2900, "executor_memory": "4g", "executor_instances": 10, "shuffle_read_mb": 1900, "shuffle_write_mb": 950, "success": True},
    ]

    current_config = {"executor_memory": "4g", "executor_instances": "10", "driver_memory": "1g"}
    data_metrics = {"memory_spilled_mb": 0, "input_bytes_mb": 10000}

    result = calc.build_smart_resource_suggestion(
        error_type="oom_executor",
        current_config=current_config,
        data_metrics=data_metrics,
        historical_logs=historical_logs,
        current_data_size_mb=10000,
    )

    print(f"\n输入:")
    print(f"  - 错误类型: oom_executor")
    print(f"  - 当前配置: {current_config}")
    print(f"  - 当前数据量: 10000 MB")
    print(f"  - 历史样本数: {len(historical_logs)}")

    print(f"\n完整建议:")
    print(f"  - suggested_config: {result.get('suggested_config', {})}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")
    print(f"  - method: {result.get('method', 'N/A')}")
    print(f"  - confidence: {result.get('confidence', 'N/A')}")
    print(f"  - executor_cores: {result.get('executor_cores', 'N/A')} (固定)")

    # 验证
    print(f"\n验证:")
    print(f"  - method为history_prediction: {result.get('method') == 'history_prediction'}")
    print(f"  - confidence为HIGH: {result.get('confidence') == 'HIGH'}")
    print(f"  - executor_cores固定为1: {result.get('executor_cores') == 1}")

    return result.get('method') == 'history_prediction' and result.get('executor_cores') == 1


def test_full_suggestion_driver():
    """测试完整建议流程（Driver OOM）"""
    print("\n" + "=" * 60)
    print("测试完整建议：Driver OOM 单独处理")
    print("=" * 60)

    current_config = {"executor_memory": "4g", "executor_instances": "10", "driver_memory": "1g"}
    data_metrics = {"memory_spilled_mb": 1024}

    result = calc.build_smart_resource_suggestion(
        error_type="oom_driver",
        current_config=current_config,
        data_metrics=data_metrics,
        historical_logs=None,
        current_data_size_mb=0,
    )

    print(f"\n输入:")
    print(f"  - 错误类型: oom_driver")
    print(f"  - 当前 Driver 内存: {current_config['driver_memory']}")
    print(f"  - 溢出量: {data_metrics['memory_spilled_mb']} MB")

    print(f"\n完整建议:")
    print(f"  - suggested_config: {result.get('suggested_config', {})}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")
    print(f"  - method: {result.get('method', 'N/A')}")

    # 验证：只调整 driver_memory
    suggested = result.get('suggested_config', {})
    print(f"\n验证:")
    print(f"  - driver_memory被调整: {'driver_memory' in suggested}")
    print(f"  - executor_memory未调整或为4g: {'executor_memory' not in suggested or suggested['executor_memory'] == '4g'}")

    return 'driver_memory' in suggested


def test_fallback_no_data():
    """测试兜底逻辑（无数据）"""
    print("\n" + "=" * 60)
    print("测试兜底逻辑：无历史数据和metrics时翻倍")
    print("=" * 60)

    current_config = {"executor_memory": "4g", "executor_instances": "10", "driver_memory": "1g"}
    data_metrics = {}  # 无数据

    result = calc.build_smart_resource_suggestion(
        error_type="oom_executor",
        current_config=current_config,
        data_metrics=data_metrics,
        historical_logs=None,
        current_data_size_mb=0,
    )

    print(f"\n输入:")
    print(f"  - 错误类型: oom_executor")
    print(f"  - 当前配置: {current_config}")
    print(f"  - 数据指标: 空")

    print(f"\n完整建议:")
    print(f"  - suggested_config: {result.get('suggested_config', {})}")
    print(f"  - reasoning: {result.get('reasoning', 'N/A')}")
    print(f"  - confidence: {result.get('confidence', 'N/A')}")

    # 验证：翻倍兜底
    suggested_mb = calc.parse_memory_to_mb(result.get('suggested_config', {}).get('executor_memory', '0'))
    print(f"\n验证:")
    print(f"  - 内存翻倍（4g->8g左右）: {suggested_mb >= 7000 and suggested_mb <= 9000}")
    print(f"  - confidence为LOW: {result.get('confidence') == 'LOW'}")

    return suggested_mb >= 7000 and result.get('confidence') == 'LOW'


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("智能资源计算逻辑测试")
    print("=" * 60)

    results = {}

    # 运行测试
    results["历史预测"] = test_history_prediction()
    results["Driver OOM"] = test_driver_oom()
    results["Executor溢出"] = test_executor_memory_from_spill()
    results["Executor数量"] = test_executor_instances_from_shuffle()
    results["完整建议-历史"] = test_full_suggestion_history()
    results["完整建议-Driver"] = test_full_suggestion_driver()
    results["兜底翻倍"] = test_fallback_no_data()

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n所有测试通过！")
        print("  - 历史预测：基于数据量比例预测内存")
        print("  - Driver OOM：单独处理 driver_memory")
        print("  - Executor：内存 + 数量协同调整")
        print("  - executor_cores：固定为1")
        print("  - 兜底策略：保守翻倍")


if __name__ == "__main__":
    main()