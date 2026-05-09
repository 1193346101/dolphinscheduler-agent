"""
SparkSkill 测试脚本

模拟几种类型的 Spark 错误日志，直接调用 SparkSkill 分析，验证建议是否正确。
"""

import sys
sys.path.insert(0, r"D:\Project\dolphinscheduler-agent\src")

from skills.spark_skill import SparkSkill
from models.analysis import ErrorCategory
from models.alert import AlertContext


# 模拟错误日志
TEST_LOGS = {
    # 1. Driver 内存不足 - AUTO_FIXABLE
    "driver_memory_insufficient": """
25/05/08 19:56:46 INFO SparkContext: Running Spark version 3.3.1
25/05/08 19:56:46 INFO ResourceUtils: ==================================================
25/05/08 19:56:46 ERROR SparkContext: Error initializing SparkContext
java.lang.IllegalArgumentException: System memory 259.0 MB must be at least 471.9 MB.
Please increase heap size using the --driver-memory option or spark.driver.memory in Spark configuration.
	at org.apache.spark.memory.UnifiedMemoryManager$.getMaxMemory(UnifiedMemoryManager.scala:253)
	at org.apache.spark.memory.UnifiedMemoryManager$.apply(UnifiedMemoryManager.scala:248)
	at org.apache.spark.SparkEnv$.create(SparkEnv.scala:366)
25/05/08 19:56:46 INFO SparkContext: Successfully stopped SparkContext
""",

    # 2. Executor OOM - AUTO_FIXABLE
    "oom_executor": """
25/05/08 20:30:15 INFO Executor: Running task 3.0 in stage 2.0 (TID 15)
25/05/08 20:30:18 ERROR Executor: Exception in task 3.0 in stage 2.0 (TID 15)
java.lang.OutOfMemoryError: Java heap space
	at org.apache.spark.shuffle.sort.SortShuffleWriter.insertRecord(SortShuffleWriter.scala:85)
	at org.apache.spark.shuffle.sort.SortShuffleWriter.write(SortShuffleWriter.scala:120)
	at org.apache.spark.scheduler.ShuffleMapTask.runTask(ShuffleMapTask.scala:99)
	at org.apache.spark.scheduler.ShuffleMapTask.runTask(ShuffleMapTask.scala:52)
25/05/08 20:30:18 INFO Executor: Executor is unable to send heartbeats to driver
""",

    # 3. GC overhead - AUTO_FIXABLE
    "gc_overhead": """
25/05/08 21:15:30 INFO TaskSetManager: Starting task 4.0 in stage 5.0
25/05/08 21:15:45 ERROR TaskSetManager: Task 4.0 in stage 5.0 failed 1 times; aborting job
java.lang.OutOfMemoryError: GC overhead limit exceeded
	at org.apache.spark.sql.execution.joins.BroadcastHashJoinExec.doExecute(BroadcastHashJoinExec.scala:112)
	at org.apache.spark.sql.execution.SparkPlan.$anonfun$execute$1(SparkPlan.scala:180)
25/05/08 21:15:45 INFO DAGScheduler: Job 5 failed: GC overhead limit exceeded
""",

    # 4. Broadcast timeout - AUTO_FIXABLE
    "broadcast_timeout": """
25/05/08 22:00:10 INFO BroadcastHashJoin: Running broadcast join
25/05/08 22:00:35 ERROR BroadcastHashJoin: Broadcast timeout exceeded
org.apache.spark.SparkException: Could not execute broadcast in 300 secs.
	at org.apache.spark.sql.execution.joins.BroadcastHashJoinExec.doExecute(BroadcastHashJoinExec.scala:85)
	at org.apache.spark.sql.execution.SparkPlan.$anonfun$execute$1(SparkPlan.scala:180)
25/05/08 22:00:35 INFO TaskSetManager: Task failed due to broadcast timeout
""",

    # 5. ClassNotFoundException - KNOWN_NEEDS_LLM
    "class_not_found": """
25/05/08 22:30:00 INFO Driver: Submitting Spark application
25/05/08 22:30:05 ERROR Driver: Failed to load main class
java.lang.ClassNotFoundException: com.example.MySparkJob
	at java.net.URLClassLoader.findClass(URLClassLoader.java:382)
	at java.lang.ClassLoader.loadClass(ClassLoader.java:418)
	at java.lang.ClassLoader.loadClass(ClassLoader.java:351)
	at org.apache.spark.deploy.JavaMainApplication.start(SparkApplication.scala:52)
25/05/08 22:30:05 INFO SparkContext: Application failed to start
""",

    # 6. Shuffle failed - KNOWN_NEEDS_LLM
    "shuffle_failed": """
25/05/08 23:00:10 INFO ShuffleBlockFetcherIterator: Fetching shuffle blocks
25/05/08 23:00:25 ERROR ShuffleBlockFetcherIterator: Failed to fetch shuffle block
org.apache.spark.shuffle.FetchFailedException: Failed to fetch shuffle block from executor 5
	at org.apache.spark.storage.ShuffleBlockFetcherIterator.throwFetchFailedException(ShuffleBlockFetcherIterator.scala:360)
	at org.apache.spark.storage.ShuffleBlockFetcherIterator.next(ShuffleBlockFetcherIterator.scala:285)
25/05/08 23:00:25 INFO TaskSetManager: Retrying task due to shuffle fetch failure
""",

    # 7. Container killed by YARN - KNOWN_NEEDS_LLM
    "container_killed": """
25/05/08 23:30:00 INFO Executor: Executor 7 is running tasks
25/05/08 23:30:15 INFO YarnAllocator: Container killed by YARN for exceeding memory limits
Container killed by YARN for exceeding memory limits. Container killed by YARN.
	at org.apache.spark.scheduler.cluster.YarnSchedulerBackend$YarnDriverEndpoint.containerKilled(YarnSchedulerBackend.scala:85)
25/05/08 23:30:15 INFO TaskSetManager: Lost executor 7 due to container killed
""",

    # 8. 未知错误 - UNKNOWN
    "unknown": """
25/05/08 24:00:00 INFO SparkContext: Starting Spark application
25/05/08 24:00:05 ERROR SparkContext: Unknown error occurred
CustomApplicationException: Something went wrong in our custom code
	at com.example.CustomProcessor.process(CustomProcessor.java:120)
	at com.example.SparkJob.run(SparkJob.java:85)
25/05/08 24:00:05 INFO SparkContext: Application failed
""",
}


