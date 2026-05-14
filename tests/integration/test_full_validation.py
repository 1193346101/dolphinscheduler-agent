"""
全面测试 dolphinscheduler-agent 核心功能

测试范围:
1. 告警处理: 日志拉取、预处理、错误分析、报告生成
2. 血缘关系: dsctl用法、代码解析、血缘构建、验证
"""

import sys
import os
import json
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 测试结果记录
test_results = {
    "alert_processing": {"passed": 0, "failed": 0, "tests": []},
    "lineage": {"passed": 0, "failed": 0, "tests": []},
}

def record_test(category, name, passed, details=""):
    """记录测试结果"""
    test_results[category]["tests"].append({
        "name": name,
        "passed": passed,
        "details": details
    })
    if passed:
        test_results[category]["passed"] += 1
        status = "PASS"
    else:
        test_results[category]["failed"] += 1
        status = "FAIL"

    print(f"  [{status}] {name}")
    if details:
        print(f"       {details}")


print("=" * 80)
print("DolphinScheduler Agent 全面功能测试")
print("=" * 80)


# ============================================================================
# 一、告警处理流程测试
# ============================================================================

print("\n" + "=" * 80)
print("【一】告警处理流程测试")
print("=" * 80)


# 1.1 日志获取层
print("\n[1.1] 日志获取层")

try:
    from src.tools.yarn_log import YARNLogTool
    from src.tools.spark_hist import SparkHistTool

    # YARNLogTool 方法验证
    yarn_tool = YARNLogTool()
    methods = ['fetch_container_log', 'fetch_executor_logs', 'fetch_executor_logs_smart']
    for m in methods:
        if hasattr(yarn_tool, m):
            record_test("alert_processing", f"YARNLogTool.{m}", True)
        else:
            record_test("alert_processing", f"YARNLogTool.{m}", False, "方法不存在")

    # SparkHistTool 方法验证
    spark_tool = SparkHistTool()
    methods = ['fetch_logs', 'fetch_spark_history_metrics']
    for m in methods:
        if hasattr(spark_tool, m):
            record_test("alert_processing", f"SparkHistTool.{m}", True)
        else:
            record_test("alert_processing", f"SparkHistTool.{m}", False, "方法不存在")

except Exception as e:
    record_test("alert_processing", "日志工具初始化", False, str(e))


# 1.2 日志预处理层
print("\n[1.2] 日志预处理层")

try:
    from src.skills.common.preprocess_log import (
        extract_error_blocks,
        extract_config_lines,
        extract_executor_events,
    )

    # 测试错误块提取
    mock_log = """
2024-01-01 INFO Starting executor
2024-01-01 ERROR java.lang.OutOfMemoryError: Java heap space
    at org.apache.spark.executor.Executor.coalesce(Executor.scala:123)
    at org.apache.spark.rdd.RDD.map(RDD.scala:456)
2024-01-01 INFO Executor finished
2024-01-01 FATAL Container killed by YARN
"""

    error_blocks = extract_error_blocks(mock_log)
    if len(error_blocks) >= 2:
        record_test("alert_processing", "extract_error_blocks", True, f"提取{len(error_blocks)}个错误块")
    else:
        record_test("alert_processing", "extract_error_blocks", False, f"只提取{len(error_blocks)}个错误块")

    # 测试配置行提取
    config_lines = extract_config_lines(mock_log)
    record_test("alert_processing", "extract_config_lines", True, f"配置行提取功能存在")

    # 测试Executor事件提取
    events = extract_executor_events(mock_log)
    record_test("alert_processing", "extract_executor_events", True, "事件提取功能存在")

except ImportError as e:
    record_test("alert_processing", "preprocess_log导入", False, str(e))
except Exception as e:
    record_test("alert_processing", "预处理函数测试", False, str(e))


# 1.3 错误分析 Skills
print("\n[1.3] 错误分析 Skills")

skills_to_test = [
    ("src.skills.spark.analyzer", "SparkAnalyzer"),
    ("src.skills.common.oss_validator", "OSSValidator"),
]

