"""
Spark Skill - Spark 任务错误分析

扩展错误模式覆盖更多场景:
- OOM (Executor/Driver/Direct Memory)
- ClassNotFound / NoClassDefFoundError
- Shuffle 失败
- Container killed
- Network 连接失败
- Data 文件不存在 / Schema 不匹配
- Performance Broadcast timeout / Data skew
- Driver disconnected

可自动修复: OOM 错误（自动调整内存配置）、Broadcast timeout（禁用 BroadcastJoin）
"""

import re
from typing import Optional, List, Dict
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .base import BaseSkill


class SparkSkill(BaseSkill):
    """
    Spark 任务分析 Skill

    扩展错误模式:
    - OOM (Executor/Driver/Direct Memory)
    - ClassNotFound / NoClassDefFoundError
    - Shuffle 失败
    - Container killed
    - Network 连接失败
    - Data 文件不存在 / Schema 不匹配
    - Performance Broadcast timeout / Data skew
    - Driver disconnected
    """

    skill_name = "spark"
    task_types = ["SPARK", "SPARK_STREAMING"]

    # 扩展的错误模式
    error_patterns = {
        # Resource errors
        "oom_executor": "java.lang.OutOfMemoryError: Java heap space",
        "oom_driver": "OutOfMemoryError: unable to create new native thread",
        "oom_driver_direct": "OutOfMemoryError: Container memory exceeded",
        "container_killed": "Container killed by YARN",
        "executor_lost": "Executor lost",

        # Config errors
        "class_not_found": "ClassNotFoundException",
        "no_class_def": "NoClassDefFoundError",
        "spark_config_invalid": "Spark config.*invalid",

        # Network errors
        "shuffle_failed": "FetchFailedException",
        "connection_refused": "Connection refused|ConnectException",
        "driver_disconnected": "Driver disconnected",

        # Data errors
        "hdfs_not_found": "does not exist|FileNotFound|InvalidInputException.*path",
        "schema_mismatch": "Schema mismatch|cannot resolve",
        "partition_not_found": "Partition not found",

        # Execution errors
        "spark_sql_error": "SparkSQLException",
        "job_aborted": "SparkException: Job aborted",
        "stage_failed": "Stage \\d+ failed",
        "app_submission_failed": "Application submission failed",

        # Performance errors
        "broadcast_timeout": "BroadcastHashJoin.*timeout",
        "skewed_partition": "Skewed partition",

        # User action
        "killed_by_user": "Killed by user",
    }

    # 扩展的建议模板
    suggestion_templates = {
        "oom_executor": "增加 Executor 内存: spark.executor.memory=4g, spark.executor.memoryOverhead=1g",
        "oom_driver": "增加 Driver 内存: spark.driver.memory=2g",
        "oom_driver_direct": "增加 Driver 直接内存: spark.driver.maxResultSize=2g",
        "container_killed": "检查 YARN 资源配额或减少 Executor 数量",
        "executor_lost": "检查 Executor 状态或增加 spark.executor.heartbeatInterval",
        "class_not_found": "检查依赖包是否已上传到资源中心",
        "no_class_def": "检查依赖包是否正确加载",
        "spark_config_invalid": "检查 Spark 配置参数是否正确",
        "shuffle_failed": "检查网络连接或增加 shuffle service",
        "connection_refused": "检查目标服务是否运行",
        "driver_disconnected": "检查 Driver 状态和网络连接",
        "hdfs_not_found": "检查输入文件路径是否存在",
        "schema_mismatch": "检查数据 Schema 是否匹配",
        "partition_not_found": "检查分区是否存在",
        "spark_sql_error": "检查 SQL 语法错误",
        "job_aborted": "检查具体失败原因，可能是 OOM 或依赖问题",
        "stage_failed": "检查 Stage 失败日志",
        "app_submission_failed": "检查应用提交配置",
        "broadcast_timeout": "禁用 BroadcastJoin: spark.sql.autoBroadcastJoinThreshold=-1",
        "skewed_partition": "处理数据倾斜: spark.sql.adaptive.skewedPartitionFactor",
        "killed_by_user": "任务被手动终止，无需自动修复",
    }

    # 可自动修复的错误类型
    auto_fixable_errors = [
        "oom_executor",
        "oom_driver",
        "oom_driver_direct",
        "broadcast_timeout",
        "connection_refused",  # 临时网络错误可重试
    ]

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """使用预定义规则分析日志"""
        # 遍历错误模式，找到匹配
        for error_type, pattern in self.error_patterns.items():
            if re.search(pattern, log_content, re.IGNORECASE):
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=self._extract_error_message(log_content, pattern),
                    matched_pattern=pattern,
                    spark_app_id=self._extract_app_id(log_content),
                    can_auto_fix=error_type in self.auto_fixable_errors,
                    confidence=0.9,
                )

        # 未匹配到预定义模式
        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            can_auto_fix=False,
            confidence=0.5,
        )

    def suggest(self, analysis: ErrorAnalysis) -> List[str]:
        """
        给出修复建议（扩展版）

        返回多个建议选项
        """
        suggestions = []

        if analysis.error_type in self.suggestion_templates:
            suggestions.append(self.suggestion_templates[analysis.error_type])

        # 补充通用建议
        if analysis.can_auto_fix:
            suggestions.append("可尝试自动修复")
        else:
            suggestions.append("请联系运维人员查看")

        return suggestions

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                return "\n".join(lines[start:end])
        return pattern

    def _extract_app_id(self, log_content: str) -> Optional[str]:
        """提取 Spark ApplicationId"""
        patterns = [
            r"application_\d+_\d+",
            r"app-\d+-\d+",
            r"application_\d+",
        ]

        for p in patterns:
            match = re.search(p, log_content)
            if match:
                return match.group(0)

        return None

    def _build_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """构建自动修复动作"""
        if analysis.error_type == "oom_executor":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.executor.memory": "4g",
                    "spark.executor.memoryOverhead": "1g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "oom_driver":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.driver.memory": "2g",
                    "spark.driver.maxResultSize": "2g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "oom_driver_direct":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.driver.maxResultSize": "2g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "broadcast_timeout":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.sql.autoBroadcastJoinThreshold": "-1",
                },
                need_recover=True,
            )
        elif analysis.error_type == "connection_refused":
            # 网络错误建议重试，不修改配置
            return AutoFixAction(
                action_type="rerun",
                config_changes={},
                need_recover=True,
            )

        return None

    def get_auto_fix_rules(self) -> List[Dict]:
        """获取自动修复规则列表"""
        return [
            {
                "action_type": "config-change",
                "conditions": {"error": "OutOfMemoryError", "component": "executor"},
                "description": "增加 Executor 内存 50%",
                "risk_level": "LOW",
            },
            {
                "action_type": "config-change",
                "conditions": {"error": "OutOfMemoryError", "component": "driver"},
                "description": "增加 Driver 内存 50%",
                "risk_level": "LOW",
            },
            {
                "action_type": "config-change",
                "conditions": {"error": "BroadcastHashJoin timeout"},
                "description": "禁用 Broadcast Join",
                "risk_level": "LOW",
            },
            {
                "action_type": "rerun",
                "conditions": {"error": "Connection refused", "retry_count": "<3"},
                "description": "重试工作流（临时网络错误）",
                "risk_level": "MEDIUM",
            },
            {
                "action_type": "recover-failed",
                "conditions": {"error": "Stage failed", "upstream_success": True},
                "description": "从失败任务恢复",
                "risk_level": "MEDIUM",
            },
        ]


__all__ = ["SparkSkill"]