# skills/datax-error-analyzer/scripts/match_error.py
"""
DataX 错误模式匹配脚本
"""

import re
import json
from typing import Dict, Optional, Tuple
from pathlib import Path


def load_patterns(patterns_file: str) -> Dict:
    """加载模式表

    Args:
        patterns_file: 模式文件路径 (datax_patterns.md)

    Returns:
        dict: {error_type: {pattern, category, llm_hint}}
    """
    patterns = {}

    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        current_category = "KNOWN_NEEDS_LLM"

        for line in content.split('\n'):
            # 检测分类标题
            if '## KNOWN_NEEDS_LLM' in line or '## AUTO_FIXABLE' in line:
                current_category = line.replace('#', '').strip()
                continue

            # 跳过子分类标题 (###)
            if line.strip().startswith('###'):
                continue

            # 解析表格行
            if line.startswith('|') and not line.startswith('| error_type') and not line.startswith('|--') and not line.startswith('| ---'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    error_type = parts[1]
                    pattern = parts[2]
                    llm_hint = parts[3] if len(parts) > 3 else ''

                    if error_type and pattern:
                        patterns[error_type] = {
                            'pattern': pattern,
                            'category': current_category,
                            'llm_hint': llm_hint
                        }
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error loading patterns: {e}", file=__import__('sys').stderr)

    return patterns


def match_error(log_content: str, patterns_file: str) -> Dict:
    """匹配错误模式

    Args:
        log_content: 日志内容
        patterns_file: 模式文件路径

    Returns:
        dict: {
            error_type: str,
            category: str,
            matched_pattern: str,
            llm_hint: str,
            error_message: str
        }
    """
    patterns = load_patterns(patterns_file)

    for error_type, info in patterns.items():
        pattern = info['pattern']
        try:
            if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
                # 提取匹配的错误消息片段
                error_message = _extract_error_snippet(log_content, pattern)

                return {
                    'error_type': error_type,
                    'category': info['category'],
                    'matched_pattern': pattern,
                    'llm_hint': info['llm_hint'],
                    'error_message': error_message
                }
        except re.error:
            continue

    return {
        'error_type': 'unknown',
        'category': 'UNKNOWN',
        'error_message': log_content[:500]
    }


def _extract_error_snippet(log_content: str, pattern: str, context_lines: int = 5) -> str:
    """提取错误消息片段

    Args:
        log_content: 完整日志内容
        pattern: 匹配的正则模式
        context_lines: 上下文行数

    Returns:
        str: 包含上下文的错误片段
    """
    lines = log_content.split('\n')

    for i, line in enumerate(lines):
        try:
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                return '\n'.join(lines[start:end])
        except re.error:
            continue

    return log_content[:500]


def match_error_with_details(log_content: str, patterns_file: str) -> Dict:
    """匹配错误模式并返回详细信息

    包含额外的诊断信息，如数据库类型、连接信息等。

    Args:
        log_content: 日志内容
        patterns_file: 模式文件路径

    Returns:
        dict: 包含错误信息和诊断详情
    """
    result = match_error(log_content, patterns_file)

    # 提取数据库类型
    result['database_type'] = _detect_database_type(log_content)

    # 提取连接信息（脱敏）
    result['connection_info'] = _extract_connection_info(log_content)

    # 提取 Job 信息
    result['job_info'] = _extract_job_info(log_content)

    return result


def _detect_database_type(log_content: str) -> Optional[str]:
    """检测数据库类型

    Args:
        log_content: 日志内容

    Returns:
        str: 数据库类型 (mysql, oracle, postgresql, sqlserver 等)
    """
    db_patterns = {
        'mysql': [r'mysql', r'com\.mysql', r'MySQLIntegrityConstraintViolationException'],
        'oracle': [r'oracle', r'ORA-\d+', r'oracle\.jdbc'],
        'postgresql': [r'postgresql', r'org\.postgresql', r'psql'],
        'sqlserver': [r'sqlserver', r'microsoft\.sqlserver', r'com\.microsoft\.sqlserver'],
        'hive': [r'hive', r'org\.apache\.hadoop\.hive'],
        'hbase': [r'hbase', r'org\.apache\.hadoop\.hbase'],
        'mongodb': [r'mongodb', r'com\.mongodb'],
        'clickhouse': [r'clickhouse', r'ru\.yandex\.clickhouse'],
    }

    for db_type, patterns in db_patterns.items():
        for pattern in patterns:
            if re.search(pattern, log_content, re.IGNORECASE):
                return db_type

    return None


def _extract_connection_info(log_content: str) -> Dict:
    """提取连接信息（脱敏）

    Args:
        log_content: 日志内容

    Returns:
        dict: 连接信息（密码已脱敏）
    """
    info = {}

    # 提取 JDBC URL
    jdbc_match = re.search(r'jdbc:[a-z]+://([^\s,"\'>]+)', log_content, re.IGNORECASE)
    if jdbc_match:
        info['jdbc_host'] = jdbc_match.group(1).split(':')[0]

    # 提取用户名（不提取密码）
    user_match = re.search(r'user[=:\s]+([^\s&"\']+)', log_content, re.IGNORECASE)
    if user_match:
        info['username'] = user_match.group(1)

    return info


def _extract_job_info(log_content: str) -> Dict:
    """提取 DataX Job 信息

    Args:
        log_content: 日志内容

    Returns:
        dict: Job 信息
    """
    info = {}

    # 提取 Job ID
    job_match = re.search(r'\[job-(\d+)\]', log_content)
    if job_match:
        info['job_id'] = f"job-{job_match.group(1)}"

    # 提取 Channel 数量
    channel_match = re.search(r'channel.*?(\d+)', log_content, re.IGNORECASE)
    if channel_match:
        info['channels'] = int(channel_match.group(1))

    # 提取 Reader 类型
    reader_match = re.search(r'(mysql|oracle|postgresql|sqlserver|hive|hbase|mongodb|clickhouse)reader', log_content, re.IGNORECASE)
    if reader_match:
        info['reader_type'] = reader_match.group(1).lower()

    # 提取 Writer 类型
    writer_match = re.search(r'(mysql|oracle|postgresql|sqlserver|hive|hbase|mongodb|clickhouse)writer', log_content, re.IGNORECASE)
    if writer_match:
        info['writer_type'] = writer_match.group(1).lower()

    return info


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='DataX 错误模式匹配')
    parser.add_argument('--patterns', required=True, help='模式文件路径')
    parser.add_argument('--log', required=True, help='日志内容')
    parser.add_argument('--detailed', action='store_true', help='返回详细信息')
    args = parser.parse_args()

    if args.detailed:
        result = match_error_with_details(args.log, args.patterns)
    else:
        result = match_error(args.log, args.patterns)

    print(json.dumps(result, ensure_ascii=False, indent=2))