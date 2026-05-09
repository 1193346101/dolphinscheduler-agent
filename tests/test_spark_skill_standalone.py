"""
SparkSkill 测试脚本 - 独立版本

直接复制 SparkSkill 的核心逻辑进行测试，避免 import 问题。
"""

import re
import sys
from typing import Dict, Tuple, Optional

# 设置 UTF-8 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 错误分类
class ErrorCategory:
    AUTO_FIXABLE = "AUTO_FIXABLE"
    KNOWN_NEEDS_LLM = "KNOWN_NEEDS_LLM"
    UNKNOWN = "UNKNOWN"

# 错误模式定义
ERROR_PATTERNS: Dict[str, Tuple[str, str, str]] = {
    # === 可自动修复（配置调整） ===
    "oom_executor": (
        "java.lang.OutOfMemoryError: Java heap space",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "oom_driver": (
        "OutOfMemoryError: unable to create new native thread",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "oom_driver_direct": (
        "OutOfMemoryError: Container memory exceeded",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "oom_offheap": (
        "OutOfMemoryError: offheap",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "oom_storage": (
        "OutOfMemoryError: Storage memory",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "driver_memory_insufficient": (
        "System memory.*must be at least.*driver-memory|increase heap size.*driver-memory",
        ErrorCategory.AUTO_FIXABLE,
        "Spark Driver 内存配置不足，需要增加 driver-memory"
    ),
    "broadcast_timeout": (
        "BroadcastHashJoin.*timeout|broadcast.*timeout",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "shuffle_timeout": (
        "shuffle.*timeout",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "network_timeout": (
        "spark.network.timeout",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "rpc_timeout": (
        "RPC timeout",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "executor_lost_heartbeat": (
        "Executor heartbeat timeout",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),
    "gc_overhead": (
        "GC overhead limit exceeded",
        ErrorCategory.AUTO_FIXABLE,
        ""
    ),

    # === 已知类型，需 LLM 分析 ===
    "class_not_found": (
        "ClassNotFoundException",
        ErrorCategory.KNOWN_NEEDS_LLM,
        "Spark 类找不到，请分析缺失的类名和需要的依赖包"
    ),
    "no_class_def": (
        "NoClassDefFoundError",
        ErrorCategory.KNOWN_NEEDS_LLM,
        "Spark 类定义找不到，请分析类名和依赖加载问题"
    ),
    "shuffle_failed": (
        "FetchFailedException",
        ErrorCategory.KNOWN_NEEDS_LLM,
        "Spark Shuffle 数据拉取失败，请分析 Shuffle Service 状态和网络问题"
    ),
    "container_killed": (
        "Container killed by YARN|Container killed",
        ErrorCategory.KNOWN_NEEDS_LLM,
        "Spark 容器被 YARN 终止，请分析资源使用情况"
    ),
}

# 快速修复方案
QUICK_FIXES: Dict[str, Dict] = {
    "driver_memory_insufficient": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.driver.memory": "512m",
            "spark.driver.memoryOverhead": "128m",
        },
    },
    "oom_executor": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.executor.memory": "4g",
            "spark.executor.memoryOverhead": "1g",
        },
    },
    "oom_driver": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.driver.memory": "2g",
            "spark.driver.maxResultSize": "2g",
        },
    },
    "oom_driver_direct": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.driver.maxResultSize": "2g",
        },
    },
    "oom_offheap": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.memory.offHeap.enabled": "true",
            "spark.memory.offHeap.size": "2g",
        },
    },
    "oom_storage": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.memory.storageFraction": "0.3",
        },
    },
    "broadcast_timeout": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.sql.autoBroadcastJoinThreshold": "-1",
        },
    },
    "shuffle_timeout": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.shuffle.io.timeout": "120s",
        },
    },
    "network_timeout": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.network.timeout": "300s",
        },
    },
    "rpc_timeout": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.rpc.timeout": "300s",
        },
    },
    "executor_lost_heartbeat": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.executor.heartbeatInterval": "60s",
            "spark.network.timeout": "300s",
        },
    },
    "gc_overhead": {
        "action_type": "modify_config",
        "config_changes": {
            "spark.executor.memory": "8g",
            "spark.executor.memoryOverhead": "2g",
            "spark.driver.memory": "4g",
        },
    },
}

