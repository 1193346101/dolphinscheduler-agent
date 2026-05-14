"""
测试隐式依赖检测

运行检测并生成报告
"""

import sys
import os

# 添加项目路径
project_root = "D:/Project/dolphinscheduler-agent"
sys.path.insert(0, project_root)

from src.graph.implicit_dependency_detector import (
    ImplicitDependencyDetector,
    detect_implicit_dependencies,
    generate_detection_report,
)


def main():
    """运行 ad_monitor 隐式依赖检测"""
    print("=" * 80)
    print("隐式依赖检测 - ad_monitor 项目")
    print("=" * 80)

    # 项目代码（ad_monitor 的 project_code）
    project_code = "11598158952448"

    print(f"\n项目代码: {project_code}")
    print("开始检测...\n")

    # 运行检测
    detector = ImplicitDependencyDetector()
    result = detector.detect_all_implicit_dependencies(project_code)

    # 打印报告
    print(detector.generate_report(result))

    # 导出报告
    output_dir = os.path.join(project_root, "data", "graph")
    text_path = os.path.join(output_dir, f"{project_code}_implicit_dep_report.txt")
    json_path = os.path.join(output_dir, f"{project_code}_implicit_dep_report.json")

    detector.export_json_report(result, json_path)
    print(f"\n报告已导出:")
    print(f"  - 文本报告: {text_path}")
    print(f"  - JSON 报告: {json_path}")

    # 统计
    print("\n" + "=" * 80)
    print("检测统计")
    print("=" * 80)
    print(f"  总工作流数: {result.total_workflows}")
    print(f"  隐式依赖总数: {len(result.implicit_dependencies)}")
    print(f"  缺失依赖数: {len(result.missing_dependencies)}")
    print(f"  已配置依赖数: {len([d for d in result.implicit_dependencies if d.is_explicit])}")
    print(f"  血缘准确性问题: {len(result.lineage_accuracy_issues)}")


if __name__ == "__main__":
    main()