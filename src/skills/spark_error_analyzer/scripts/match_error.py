"""
match_error.py - Spark error pattern matching script

Reads spark_patterns.md and matches error patterns from log content.
"""

import re
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ErrorPattern:
    """Represents a single error pattern"""
    error_type: str
    pattern: str
    category: str  # AUTO_FIXABLE | KNOWN_NEEDS_LLM
    fix_action: str
    llm_hint: str


def load_patterns(patterns_file: str) -> Dict[str, Dict]:
    """
    Load error patterns from a Markdown table file.

    Args:
        patterns_file: Path to the Markdown file containing patterns table

    Returns:
        Dict mapping error_type to pattern info:
        {
            'oom_executor': {
                'pattern': 'java.lang.OutOfMemoryError: Java heap space',
                'category': 'AUTO_FIXABLE',
                'fix_action': 'increase executor memory',
                'llm_hint': ''
            },
            ...
        }

    Raises:
        FileNotFoundError: If patterns_file does not exist
    """
    path = Path(patterns_file)
    if not path.exists():
        raise FileNotFoundError(f"Patterns file not found: {patterns_file}")

    patterns = {}

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        line = line.rstrip('\n\r')

        # Skip empty lines
        if not line.strip():
            continue

        # Check if this is a table row (starts with |)
        if not line.startswith('|'):
            continue

        # Split by | and strip whitespace
        parts = [p.strip() for p in line.split('|')]

        # Remove empty strings from the beginning and end
        while parts and not parts[0]:
            parts.pop(0)
        while parts and not parts[-1]:
            parts.pop()

        # Skip header row
        if parts and parts[0] == 'error_type':
            continue

        # Skip separator row (contains only dashes and pipes)
        if parts and all(set(p.replace('-', '').replace('|', '')) == set() or not p for p in parts):
            continue

        # Need at least 3 columns: error_type, pattern, category
        if len(parts) < 3:
            continue

        error_type = parts[0]
        pattern = parts[1]
        category = parts[2]
        fix_action = parts[3] if len(parts) > 3 else ''
        llm_hint = parts[4] if len(parts) > 4 else ''

        # Clean up pattern - remove backticks if present
        pattern = pattern.strip('`')

        patterns[error_type] = {
            'pattern': pattern,
            'category': category,
            'fix_action': fix_action,
            'llm_hint': llm_hint
        }

    return patterns


def match_error(log_content: str, patterns_file: str) -> Dict:
    """
    Match error patterns against log content.

    Args:
        log_content: The log content to analyze
        patterns_file: Path to the Markdown patterns file

    Returns:
        Dict with:
        - error_type: str (matched error type or 'unknown')
        - category: 'AUTO_FIXABLE' | 'KNOWN_NEEDS_LLM' | 'UNKNOWN'
        - matched_pattern: str (the regex pattern that matched, or '')
        - extra: str (fix_action for AUTO_FIXABLE, llm_hint for KNOWN_NEEDS_LLM, or '')
        - error_message: str (extracted error context)
    """
    if not log_content or not log_content.strip():
        return {
            'error_type': 'unknown',
            'category': 'UNKNOWN',
            'matched_pattern': '',
            'extra': '',
            'error_message': ''
        }

    try:
        patterns = load_patterns(patterns_file)
    except FileNotFoundError:
        return {
            'error_type': 'unknown',
            'category': 'UNKNOWN',
            'matched_pattern': '',
            'extra': '',
            'error_message': log_content[:500] if log_content else ''
        }

    # Try each pattern in order
    for error_type, pattern_info in patterns.items():
        pattern = pattern_info['pattern']
        category = pattern_info['category']
        fix_action = pattern_info.get('fix_action', '')
        llm_hint = pattern_info.get('llm_hint', '')

        try:
            # Use re.DOTALL (re.S) to allow . to match newlines
            # Use re.IGNORECASE for case-insensitive matching
            match = re.search(pattern, log_content, re.IGNORECASE | re.DOTALL)

            if match:
                # Extract error context
                error_message = _extract_error_message(log_content, pattern)

                # Determine extra field based on category
                if category == 'AUTO_FIXABLE':
                    extra = fix_action
                else:
                    extra = llm_hint

                return {
                    'error_type': error_type,
                    'category': category,
                    'matched_pattern': pattern,
                    'extra': extra,
                    'error_message': error_message
                }
        except re.error:
            # Skip invalid regex patterns
            continue

    # No match found
    return {
        'error_type': 'unknown',
        'category': 'UNKNOWN',
        'matched_pattern': '',
        'extra': '',
        'error_message': log_content[:500] if log_content else ''
    }


def _extract_error_message(log_content: str, pattern: str) -> str:
    """
    Extract error message context from log content.

    Args:
        log_content: Full log content
        pattern: The regex pattern that matched

    Returns:
        Extracted error context (up to 500 chars)
    """
    lines = log_content.split('\n')

    # Try to find the matching line and get context
    for i, line in enumerate(lines):
        try:
            if re.search(pattern, line, re.IGNORECASE):
                # Get context: 3 lines before, 3 lines after
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                context = '\n'.join(lines[start:end])
                return context[:500] if len(context) > 500 else context
        except re.error:
            continue

    # If single line match didn't work, try multi-line match
    try:
        match = re.search(pattern, log_content, re.IGNORECASE | re.DOTALL)
        if match:
            start = max(0, match.start() - 200)
            end = min(len(log_content), match.end() + 200)
            return log_content[start:end]
    except re.error:
        pass

    # Fallback: return first 500 chars
    return log_content[:500] if log_content else ''


if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python match_error.py <patterns_file> [log_file]")
        print("       python match_error.py <patterns_file> -  # reads log from stdin")
        sys.exit(1)

    patterns_file = sys.argv[1]

    if len(sys.argv) >= 3:
        if sys.argv[2] == '-':
            log_content = sys.stdin.read()
        else:
            with open(sys.argv[2], 'r', encoding='utf-8') as f:
                log_content = f.read()
    else:
        # Read from stdin by default
        log_content = sys.stdin.read()

    result = match_error(log_content, patterns_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))