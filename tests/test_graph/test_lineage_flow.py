"""
Quick validation of improved lineage scanning

Test the complete flow: workflow -> task -> class -> tables
"""

import sys
import os

project_root = "D:/Project/dolphinscheduler-agent"
sys.path.insert(0, project_root)

import importlib.util

# Load CodeSearcher
spec = importlib.util.spec_from_file_location(
    "code_searcher",
    f"{project_root}/src/graph/code_searcher.py"
)
code_searcher_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code_searcher_module)

CodeSearcher = code_searcher_module.CodeSearcher
extract_project_from_jar = code_searcher_module.extract_project_from_jar

# Load SQLParser
spec2 = importlib.util.spec_from_file_location(
    "sql_parser",
    f"{project_root}/src/graph/sql_parser.py"
)
sql_parser_module = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(sql_parser_module)

SQLParser = sql_parser_module.SQLParser

# Test jar name extraction
jar_tests = [
    "ad-monitor-1.0-jar-with-dependencies.jar",
    "data-product-2.0.jar",
    "hdfs://ha-nn/dolphin-scheduler/ad_monitor/resources/ad_monitor/ad-monitor-1.0-jar-with-dependencies.jar",
]

print("=" * 60)
print("Test: Extract project name from jar")
print("=" * 60)

for jar in jar_tests:
    project = extract_project_from_jar(jar)
    print(f"Jar: {jar}")
    print(f"  -> Project: {project}")

# Test complete flow
print("\n" + "=" * 60)
print("Test: Complete flow (task -> class -> tables)")
print("=" * 60)

code_root = "D:/Project/spark-etl"
searcher = CodeSearcher(code_root)
parser = SQLParser()

# Simulate task config from DS API
task_config = {
    "task_code": "11599826665352",
    "task_name": "impression_mark_day_report",
    "mainClass": "tv.huan.ad.monitor.upgrade.ImpressionMarkDayReport",
    "mainJar": "hdfs://ha-nn/dolphin-scheduler/ad_monitor/resources/ad_monitor/ad-monitor-1.0-jar-with-dependencies.jar",
}

class_name = task_config["mainClass"]
jar_name = task_config["mainJar"]

# Step 1: Extract project from jar
project_from_jar = extract_project_from_jar(jar_name)
print(f"\nStep 1: Project from jar -> {project_from_jar}")

# Step 2: Search class file
result = searcher.search_class(class_name, project_from_jar or "ad_monitor")
print(f"\nStep 2: Search class file")
print(f"  Found: {result['found']}")
print(f"  Path: {result['file_path']}")

# Step 3: Parse tables from file
if result["found"]:
    content = searcher.read_file_content(result["file_path"])
    if content:
        tables = parser.parse_file_content(content, ".scala")
        print(f"\nStep 3: Parse tables")
        print(f"  Input tables: {tables['input']}")
        print(f"  Output tables: {tables['output']}")

        # Verify output
        if tables['output']:
            print(f"\n[SUCCESS] Found output table: {tables['output']}")
        else:
            print(f"\n[FAIL] No output table found")

print("\n" + "=" * 60)
print("Validation complete")
print("=" * 60)