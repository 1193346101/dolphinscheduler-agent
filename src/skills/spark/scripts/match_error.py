"""
Spark 错误模式匹配脚本

使用公共 pattern_matcher 模块，符合 anthropics/skills 规范。
所有模式维护在 patterns.md 文件中。

支持分类:
- AUTO_FIXABLE: 可直接修复
- RESOURCE_SUGGESTED: 资源问题，需智能计算
- KNOWN_NEEDS_LLM: 已知类型，需LLM分析
"""

import sys
import json
from pathlib import Path
from typing import Dict, Optional

# 动态导入公共 pattern_matcher（处理相对导入路径）
_pattern_matcher_path = Path(__file__).parent.parent.parent / "common" / "pattern_matcher.py"


def _import_pattern_matcher():
    """动态导入 pattern_matcher 模块"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("pattern_matcher", _pattern_matcher_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def match_error(log_content: str, patterns_file: str = None) -> Dict:
    """
    匹配 Spark 错误模式

    Args:
        log_content: 日志内容
        patterns_file: 模式文件路径（默认使用 ../patterns.md）

    Returns:
        dict: {
            error_type: str,
            category: str,
            matched_pattern: str,
            hint: str,
            error_message: str,
            extra: dict
        }
    """
    if patterns_file is None:
        patterns_file = str(Path(__file__).parent.parent / "patterns.md")

    try:
        pattern_matcher = _import_pattern_matcher()
        matcher = pattern_matcher.PatternMatcher("spark", patterns_file)
        result = matcher.match(log_content)

        return {
            'error_type': result.error_type,
            'category': result.category,
            'matched_pattern': result.matched_pattern,
            'hint': result.hint,
            'error_message': result.error_message,
            'extra': result.extra_info,
        }
    except Exception as e:
        print(f"Error in match_error: {e}", file=sys.stderr)
        return {
            'error_type': 'unknown',
            'category': 'UNKNOWN',
            'matched_pattern': '',
            'hint': '',
            'error_message': log_content[:500],
            'extra': {},
        }


def load_patterns(patterns_file: str) -> Dict:
    """
    加载模式表（兼容旧接口）

    Args:
        patterns_file: 模式文件路径

    Returns:
        dict: {error_type: {pattern, category, llm_hint}}
    """
    if patterns_file is None:
        patterns_file = str(Path(__file__).parent.parent / "patterns.md")

    try:
        pattern_matcher = _import_pattern_matcher()
        patterns = pattern_matcher.parse_patterns_file(patterns_file)

        # 转换为扁平字典格式（兼容旧接口）
        flat_patterns = {}
        for category, entries in patterns.items():
            for entry in entries:
                flat_patterns[entry.error_type] = {
                    'pattern': entry.pattern,
                    'category': entry.category.value,
                    'llm_hint': entry.hint,
                    'sub_category': entry.sub_category,
                }
        return flat_patterns
    except Exception as e:
        print(f"Error loading patterns: {e}", file=sys.stderr)
        return {}


def match_error_with_app_info(log_content: str, patterns_file: str = None) -> Dict:
    """
    匹配错误并提取 Spark Application 信息

    Args:
        log_content: 日志内容
        patterns_file: 模式文件路径

    Returns:
        dict: 包含错误信息和 App ID
    """
    result = match_error(log_content, patterns_file)

    # 提取 Spark App ID
    import re
    app_patterns = [
        r"application_\d+_\d+",
        r"app-\d+-\d+",
        r"application_\d+",
    ]
    for p in app_patterns:
        match = re.search(p, log_content)
        if match:
            result['app_id'] = match.group(0)
            break

    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Spark 错误模式匹配')
    parser.add_argument('--patterns', required=False, default=None,
                        help='模式文件路径（默认使用 ../patterns.md）')
    parser.add_argument('--log', required=True, help='日志内容')
    parser.add_argument('--stats', action='store_true', help='显示模式统计信息')
    args = parser.parse_args()

    patterns_file = args.patterns or str(Path(__file__).parent.parent / "patterns.md")

    if args.stats:
        # 显示模式统计
        pattern_matcher = _import_pattern_matcher()
        matcher = pattern_matcher.PatternMatcher("spark", patterns_file)
        stats = matcher.get_pattern_count()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        result = match_error(args.log, patterns_file)
        print(json.dumps(result, ensure_ascii=False, indent=2))