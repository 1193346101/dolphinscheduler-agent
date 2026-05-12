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
        分析 Spark 任务错误 - 使用公共 pattern_matcher

        流程:
        1. preprocess_log - 日志预处理
        2. PatternMatcher.match - 模式匹配
        3. _build_analysis - 构建 ErrorAnalysis
        """
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="spark")
        error_blocks = preprocessed.get("error_blocks", [])
        app_info = preprocessed.get("app_info", {})
        data_metrics = preprocessed.get("data_metrics", {})
        oss_paths = preprocessed.get("oss_paths", [])

        # 没有错误块时返回 UNKNOWN
        if not error_blocks:
            return ErrorAnalysis(
                error_type="unknown",
                category=ErrorCategory.UNKNOWN,
                error_message=log_content[:500],
                original_log_error=log_content[:300],
                analysis_process="无错误块提取",
                reasoning="日志预处理未发现错误信息，建议人工分析",
            )

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 使用 PatternMatcher 进行模式匹配
        matcher = self._get_matcher()
        match_result = matcher.match(error_text)

        # 3. OSS 路径验证（针对路径相关错误）
        oss_validation = self._validate_oss_paths(match_result, oss_paths)

        # 4. 构建 ErrorAnalysis
        return self._build_analysis(
            match_result,
            preprocessed,
            error_blocks[0] if error_blocks else error_text[:300],
            oss_validation,
        )

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
            skill_suggestion = self._calculate_resource_suggestion(
                match_result.error_type,
                config_lines,
                preprocessed.get("data_metrics", {}),
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
        config_lines: list,
        data_metrics: Dict[str, Any],
        app_info: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        计算资源建议（调用 scripts/calculate_resource.py）

        Args:
            error_type: 错误类型
            config_lines: 配置行列表
            data_metrics: 数据量指标
            app_info: 应用信息

        Returns:
            资源建议字典或 None
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

            # 提取当前配置
            current_config = {}
            for line in config_lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key.startswith("spark."):
                        current_config[key] = value.strip()

            # 调用计算函数
            if hasattr(calc_module, 'calculate'):
                result = calc_module.calculate(error_type, current_config, data_metrics)
                return result
            elif hasattr(calc_module, 'build_resource_suggestion'):
                result = calc_module.build_resource_suggestion(error_type, current_config, data_metrics, app_info)
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