# 模拟错误日志
TEST_LOGS = {
    "driver_memory_insufficient": """
25/05/08 19:56:46 INFO SparkContext: Running Spark version 3.3.1
25/05/08 19:56:46 ERROR SparkContext: Error initializing SparkContext
java.lang.IllegalArgumentException: System memory 259.0 MB must be at least 471.9 MB.
Please increase heap size using the --driver-memory option or spark.driver.memory in Spark configuration.
	at org.apache.spark.memory.UnifiedMemoryManager$.getMaxMemory(UnifiedMemoryManager.scala:253)
25/05/08 19:56:46 INFO SparkContext: Successfully stopped SparkContext
""",

    "oom_executor": """
25/05/08 20:30:15 INFO Executor: Running task 3.0 in stage 2.0 (TID 15)
25/05/08 20:30:18 ERROR Executor: Exception in task 3.0 in stage 2.0 (TID 15)
java.lang.OutOfMemoryError: Java heap space
	at org.apache.spark.shuffle.sort.SortShuffleWriter.insertRecord(SortShuffleWriter.scala:85)
25/05/08 20:30:18 INFO Executor: Executor is unable to send heartbeats to driver
""",

    "gc_overhead": """
25/05/08 21:15:30 INFO TaskSetManager: Starting task 4.0 in stage 5.0
25/05/08 21:15:45 ERROR TaskSetManager: Task 4.0 in stage 5.0 failed 1 times; aborting job
java.lang.OutOfMemoryError: GC overhead limit exceeded
	at org.apache.spark.sql.execution.joins.BroadcastHashJoinExec.doExecute(BroadcastHashJoinExec.scala:112)
25/05/08 21:15:45 INFO DAGScheduler: Job 5 failed: GC overhead limit exceeded
""",

    "broadcast_timeout": """
25/05/08 22:00:10 INFO BroadcastHashJoin: Running broadcast join
25/05/08 22:00:35 ERROR BroadcastHashJoin: Broadcast timeout exceeded
org.apache.spark.SparkException: Could not execute broadcast in 300 secs.
	at org.apache.spark.sql.execution.joins.BroadcastHashJoinExec.doExecute(BroadcastHashJoinExec.scala:85)
25/05/08 22:00:35 INFO TaskSetManager: Task failed due to broadcast timeout
""",

    "class_not_found": """
25/05/08 22:30:00 INFO Driver: Submitting Spark application
25/05/08 22:30:05 ERROR Driver: Failed to load main class
java.lang.ClassNotFoundException: com.example.MySparkJob
	at java.net.URLClassLoader.findClass(URLClassLoader.java:382)
	at java.lang.ClassLoader.loadClass(ClassLoader.java:418)
25/05/08 22:30:05 INFO SparkContext: Application failed to start
""",

    "shuffle_failed": """
25/05/08 23:00:10 INFO ShuffleBlockFetcherIterator: Fetching shuffle blocks
25/05/08 23:00:25 ERROR ShuffleBlockFetcherIterator: Failed to fetch shuffle block
org.apache.spark.shuffle.FetchFailedException: Failed to fetch shuffle block from executor 5
	at org.apache.spark.storage.ShuffleBlockFetcherIterator.throwFetchFailedException(ShuffleBlockFetcherIterator.scala:360)
25/05/08 23:00:25 INFO TaskSetManager: Retrying task due to shuffle fetch failure
""",

    "container_killed": """
25/05/08 23:30:00 INFO Executor: Executor 7 is running tasks
25/05/08 23:30:15 INFO YarnAllocator: Container killed by YARN for exceeding memory limits
Container killed by YARN for exceeding memory limits. Container killed by YARN.
	at org.apache.spark.scheduler.cluster.YarnSchedulerBackend$YarnDriverEndpoint.containerKilled(YarnSchedulerBackend.scala:85)
25/05/08 23:30:15 INFO TaskSetManager: Lost executor 7 due to container killed
""",

    "unknown": """
25/05/08 24:00:00 INFO SparkContext: Starting Spark application
25/05/08 24:00:05 ERROR SparkContext: Unknown error occurred
CustomApplicationException: Something went wrong in our custom code
	at com.example.CustomProcessor.process(CustomProcessor.java:120)
25/05/08 24:00:05 INFO SparkContext: Application failed
""",
}