for module_name, class_name in skills_to_test:
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)

        # 检查关键方法
        analyzer_methods = ['analyze', 'analyze_error', 'diagnose']
        oss_methods = ['check_path', 'validate_partition', 'check_oss_path']

        if class_name == "SparkAnalyzer":
            key_methods = analyzer_methods
        elif class_name == "OSSValidator":
            key_methods = oss_methods
        else:
            key_methods = []

        found = sum(1 for m in key_methods if hasattr(cls, m))
        if found > 0:
            record_test("alert_processing", f"{class_name}初始化", True, f"{found}个分析方法")
        else:
            record_test("alert_processing", f"{class_name}初始化", False, "缺少分析方法")

    except Exception as e:
        record_test("alert_processing", f"{class_name}导入", False, str(e))


# 1.4 错误报告层
print("\n[1.4] 错误报告层")

try:
    from src.tools.report_generator import ReportGenerator
    from src.tools.risk_assess import RiskAssessTool
    from src.tools.graph_impact import GraphImpactTool

    # ReportGenerator
    gen = ReportGenerator()
    if hasattr(gen, 'generate_report'):
        record_test("alert_processing", "ReportGenerator.generate_report", True)
    else:
        record_test("alert_processing", "ReportGenerator.generate_report", False)

    # RiskAssessTool
    risk = RiskAssessTool()
    methods = ['assess', 'assess_risk', 'get_risk_level']
    found = sum(1 for m in methods if hasattr(risk, m))
    if found > 0:
        record_test("alert_processing", "RiskAssessTool", True, f"{found}个方法")
    else:
        record_test("alert_processing", "RiskAssessTool", False, "缺少方法")

    # GraphImpactTool
    impact = GraphImpactTool()
    methods = ['analyze_downstream', 'analyze_workflow_downstream', 'analyze_task_downstream']
    found = sum(1 for m in methods if hasattr(impact, m))
    if found > 0:
        record_test("alert_processing", "GraphImpactTool", True, f"{found}个方法")
    else:
        record_test("alert_processing", "GraphImpactTool", False)

except Exception as e:
    record_test("alert_processing", "报告工具初始化", False, str(e))


# 1.5 复杂错误场景模拟
print("\n[1.5] 复杂错误场景模拟测试")

# OOM错误分析
oom_log = """
2024-05-14 10:00:00 INFO SparkExecutor started
2024-05-14 10:05:00 ERROR java.lang.OutOfMemoryError: Java heap space
    at org.apache.spark.memory.MemoryManager.acquire(MemoryManager.scala:123)
    at org.apache.spark.executor.Executor.executeTask(Executor.scala:456)
2024-05-14 10:05:01 WARN Memory limit exceeded: 8GB requested, 4GB available
"""

try:
    from src.skills.common.preprocess_log import extract_error_blocks
    blocks = extract_error_blocks(oom_log)

    # 验证是否识别OOM
    oom_detected = any("OutOfMemoryError" in block or "OOM" in block for block in blocks)
    if oom_detected:
        record_test("alert_processing", "OOM错误识别", True, "正确识别OutOfMemoryError")
    else:
        record_test("alert_processing", "OOM错误识别", False, "未识别OOM错误")

except Exception as e:
    record_test("alert_processing", "OOM场景测试", False, str(e))


# Shuffle失败分析
shuffle_log = """
2024-05-14 11:00:00 ERROR Failed to fetch shuffle block from shuffle service
2024-05-14 11:00:01 WARN External shuffle service unavailable on node-01
2024-05-14 11:00:02 ERROR Shuffle block fetch failed after 3 retries
"""

try:
    blocks = extract_error_blocks(shuffle_log)
    shuffle_detected = any("shuffle" in block.lower() for block in blocks)
    if shuffle_detected:
        record_test("alert_processing", "Shuffle失败识别", True, "正确识别Shuffle错误")
    else:
        record_test("alert_processing", "Shuffle失败识别", False, "未识别Shuffle错误")
except Exception as e:
    record_test("alert_processing", "Shuffle场景测试", False, str(e))


# ============================================================================
# 二、血缘关系流程测试
# ============================================================================

print("\n" + "=" * 80)
print("【二】血缘关系流程测试")
print("=" * 80)


# 2.1 dsctl用法验证
print("\n[2.1] dsctl用法验证")

