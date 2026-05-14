#!/usr/bin/env python
"""
隐式依赖分析脚本 - 命令行入口

扫描 DolphinScheduler 项目的工作流，分析隐式依赖关系：
1. SUB_PROCESS 任务 - 子工作流调用
2. DEPENDENT 任务 - 外部依赖等待

输出依赖图和未关联依赖的工作流报告。

Usage:
    python scripts/analyze_implicit_dependency.py <project_name> [--output-dir <dir>]

Example:
    python scripts/analyze_implicit_dependency.py ad_monitor
    python scripts/analyze_implicit_dependency.py ad_monitor --output-dir ./reports
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.implicit_dependency_analyzer import analyze_implicit_dependency, ImplicitDependencyAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="分析 DolphinScheduler 项目工作流的隐式依赖关系"
    )
    parser.add_argument(
        "project_name",
        help="项目名称（如 ad_monitor）"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(PROJECT_ROOT / "data" / "analysis"),
        help="输出目录（默认: data/analysis）"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存报告文件，只打印结果"
    )

    args = parser.parse_args()

    # 创建输出目录
    output_dir = None if args.no_save else args.output_dir
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 执行分析
    result = analyze_implicit_dependency(args.project_name, output_dir)

    if result.total_workflows == 0:
        print("\n[ERROR] 分析失败，请检查项目名称和 API 配置")
        sys.exit(1)

    # 打印报告
    print("\n" + "=" * 80)
    print("分析报告")
    print("=" * 80)
    analyzer = ImplicitDependencyAnalyzer()
    print(analyzer.generate_report(result))

    # 提示
    if output_dir:
        print(f"\n[INFO] 报告文件已保存到: {output_dir}")
        print(f"[INFO] 可用浏览器打开 HTML 报告查看依赖图:")
        print(f"       {Path(output_dir) / f'{result.project_code}_implicit_dependency.html'}")
        print(f"[INFO] 或使用在线 DOT 渲染器: https://dreampuf.github.io/GraphvizOnline")


if __name__ == "__main__":
    main()