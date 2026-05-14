"""
测试改进后的血缘扫描组件

验证：
1. CodeSearcher 能否找到 ad-monitor 项目的类文件
2. SQLParser 能否正确解析 INSERT 输出表
"""

import sys
import os

# 项目路径
project_root = "D:/Project/dolphinscheduler-agent"
sys.path.insert(0, project_root)

import importlib.util

# 加载 CodeSearcher
spec = importlib.util.spec_from_file_location(
    "code_searcher",
    f"{project_root}/src/graph/code_searcher.py"
)
code_searcher_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code_searcher_module)

CodeSearcher = code_searcher_module.CodeSearcher

# 加载 SQLParser
spec2 = importlib.util.spec_from_file_location(
    "sql_parser",
    f"{project_root}/src/graph/sql_parser.py"
)
sql_parser_module = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(sql_parser_module)

SQLParser = sql_parser_module.SQLParser


def test_code_searcher():
    """测试 CodeSearcher 能否找到类文件"""
    print("=" * 80)
    print("测试 CodeSearcher - 项目名映射和路径搜索")
    print("=" * 80)

    # 代码仓库路径
    code_root = "D:/Project/spark-etl"

    searcher = CodeSearcher(code_root)

    # 测试类名（来自验证报告）
    test_classes = [
        ("tv.huan.ad.monitor.upgrade.ImpressionMarkDayReport", "ad_monitor"),
        ("tv.huan.ad.monitor.ads.spot.AkSpotFreqDayReport", "ad_monitor"),
        ("tv.huan.ad.monitor.upgrade.ClickLogOrc", "ad_monitor"),
        ("tv.huan.ad.monitor.dwd.DwdImpressionMultiDimCount", "ad_monitor"),
    ]

    results = []
    for class_name, project_name in test_classes:
        result = searcher.search_class(class_name, project_name)

        status = "[OK]" if result["found"] else "[FAIL]"
        print(f"\n{status} 类: {class_name}")
        print(f"  DS项目名: {project_name}")
        print(f"  找到: {result['found']}")
        print(f"  文件路径: {result['file_path']}")
        print(f"  跨项目: {result['cross_project']}")

        results.append(result["found"])

    return all(results)


def test_sql_parser():
    """测试 SQLParser 能否正确解析 INSERT 输出表"""
    print("\n" + "=" * 80)
    print("测试 SQLParser - INSERT 输出表解析")
    print("=" * 80)

    parser = SQLParser()

    # 测试 SQL（来自 ImpressionMarkDayReport.scala）
    test_sqls = [
        # INSERT OVERWRITE
        """
        insert overwrite table ad_monitor.impression_mark_day_report partition(dt = '2026-05-14')
        select * from view_result
        """,
        # 带 FROM 的完整 SQL
        """
        select campaign_id, mark_id
        from ad_monitor.impression_log
        where dt = '2026-05-14'
        """,
        # 多表 JOIN
        """
        SELECT a.*, b.name
        FROM ad_monitor.impression_log a
        JOIN ad_monitor.campaign_info b ON a.campaign_id = b.id
        """,
    ]

    results = []
    for i, sql in enumerate(test_sqls, 1):
        tables = parser.extract_tables(sql)

        print(f"\n测试 SQL {i}:")
        print(f"  输入表: {tables['input']}")
        print(f"  输出表: {tables['output']}")

        # 验证
        if i == 1:
            # INSERT OVERWRITE 应该识别输出表
            success = "ad_monitor.impression_mark_day_report" in tables["output"]
            results.append(success)
            print(f"  验证: {success}")

        if i == 2:
            # FROM 应该识别输入表
            success = "ad_monitor.impression_log" in tables["input"]
            results.append(success)
            print(f"  验证: {success}")

        if i == 3:
            # JOIN 应该识别两个输入表
            success = "ad_monitor.impression_log" in tables["input"] and "ad_monitor.campaign_info" in tables["input"]
            results.append(success)
            print(f"  验证: {success}")

    return all(results)


def test_parse_scala_file():
    """测试解析真实 Scala 文件"""
    print("\n" + "=" * 80)
    print("测试解析真实 Scala 文件")
    print("=" * 80)

    code_root = "D:/Project/spark-etl"
    searcher = CodeSearcher(code_root)
    parser = SQLParser()

    # 查找类文件
    class_name = "tv.huan.ad.monitor.upgrade.ImpressionMarkDayReport"
    result = searcher.search_class(class_name, "ad_monitor")

    if not result["found"]:
        print("[FAIL] 无法找到类文件")
        return False

    file_path = result["file_path"]
    print(f"\n找到文件: {file_path}")

    # 读取文件内容
    content = searcher.read_file_content(file_path)
    if not content:
        print("[FAIL] 无法读取文件内容")
        return False

    print(f"文件长度: {len(content)} 字符")

    # 解析 SQL
    file_ext = ".scala"
    tables = parser.parse_file_content(content, file_ext)

    print(f"\n解析结果:")
    print(f"  输入表: {tables['input']}")
    print(f"  输出表: {tables['output']}")

    # 验证
    has_input = len(tables['input']) > 0
    has_output = len(tables['output']) > 0

    print(f"\n验证:")
    print(f"  有输入表: {has_input}")
    print(f"  有输出表: {has_output}")

    return has_input and has_output


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("血缘扫描组件改进测试")
    print("=" * 80)

    results = {}

    # 运行测试
    results["CodeSearcher"] = test_code_searcher()
    results["SQLParser"] = test_sql_parser()
    results["ScalaFileParse"] = test_parse_scala_file()

    # 总结
    print("\n" + "=" * 80)
    print("测试结果总结")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n所有测试通过！改进生效：")
        print("  - 项目名映射正确：ad_monitor -> ad-monitor")
        print("  - 类文件搜索正确：找到 src/main/scala 路径")
        print("  - SQL 解析正确：识别 INSERT OVERWRITE 输出表")


if __name__ == "__main__":
    main()