try:
    from src.integrations.dsctl_wrapper import DSCLIClient, CLIResult
    from src.config import settings

    # 检查DSCLIClient方法
    client = DSCLIClient(api_url=settings.DS_API_URL, api_token=settings.DS_API_TOKEN)

    required_methods = [
        'list_workflows',
        'describe_workflow',
        'list_schedules',
    ]

    for m in required_methods:
        if hasattr(client, m):
            record_test("lineage", f"DSCLIClient.{m}", True)
        else:
            record_test("lineage", f"DSCLIClient.{m}", False, "方法不存在")

    # 测试实际调用
    try:
        result = client.list_workflows(11598158952448)
        if result.success:
            workflows = json.loads(result.stdout)
            count = len(workflows.get('data', workflows) if isinstance(workflows, dict) else workflows)
            record_test("lineage", "list_workflows实际调用", True, f"返回{count}个工作流")
        else:
            record_test("lineage", "list_workflows实际调用", False, result.stderr[:100])
    except Exception as e:
        record_test("lineage", "list_workflows实际调用", False, str(e)[:100])

except Exception as e:
    record_test("lineage", "DSCLIClient初始化", False, str(e))


# 2.2 项目解析验证
print("\n[2.2] 项目解析验证")

try:
    from src.integrations import project_resolver

    code, name = project_resolver.resolve('ad_monitor')
    if code:
        record_test("lineage", "project_resolver.resolve", True, f"ad_monitor -> {code}")
    else:
        record_test("lineage", "project_resolver.resolve", False, "返回None")

except Exception as e:
    record_test("lineage", "project_resolver测试", False, str(e))


# 2.3 代码解析层验证
print("\n[2.3] 代码解析层验证")

try:
    from src.graph.code_searcher import CodeSearcher, extract_project_from_jar
    from src.graph.sql_parser import SQLParser

    # jar包名提取测试
    jar_tests = [
        ("ad-monitor-1.0-jar-with-dependencies.jar", "ad-monitor"),
        ("data-product-2.0.jar", "data-product"),
        ("hdfs://ha-nn/path/ad-monitor-1.0.jar", "ad-monitor"),
    ]

    for jar, expected in jar_tests:
        result = extract_project_from_jar(jar)
        if result == expected:
            record_test("lineage", f"jar提取: {jar[:30]}...", True, f"-> {result}")
        else:
            record_test("lineage", f"jar提取: {jar[:30]}...", False, f"得到{result}, 期望{expected}")

    # SQLParser测试
    parser = SQLParser()

    sql_tests = [
        ("INSERT OVERWRITE TABLE db.output SELECT * FROM db.input",
         {"output": ["db.output"], "input": ["db.input"]}),
        ("SELECT a.*, b.name FROM db.table1 a JOIN db.table2 b ON a.id = b.id",
         {"input": ["db.table1", "db.table2"]}),
    ]

    for sql, expected in sql_tests:
        result = parser.extract_tables(sql)

        # 检查输出表
        output_ok = all(t in result["output"] for t in expected.get("output", []))
        input_ok = all(t in result["input"] for t in expected.get("input", []))

        if output_ok and input_ok:
            record_test("lineage", f"SQL解析: {sql[:30]}...", True)
        else:
            record_test("lineage", f"SQL解析: {sql[:30]}...", False,
                       f"output={result['output']}, input={result['input']}")

    # 类文件搜索测试
    searcher = CodeSearcher("D:/Project/spark-etl")
    result = searcher.search_class("tv.huan.ad.monitor.upgrade.ImpressionMarkDayReport", "ad_monitor")

    if result["found"]:
        record_test("lineage", "类文件搜索", True, result["file_path"][-50:])
    else:
        record_test("lineage", "类文件搜索", False, "未找到类文件")

except Exception as e:
    record_test("lineage", "代码解析层测试", False, str(e))


# 2.4 血缘构建验证
print("\n[2.4] 血缘构建验证")

try:
    from src.graph import GraphScanner, GraphStorage

    storage = GraphStorage()
    graph_data = storage.load_graph("11598158952448")

    if graph_data:
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})

        wf_count = len(nodes.get("workflows", []))
        task_count = len(nodes.get("tasks", []))
        class_count = len(nodes.get("classes", []))
        table_count = len(nodes.get("tables", []))
        produces_count = len(edges.get("task_produces_table", []))
        consumes_count = len(edges.get("task_consumes_table", []))

        record_test("lineage", "图谱数据加载", True,
                   f"wf={wf_count}, task={task_count}, class={class_count}")

        # 验证数据完整性
        if wf_count > 0 and task_count > 0:
            record_test("lineage", "工作流/任务数据", True)
        else:
            record_test("lineage", "工作流/任务数据", False, "数据为空")

        if class_count > 0:
            record_test("lineage", "类映射数据", True, f"{class_count}个类")
        else:
            record_test("lineage", "类映射数据", False, "无类映射")

        if produces_count > 0:
            record_test("lineage", "输出表关系", True, f"{produces_count}条produces边")
        else:
            record_test("lineage", "输出表关系", False, "无输出表关系")

    else:
        record_test("lineage", "图谱数据加载", False, "图谱不存在")

