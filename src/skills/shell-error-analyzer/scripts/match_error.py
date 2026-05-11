# skills/shell-error-analyzer/scripts/match_error.py
"""
Shell 错误模式匹配脚本
"""

import re
import json
from typing import Dict

def load_patterns(patterns_file: str) -> Dict:
    """加载模式表"""
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        for line in content.split('\n'):
            if line.startswith('|') and not line.startswith('| error_type') and not line.startswith('|--'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    error_type = parts[1]
                    pattern = parts[2].strip('`')  # Remove backticks from pattern
                    llm_hint = parts[3] if len(parts) > 3 else ''
                    patterns[error_type] = {
                        'pattern': pattern,
                        'category': 'KNOWN_NEEDS_LLM',
                        'llm_hint': llm_hint
                    }
    except FileNotFoundError:
        pass

    return patterns

def match_error(log_content: str, patterns_file: str) -> Dict:
    """匹配错误模式"""
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
    parser.add_argument('--patterns', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = match_error(args.log, args.patterns)
    print(json.dumps(result, ensure_ascii=False))