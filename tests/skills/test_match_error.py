"""
Tests for pattern_matcher.py - Pattern matching module tests

Updated for refactored pattern_matcher module
"""

import pytest
import tempfile
import os

from src.skills.common.pattern_matcher import (
    PatternMatcher,
    parse_patterns_file,
    match_error,
    extract_error_snippet,
    PatternCategory,
    PatternEntry,
    MatchResult,
)


class TestParsePatternsFile:
    """Test parse_patterns_file function"""

    def test_parse_patterns_valid_file(self):
        """Test parsing patterns from a valid markdown file"""
        patterns_content = """# Error Patterns

## AUTO_FIXABLE

| error_type | pattern | hint |
|------------|---------|------|
| oom_executor | `java.lang.OutOfMemoryError: Java heap space` | Increase executor memory |
| path_verified | `No such file.*oss://` | {"action_type": "path_verification"} |

## RESOURCE_SUGGESTED

| error_type | pattern | hint |
|------------|---------|------|
| gc_overhead | `GC overhead limit exceeded` | Increase memory and tune GC |

## KNOWN_NEEDS_LLM

| error_type | pattern | hint |
|------------|---------|------|
| class_not_found | `ClassNotFoundException` | Check missing class and dependencies |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_file = f.name

        try:
            patterns = parse_patterns_file(patterns_file)

            # Check AUTO_FIXABLE patterns
            assert len(patterns[PatternCategory.AUTO_FIXABLE]) == 2
            assert patterns[PatternCategory.AUTO_FIXABLE][0].error_type == 'oom_executor'

            # Check RESOURCE_SUGGESTED patterns
            assert len(patterns[PatternCategory.RESOURCE_SUGGESTED]) == 1

            # Check KNOWN_NEEDS_LLM patterns
            assert len(patterns[PatternCategory.KNOWN_NEEDS_LLM]) == 1
            assert patterns[PatternCategory.KNOWN_NEEDS_LLM][0].error_type == 'class_not_found'
        finally:
            os.unlink(patterns_file)

    def test_parse_patterns_with_subcategories(self):
        """Test parsing patterns with subcategory headers"""
        patterns_content = """# Error Patterns

## KNOWN_NEEDS_LLM

### Connection Errors

| error_type | pattern | hint |
|------------|---------|------|
| connection_refused | `Connection refused` | Check target service |

### File Errors

| error_type | pattern | hint |
|------------|---------|------|
| file_not_found | `File not found` | Check file path |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_file = f.name

        try:
            patterns = parse_patterns_file(patterns_file)

            # Check sub_category is set
            entries = patterns[PatternCategory.KNOWN_NEEDS_LLM]
            assert len(entries) == 2
            assert entries[0].sub_category == 'Connection Errors'
            assert entries[1].sub_category == 'File Errors'
        finally:
            os.unlink(patterns_file)

    def test_parse_patterns_empty_file(self):
        """Test parsing patterns from empty file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("")
            patterns_file = f.name

        try:
            patterns = parse_patterns_file(patterns_file)
            assert len(patterns[PatternCategory.AUTO_FIXABLE]) == 0
            assert len(patterns[PatternCategory.RESOURCE_SUGGESTED]) == 0
            assert len(patterns[PatternCategory.KNOWN_NEEDS_LLM]) == 0
        finally:
            os.unlink(patterns_file)

    def test_parse_patterns_missing_file(self):
        """Test parsing patterns from non-existent file"""
        patterns = parse_patterns_file("/non/existent/path/patterns.md")
        assert len(patterns[PatternCategory.AUTO_FIXABLE]) == 0


class TestMatchError:
    """Test match_error function"""

    @pytest.fixture
    def patterns(self):
        """Create patterns for testing"""
        patterns_content = """# Error Patterns

## AUTO_FIXABLE

| error_type | pattern | hint |
|------------|---------|------|
| oom_executor | `java.lang.OutOfMemoryError: Java heap space` | Increase executor memory to 4g |
| path_verified | `No such file.*oss://` | {"action_type": "path_verification"} |

## RESOURCE_SUGGESTED

| error_type | pattern | hint |
|------------|---------|------|
| gc_overhead | `GC overhead limit exceeded` | Increase memory |

## KNOWN_NEEDS_LLM

