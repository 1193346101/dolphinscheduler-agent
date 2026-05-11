# skills/python-error-analyzer/scripts/match_error.py
"""
Python 错误模式匹配脚本
"""

import re
import json
from typing import Dict
from pathlib import Path

def load_patterns(patterns_file: str) -> Dict:
    """加载模式表"""
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        in_table = False
        for line in content.split('\n'):
            # Detect table start
            if '| error_type | pattern |' in line:
                in_table = True
                continue

            # Skip table separator
            if '|--' in line or '|---' in line:
                continue

            # Parse table rows
            if in_table and line.startswith('|'):
                parts = [p.strip() for p in line.split('|')]
                # parts[0] is empty (before first |), parts[-1] is empty (after last |)
                if len(parts) >= 4:
                    error_type = parts[1]
                    pattern = parts[2]
                    llm_hint = parts[3] if len(parts) > 3 else ''
                    if error_type and error_type != 'error_type':
                        patterns[error_type] = {
                            'pattern': pattern,
                            'category': 'KNOWN_NEEDS_LLM',
                            'llm_hint': llm_hint
                        }
            elif in_table and not line.startswith('|'):
                # End of table
                in_table = False

    except FileNotFoundError:
        pass

    return patterns

def match_error(log_content: str, patterns_file: str = None) -> Dict:
    """匹配错误模式"""
    # Use default patterns if no file specified
    if patterns_file is None:
        patterns_file = str(Path(__file__).parent.parent / 'python_patterns.md')

    patterns = load_patterns(patterns_file)

    for error_type, info in patterns.items():
        pattern = info['pattern']
        try:
            if re.search(pattern, log_content, re.IGNORECASE):
                return {
                    'error_type': error_type,
                    'category': 'KNOWN_NEEDS_LLM',
                    'matched_pattern': pattern,
                    'llm_hint': info['llm_hint'],
                    'error_message': log_content[:500]
                }
        except re.error:
            continue

    return {
        'error_type': 'unknown',
        'category': 'UNKNOWN',
        'error_message': log_content[:500]
    }

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns', required=False, default=None)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = match_error(args.log, args.patterns)
    print(json.dumps(result, ensure_ascii=False))