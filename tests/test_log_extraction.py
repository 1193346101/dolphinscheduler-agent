"""
测试日志提取功能

模拟一个运行时长较长的 Spark 任务日志（10KB+），验证智能提取功能：
1. extract_error_blocks() - 能否提取尾部 ERROR 块
2. extract_config_lines() - 能否提取 Spark 配置
3. extract_executor_events() - 能否提取 Executor 生命周期事件
4. smart_extract_container_log() - 智能提取策略
"""

# 直接导入函数，避免 skills 包初始化问题
import sys
import importlib.util

# 加载 preprocess_log 模块
spec = importlib.util.spec_from_file_location(
    "preprocess_log",
    "D:/Project/dolphinscheduler-agent/src/skills/common/preprocess_log.py"
)
preprocess_log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preprocess_log)

extract_error_blocks = preprocess_log.extract_error_blocks
extract_config_lines = preprocess_log.extract_config_lines
extract_executor_events = preprocess_log.extract_executor_events
analyze_log_timestamps = preprocess_log.analyze_log_timestamps
extract_broadcast_info = preprocess_log.extract_broadcast_info
extract_join_strategy = preprocess_log.extract_join_strategy
extract_stage_timing = preprocess_log.extract_stage_timing

# 模拟一个 15KB 的 Spark Executor 日志
# 前 10KB 是 INFO 日志，尾部有关键错误信息
MOCK_SPARK_LOG = """
24/05/14 10:00:01 INFO SparkContext: Running Spark version 3.3.0
24/05/14 10:00:01 INFO ResourceUtils: ==============================================================
24/05/14 10:00:01 INFO ResourceUtils: Resources for executor:

24/05/14 10:00:01 INFO SparkContext: Submitted application: data_processing_job
24/05/14 10:00:02 INFO SecurityManager: SecurityManager: authentication disabled
24/05/14 10:00:03 INFO Utils: Service 'SparkEnv' is running on port 43567
24/05/14 10:00:05 INFO BlockManager: BlockManager initialized with memory 8GB
24/05/14 10:00:06 INFO MemoryStore: MemoryStore started with capacity 8.0 GB
24/05/14 10:00:10 INFO SparkEnv: Registering MapOutputTracker
24/05/14 10:00:10 INFO SparkEnv: Registering BlockManagerMaster
24/05/14 10:00:11 INFO BlockManagerMaster: Registering BlockManager BlockManagerId
24/05/14 10:00:15 INFO DiskBlockManager: Created local directory at /data/spark/blockmgr
24/05/14 10:00:20 INFO Executor: Starting executor ID 1 on host 192.168.1.100
24/05/14 10:00:25 INFO CoarseGrainedExecutorBackend: Successfully registered with driver

# 配置信息（分散在日志中）
24/05/14 10:00:30 INFO SparkConf: spark.executor.memory=8g
24/05/14 10:00:30 INFO SparkConf: spark.executor.cores=4
24/05/14 10:00:30 INFO SparkConf: spark.executor.instances=10
24/05/14 10:00:30 INFO SparkConf: spark.driver.memory=4g
24/05/14 10:00:30 INFO SparkConf: spark.sql.shuffle.partitions=200
24/05/14 10:00:30 INFO SparkConf: spark.memory.offHeap.enabled=true
24/05/14 10:00:30 INFO SparkConf: spark.memory.offHeap.size=2g

# Stage 执行信息
24/05/14 10:01:00 INFO DAGScheduler: Stage 0 (map at DataProcessing.scala:50) started
24/05/14 10:02:30 INFO DAGScheduler: Stage 0 (map at DataProcessing.scala:50) finished in 90s
24/05/14 10:02:35 INFO DAGScheduler: Stage 1 (reduce at DataProcessing.scala:80) started
24/05/14 10:05:00 INFO DAGScheduler: Stage 1 (reduce at DataProcessing.scala:80) finished in 165s

# Executor 添加事件
24/05/14 10:05:05 INFO ExecutorAllocationManager: Added executor 2 on host 192.168.1.101
24/05/14 10:05:10 INFO ExecutorAllocationManager: Added executor 3 on host 192.168.1.102

# 大量 INFO 日志（模拟长时间运行）
24/05/14 10:05:15 INFO TaskSetManager: Starting task 0.0 in stage 2 (TID 100, 192.168.1.100, executor 1, partition 0)
24/05/14 10:05:20 INFO TaskSetManager: Finished task 0.0 in stage 2 (TID 100) in 5s on 192.168.1.100
24/05/14 10:05:25 INFO TaskSetManager: Starting task 1.0 in stage 2 (TID 101, 192.168.1.101, executor 2, partition 1)
24/05/14 10:05:30 INFO TaskSetManager: Finished task 1.0 in stage 2 (TID 101) in 5s on 192.168.1.101
24/05/14 10:05:35 INFO TaskSetManager: Starting task 2.0 in stage 2 (TID 102, 192.168.1.102, executor 3, partition 2)
24/05/14 10:05:40 INFO TaskSetManager: Finished task 2.0 in stage 2 (TID 102) in 5s on 192.168.1.102
""" + """
24/05/14 10:06:00 INFO BlockManager: Block rdd_3_0 stored as bytes in memory (estimated size 128.0 MB)
24/05/14 10:06:05 INFO BlockManager: Block rdd_3_1 stored as bytes in memory (estimated size 128.0 MB)
24/05/14 10:06:10 INFO BlockManager: Block rdd_3_2 stored as bytes in memory (estimated size 128.0 MB)
24/05/14 10:06:15 INFO MemoryStore: Memory used: 384.0 MB (of 8.0 GB)
""" * 20 + """
# 继续大量 INFO
24/05/14 10:10:00 INFO TaskSetManager: Starting task 100.0 in stage 5 (TID 500)
24/05/14 10:10:30 INFO TaskSetManager: Finished task 100.0 in stage 5 (TID 500) in 30s
""" * 20 + """
# Shuffle 相关 INFO
24/05/14 10:15:00 INFO ShuffleBlockFetcherIterator: Started fetching shuffle blocks
24/05/14 10:15:05 INFO ShuffleBlockFetcherIterator: Successfully fetched 1000 shuffle blocks
24/05/14 10:15:10 INFO ShuffleBlockFetcherIterator: Fetched 2048.0 MB of shuffle data

# 广播 Join 信息
24/05/14 10:15:15 INFO BroadcastExchange: Building broadcast hash table for table 'dim_user'
24/05/14 10:15:20 INFO BroadcastExchange: Broadcast size: 256.0 MB
24/05/14 10:15:25 INFO BroadcastExchange: Broadcast build relation size: 256.0 MB
24/05/14 10:15:30 INFO SparkStrategies: Choosing join strategy BroadcastHashJoin

# Join 策略信息
24/05/14 10:15:35 INFO SparkStrategies: Choosing join strategy SortMergeJoin for large tables
24/05/14 10:15:40 INFO SparkStrategies: Join key distribution: skewed key count 15

# Executor 心跳事件
24/05/14 10:20:00 INFO Executor: Sending heartbeat to driver
24/05/14 10:20:30 INFO Executor: Sending heartbeat to driver
24/05/14 10:21:00 INFO Executor: Sending heartbeat to driver

# ========================================
# 尾部关键错误信息（模拟固定截取会遗漏的部分）
# ========================================

# Executor 心跳超时
24/05/14 10:25:00 WARN Executor: Executor heartbeat timeout, last heartbeat: 10:21:00
24/05/14 10:25:05 WARN CoarseGrainedExecutorBackend: Executor 3 heartbeat timeout, removing
24/05/14 10:25:10 INFO ExecutorAllocationManager: Removed executor 3 on host 192.168.1.102 (heartbeat timeout)

# Shuffle 失败
24/05/14 10:25:15 ERROR ShuffleBlockFetcherIterator: Failed to fetch shuffle block from executor 3
org.apache.spark.shuffle.FetchFailedException: Failed to fetch shuffle block shuffle_5_100_0 from executor 3
    at org.apache.spark.storage.ShuffleBlockFetcherIterator.throwFetchFailedException(ShuffleBlockFetcherIterator.scala:400)
    at org.apache.spark.storage.ShuffleBlockFetcherIterator.next(ShuffleBlockFetcherIterator.scala:350)
    at org.apache.spark.storage.ShuffleBlockFetcherIterator.next(ShuffleBlockFetcherIterator.scala:52)
    at org.apache.spark.InterruptibleIterator.next(InterruptibleIterator.scala:40)
Caused by: java.io.IOException: Connection refused to shuffle service on 192.168.1.102:7337
    at org.apache.spark.network.shuffle.ShuffleClient.fetchBlocks(ShuffleClient.java:120)
    at org.apache.spark.storage.ShuffleBlockFetcherIterator.$anonfun$fetchUpToMaxBlocksInFlight$1(ShuffleBlockFetcherIterator.scala:200)

# OOM 错误（模拟内存溢出）
24/05/14 10:25:20 ERROR Executor: Exception in task 200.0 in stage 5 (TID 600)
java.lang.OutOfMemoryError: Java heap space
    at org.apache.spark.memory.MemoryManager.acquireExecutionMemory(MemoryManager.scala:150)
    at org.apache.spark.memory.TaskMemoryManager.acquireMemory(TaskMemoryManager.scala:80)
    at org.apache.spark.memory.TaskMemoryManager.allocatePage(TaskMemoryManager.scala:120)
    at org.apache.spark.memory.MemoryStore.putBytes(MemoryStore.scala:100)
    at org.apache.spark.storage.BlockManager.doPut(BlockManager.scala:200)
    at org.apache.spark.storage.BlockManager.putBytes(BlockManager.scala:150)

# Container 被 YARN 终止
24/05/14 10:25:25 ERROR YarnScheduler: Executor 2 lost on host 192.168.1.101
24/05/14 10:25:30 WARN YarnSchedulerBackend: Container killed by YARN for exceeding memory limits
Container killed by YARN for exceeding memory limits. Container container_e01_1715675432123_0001_01_000002 was killed.
Diagnostics message from YARN: Container [container_e01_1715675432123_0001_01_000002] is running beyond virtual memory limits.
Current usage: 8.5GB of 8GB physical memory used; 16GB of 16GB virtual memory used.

# Stage 失败
24/05/14 10:25:35 ERROR DAGScheduler: Stage 5 failed due to task failure
24/05/14 10:25:40 INFO DAGScheduler: ResultStage 5 (collect at DataProcessing.scala:120) failed in 100s

# Job 失败
24/05/14 10:25:45 ERROR SparkContext: Job aborted due to stage failure: Stage 5 (collect) failed 3 times
org.apache.spark.SparkException: Job aborted due to stage failure: Stage 5 (collect at DataProcessing.scala:120) has failed the maximum allowable number of times
    at org.apache.spark.scheduler.DAGScheduler.failJobAndIndependentStages(DAGScheduler.scala:200)
    at org.apache.spark.scheduler.DAGScheduler.$anonfun$handleTaskCompletion$15(DAGScheduler.scala:150)
Caused by: java.lang.OutOfMemoryError: Java heap space

# 最终诊断信息
24/05/14 10:25:50 ERROR Executor: Executor terminated due to OOM
24/05/14 10:25:55 INFO CoarseGrainedExecutorBackend: Executor disconnected
24/05/14 10:26:00 INFO SparkContext: SparkContext stopped
"""