| error_type | pattern | hint |
|------------|---------|------|
| class_not_found | `ClassNotFoundException` | Check missing class |
| shuffle_failed | `FetchFailedException` | Analyze Shuffle Service |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            patterns_path = f.name

        patterns = parse_patterns_file(patterns_path)
        yield patterns
        os.unlink(patterns_path)

    def test_match_oom_error(self, patterns):
        """Test matching OOM error"""
        log_content = """ERROR Executor: Exception in task 0.0
java.lang.OutOfMemoryError: Java heap space
at org.apache.spark.executor.Executor.taskRun"""

        result = match_error(log_content, patterns)

        assert result.error_type == 'oom_executor'
        assert result.category == 'AUTO_FIXABLE'
        assert 'OutOfMemoryError' in result.error_message

    def test_match_class_not_found(self, patterns):
        """Test matching ClassNotFoundException"""
        log_content = """java.lang.ClassNotFoundException: com.example.MyClass"""

        result = match_error(log_content, patterns)

        assert result.error_type == 'class_not_found'
        assert result.category == 'KNOWN_NEEDS_LLM'
        assert result.hint == 'Check missing class'

    def test_match_unknown_error(self, patterns):
        """Test matching unknown error"""
        log_content = """Some random error that doesn't match any pattern"""

        result = match_error(log_content, patterns)

        assert result.error_type == 'unknown'
        assert result.category == 'UNKNOWN'

    def test_match_priority_order(self, patterns):
        """Test that AUTO_FIXABLE matches before KNOWN_NEEDS_LLM"""
        # Patterns file with overlapping patterns
        patterns_content = """# Error Patterns

## AUTO_FIXABLE

| error_type | pattern | hint |
|------------|---------|------|
| memory_error | `OutOfMemoryError` | Auto fix memory |

## KNOWN_NEEDS_LLM

| error_type | pattern | hint |
|------------|---------|------|
| general_oom | `OutOfMemoryError` | Needs analysis |
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(patterns_content)
            temp_file = f.name

        try:
            test_patterns = parse_patterns_file(temp_file)
            log_content = "java.lang.OutOfMemoryError: Java heap space"
            result = match_error(log_content, test_patterns)

            # AUTO_FIXABLE should match first
            assert result.category == 'AUTO_FIXABLE'
            assert result.error_type == 'memory_error'
        finally:
            os.unlink(temp_file)

    def test_case_insensitive_match(self, patterns):
        """Test that pattern matching is case insensitive"""
        log_content = """JAVA.LANG.CLASSNOTFOUNDEXCEPTION: Test"""

        result = match_error(log_content, patterns)

        assert result.error_type == 'class_not_found'


class TestExtractErrorSnippet:
    """Test extract_error_snippet function"""

    def test_extract_with_context(self):
        """Test extracting error snippet with context lines"""
        log_content = """line 1
line 2
line 3
ERROR: java.lang.OutOfMemoryError: Java heap space
line 5
line 6
line 7"""

        snippet = extract_error_snippet(log_content, 'OutOfMemoryError', context_lines=2)

        assert 'line 3' in snippet
        assert 'OutOfMemoryError' in snippet
        assert 'line 5' in snippet

    def test_extract_at_beginning(self):
        """Test extracting error at the beginning of log"""
        log_content = """ERROR: java.lang.OutOfMemoryError
line 2
line 3"""

        snippet = extract_error_snippet(log_content, 'OutOfMemoryError')

        assert 'OutOfMemoryError' in snippet


class TestPatternMatcher:
    """Test PatternMatcher class"""

    def test_matcher_initialization(self):
        """Test PatternMatcher initialization"""
        matcher = PatternMatcher('spark', 'src/skills/spark/patterns.md')

        patterns = matcher.load_patterns()
        assert len(patterns[PatternCategory.RESOURCE_SUGGESTED]) > 0
        assert len(patterns[PatternCategory.KNOWN_NEEDS_LLM]) > 0

    def test_matcher_match(self):
        """Test PatternMatcher match method"""
        matcher = PatternMatcher('spark', 'src/skills/spark/patterns.md')

        log_content = """java.lang.OutOfMemoryError: Java heap space"""
        result = matcher.match(log_content)

        assert result.error_type == 'oom_executor'
        assert result.category == 'RESOURCE_SUGGESTED'

    def test_matcher_get_pattern_count(self):
        """Test PatternMatcher get_pattern_count method"""
        matcher = PatternMatcher('spark', 'src/skills/spark/patterns.md')

        stats = matcher.get_pattern_count()
        assert 'AUTO_FIXABLE' in stats
        assert stats['RESOURCE_SUGGESTED'] > 0
        assert stats['KNOWN_NEEDS_LLM'] > 0


class TestMatchResult:
    """Test MatchResult dataclass"""

    def test_to_dict(self):
        """Test MatchResult to_dict method"""
        result = MatchResult(
            error_type='oom_executor',
            category='AUTO_FIXABLE',
            matched_pattern='OutOfMemoryError',
            hint='Increase memory',
            error_message='OOM error',
            extra_info={'sub_category': 'memory'},
        )

        d = result.to_dict()
        assert d['error_type'] == 'oom_executor'
        assert d['category'] == 'AUTO_FIXABLE'
        assert d['hint'] == 'Increase memory'
        assert d['extra_info']['sub_category'] == 'memory'


class TestPatternEntry:
    """Test PatternEntry dataclass"""

    def test_to_dict(self):
        """Test PatternEntry to_dict method"""
        entry = PatternEntry(
            error_type='test_error',
            pattern='TestPattern',
            category=PatternCategory.KNOWN_NEEDS_LLM,
            hint='Test hint',
            sub_category='Test sub',
        )

        d = entry.to_dict()
        assert d['error_type'] == 'test_error'
        assert d['category'] == 'KNOWN_NEEDS_LLM'
        assert d['sub_category'] == 'Test sub'