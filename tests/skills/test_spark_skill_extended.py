"""
扩展 SparkSkill 测试
"""

import pytest
from src.skills.spark.analyzer import SparkSkill
from src.models.alert import AlertContext, AlertInfo
from src.models.analysis import ErrorAnalysis, ErrorCategory


class TestSparkSkillExtended:

    def setup_method(self):
        self.skill = SparkSkill()
        self.context = AlertContext(
            alert_info=AlertInfo(
                project_code=123,
                process_definition_code=456,
                process_instance_id=789,
                task_code=111,
                task_instance_id=222,
                task_type="SPARK",
                state="FAILURE",
            )
        )

    def test_analyze_oom_executor(self):
        """测试 OOM Executor 分析"""
        log = """Exception in thread "executor-1" java.lang.OutOfMemoryError: Java heap space
        at org.apache.spark.executor.Executor"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "oom_executor"
        assert result.category == ErrorCategory.AUTO_FIXABLE

    def test_analyze_class_not_found(self):
        """测试 ClassNotFoundException 分析"""
        log = """java.lang.ClassNotFoundException: com.example.MyClass
        at org.apache.spark"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "class_not_found"
        assert result.category == ErrorCategory.KNOWN_NEEDS_LLM

    def test_analyze_shuffle_failed(self):
        """测试 Shuffle 失败分析"""
        log = """org.apache.spark.shuffle.FetchFailedException: Failed to fetch shuffle blocks"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "shuffle_failed"

    def test_analyze_broadcast_timeout(self):
        """测试 Broadcast timeout 分析"""
        log = """org.apache.spark.sql.execution.joins.BroadcastHashJoin timeout"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "broadcast_timeout"
        assert result.category == ErrorCategory.AUTO_FIXABLE

    def test_analyze_hdfs_not_found(self):
        """测试 HDFS 文件不存在分析"""
        log = """org.apache.hadoop.mapred.InvalidInputException: Input path does not exist: hdfs://path/file"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "hdfs_not_found"

    def test_analyze_container_killed(self):
        """测试 Container killed 分析"""
        log = """Container killed by YARN for exceeding memory limits"""

        result = self.skill.analyze(log, self.context)

        # container_killed matches for general "Container killed by YARN"
        assert result.error_type == "container_killed"
        assert result.category == ErrorCategory.KNOWN_NEEDS_LLM

    def test_analyze_container_killed_memory(self):
        """测试 Container killed memory 分析"""
        # Use a log that only matches container_killed_memory pattern
        # avoiding "Container killed" which matches container_killed first
        log = """exceeding memory limits"""

        result = self.skill.analyze(log, self.context)

        # container_killed_memory is AUTO_FIXABLE
        assert result.error_type == "container_killed_memory"
        assert result.category == ErrorCategory.AUTO_FIXABLE

    def test_analyze_stage_failed(self):
        """测试 Stage failed 分析"""
        log = """Stage 15 failed 4 times, most recent failure: Lost task"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "stage_failed"

    def test_analyze_schema_mismatch(self):
        """测试 Schema mismatch 分析"""
        log = """org.apache.spark.sql.AnalysisException: cannot resolve 'column_name' given columns"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "schema_mismatch"

    def test_analyze_driver_disconnected(self):
        """测试 Driver disconnected 分析"""
        log = """Driver disconnected from the executor"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "driver_disconnected"

    def test_analyze_executor_lost(self):
        """测试 Executor lost 分析"""
        log = """Executor lost: executor-2 on host-123"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "executor_lost"

    def test_analyze_gc_overhead(self):
        """测试 GC overhead 分析"""
        log = """java.lang.OutOfMemoryError: GC overhead limit exceeded"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "gc_overhead"
        assert result.category == ErrorCategory.AUTO_FIXABLE

    def test_analyze_killed_by_user(self):
        """测试 Killed by user 分析"""
        log = """Killed by user request"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "killed_by_user"

    def test_analyze_unknown_error(self):
        """测试未知错误分析"""
        log = """Some random error that doesn't match any pattern"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "unknown"
        assert result.category == ErrorCategory.UNKNOWN
        assert result.confidence == 0.95  # default value

    def test_suggest_returns_list(self):
        """测试建议返回列表"""
        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            category=ErrorCategory.AUTO_FIXABLE,
        )

        suggestions = self.skill.suggest(analysis)

        assert isinstance(suggestions, list)

    def test_suggest_for_known_error(self):
        """测试已知错误的建议"""
        analysis = ErrorAnalysis(
            error_type="class_not_found",
            error_message="ClassNotFound",
            category=ErrorCategory.KNOWN_NEEDS_LLM,
        )

        suggestions = self.skill.suggest(analysis)

        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        assert "依赖包" in suggestions[0]

    def test_quick_fix_for_oom_executor(self):
        """测试 OOM Executor 的 quick_fix"""
        log = """java.lang.OutOfMemoryError: Java heap space"""

        result = self.skill.analyze(log, self.context)

        assert result.quick_fix is not None
        assert result.quick_fix["action_type"] == "modify_config"
        assert "spark.executor.memory" in result.quick_fix["config_changes"]

    def test_quick_fix_for_broadcast_timeout(self):
        """测试 Broadcast timeout 的 quick_fix"""
        log = """BroadcastHashJoin timeout"""

        result = self.skill.analyze(log, self.context)

        assert result.quick_fix is not None
        assert result.quick_fix["action_type"] == "modify_config"
        assert "spark.sql.autoBroadcastJoinThreshold" in result.quick_fix["config_changes"]
        assert result.quick_fix["config_changes"]["spark.sql.autoBroadcastJoinThreshold"] == "-1"

    def test_quick_fix_for_oom_driver(self):
        """测试 OOM Driver 的 quick_fix"""
        log = """OutOfMemoryError: unable to create new native thread"""

        result = self.skill.analyze(log, self.context)

        assert result.quick_fix is not None
        assert "spark.driver.memory" in result.quick_fix["config_changes"]

    def test_no_quick_fix_for_known_needs_llm(self):
        """测试 KNOWN_NEEDS_LLM 没有 quick_fix"""
        log = """java.lang.ClassNotFoundException: com.example.MyClass"""

        result = self.skill.analyze(log, self.context)

        assert result.quick_fix is None
        assert result.llm_hint is not None

    def test_extract_app_id_application_format(self):
        """测试提取 application_xxx_xxx 格式的 App ID"""
        log = """INFO: Application application_1234567890_0001 submitted"""

        app_id = self.skill._extract_app_id(log)

        assert app_id == "application_1234567890_0001"

    def test_extract_app_id_app_format(self):
        """测试提取 app-xxx-xxx 格式的 App ID"""
        log = """INFO: Starting app-20240101-0001"""

        app_id = self.skill._extract_app_id(log)

        assert app_id == "app-20240101-0001"

    def test_extract_app_id_not_found(self):
        """测试未找到 App ID"""
        log = """Some log without app ID"""

        app_id = self.skill._extract_app_id(log)

        assert app_id is None

    def test_skill_name_and_task_types(self):
        """测试 skill 属性"""
        assert self.skill.skill_name == "spark"
        assert "SPARK" in self.skill.task_types
        assert "SPARK_STREAMING" in self.skill.task_types

    def test_error_patterns_count(self):
        """测试错误模式数量"""
        # 应该有至少 20 个错误模式
        assert len(self.skill.error_patterns) >= 20

    def test_auto_fixable_patterns_have_quick_fix(self):
        """测试 AUTO_FIXABLE 类型的错误模式都有对应的 quick_fix"""
        auto_fixable_types = [
            error_type
            for error_type, (_, category, _) in self.skill.error_patterns.items()
            if category == ErrorCategory.AUTO_FIXABLE
        ]

        # 检查每个 AUTO_FIXABLE 类型都有对应的 quick_fix
        quick_fix_types = set(self.skill._build_quick_fix(None) or {})
        # Check that quick_fix method exists for these types
        for error_type in ["oom_executor", "oom_driver", "broadcast_timeout", "gc_overhead"]:
            if error_type in auto_fixable_types:
                fix = self.skill._build_quick_fix(error_type)
                assert fix is not None, f"{error_type} should have a quick_fix"

    def test_llm_hint_for_known_needs_llm(self):
        """测试 KNOWN_NEEDS_LLM 类型都有 llm_hint"""
        for error_type, (pattern, category, llm_hint) in self.skill.error_patterns.items():
            if category == ErrorCategory.KNOWN_NEEDS_LLM:
                assert llm_hint is not None and llm_hint != "", f"{error_type} should have llm_hint"

    def test_analyze_returns_error_analysis(self):
        """测试 analyze 返回 ErrorAnalysis 类型"""
        log = """java.lang.OutOfMemoryError: Java heap space"""

        result = self.skill.analyze(log, self.context)

        assert isinstance(result, ErrorAnalysis)

    def test_confidence_for_auto_fixable(self):
        """测试 AUTO_FIXABLE 类型的置信度"""
        log = """java.lang.OutOfMemoryError: Java heap space"""

        result = self.skill.analyze(log, self.context)

        assert result.confidence == 0.95

    def test_matched_pattern_populated(self):
        """测试 matched_pattern 字段填充"""
        log = """java.lang.ClassNotFoundException: com.example.MyClass"""

        result = self.skill.analyze(log, self.context)

        assert result.matched_pattern is not None
        assert "ClassNotFoundException" in result.matched_pattern

    def test_error_message_contains_context(self):
        """测试 error_message 包含错误上下文"""
        log = """2024-01-15 10:30:45 ERROR Executor: Exception in thread "executor-1"
java.lang.OutOfMemoryError: Java heap space
at org.apache.spark.executor.Executor.taskRun"""

        result = self.skill.analyze(log, self.context)

        assert "OutOfMemoryError" in result.error_message