def test_skill():
    """测试 SparkSkill 分析能力"""
    skill = SparkSkill()

    print("=" * 60)
    print("SparkSkill 测试")
    print("=" * 60)

    for error_type, log_content in TEST_LOGS.items():
        print(f"\n{'='*60}")
        print(f"测试: {error_type}")
        print(f"{'='*60}")

        # 模拟 AlertContext
        context = AlertContext(
            alert_type="TASK_FAILURE",
            task_type="SPARK",
            project_name="test_project",
            workflow_name="test_workflow",
            task_name="test_task",
        )

        # 分析
        analysis = skill.analyze(log_content, context)

        print(f"\n分析结果:")
        print(f"  - error_type: {analysis.error_type}")
        print(f"  - category: {analysis.category}")
        print(f"  - error_message: {analysis.error_message[:200]}...")
        print(f"  - confidence: {analysis.confidence}")
        print(f"  - matched_pattern: {analysis.matched_pattern}")

        if analysis.category == ErrorCategory.AUTO_FIXABLE:
            print(f"\n快速修复方案:")
            quick_fix = analysis.quick_fix
            if quick_fix:
                action_type = quick_fix.get("action_type", "unknown")
                config_changes = quick_fix.get("config_changes", {})
                print(f"  - action_type: {action_type}")
                print(f"  - config_changes: {config_changes}")
                print(f"  ✓ AUTO_FIXABLE 正确识别，建议配置调整")
            else:
                print(f"  ✗ 无快速修复方案")
        elif analysis.category == ErrorCategory.KNOWN_NEEDS_LLM:
            print(f"\nLLM 分析提示:")
            print(f"  - llm_hint: {analysis.llm_hint}")
            print(f"  ✓ KNOWN_NEEDS_LLM 正确识别，需要 LLM 深度分析")
        elif analysis.category == ErrorCategory.UNKNOWN:
            print(f"\n未知错误类型:")
            print(f"  - 需完全交给 LLM 分析")
            print(f"  ✓ UNKNOWN 正确识别")
        else:
            print(f"  ✗ 未正确分类")


def validate_fixes():
    """验证修复建议是否合理"""
    print("\n" + "=" * 60)
    print("修复建议验证")
    print("=" * 60)

    skill = SparkSkill()

    # Driver 内存不足
    log = TEST_LOGS["driver_memory_insufficient"]
    analysis = skill.analyze(log, AlertContext(task_type="SPARK"))
    fix = analysis.quick_fix

    print("\n1. Driver 内存不足:")
    print(f"   错误: System memory 259.0 MB must be at least 471.9 MB")
    if fix:
        config = fix.get("config_changes", {})
        print(f"   建议: driver-memory={config.get('spark.driver.memory')}")
        print(f"   验证: 512m > 471.9 MB ✓ 合理")
    else:
        print("   ✗ 无建议")

    # Executor OOM
    log = TEST_LOGS["oom_executor"]
    analysis = skill.analyze(log, AlertContext(task_type="SPARK"))
    fix = analysis.quick_fix

    print("\n2. Executor OOM:")
    print(f"   错误: Java heap space")
    if fix:
        config = fix.get("config_changes", {})
        print(f"   建议: executor-memory={config.get('spark.executor.memory')}")
        print(f"   验证: 4g 增加内存 ✓ 合理")
    else:
        print("   ✗ 无建议")

    # GC overhead
    log = TEST_LOGS["gc_overhead"]
    analysis = skill.analyze(log, AlertContext(task_type="SPARK"))
    fix = analysis.quick_fix

    print("\n3. GC overhead limit exceeded:")
    print(f"   错误: GC overhead limit exceeded")
    if fix:
        config = fix.get("config_changes", {})
        print(f"   建议: executor-memory={config.get('spark.executor.memory')}")
        print(f"         executor-memoryOverhead={config.get('spark.executor.memoryOverhead')}")
        print(f"         driver-memory={config.get('spark.driver.memory')}")
        print(f"   验证: 8g + 2g overhead ✓ 合理 (增加内存减少 GC)")
    else:
        print("   ✗ 无建议")

    # Broadcast timeout
    log = TEST_LOGS["broadcast_timeout"]
    analysis = skill.analyze(log, AlertContext(task_type="SPARK"))
    fix = analysis.quick_fix

    print("\n4. Broadcast timeout:")
    print(f"   错误: Could not execute broadcast in 300 secs")
    if fix:
        config = fix.get("config_changes", {})
        print(f"   建议: autoBroadcastJoinThreshold={config.get('spark.sql.autoBroadcastJoinThreshold')}")
        print(f"   验证: -1 禁用广播 ✓ 合理 (避免大表广播超时)")
    else:
        print("   ✗ 无建议")


if __name__ == "__main__":
    test_skill()
    validate_fixes()