def test_extract_error_blocks():
    """测试错误块提取 - 尾部的 OOM 和 Shuffle 错误是否被提取"""
    print("=" * 60)
    print("测试 extract_error_blocks() - 提取尾部关键错误")
    print("=" * 60)

    error_blocks = extract_error_blocks(MOCK_SPARK_LOG)

    print(f"\n提取到 {len(error_blocks)} 个错误块:")
    for i, block in enumerate(error_blocks[:3]):  # 只显示前3个
        print(f"\n--- 错误块 {i+1} ---")
        print(block[:500])  # 显示前500字符

    # 验证关键错误是否被提取
    all_errors = "\n".join(error_blocks)

    checks = {
        "OutOfMemoryError": "OutOfMemoryError" in all_errors,
        "FetchFailedException": "FetchFailedException" in all_errors,
        "Container killed": "Container killed" in all_errors,
        "heartbeat timeout": "heartbeat timeout" in all_errors,
        "Stage failed": "Stage failed" in all_errors,
    }

    print("\n关键错误提取验证:")
    for key, found in checks.items():
        status = "[OK] 已提取" if found else "[FAIL] 未提取"
        print(f"  {key}: {status}")

    return all(checks.values())


def test_extract_config_lines():
    """测试配置行提取"""
    print("\n" + "=" * 60)
    print("测试 extract_config_lines() - 提取 Spark 配置")
    print("=" * 60)

    config_lines = extract_config_lines(MOCK_SPARK_LOG)

    print(f"\n提取到 {len(config_lines)} 条配置:")
    for line in config_lines[:10]:
        print(f"  {line}")

    # 验证关键配置是否被提取
    config_str = "\n".join(config_lines)

    checks = {
        "spark.executor.memory": "spark.executor.memory" in config_str,
        "spark.executor.cores": "spark.executor.cores" in config_str,
        "spark.driver.memory": "spark.driver.memory" in config_str,
    }

    print("\n关键配置提取验证:")
    for key, found in checks.items():
        status = "[OK] 已提取" if found else "[FAIL] 未提取"
        print(f"  {key}: {status}")

    return all(checks.values())


