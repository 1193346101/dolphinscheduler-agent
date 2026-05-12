"""
Pattern Matcher - 统一的错误模式匹配模块

提供公共的模式解析和匹配功能，符合 anthropics/skills 规范。
所有模式维护在 patterns.md 文件中，实现"人可编辑维护"原则。

核心功能:
- parse_patterns_file: 解析 patterns.md Markdown 文件
- match_error: 执行正则匹配，返回 MatchResult
- PatternMatcher: 封装完整匹配流程的类

模式分类（优先级从高到低）:
- AUTO_FIXABLE: 可直接修复（如拼写错误、配置调整）
- RESOURCE_SUGGESTED: 资源问题，Skill计算+LLM验证
- KNOWN_NEEDS_LLM: 已知类型，需LLM分析
- UNKNOWN: 未知错误，完全交给LLM
"""

import re
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


class PatternCategory(Enum):
    """模式分类枚举"""
    AUTO_FIXABLE = "AUTO_FIXABLE"
    RESOURCE_SUGGESTED = "RESOURCE_SUGGESTED"
    KNOWN_NEEDS_LLM = "KNOWN_NEEDS_LLM"
    UNKNOWN = "UNKNOWN"


@dataclass
class PatternEntry:
    """单个模式条目"""
    error_type: str
    pattern: str              # 正则表达式
    category: PatternCategory
    hint: str                 # 根据 category：fix_action / skill_hint / llm_hint
    sub_category: Optional[str] = None  # 子分类（如 "连接错误"、"数据错误"）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_type": self.error_type,
            "pattern": self.pattern,
            "category": self.category.value,
            "hint": self.hint,
            "sub_category": self.sub_category,
        }


@dataclass
class MatchResult:
    """匹配结果"""
    error_type: str
    category: str
    matched_pattern: str
    hint: str
    error_message: str
    extra_info: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_type": self.error_type,
            "category": self.category,
            "matched_pattern": self.matched_pattern,
            "hint": self.hint,
            "error_message": self.error_message,
            "extra_info": self.extra_info or {},
        }


def parse_patterns_file(patterns_file: str) -> Dict[PatternCategory, List[PatternEntry]]:
    """
    解析 patterns.md 文件

    支持格式:
    - ## AUTO_FIXABLE / ## RESOURCE_SUGGESTED / ## KNOWN_NEEDS_LLM 分类标题
    - ### 子分类标题（可选）
    - Markdown 表格: | error_type | pattern | hint |

    Args:
        patterns_file: patterns.md 文件路径

    Returns:
        Dict[PatternCategory, List[PatternEntry]]: 分类模式字典
    """
    patterns = {
        PatternCategory.AUTO_FIXABLE: [],
        PatternCategory.RESOURCE_SUGGESTED: [],
        PatternCategory.KNOWN_NEEDS_LLM: [],
    }

    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        current_category = PatternCategory.KNOWN_NEEDS_LLM  # 默认分类
        current_sub_category = None

        for line in content.split('\n'):
            line_stripped = line.strip()

            # 检测分类标题 ## AUTO_FIXABLE / ## RESOURCE_SUGGESTED / ## KNOWN_NEEDS_LLM
            if line_stripped.startswith('## '):
                category_name = line_stripped.replace('## ', '').strip()
                if 'AUTO_FIXABLE' in category_name.upper():
                    current_category = PatternCategory.AUTO_FIXABLE
                elif 'RESOURCE_SUGGESTED' in category_name.upper():
                    current_category = PatternCategory.RESOURCE_SUGGESTED
                elif 'KNOWN_NEEDS_LLM' in category_name.upper():
                    current_category = PatternCategory.KNOWN_NEEDS_LLM
                current_sub_category = None
                continue

            # 检测子分类标题 ###
            if line_stripped.startswith('### '):
                current_sub_category = line_stripped.replace('### ', '').strip()
                continue

            # 跳过空行和注释
            if not line_stripped or line_stripped.startswith('#'):
                continue

            # 解析表格行 | error_type | pattern | hint |
            if line_stripped.startswith('|'):
                # 跳过表头和分隔行
                if 'error_type' in line_stripped.lower():
                    continue
                if line_stripped.startswith('|--') or line_stripped.startswith('| ---'):
                    continue

                parts = [p.strip() for p in line_stripped.split('|')]
                # parts 结构: ['', 'error_type', 'pattern', 'hint', '']
                # 过滤空元素
                parts = [p for p in parts if p]

                if len(parts) >= 3:
                    error_type = parts[0]
                    pattern = parts[1].strip('`')  # 移除反引号
                    hint = parts[2] if len(parts) > 2 else ''

                    if error_type and pattern and error_type != 'error_type':
                        entry = PatternEntry(
                            error_type=error_type,
                            pattern=pattern,
                            category=current_category,
                            hint=hint,
                            sub_category=current_sub_category,
                        )
                        patterns[current_category].append(entry)

    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error parsing patterns file: {e}", file=__import__('sys').stderr)

    return patterns


