# skills/shell-error-analyzer/scripts/analyze_traceback.py
"""
Shell 错误位置解析

提取：
- 错误行号
- 错误位置（文件:行）
"""

import re
import json
from typing import Dict, Optional

def parse_shell_error(log: str) -> Dict:
    """解析 Shell 错误位置"""
    result = {
        'error_type': None,
        'line_number': None,
        'file': None,
        'error_message': None
    }

    # 提取行号: line {number}:
    line_pattern = r'line (\d+):'
    line_match = re.search(line_pattern, log)
    if line_match:
        result['line_number'] = int(line_match.group(1))

    # 提取错误类型
    error_types = ['syntax error', 'unexpected EOF', 'Permission denied', 'command not found']
    for et in error_types:
        if et.lower() in log.lower():
            result['error_type'] = et
            break

    # 提取错误消息
    result['error_message'] = log[:200]

    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = parse_shell_error(args.log)
    print(json.dumps(result, ensure_ascii=False))