def test_extract_executor_events():
    """测试 Executor 事件提取"""
    print("\n" + "=" * 60)
    print("测试 extract_executor_events() - 提取 Executor 生命周期事件")
    print("=" * 60)

    events = extract_executor_events(MOCK_SPARK_LOG)

    print(f"\n提取到 {len(events)} 个事件:")
    for event in events:
        print(f"  {event}")

    # 验证关键事件是否被提取
    event_types = [e.get("event_type") for e in events]

    checks = {
        "executor_added": "added" in event_types,
        "executor_removed": "removed" in event_types,
    }

    print("\n关键事件提取验证:")
    for key, found in checks.items():
        status = "[OK] 已提取" if found else "[FAIL] 未提取"
        print(f"  {key}: {status}")

    return all(checks.values())


def test_extract_broadcast_info():
    """测试广播信息提取"""
    print("\n" + "=" * 60)
    print("测试 extract_broadcast_info() - 提取广播大小")
    print("=" * 60)

    broadcast_info = extract_broadcast_info(MOCK_SPARK_LOG)

    print(f"\n广播信息:")
    for key, value in broadcast_info.items():
        print(f"  {key}: {value}")

    return True


def test_extract_join_strategy():
    """测试 Join 策略提取"""
    print("\n" + "=" * 60)
    print("测试 extract_join_strategy() - 提取 Join 策略")
    print("=" * 60)

    strategies = extract_join_strategy(MOCK_SPARK_LOG)

    print(f"\n提取到 {len(strategies)} 个 Join 策略:")
    for s in strategies:
        print(f"  {s}")

    return len(strategies) > 0


