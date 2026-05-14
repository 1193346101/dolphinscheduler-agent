"""
Skills错误分析功能全面测试

测试流程:
1. 加载各场景日志文件 (完整生产格式)
2. 运行完整告警处理流程
3. 验证分析结果准确性
4. 生成HTML错误报告
5. 对比预期与实际差异

场景列表:
- spark_oom_executor: Executor OOM (内存不足)
- spark_oom_driver: Driver OOM
- spark_shuffle_failed: Shuffle Service失败
- spark_class_not_found: 类找不到
- spark_partition_missing: 分区不存在
- spark_sql_error: SQL语法错误
- datax_sync_failed: DataX同步失败
- shell_command_error: Shell命令错误
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.workflow.nodes.analyze import analyze_error
from src.workflow.state import AgentState
from src.tools.report_generator import ReportGenerator
from src.skills.common.preprocess_log import preprocess_log, extract_error_blocks
from src.config import settings

# 测试结果记录
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "scenarios": []
}

def run_scenario_test(scenario_name, log_file, expected_result):
    """
    运行单个场景测试

    Args:
        scenario_name: 场景名称
        log_file: 日志文件路径
        expected_result: 预期结果 {error_type, category, should_have_action}
    """
    print(f"\n{'='*70}")
    print(f"测试场景: {scenario_name}")
    print(f"{'='*70}")

    # 加载日志
    log_path = project_root / "tests" / "scenarios" / "logs" / log_file
    if not log_path.exists():
        print(f"[ERROR] 日志文件不存在: {log_path}")
        return False

    with open(log_path, 'r', encoding='utf-8') as f:
        log_content = f.read()

    print(f"[1] 日志加载: {len(log_content)} 字符")

    # 预处理日志
    preprocessed = preprocess_log(log_content, task_type='spark')
    error_blocks = preprocessed.get('error_blocks', [])
    config_lines = preprocessed.get('config_lines', [])

    print(f"[2] 预处理结果:")
    print(f"    - 错误块: {len(error_blocks)}个")
    print(f"    - 配置行: {len(config_lines)}条")

    # 显示前2个错误块
    if error_blocks:
        print(f"    - 错误块样例:")
        for i, block in enumerate(error_blocks[:2], 1):
            block_preview = block[:150].replace('\n', ' ')
            print(f"      [{i}] {block_preview}...")

    # 构建测试状态
    state = AgentState(
        project_code="11598158952448",
        project_name="ad_monitor",
        workflow_code="11598178397184",
        workflow_name="测试工作流",
        task_code="12345",
        task_name=scenario_name,
        task_type="SPARK",
        driver_logs=log_content,
        spark_logs="",
        yarn_logs="",
        token_consumption=0,
        token_details={},
    )

    # 运行分析
    print(f"[3] 执行错误分析...")
    try:
        result_state = analyze_error(state)

        error_analysis = result_state.get('error_analysis', {})
        error_type = error_analysis.get('error_type', 'unknown')
        category = error_analysis.get('category', 'UNKNOWN')
        suggested_actions = result_state.get('suggested_actions', [])

        print(f"[4] 分析结果:")
        print(f"    - 错误类型: {error_type}")
        print(f"    - 错误类别: {category}")
        print(f"    - 建议数量: {len(suggested_actions)}")

        # 显示建议
        if suggested_actions:
            print(f"    - 建议内容:")
            for i, action in enumerate(suggested_actions[:3], 1):
                action_type = action.get('action_type', 'unknown')
                desc = action.get('description', '')[:100]
                print(f"      [{i}] {action_type}: {desc}")

        # 验证结果
        print(f"[5] 验证结果:")

        # 检查错误类型是否匹配
        expected_error_type = expected_result.get('error_type', '')
        error_type_match = expected_error_type in error_type.lower() or error_type.lower() in expected_error_type

        if error_type_match:
            print(f"    [PASS] 错误类型匹配: 期望'{expected_error_type}', 实际'{error_type}'")
        else:
            print(f"    [FAIL] 错误类型不匹配: 期望'{expected_error_type}', 实际'{error_type}'")

        # 检查是否有建议
        should_have_action = expected_result.get('should_have_action', True)
        has_actions = len(suggested_actions) > 0

        if should_have_action and has_actions:
            print(f"    [PASS] 生成了修复建议: {len(suggested_actions)}条")
        elif should_have_action and not has_actions:
            print(f"    [FAIL] 未生成修复建议")
        else:
            print(f"    [INFO] 无需修复建议")

        # 检查建议合理性
        action_reasonable = True
        for action in suggested_actions:
            # 检查建议是否有明确的描述
            desc = action.get('description', '')
            if not desc or len(desc) < 10:
                action_reasonable = False
                print(f"    [WARN] 建议描述不完整: {action}")

        if action_reasonable:
            print(f"    [PASS] 建议描述完整")
        else:
            print(f"    [FAIL] 建议描述不完整")

        # 生成报告
        print(f"[6] 生成错误报告...")
        report_gen = ReportGenerator()
        report_id = report_gen.generate_report(result_state)
        print(f"    - 报告ID: {report_id}")

        # 检查报告文件
        report_dir = project_root / "data" / "reports" / datetime.now().strftime("%Y-%m-%d")
        report_path = report_dir / "12345" / report_id

        if report_path.exists():
            print(f"    [PASS] 报告文件已生成: {report_path}")

            # 检查HTML报告
            html_file = report_path / "report.html"
            if html_file.exists():
                print(f"    [PASS] HTML报告: {html_file}")

            # 检查JSON报告
            json_file = report_path / "report.json"
            if json_file.exists():
                print(f"    [PASS] JSON报告: {json_file}")
        else:
            print(f"    [FAIL] 报告文件未生成")

        # 记录结果
        passed = error_type_match and (not should_have_action or has_actions) and action_reasonable

        test_results["scenarios"].append({
            "name": scenario_name,
            "passed": passed,
            "error_type": error_type,
            "expected_error_type": expected_error_type,
            "category": category,
            "actions_count": len(suggested_actions),
            "report_id": report_id,
        })

        if passed:
            test_results["passed"] += 1
        else:
            test_results["failed"] += 1
        test_results["total"] += 1

        return passed

    except Exception as e:
        import traceback
        print(f"[ERROR] 分析失败: {e}")
        traceback.print_exc()

        test_results["scenarios"].append({
            "name": scenario_name,
            "passed": False,
            "error": str(e),
        })
        test_results["failed"] += 1
        test_results["total"] += 1

        return False


# 测试场景定义
scenarios = [
    {
        "name": "Spark Executor OOM",
        "log_file": "spark_oom_executor_full.txt",
        "expected": {
            "error_type": "oom",
            "category": "RESOURCE",
            "should_have_action": True,
        }
    },
    {
        "name": "Spark Shuffle失败",
        "log_file": "spark_shuffle_failed.txt",
        "expected": {
            "error_type": "shuffle",
            "category": "NETWORK",
            "should_have_action": True,
        }
    },
    {
        "name": "Spark ClassNotFound",
        "log_file": "spark_class_not_found.txt",
        "expected": {
            "error_type": "class_not_found",
            "category": "CONFIG",
            "should_have_action": True,
        }
    },
    {
        "name": "Spark 分区不存在",
        "log_file": "spark_partition_missing.txt",
        "expected": {
            "error_type": "partition",
            "category": "DATA",
            "should_have_action": True,
        }
    },
]


def main():
    """运行所有场景测试"""
    print("="*70)
    print("Skills错误分析功能全面测试")
    print("="*70)
    print(f"测试场景数: {len(scenarios)}")
    print(f"配置检查:")
    print(f"  - DS_API_URL: {settings.DS_API_URL[:50]}...")
    print(f"  - SPARK_HISTORY_URL: {settings.SPARK_HISTORY_URL}")
    print(f"  - YARN_RM_URL: {settings.YARN_RM_URL}")

    # 运行每个场景
    for scenario in scenarios:
        run_scenario_test(
            scenario["name"],
            scenario["log_file"],
            scenario["expected"]
        )

    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    print(f"总计: {test_results['total']}个场景")
    print(f"通过: {test_results['passed']}个")
    print(f"失败: {test_results['failed']}个")

    if test_results['failed'] > 0:
        print("\n失败场景:")
        for s in test_results['scenarios']:
            if not s['passed']:
                print(f"  - {s['name']}: {s.get('error', '分析结果不符合预期')}")

    # 保存结果
    result_file = project_root / "tests" / "scenarios" / "test_results.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {result_file}")

    return test_results['passed'] == test_results['total']


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)