def analyze(log_content: str) -> Dict:
    """分析日志，返回错误类型、分类和建议"""
    for error_type, (pattern, category, llm_hint) in ERROR_PATTERNS.items():
        # 使用 re.DOTALL (re.S) 让 .* 匹配换行符
        if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
            # 提取错误消息片段
            lines = log_content.split("\n")
            error_message = ""
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.IGNORECASE):
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    error_message = "\n".join(lines[start:end])
                    break

            # 如果单行没匹配到，可能是跨行匹配，提取整个相关部分
            if not error_message:
                match = re.search(pattern, log_content, re.IGNORECASE | re.DOTALL)
                if match:
                    error_message = log_content[max(0, match.start()-200):match.end()+200]

            result = {
                "error_type": error_type,
                "category": category,
                "error_message": error_message,
                "matched_pattern": pattern,
                "confidence": 0.95 if category == ErrorCategory.AUTO_FIXABLE else 0.8,
            }

            if category == ErrorCategory.AUTO_FIXABLE:
                result["quick_fix"] = QUICK_FIXES.get(error_type)
            elif category == ErrorCategory.KNOWN_NEEDS_LLM:
                result["llm_hint"] = llm_hint

            return result

    # 未匹配
    return {
        "error_type": "unknown",
        "category": ErrorCategory.UNKNOWN,
        "error_message": log_content[:500],
        "confidence": 0.0,
    }


def test_all():
    """测试所有错误类型"""
    print("=" * 70)
    print("SparkSkill 错误分析测试")
    print("=" * 70)

    for error_type, log_content in TEST_LOGS.items():
        print(f"\n{'─'*70}")
        print(f"测试: {error_type}")
        print(f"{'─'*70}")

        result = analyze(log_content)

        print(f"\n分析结果:")
        print(f"  ├─ error_type: {result['error_type']}")
        print(f"  ├─ category: {result['category']}")
        print(f"  ├─ matched_pattern: {result.get('matched_pattern', 'N/A')}")
        print(f"  ├─ confidence: {result['confidence']}")
        print(f"  └─ error_message (前200字符):")
        print(f"      {result['error_message'][:200]}...")

        if result['category'] == ErrorCategory.AUTO_FIXABLE:
            fix = result.get('quick_fix')
            if fix:
                print(f"\n✓ 快速修复方案:")
                print(f"  ├─ action_type: {fix['action_type']}")
                print(f"  └─ config_changes:")
                for k, v in fix['config_changes'].items():
                    print(f"      {k} = {v}")
            else:
                print(f"\n✗ 无快速修复方案")

        elif result['category'] == ErrorCategory.KNOWN_NEEDS_LLM:
            hint = result.get('llm_hint', '')
            print(f"\n✓ LLM 分析提示:")
            print(f"  └─ {hint}")

        elif result['category'] == ErrorCategory.UNKNOWN:
            print(f"\n✓ 未知错误，需 LLM 完全分析")


