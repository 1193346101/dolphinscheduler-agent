"""
测试血缘依赖验证

验证图谱数据的准确性
"""

import sys
import os
import importlib.util

# 项目路径
project_root = "D:/Project/dolphinscheduler-agent"
sys.path.insert(0, project_root)

# 直接加载模块避免导入问题
spec = importlib.util.spec_from_file_location(
    "lineage_validator",
    f"{project_root}/src/graph/lineage_validator.py"
)
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)

LineageValidator = validator_module.LineageValidator


def main():
    """运行血缘验证"""
    print("=" * 80)
    print("血缘依赖验证 - ad_monitor 项目")
    print("=" * 80)

    # 项目代码
    project_code = "11598158952448"

    print(f"\n项目代码: {project_code}")
    print("开始验证...\n")

    # 运行验证
    validator = LineageValidator()
    result = validator.validate_project(project_code, fetch_ds=True)

    # 打印报告
    print(validator.generate_report(result))

    # 导出报告
    output_dir = os.path.join(project_root, "data", "graph")
    text_path = os.path.join(output_dir, f"{project_code}_lineage_validation.txt")
    json_path = os.path.join(output_dir, f"{project_code}_lineage_validation.json")

    validator.export_json_report(result, json_path)

    print(f"\n报告已导出:")
    print(f"  - 文本报告: {text_path}")
    print(f"  - JSON 报告: {json_path}")

    # 统计
    print("\n" + "=" * 80)
    print("验证统计")
    print("=" * 80)
    print(f"  工作流: 图谱 {result.total_workflows_graph} vs DS {result.total_workflows_ds}")
    print(f"  任务: 图谱 {result.total_tasks_graph} vs DS {result.total_tasks_ds}")
    print(f"  问题总数: {len(result.issues)}")
    print(f"  HIGH: {len([i for i in result.issues if i.severity == 'HIGH'])}")
    print(f"  MEDIUM: {len([i for i in result.issues if i.severity == 'MEDIUM'])}")
    print(f"  LOW: {len([i for i in result.issues if i.severity == 'LOW'])}")


if __name__ == "__main__":
    main()