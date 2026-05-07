"""
扩展 SparkSkill 测试
"""

import pytest
from src.skills.spark_skill import SparkSkill
from src.models.alert import AlertContext, AlertInfo


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
        assert result.can_auto_fix is True

    def test_analyze_class_not_found(self):
        """测试 ClassNotFoundException 分析"""
        log = """java.lang.ClassNotFoundException: com.example.MyClass
        at org.apache.spark"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "class_not_found"
        assert result.can_auto_fix is False

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
        assert result.can_auto_fix is True

    def test_analyze_hdfs_not_found(self):
        """测试 HDFS 文件不存在分析"""
        log = """org.apache.hadoop.mapred.InvalidInputException: Input path does not exist: hdfs://path/file"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "hdfs_not_found"

    def test_analyze_container_killed(self):
        """测试 Container killed 分析"""
        log = """Container killed by YARN for exceeding memory limits"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "container_killed"
        assert result.can_auto_fix is False

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

    def test_analyze_skewed_partition(self):
        """测试 Skewed partition 分析"""
        log = """Skewed partition detected in join operation"""

        result = self.skill.analyze(log, self.context)

        assert result.error_type == "skewed_partition"

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
        assert result.can_auto_fix is False
        assert result.confidence == 0.5

    def test_suggest_returns_list(self):
        """测试建议返回列表"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            can_auto_fix=True,
        )

        suggestions = self.skill.suggest(analysis)

        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        assert "spark.executor.memory" in suggestions[0]

    def test_suggest_for_non_auto_fixable(self):
        """测试非自动修复错误的建议"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="class_not_found",
            error_message="ClassNotFound",
            can_auto_fix=False,
        )

        suggestions = self.skill.suggest(analysis)

        assert isinstance(suggestions, list)
        assert "请联系运维人员查看" in suggestions

    def test_get_auto_fix_rules(self):
        """测试获取自动修复规则"""
        rules = self.skill.get_auto_fix_rules()

        assert isinstance(rules, list)
        assert len(rules) >= 4
        assert any(r["action_type"] == "config-change" for r in rules)

    def test_build_auto_fix_action_oom_executor(self):
        """测试构建 OOM Executor 修复动作"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            can_auto_fix=True,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.executor.memory" in action.config_changes

    def test_build_auto_fix_action_oom_driver(self):
        """测试构建 OOM Driver 修复动作"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="oom_driver",
            error_message="OOM Driver",
            can_auto_fix=True,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.driver.memory" in action.config_changes

    def test_build_auto_fix_action_oom_driver_direct(self):
        """测试构建 OOM Driver Direct 修复动作"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="oom_driver_direct",
            error_message="OOM Driver Direct",
            can_auto_fix=True,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.driver.maxResultSize" in action.config_changes

    def test_build_auto_fix_action_broadcast_timeout(self):
        """测试构建 Broadcast timeout 修复动作"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="broadcast_timeout",
            error_message="Broadcast timeout",
            can_auto_fix=True,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.sql.autoBroadcastJoinThreshold" in action.config_changes
        assert action.config_changes["spark.sql.autoBroadcastJoinThreshold"] == "-1"

    def test_build_auto_fix_action_connection_refused(self):
        """测试构建 Connection refused 修复动作"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="connection_refused",
            error_message="Connection refused",
            can_auto_fix=True,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is not None
        assert action.action_type == "rerun"
        assert action.config_changes == {}

    def test_build_auto_fix_action_non_fixable(self):
        """测试非自动修复错误返回 None"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="class_not_found",
            error_message="ClassNotFound",
            can_auto_fix=False,
        )

        action = self.skill._build_auto_fix_action(analysis)

        assert action is None

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

    def test_can_auto_fix_returns_true(self):
        """测试 can_auto_fix 返回 True"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            can_auto_fix=True,
        )

        result = self.skill.can_auto_fix(analysis)

        assert result is True

    def test_can_auto_fix_returns_false(self):
        """测试 can_auto_fix 返回 False"""
        from src.models.analysis import ErrorAnalysis

        analysis = ErrorAnalysis(
            error_type="shuffle_failed",
            error_message="Shuffle failed",
            can_auto_fix=False,
        )

        result = self.skill.can_auto_fix(analysis)

        assert result is False

    def test_skill_name_and_task_types(self):
        """测试 skill 属性"""
        assert self.skill.skill_name == "spark"
        assert "SPARK" in self.skill.task_types
        assert "SPARK_STREAMING" in self.skill.task_types

    def test_error_patterns_count(self):
        """测试错误模式数量"""
        # 应该有至少 20 个错误模式
        assert len(self.skill.error_patterns) >= 20

    def test_suggestion_templates_count(self):
        """测试建议模板数量"""
        # 每个错误模式都应该有对应的建议
        assert len(self.skill.suggestion_templates) >= len(self.skill.error_patterns)

    def test_auto_fixable_errors_in_patterns(self):
        """测试可自动修复错误都在错误模式中"""
        for error_type in self.skill.auto_fixable_errors:
            assert error_type in self.skill.error_patterns
            assert error_type in self.skill.suggestion_templates