def extract_error_snippet(log_content: str, pattern: str, context_lines: int = 5) -> str:
    """
    提取错误消息片段（带上下文）

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

    # 如果单行没匹配到，返回前500字符
    return log_content[:500]


def match_error(log_content: str, patterns: Dict[PatternCategory, List[PatternEntry]]) -> MatchResult:
    """
    执行错误模式匹配

    匹配顺序（优先级）: AUTO_FIXABLE > RESOURCE_SUGGESTED > KNOWN_NEEDS_LLM

    使用 re.IGNORECASE | re.DOTALL 处理跨行日志

    Args:
        log_content: 日志内容
        patterns: 分类模式字典（由 parse_patterns_file 返回）

    Returns:
        MatchResult: 匹配结果
    """
    # 按优先级遍历
    category_order = [
        PatternCategory.AUTO_FIXABLE,
        PatternCategory.RESOURCE_SUGGESTED,
        PatternCategory.KNOWN_NEEDS_LLM,
    ]

    for category in category_order:
        for entry in patterns.get(category, []):
            try:
                # 使用 re.IGNORECASE | re.DOTALL 处理跨行匹配
                if re.search(entry.pattern, log_content, re.IGNORECASE | re.DOTALL):
                    error_message = extract_error_snippet(log_content, entry.pattern)

                    # 解析 hint 中的 JSON（AUTO_FIXABLE 可能有 fix_action）
                    extra_info = {"sub_category": entry.sub_category}
                    hint = entry.hint

                    # 如果 hint 是 JSON 格式，解析并放入 extra_info
                    if hint and hint.startswith('{'):
                        try:
                            fix_action = json.loads(hint)
                            extra_info["fix_action"] = fix_action
                        except json.JSONDecodeError:
                            pass

                    return MatchResult(
                        error_type=entry.error_type,
                        category=entry.category.value,
                        matched_pattern=entry.pattern,
                        hint=hint,
                        error_message=error_message,
                        extra_info=extra_info,
                    )
            except re.error:
                # 无效正则，跳过
                continue

    # 未匹配任何模式
    return MatchResult(
        error_type='unknown',
        category='UNKNOWN',
        matched_pattern='',
        hint='',
        error_message=log_content[:500],
        extra_info={},
    )


class PatternMatcher:
    """
    统一的错误模式匹配器

    封装完整的模式加载和匹配流程，支持缓存。

    使用方式:
        matcher = PatternMatcher("spark", "path/to/patterns.md")
        result = matcher.match(log_content)
    """

    def __init__(self, skill_name: str, patterns_file: Optional[str] = None):
        """
        初始化 PatternMatcher

        Args:
            skill_name: Skill 名称（如 spark, shell, python, datax）
            patterns_file: patterns.md 文件路径（可选，自动查找）
        """
        self.skill_name = skill_name
        self._patterns: Optional[Dict[PatternCategory, List[PatternEntry]]] = None
        self._patterns_file = patterns_file

    def _find_patterns_file(self) -> Optional[str]:
        """自动查找 patterns.md 文件"""
        # 根据 skill_name 定位 patterns.md
        skill_dir = Path(__file__).parent.parent / self.skill_name
        patterns_file = skill_dir / "patterns.md"
        if patterns_file.exists():
            return str(patterns_file)

        # 尝试其他命名
        for name in [f"{self.skill_name}_patterns.md", "error_patterns.md"]:
            alt_file = skill_dir / name
            if alt_file.exists():
                return str(alt_file)

        return None

    def load_patterns(self) -> Dict[PatternCategory, List[PatternEntry]]:
        """
        加载模式表（支持缓存）

        Returns:
            Dict[PatternCategory, List[PatternEntry]]: 分类模式字典
        """
        if self._patterns is None:
            patterns_file = self._patterns_file
            if not patterns_file:
                patterns_file = self._find_patterns_file()

            if patterns_file:
                self._patterns = parse_patterns_file(patterns_file)
            else:
                self._patterns = {}

        return self._patterns

    def match(self, log_content: str) -> MatchResult:
        """
        执行模式匹配

        Args:
            log_content: 日志内容

        Returns:
            MatchResult: 匹配结果
        """
        patterns = self.load_patterns()
        return match_error(log_content, patterns)

    def get_pattern_count(self) -> Dict[str, int]:
        """
        获取各分类的模式数量

        Returns:
            Dict[str, int]: {category_name: count}
        """
        patterns = self.load_patterns()
        return {
            category.value: len(entries)
            for category, entries in patterns.items()
        }

    def reload_patterns(self) -> None:
        """重新加载模式表（清除缓存）"""
        self._patterns = None


def get_matcher_for_skill(skill_name: str) -> PatternMatcher:
    """
    获取特定 Skill 的 PatternMatcher 实例

    Args:
        skill_name: Skill 名称

    Returns:
        PatternMatcher: 模式匹配器实例
    """
    return PatternMatcher(skill_name)


# CLI 入口（支持命令行调用）
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='错误模式匹配工具')
    parser.add_argument('--patterns', required=True, help='patterns.md 文件路径')
    parser.add_argument('--log', required=True, help='日志内容')
    parser.add_argument('--skill', default='unknown', help='Skill 名称')
    parser.add_argument('--stats', action='store_true', help='显示模式统计信息')
    args = parser.parse_args()

    matcher = PatternMatcher(args.skill, args.patterns)

    if args.stats:
        stats = matcher.get_pattern_count()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        result = matcher.match(args.log)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


__all__ = [
    "PatternCategory",
    "PatternEntry",
    "MatchResult",
    "parse_patterns_file",
    "match_error",
    "extract_error_snippet",
    "PatternMatcher",
    "get_matcher_for_skill",
]