except Exception as e:
    record_test("lineage", "血缘构建测试", False, str(e))


# 2.5 隐式依赖检测验证
print("\n[2.5] 隐式依赖检测验证")

try:
    from src.graph.implicit_dependency_detector import ImplicitDependencyDetector

    detector = ImplicitDependencyDetector()

    # 检查方法
    methods = ['detect', 'detect_implicit_dependencies', 'find_table_based_deps']
    found = sum(1 for m in methods if hasattr(detector, m))

    if found > 0:
        record_test("lineage", "ImplicitDependencyDetector", True, f"{found}个检测方法")

        # 测试实际检测
        try:
            # 使用已有图谱数据测试
            implicit_deps = detector.detect("11598158952448")
            if implicit_deps:
                count = len(implicit_deps) if isinstance(implicit_deps, list) else 0
                record_test("lineage", "隐式依赖检测实际运行", True, f"检测到{count}个隐式依赖")
            else:
                record_test("lineage", "隐式依赖检测实际运行", True, "无隐式依赖")
        except Exception as e:
            record_test("lineage", "隐式依赖检测实际运行", False, str(e)[:100])
    else:
        record_test("lineage", "ImplicitDependencyDetector", False, "缺少检测方法")

except ImportError:
    record_test("lineage", "ImplicitDependencyDetector导入", False, "模块不存在")
except Exception as e:
    record_test("lineage", "隐式依赖测试", False, str(e))


# 2.6 HTML展示验证
print("\n[2.6] HTML展示验证")

try:
    graph_dir = project_root / "data" / "graph"

    # 检查必要文件
    required_files = [
        "index.html",
        "project_list.js",
        "ad_monitor/graph_data.js",
    ]

    for f in required_files:
        path = graph_dir / f
        if path.exists():
            record_test("lineage", f"文件存在: {f}", True)
        else:
            record_test("lineage", f"文件存在: {f}", False, "文件不存在")

    # 检查project_list.js格式
    with open(graph_dir / "project_list.js", "r") as f:
        content = f.read()
        if "projectList" in content and "ad_monitor" in content:
            record_test("lineage", "project_list.js格式", True)
        else:
            record_test("lineage", "project_list.js格式", False)

    # 检查graph_data.js格式
    with open(graph_dir / "ad_monitor" / "graph_data.js", "r") as f:
        content = f.read()
        if "graphData" in content:
            record_test("lineage", "graph_data.js格式", True)
        else:
            record_test("lineage", "graph_data.js格式", False, "缺少graphData变量")

except Exception as e:
    record_test("lineage", "HTML展示测试", False, str(e))


# ============================================================================
# 测试总结
# ============================================================================

print("\n" + "=" * 80)
print("测试总结")
print("=" * 80)

print(f"\n【告警处理】通过: {test_results['alert_processing']['passed']}, 失败: {test_results['alert_processing']['failed']}")
print(f"【血缘关系】通过: {test_results['lineage']['passed']}, 失败: {test_results['lineage']['failed']}")

total_passed = test_results['alert_processing']['passed'] + test_results['lineage']['passed']
total_failed = test_results['alert_processing']['failed'] + test_results['lineage']['failed']

print(f"\n总计: 通过 {total_passed}/{total_passed + total_failed}")

if total_failed > 0:
    print("\n失败项目:")
    for category in ["alert_processing", "lineage"]:
        for t in test_results[category]["tests"]:
            if not t["passed"]:
                print(f"  - [{category}] {t['name']}: {t['details']}")

# 保存结果到文件
result_file = project_root / "tests" / "test_results.json"
with open(result_file, "w", encoding="utf-8") as f:
    json.dump(test_results, f, ensure_ascii=False, indent=2)

print(f"\n详细结果已保存到: {result_file}")