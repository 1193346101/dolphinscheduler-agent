"""
Spark Skill - Spark 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Spark 错误模式
- RESOURCE_SUGGESTED: OOM等资源问题，智能计算+LLM验证
- KNOWN_NEEDS_LLM: ClassNotFound、Shuffle 失败等，给 LLM 提供提示
- AUTO_FIXABLE: 路径验证（使用 ossutil 检查）
- UNKNOWN: 无匹配，完全交给 LLM

重构版: 使用公共 pattern_matcher 模块，移除硬编码模式表
所有模式维护在 patterns.md 文件中，符合 anthropics/skills 规范
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.risk import RiskLevel, AutoFixAction
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log
from ..common.oss_validator import OSSValidator, get_oss_validator
from ..common.pattern_matcher import PatternMatcher, PatternCategory, MatchResult


class SparkSkill(BaseSkill):
    """
    Spark 任务分析 Skill - 重构版

    使用公共 pattern_matcher 模块进行模式匹配，移除硬编码模式表。
    """

    skill_name = "spark"
    task_types = ["SPARK", "SPARK_STREAMING"]

    # OSS 验证器（延迟初始化）
    _oss_validator: Optional[OSSValidator] = None
    # Pattern Matcher（延迟初始化）
    _matcher: Optional[PatternMatcher] = None

    def _get_matcher(self) -> PatternMatcher:
        """获取模式匹配器"""
        if self._matcher is None:
            patterns_file = str(Path(__file__).parent / "patterns.md")
            self._matcher = PatternMatcher("spark", patterns_file)
        return self._matcher

    def get_oss_validator(self) -> Optional[OSSValidator]:
        """获取 OSS 验证器实例"""
        if self._oss_validator is None:
            self._oss_validator = get_oss_validator()
        return self._oss_validator

    def check_oss_path(self, oss_path: str):
        """检查 OSS 路径是否存在"""
        validator = self.get_oss_validator()
        if validator and validator.is_configured():
            return validator.check_exists(oss_path)
        return None

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析 Spark 任务错误 - Driver 日志配置优先 + History/YARN 深度分析

        流程:
        1. preprocess_log - 日志预处理（从 Driver 日志提取配置、错误块）
        2. PatternMatcher.match - 模式匹配
        3. 按需调用 History/YARN API 获取深度分析数据（仅用于补充 metrics 和诊断）
        4. _validate_oss_paths - OSS 路径验证
        5. _build_analysis - 构建 ErrorAnalysis（配置来自 Driver 日志）

        数据来源策略：
        - Driver 日志：**配置信息主要来源**（spark.driver.memory 等）
        - Spark History Server：Executor metrics、Shuffle 数据量（用于深度分析建议）
        - YARN ResourceManager：容器诊断信息（用于错误定位）
        """
        # 1. 日志预处理（从 Driver 日志提取配置、错误块）
        preprocessed = preprocess_log(log_content, task_type="spark")
        config_lines = preprocessed.get("config_lines", [])  # Driver 日志配置
        error_blocks = preprocessed.get("error_blocks", [])
        app_info = preprocessed.get("app_info", {})
        data_metrics = preprocessed.get("data_metrics", {})
        oss_paths = preprocessed.get("oss_paths", [])
        app_id = app_info.get("app_id")

        # 从 Driver 日志配置行解析 Spark 配置（主要来源）
        current_config = {}

        # 打印前 5 行 config_lines 帮助调试格式
        if config_lines:
            print(f"[SparkSkill] Sample config_lines (first 5):")
            for i, line in enumerate(config_lines[:5]):
                print(f"  [{i}] {line[:100]}")

        spark_config_pattern = re.compile(
            r'(spark\.(?:driver|executor)\.(?:memory|cores|instances))\s*[=:->]\s*(\S+)',
            re.IGNORECASE
        )

        for line in config_lines:
            # 使用正则匹配，支持多种格式：
            # - spark.driver.memory=4g
            # - Setting spark.driver.memory=4g
            # - spark.driver.memory: 4g
            # - spark.driver.memory -> 4g
            match = spark_config_pattern.search(line)
            if match:
                key = match.group(1).lower()  # spark.driver.memory
                value = match.group(2)        # 4g

                # 映射 Spark 配置名到 DolphinScheduler UI 参数名
                if key == "spark.driver.memory":
                    current_config["driver_memory"] = value
                elif key == "spark.driver.cores":
                    current_config["driver_cores"] = value
                elif key == "spark.executor.memory":
                    current_config["executor_memory"] = value
                elif key == "spark.executor.cores":
                    current_config["executor_cores"] = value
                elif key == "spark.executor.instances":
                    current_config["executor_instances"] = value

        print(f"[SparkSkill] Driver config: {current_config}")

        # 按需获取补充信息（从 History Server 和 YARN）- 仅用于深度分析，不覆盖配置
        real_metrics = {}
        yarn_info = {}

        if app_id:
            # 先判断是否需要深度分析
            need_deep_analysis = False
            if not error_blocks:
                need_deep_analysis = True
            else:
                matcher = self._get_matcher()
                match_result = matcher.match("\n".join(error_blocks))
                if match_result.category in ["RESOURCE_SUGGESTED", "UNKNOWN"]:
                    need_deep_analysis = True

            if need_deep_analysis:
                try:
                    from ..common.preprocess_log import fetch_real_spark_metrics
                    real_data = fetch_real_spark_metrics(app_id)
                    # 只获取 metrics 数据，不使用 real_config
                    real_metrics = real_data.get("data_metrics", {})
                    yarn_info = real_data.get("yarn_info", {})

                    # YARN diagnostics 补充错误信息
                    if yarn_info.get("diagnostics"):
                        diagnostics_block = f"[YARN Diagnostics] {yarn_info['diagnostics']}"
                        if diagnostics_block not in error_blocks:
                            error_blocks.append(diagnostics_block)

                    # Spark Executor metrics 补充
                    spark_metrics = real_data.get("spark_metrics", {})
                    if spark_metrics:
                        data_metrics = {**data_metrics, **spark_metrics}

                except Exception as e:
                    print(f"[SparkSkill] Failed to fetch deep analysis data: {e}", file=__import__('sys').stderr)

        # 合并 metrics 数据（用于深度分析建议）
        combined_metrics = {**data_metrics, **real_metrics}

        # 存入 preprocessed（注意：current_config 来自 Driver 日志）
        preprocessed["config_lines"] = config_lines
        preprocessed["current_config"] = current_config  # Driver 日志解析的配置
        preprocessed["data_metrics"] = combined_metrics
        preprocessed["yarn_info"] = yarn_info
        preprocessed["error_blocks"] = error_blocks

        # 没有错误块时返回 UNKNOWN（交给 LLM）
        if not error_blocks:
            initial = ErrorAnalysis(
                error_type="unknown",
                category=ErrorCategory.UNKNOWN,
                error_message=log_content[:500],
                original_log_error=log_content[:300],
                analysis_process="无错误块提取",
                reasoning="日志预处理未发现错误信息，交给 LLM 分析",
                spark_app_id=app_id,
                data_metrics=data_metrics,
            )
            return self.analyze_with_llm_fallback(log_content, initial, context)

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 使用 PatternMatcher 进行模式匹配
        matcher = self._get_matcher()
        match_result = matcher.match(error_text)

        # 3. OSS 路径验证（针对路径相关错误）
        oss_validation = self._validate_oss_paths(match_result, oss_paths)

        # 4. 构建 ErrorAnalysis
        initial = self._build_analysis(
            match_result,
            preprocessed,
            error_blocks[0] if error_blocks else error_text[:300],
            oss_validation,
        )

        # 5. UNKNOWN -> LLM fallback
        if initial.category == ErrorCategory.UNKNOWN:
            return self.analyze_with_llm_fallback(log_content, initial, context)

        return initial

    def _validate_oss_paths(
        self,
        match_result: MatchResult,
        oss_paths: list,
    ) -> Optional[Dict[str, Any]]:
        """
        OSS 路径验证（针对路径相关错误）

        Args:
            match_result: 模式匹配结果
            oss_paths: 预处理提取的 OSS 路径列表

        Returns:
            OSS 验证结果字典或 None
        """
        # 路径相关错误类型
        PATH_ERROR_TYPES = [
            "hdfs_not_found", "file_not_found", "partition_not_found",
            "path_not_found", "input_path_error", "output_path_error",
        ]

        if match_result.error_type not in PATH_ERROR_TYPES:
            return None

        if not oss_paths:
            return None

        oss_validation = {}
        for path in oss_paths[:2]:  # 最多验证2个路径
            result = self.check_oss_path(path)
            oss_validation[path] = {
                "exists": result.exists if result else None,
                "files": result.files[:3] if result and result.files else [],
                "error": result.error if result else None,
            }

        return oss_validation

    def _build_analysis(
        self,
        match_result: MatchResult,
        preprocessed: Dict[str, Any],
        original_error: str,
        oss_validation: Optional[Dict[str, Any]],
    ) -> ErrorAnalysis:
        """
        根据匹配结果构建 ErrorAnalysis

        Args:
            match_result: 模式匹配结果
            preprocessed: 预处理结果
            original_error: 原始错误片段
            oss_validation: OSS 验证结果

        Returns:
            ErrorAnalysis 完整分析结果
        """
        category = ErrorCategory(match_result.category)

        # 构建分析过程说明
        analysis_parts = []
        config_lines = preprocessed.get("config_lines", [])
        error_blocks = preprocessed.get("error_blocks", [])
        app_info = preprocessed.get("app_info", {})

        if config_lines:
            analysis_parts.append(f"提取配置项 {len(config_lines)} 条")
        if error_blocks:
            analysis_parts.append(f"提取错误块 {len(error_blocks)} 个")
        if app_info.get("app_id"):
            analysis_parts.append(f"识别 AppId: {app_info['app_id']}")
        if match_result.matched_pattern:
            analysis_parts.append(f"匹配模式: {match_result.error_type}")
        analysis_process = ", ".join(analysis_parts) if analysis_parts else "通过错误模式库匹配"

        # 根据 category 设置不同字段
        quick_fix = None
        skill_suggestion = None
        llm_hint = None
        reasoning = match_result.hint

        if category == ErrorCategory.AUTO_FIXABLE:
            # AUTO_FIXABLE: 直接返回修复方案
            quick_fix = self._parse_fix_action(match_result.hint, match_result.extra_info)
            reasoning = match_result.hint or "根据错误模式匹配结果，提供标准修复方案"

        elif category == ErrorCategory.RESOURCE_SUGGESTED:
            # RESOURCE_SUGGESTED: Skill 智能计算初步建议
            # 只有资源类问题时才调用 YARN/Spark History Server API（按需获取）
            app_id = app_info.get("app_id")
            data_metrics = preprocessed.get("data_metrics", {})

            # 按需获取真实资源数据
            real_metrics = {}
            real_config = {}
            yarn_diagnostics = ""

            if app_id:
                try:
                    from ..common.preprocess_log import fetch_real_spark_metrics
                    real_data = fetch_real_spark_metrics(app_id)
                    real_metrics = real_data.get("data_metrics", {})
                    real_config = real_data.get("current_config", {})
                    yarn_info = real_data.get("yarn_info", {})
                    if yarn_info:
                        yarn_diagnostics = yarn_info.get("diagnostics", "")
                except Exception as e:
                    print(f"[SparkSkill] Failed to fetch real metrics: {e}", file=__import__('sys').stderr)

            # 合并真实数据到 data_metrics
            combined_metrics = {**data_metrics, **real_metrics}
            if yarn_diagnostics:
                combined_metrics["yarn_diagnostics"] = yarn_diagnostics

            # 优先从 config_lines（Driver 日志）解析配置，再用 real_config 补充
            current_config = {}
            spark_config_pattern = re.compile(
                r'(spark\.(?:driver|executor)\.(?:memory|cores|instances))\s*[=:->]\s*(\S+)',
                re.IGNORECASE
            )

            for line in config_lines:
                match = spark_config_pattern.search(line)
                if match:
                    key = match.group(1).lower()
                    value = match.group(2)
                    if key == "spark.driver.memory":
                        current_config["driver_memory"] = value
                    elif key == "spark.driver.cores":
                        current_config["driver_cores"] = value
                    elif key == "spark.executor.memory":
                        current_config["executor_memory"] = value
                    elif key == "spark.executor.cores":
                        current_config["executor_cores"] = value
                    elif key == "spark.executor.instances":
                        current_config["executor_instances"] = value

            # 用 real_config（来自 Spark History Server）补充缺失的配置
            if real_config:
                for key in ["driver_memory", "driver_cores", "executor_memory", "executor_cores", "executor_instances"]:
                    if key not in current_config and key in real_config:
                        current_config[key] = real_config[key]

            skill_suggestion = self._calculate_resource_suggestion(
                match_result.error_type,
                current_config,
                combined_metrics,
                app_info,
            )
            llm_hint = match_result.hint
            if skill_suggestion:
                reasoning = skill_suggestion.get("reasoning", match_result.hint)

        elif category == ErrorCategory.KNOWN_NEEDS_LLM:
            # KNOWN_NEEDS_LLM: 给 LLM 提供提示
            llm_hint = match_result.hint
            reasoning = match_result.hint or "已知错误类型，需进一步分析具体原因"

        else:
            # UNKNOWN: 未知错误
            reasoning = "未知错误类型，建议人工分析或查阅相关文档"

        # OSS 验证结果可能调整判断
        if oss_validation:
            first_path = list(oss_validation.keys())[0]
            first_result = oss_validation[first_path]
            if first_result.get("exists") == True:
                # 文件存在，可能是路径拼写问题
                category = ErrorCategory.AUTO_FIXABLE
                reasoning = f"ossutil 验证：文件存在于 {first_path}，可能是路径配置错误"
                quick_fix = {
                    "action_type": "path_verification",
                    "verified_path": first_path,
                    "suggestion": "请检查任务配置中的路径是否与此路径一致",
                }

        # 提取 Spark 配置
        current_config = {}
        for line in config_lines:
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("spark."):
                    current_config[key] = value.strip()

        return ErrorAnalysis(
            error_type=match_result.error_type,
            category=category,
            error_message=match_result.error_message,
            matched_pattern=match_result.matched_pattern,
            quick_fix=quick_fix,
            skill_suggestion=skill_suggestion,
            llm_hint=llm_hint,
            original_log_error=original_error,
            analysis_process=analysis_process,
            reasoning=reasoning,
            spark_app_id=app_info.get("app_id"),
            data_metrics=preprocessed.get("data_metrics"),
            oss_validation=oss_validation,
        )

    def _parse_fix_action(
        self,
        hint: str,
        extra_info: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        解析 fix_action

        Args:
            hint: 提示字符串（可能是 JSON）
            extra_info: 额外信息（可能包含 fix_action）

        Returns:
            修复动作字典或 None
        """
        # 从 extra_info 解析
        if extra_info and "fix_action" in extra_info:
            return extra_info["fix_action"]

        # 从 hint 解析 JSON
        if hint and hint.startswith('{'):
            try:
                fix_action = json.loads(hint)
                return {
                    "action_type": fix_action.get("action_type", "modify_config"),
                    "config_changes": fix_action.get("config_changes", {}),
                }
            except json.JSONDecodeError:
                pass

        return None

    def _calculate_resource_suggestion(
        self,
        error_type: str,
        current_config: Dict[str, Any],
        data_metrics: Dict[str, Any],
        app_info: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        计算资源建议（调用 scripts/calculate_resource.py）

        Args:
            error_type: 错误类型
            current_config: 当前配置（来自 History Server 或 config_lines）
                - driver_memory: Driver内存数
                - driver_cores: Driver核心数
                - executor_memory: Executor内存数
                - executor_cores: Executor核心数
                - executor_instances: Executor数量
            data_metrics: 数据量指标（来自 History Server）
                - memory_spilled: 内存溢出量（MB）
                - peak_memory: 峰值内存（MB）
                - shuffle_read: Shuffle读取量（MB）
                - yarn_diagnostics: YARN诊断信息
            app_info: 应用信息

        Returns:
            资源建议字典或 None（只包含 DolphinScheduler 支持的参数）
        """
        scripts_dir = Path(__file__).parent / "scripts"
        calculate_script = scripts_dir / "calculate_resource.py"

        if not calculate_script.exists():
            return None

        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("calculate_resource", calculate_script)
            calc_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(calc_module)

            # 调用计算函数
            if hasattr(calc_module, 'build_resource_suggestion'):
                result = calc_module.build_resource_suggestion(
                    error_type, current_config, data_metrics, app_info
                )
                return result

        except Exception as e:
            print(f"Error calculating resource: {e}", file=__import__('sys').stderr)

        return None

    def suggest(self, analysis: ErrorAnalysis) -> list[str]:
        """补充建议"""
        suggestions = []

        # 基于错误类型给出补充建议
        if analysis.error_type in ["class_not_found", "no_class_def"]:
            suggestions.append("检查依赖包是否已上传到资源中心")
        elif analysis.error_type in ["shuffle_failed", "shuffle_connection"]:
            suggestions.append("检查 Shuffle Service 状态或增加 shuffle service")
        elif analysis.error_type in ["hdfs_not_found", "file_not_found"]:
            suggestions.append("检查输入文件路径是否存在")
        elif analysis.error_type in ["schema_mismatch"]:
            suggestions.append("检查数据 Schema 是否匹配")

        return suggestions


__all__ = ["SparkSkill"]