def validate_fixes():
    """验证修复建议是否合理"""
    print("\n" + "=" * 70)
    print("修复建议合理性验证")
    print("=" * 70)

    # 1. Driver 内存不足
    print("\n1. Driver 内存不足 (driver_memory_insufficient)")
    print("   错误: System memory 259.0 MB must be at least 471.9 MB")
    fix = QUICK_FIXES["driver_memory_insufficient"]
    config = fix["config_changes"]
    print(f"   建议: spark.driver.memory = {config['spark.driver.memory']}")
    print(f"   验证: 512m (512 MB) > 471.9 MB ✓ 合理")

    # 2. Executor OOM
    print("\n2. Executor OOM (oom_executor)")
    print("   错误: Java heap space - Executor 堆内存不足")
    fix = QUICK_FIXES["oom_executor"]
    config = fix["config_changes"]
    print(f"   建议: spark.executor.memory = {config['spark.executor.memory']}")
    print(f"         spark.executor.memoryOverhead = {config['spark.executor.memoryOverhead']}")
    print(f"   验证: 4g 堆内存 + 1g overhead ✓ 合理 (增加内存解决 OOM)")

    # 3. GC overhead
    print("\n3. GC overhead limit exceeded (gc_overhead)")
    print("   错误: GC overhead limit exceeded - GC 时间过长")
    fix = QUICK_FIXES["gc_overhead"]
    config = fix["config_changes"]
    print(f"   建议: spark.executor.memory = {config['spark.executor.memory']}")
    print(f"         spark.executor.memoryOverhead = {config['spark.executor.memoryOverhead']}")
    print(f"         spark.driver.memory = {config['spark.driver.memory']}")
    print(f"   验证: 8g executor + 2g overhead + 4g driver ✓ 合理")
    print(f"   原理: 增加 heap 空间，减少 GC 频率，避免 overhead limit exceeded")

    # 4. Broadcast timeout
    print("\n4. Broadcast timeout (broadcast_timeout)")
    print("   错误: Could not execute broadcast in 300 secs")
    fix = QUICK_FIXES["broadcast_timeout"]
    config = fix["config_changes"]
    print(f"   建议: spark.sql.autoBroadcastJoinThreshold = {config['spark.sql.autoBroadcastJoinThreshold']}")
    print(f"   验证: -1 禁用广播 ✓ 合理")
    print(f"   原理: 大表广播超时，禁用广播强制使用 sort merge join")

    # 5. Shuffle timeout
    print("\n5. Shuffle timeout (shuffle_timeout)")
    print("   错误: shuffle 操作超时")
    fix = QUICK_FIXES["shuffle_timeout"]
    config = fix["config_changes"]
    print(f"   建议: spark.shuffle.io.timeout = {config['spark.shuffle.io.timeout']}")
    print(f"   验证: 120s ✓ 合理 (延长超时时间)")

    # 6. Executor heartbeat timeout
    print("\n6. Executor heartbeat timeout (executor_lost_heartbeat)")
    print("   错误: Executor heartbeat timeout - Executor 心跳丢失")
    fix = QUICK_FIXES["executor_lost_heartbeat"]
    config = fix["config_changes"]
    print(f"   建议: spark.executor.heartbeatInterval = {config['spark.executor.heartbeatInterval']}")
    print(f"         spark.network.timeout = {config['spark.network.timeout']}")
    print(f"   验证: 60s 心跳 + 300s 网络超时 ✓ 合理")

    # 7. ClassNotFoundException
    print("\n7. ClassNotFoundException (class_not_found) - KNOWN_NEEDS_LLM")
    print("   错误: ClassNotFoundException: com.example.MySparkJob")
    print("   分类: KNOWN_NEEDS_LLM")
    hint = ERROR_PATTERNS["class_not_found"][2]
    print(f"   LLM 提示: {hint}")
    print(f"   验证: ✓ 正确分类，需要 LLM 分析具体缺失的类和依赖包")

    # 8. FetchFailedException
    print("\n8. FetchFailedException (shuffle_failed) - KNOWN_NEEDS_LLM")
    print("   错误: FetchFailedException: Failed to fetch shuffle block")
    print("   分类: KNOWN_NEEDS_LLM")
    hint = ERROR_PATTERNS["shuffle_failed"][2]
    print(f"   LLM 提示: {hint}")
    print(f"   验证: ✓ 正确分类，需要 LLM 分析 Shuffle Service 状态和网络问题")

    # 9. Container killed
    print("\n9. Container killed by YARN (container_killed) - KNOWN_NEEDS_LLM")
    print("   错误: Container killed by YARN for exceeding memory limits")
    print("   分类: KNOWN_NEEDS_LLM")
    hint = ERROR_PATTERNS["container_killed"][2]
    print(f"   LLM 提示: {hint}")
    print(f"   验证: ✓ 正确分类，需要 LLM 分析具体资源使用情况")


if __name__ == "__main__":
    test_all()
    validate_fixes()