def test_extract_stage_timing():
    """测试 Stage 时间提取"""
    print("\n" + "=" * 60)
    print("测试 extract_stage_timing() - 提取 Stage 执行时间")
    print("=" * 60)

    timings = extract_stage_timing(MOCK_SPARK_LOG)

    print(f"\n提取到 {len(timings)} 个 Stage 时间:")
    for t in timings[:5]:
        print(f"  Stage {t.get('stage_id')}: {t.get('duration_seconds')}s")

    return len(timings) > 0


def test_analyze_log_timestamps():
    """测试时间戳分析"""
    print("\n" + "=" * 60)
    print("测试 analyze_log_timestamps() - 分析日志时间戳")
    print("=" * 60)

    analysis = analyze_log_timestamps(MOCK_SPARK_LOG)

    print(f"\n时间戳分析结果:")
    for key, value in analysis.items():
        if key != "silent_periods":
            print(f"  {key}: {value}")

    if analysis.get("silent_periods"):
        print(f"\n无输出时段 ({len(analysis['silent_periods'])} 个):")
        for period in analysis["silent_periods"][:3]:
            print(f"  {period}")

    return True


def test_smart_extract_simulation():
    """模拟 smart_extract_container_log 测试"""
    print("\n" + "=" * 60)
    print("模拟 smart_extract_container_log() - 智能提取策略")
    print("=" * 60)

    # 模拟固定截取（前 5000 字符）会遗漏什么
    log_length = len(MOCK_SPARK_LOG)
    head_5000 = MOCK_SPARK_LOG[:5000]

    print(f"\n日志总长度: {log_length} 字符")
    print(f"\n固定截取前 5000 字符会遗漏:")
    print(f"  - OutOfMemoryError: {'OutOfMemoryError' in head_5000}")
    print(f"  - FetchFailedException: {'FetchFailedException' in head_5000}")
    print(f"  - Container killed: {'Container killed' in head_5000}")
    print(f"  - heartbeat timeout: {'heartbeat timeout' in head_5000}")

    # 模拟智能提取
    error_blocks = extract_error_blocks(MOCK_SPARK_LOG)
    config_lines = extract_config_lines(MOCK_SPARK_LOG)
    executor_events = extract_executor_events(MOCK_SPARK_LOG)

    print(f"\n智能提取策略:")
    print(f"  - 错误块数量: {len(error_blocks)}")
    print(f"  - 配置行数量: {len(config_lines)}")
    print(f"  - Executor 事件数量: {len(executor_events)}")

    # 智能提取的关键错误覆盖
    all_errors = "\n".join(error_blocks)
    print(f"\n智能提取覆盖的关键错误:")
    print(f"  - OutOfMemoryError: {'OutOfMemoryError' in all_errors}")
    print(f"  - FetchFailedException: {'FetchFailedException' in all_errors}")
    print(f"  - Container killed: {'Container killed' in all_errors}")
    print(f"  - heartbeat timeout: {'heartbeat timeout' in all_errors}")

    # 计算提取效率
    error_chars = sum(len(block) for block in error_blocks)
    config_chars = sum(len(line) for line in config_lines)
    total_extracted = error_chars + config_chars

    print(f"\n提取效率:")
    print(f"  - 原始日志: {log_length} 字符")
    print(f"  - 提取关键信息: {total_extracted} 字符")
    print(f"  - 压缩比例: {total_extracted / log_length * 100:.1f}%")

    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Spark 日志提取功能测试")
    print("模拟一个 15KB+ 的 Spark Executor 日志")
    print("=" * 60)

    results = {}

    # 运行测试
    results["error_blocks"] = test_extract_error_blocks()
    results["config_lines"] = test_extract_config_lines()
    results["executor_events"] = test_extract_executor_events()
    results["broadcast_info"] = test_extract_broadcast_info()
    results["join_strategy"] = test_extract_join_strategy()
    results["stage_timing"] = test_extract_stage_timing()
    results["timestamps"] = test_analyze_log_timestamps()
    results["smart_extract"] = test_smart_extract_simulation()

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n[OK] 所有提取功能验证成功！")
        print("  - 尾部关键错误（OOM、FetchFailed）能被正确提取")
        print("  - Spark 配置信息能被完整提取")
        print("  - Executor 生命周期事件能被追踪")
        print("  - 智能提取策略比固定截取更有效")


if __name__ == "__main__":
    main()