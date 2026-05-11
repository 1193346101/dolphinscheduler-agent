"""
Tests for match_error.py - Spark error pattern matching
"""

import pytest
import tempfile
import os

from src.skills.spark_error_analyzer.scripts.match_error import load_patterns, match_error


class TestLoadPatterns:
    """Test load_patterns function"""

    def test_load_patterns_valid_file(self):
        """Test loading patterns from a valid markdown file"""
        # Create a temporary patterns file
        patterns_content = """# Spark Error Patterns

| error_type | pattern | category | fix_action | llm_hint |
|------------|---------|----------|------------|----------|
| oom_executor | `java.lang.OutOfMemoryError: Java heap space` | AUTO_FIXABLE | increase executor memory | |
| class_not_found | `ClassNotFoundException` | KNOWN_NEEDS_LLM | | Check missing class and dependencies |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_file = f.name

        try:
            patterns = load_patterns(patterns_file)
            assert 'oom_executor' in patterns
            assert 'class_not_found' in patterns
            assert patterns['oom_executor']['category'] == 'AUTO_FIXABLE'
            assert patterns['class_not_found']['category'] == 'KNOWN_NEEDS_LLM'
        finally:
            os.unlink(patterns_file)

    def test_load_patterns_empty_file(self):
        """Test loading patterns from empty file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("")
            patterns_file = f.name

        try:
            patterns = load_patterns(patterns_file)
            assert patterns == {}
        finally:
            os.unlink(patterns_file)

    def test_load_patterns_missing_file(self):
        """Test loading patterns from non-existent file raises error"""
        with pytest.raises(FileNotFoundError):
            load_patterns("/non/existent/path/patterns.md")


class TestMatchError:
    """Test match_error function"""

    @pytest.fixture
    def patterns_file(self):
        """Create a temporary patterns file for testing"""
        patterns_content = """# Spark Error Patterns

| error_type | pattern | category | fix_action | llm_hint |
|------------|---------|----------|------------|----------|
| oom_executor | `java.lang.OutOfMemoryError: Java heap space` | AUTO_FIXABLE | increase executor memory to 4g | |
| oom_driver | `OutOfMemoryError: unable to create new native thread` | AUTO_FIXABLE | increase driver memory | |
| class_not_found | `ClassNotFoundException` | KNOWN_NEEDS_LLM | | Check missing class and dependencies |
| jar_not_found | `jar not found` | KNOWN_NEEDS_LLM | | Check jar path and upload |
| shuffle_failed | `FetchFailedException` | KNOWN_NEEDS_LLM | | Analyze Shuffle Service status |
| broadcast_timeout | `BroadcastHashJoin.*timeout` | AUTO_FIXABLE | disable auto broadcast | |
"""
        # Create file, write content, and close before yielding
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_path = f.name
        yield patterns_path
        os.unlink(patterns_path)

    def test_match_oom_error(self, patterns_file):
        """Test matching OOM error"""
        log_content = """2024-01-15 10:30:45 ERROR Executor: Exception in thread "executor-1"
java.lang.OutOfMemoryError: Java heap space
at org.apache.spark.executor.Executor.taskRun(Executor.java:xxx)"""

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'oom_executor'
        assert result['category'] == 'AUTO_FIXABLE'
        assert result['matched_pattern'] == 'java.lang.OutOfMemoryError: Java heap space'
        assert result['extra'] == 'increase executor memory to 4g'
        assert 'OutOfMemoryError' in result['error_message']

    def test_match_class_not_found(self, patterns_file):
        """Test matching ClassNotFoundException error"""
        log_content = """2024-01-15 10:30:45 ERROR SparkContext:
java.lang.ClassNotFoundException: com.example.MyCustomClass
at java.net.URLClassLoader.findClass(URLClassLoader.java:xxx)"""

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'class_not_found'
        assert result['category'] == 'KNOWN_NEEDS_LLM'
        assert result['matched_pattern'] == 'ClassNotFoundException'
        assert result['extra'] == 'Check missing class and dependencies'

    def test_match_unknown(self, patterns_file):
        """Test matching unknown error"""
        log_content = """2024-01-15 10:30:45 ERROR SomeRandomError:
Something went wrong that doesn't match any pattern"""

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'unknown'
        assert result['category'] == 'UNKNOWN'
        assert result['matched_pattern'] == ''
        assert result['extra'] == ''

    def test_match_regex_pattern(self, patterns_file):
        """Test matching regex pattern"""
        log_content = """2024-01-15 10:30:45 ERROR BroadcastHashJoin: timeout after 300 seconds"""

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'broadcast_timeout'
        assert result['category'] == 'AUTO_FIXABLE'
        assert 'disable auto broadcast' in result['extra']

    def test_match_returns_correct_structure(self, patterns_file):
        """Test that match_error returns correct dict structure"""
        log_content = "java.lang.OutOfMemoryError: Java heap space"

        result = match_error(log_content, patterns_file)

        required_keys = ['error_type', 'category', 'matched_pattern', 'extra', 'error_message']
        for key in required_keys:
            assert key in result, f"Missing key: {key}"


class TestMatchErrorEdgeCases:
    """Test edge cases for match_error"""

    @pytest.fixture
    def patterns_file(self):
        """Create patterns file with edge case patterns"""
        patterns_content = """# Spark Error Patterns

| error_type | pattern | category | fix_action | llm_hint |
|------------|---------|----------|------------|----------|
| multi_line | `Container.*killed.*memory` | AUTO_FIXABLE | increase memory | |
| case_insensitive | `CLASSNOTFOUNDEXCEPTION` | KNOWN_NEEDS_LLM | | Check class |
"""
        # Create file, write content, and close before yielding
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_path = f.name
        yield patterns_path
        os.unlink(patterns_path)

    def test_case_insensitive_match(self, patterns_file):
        """Test that pattern matching is case insensitive"""
        log_content = "java.lang.classnotfoundexception: com.example.Test"

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'case_insensitive'
        assert result['category'] == 'KNOWN_NEEDS_LLM'

    def test_multi_line_match(self, patterns_file):
        """Test matching across multiple lines"""
        log_content = """Container killed by YARN
for exceeding memory limits"""

        result = match_error(log_content, patterns_file)

        assert result['error_type'] == 'multi_line'
        assert result['category'] == 'AUTO_FIXABLE'

    def test_empty_log_content(self, patterns_file):
        """Test with empty log content"""
        result = match_error("", patterns_file)

        assert result['error_type'] == 'unknown'
        assert result['category'] == 'UNKNOWN'

    def test_first_pattern_wins(self, patterns_file):
        """Test that first matching pattern is returned when multiple could match"""
        # Create patterns where one pattern could match before another
        patterns_content = """# Spark Error Patterns

| error_type | pattern | category | fix_action | llm_hint |
|------------|---------|----------|------------|----------|
| oom_executor | `OutOfMemoryError` | AUTO_FIXABLE | increase memory | |
| oom_heap | `OutOfMemoryError: Java heap` | AUTO_FIXABLE | specific fix | |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            temp_file = f.name

        try:
            log_content = "java.lang.OutOfMemoryError: Java heap space"
            result = match_error(log_content, temp_file)
            # First pattern that matches should be returned
            assert result['error_type'] == 'oom_executor'
        finally:
            os.unlink(temp_file)