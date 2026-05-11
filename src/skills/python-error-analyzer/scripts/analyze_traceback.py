# skills/python-error-analyzer/scripts/analyze_traceback.py
"""
Python Traceback 解析脚本

解析 Python traceback 并提取：
- 错误类型
- 错误消息
- 调用栈帧
- Root cause（最后一个调用帧）
"""

import re
import json
from typing import Dict, List, Optional, Any


def parse_traceback(log: str) -> Dict[str, Any]:
    """
    解析 Python traceback

    Args:
        log: 包含 traceback 的日志内容

    Returns:
        包含解析结果的字典
    """
    result = {
        'error_type': None,
        'error_message': None,
        'frames': [],
        'root_cause': None,
        'file_path': None,
        'line_number': None,
        'function_name': None
    }

    # Extract traceback frames: File "{file}", line {line}, in {function}
    frame_pattern = r'File "([^"]+)", line (\d+), in (\S+)'
    frames = []

    for match in re.finditer(frame_pattern, log):
        file_path = match.group(1)
        line_number = int(match.group(2))
        function_name = match.group(3)

        frame = {
            'file': file_path,
            'line': line_number,
            'function': function_name
        }
        frames.append(frame)

    result['frames'] = frames

    # Root cause is the last frame in the traceback
    if frames:
        result['root_cause'] = frames[-1]
        result['file_path'] = frames[-1]['file']
        result['line_number'] = frames[-1]['line']
        result['function_name'] = frames[-1]['function']

    # Extract error type and message from the last line
    # Common Python error types
    error_patterns = [
        # Standard exceptions
        r'(ModuleNotFoundError):\s*(.+)',
        r'(ImportError):\s*(.+)',
        r'(SyntaxError):\s*(.+)',
        r'(IndentationError):\s*(.+)',
        r'(TypeError):\s*(.+)',
        r'(ValueError):\s*(.+)',
        r'(KeyError):\s*[\'"]?([^\'"]+)[\'"]?',
        r'(AttributeError):\s*(.+)',
        r'(NameError):\s*(.+)',
        r'(IndexError):\s*(.+)',
        r'(ZeroDivisionError):\s*(.+)',
        r'(FileNotFoundError):\s*(.+)',
        r'(PermissionError):\s*(.+)',
        r'(ConnectionError):\s*(.+)',
        r'(TimeoutError):\s*(.+)',
        r'(RuntimeError):\s*(.+)',
        r'(StopIteration):\s*(.*)',
        r'(AssertionError):\s*(.+)',
        r'(NotImplementedError):\s*(.+)',
        r'(RecursionError):\s*(.+)',
        r'(MemoryError):\s*(.*)',
        r'(OSError):\s*(.+)',
        r'(UnicodeDecodeError):\s*(.+)',
        r'(UnicodeEncodeError):\s*(.+)',
        r'(JSONDecodeError):\s*(.+)',
        r'(HTTPError):\s*(.+)',
        # Generic exception pattern
        r'(\w+Error):\s*(.+)',
        r'(\w+Exception):\s*(.+)',
    ]

    for pattern in error_patterns:
        match = re.search(pattern, log, re.MULTILINE)
        if match:
            result['error_type'] = match.group(1)
            result['error_message'] = match.group(2).strip() if match.group(2) else ''
            break

    # Handle SyntaxError special case (line info in error message)
    if result['error_type'] == 'SyntaxError':
        syntax_line_match = re.search(r'line (\d+)', log)
        if syntax_line_match and not result['line_number']:
            result['line_number'] = int(syntax_line_match.group(1))

        # Extract file path for SyntaxError
        if not result['file_path']:
            file_match = re.search(r'File "([^"]+)"', log)
            if file_match:
                result['file_path'] = file_match.group(1)

    return result


def analyze_traceback(log: str) -> Dict[str, Any]:
    """
    分析 Python traceback 并返回完整分析结果

    Args:
        log: 包含 traceback 的日志内容

    Returns:
        包含完整分析结果的字典
    """
    result = parse_traceback(log)

    # Add summary
    if result['error_type']:
        result['summary'] = f"{result['error_type']}: {result['error_message']}"
    else:
        result['summary'] = "Unknown error"

    # Add location info
    if result['file_path']:
        location = f"{result['file_path']}"
        if result['line_number']:
            location += f":{result['line_number']}"
        if result['function_name']:
            location += f" in {result['function_name']}"
        result['location'] = location
    else:
        result['location'] = None

    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = analyze_traceback(args.log)
    print(json.dumps(result, ensure_ascii=False, indent=2))