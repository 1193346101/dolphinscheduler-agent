"""Spark Error Analyzer Skill Package"""

from .scripts.match_error import load_patterns, match_error

__all__ = ['load_patterns', 'match_error']