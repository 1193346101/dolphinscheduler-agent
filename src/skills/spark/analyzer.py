"""
Spark Skill - Spark 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Spark 错误模式
- RESOURCE_SUGGESTED: OOM等资源问题，智能计算+LLM验证
- KNOWN_NEEDS_LLM: ClassNotFound、Shuffle 失败等，给 LLM 提供提示
- AUTO_FIXABLE: 路径验证（使用 ossutil 检查）
- UNKNOWN: 无匹配，完全交给 LLM

改进: 使用 scripts 进行预处理、模式匹配和修复构建
"""

import re
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.risk import RiskLevel, AutoFixAction
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log
from ..common.oss_validator import OSSValidator, get_oss_validator


class SparkSkill(BaseSkill):
    """
    Spark 任务分析 Skill

    使用脚本化流程:
    1. preprocess_log.py - 提取关键信息
    2. match_error.py - 匹配错误模式
    3. build_fix.py - 构建修复方案 (AUTO_FIXABLE)
    """

    skill_name = "spark"
    task_types = ["SPARK", "SPARK_STREAMING"]

    # 错误模式: (pattern, category, llm_hint)
    error_patterns: Dict[str, Tuple[str, str, str]] = {
        # === 资源类问题：智能计算 + LLM 验证 ===
        "oom_executor": (
            "java.lang.OutOfMemoryError: Java heap space",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Executor OOM，结合数据量和当前配置计算合理内存"
        ),
        "oom_driver": (
            "OutOfMemoryError: unable to create new native thread",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Driver OOM，结合任务复杂度计算合理内存"
        ),
        "oom_driver_direct": (
            "OutOfMemoryError: Container memory exceeded",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Driver 内存超限，调整 maxResultSize"
        ),
        "oom_offheap": (
            "OutOfMemoryError: offheap",
            ErrorCategory.RESOURCE_SUGGESTED,
            "OffHeap OOM，启用并配置堆外内存"
        ),
        "oom_storage": (
            "OutOfMemoryError: Storage memory",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Storage OOM，调整存储比例"
        ),
        "driver_memory_insufficient": (
            "System memory.*must be at least.*increase heap size.*driver-memory",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Driver 内存配置不足，结合任务需求计算"
        ),
        "executor_memory_insufficient": (
            "Executor memory.*must be at least",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Executor 内存配置不足，结合数据量计算"
        ),
        "shuffle_timeout": (
            "shuffle.*timeout",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Shuffle 超时，结合网络状况调整"
        ),
        "network_timeout": (
            "spark.network.timeout",
            ErrorCategory.RESOURCE_SUGGESTED,
            "网络超时，结合任务复杂度调整"
        ),
        "rpc_timeout": (
            "RPC timeout",
            ErrorCategory.RESOURCE_SUGGESTED,
            "RPC 超时，调整通信超时"
        ),
        "executor_lost_heartbeat": (
            "Executor heartbeat timeout",
            ErrorCategory.RESOURCE_SUGGESTED,
            "Executor 心跳超时，调整心跳间隔"
        ),
        "gc_overhead": (
            "GC overhead limit exceeded",
            ErrorCategory.RESOURCE_SUGGESTED,
            "GC 开销过大，结合内存使用情况调整"
        ),

        # === 已知类型，需 LLM 分析 ===
        "broadcast_timeout": (
            "BroadcastHashJoin.*timeout|broadcast.*timeout|Could not broadcast",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "广播超时，请分析是否数据量变化或网络拥堵导致，对比历史执行情况给出合理建议"
        ),
        "class_not_found": (
            "ClassNotFoundException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 类找不到，请分析缺失的类名和需要的依赖包"
        ),
        "no_class_def": (
            "NoClassDefFoundError",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 类定义找不到，请分析类名和依赖加载问题"
        ),
        "jar_not_found": (
            "jar not found|could not find jar",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Jar 包找不到，请检查 Jar 包路径"
        ),
        "main_class_not_found": (
            "Main class not found",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 主类找不到，请检查 Main Class 名称"
        ),
        "spark_version_mismatch": (
            "Spark version mismatch",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 版本不匹配，请检查版本兼容性"
        ),

        # Network errors
        "shuffle_failed": (
            "FetchFailedException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Shuffle 数据拉取失败，请分析 Shuffle Service 状态和网络问题"
        ),
        "shuffle_connection": (
            "shuffle.*connection failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Shuffle 连接失败，请检查 Shuffle Service"
        ),
        "connection_refused": (
            "Connection refused|ConnectException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 网络连接被拒绝，请检查目标服务是否运行"
        ),
        "connection_timeout": (
            "Connection timed out|SocketTimeoutException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 网络连接超时，请检查网络状态"
        ),
        "driver_disconnected": (
            "Driver disconnected|Driver closed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Driver 断开连接，请分析 Driver 状态"
        ),
        "block_manager_lost": (
            "BlockManager.*lost|BlockManagerId.*lost",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark BlockManager 丢失，请检查存储状态"
        ),

        # Data errors
        "hdfs_not_found": (
            "does not exist|FileNotFound|InvalidInputException.*path",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark HDFS 文件不存在，请检查输入路径是否正确"
        ),
        "file_not_found": (
            "FileNotFoundException|file not found",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 文件不存在，请检查文件路径"
        ),
        "hdfs_permission": (
            "Permission denied.*hdfs|access denied",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark HDFS 权限不足，请检查文件权限"
        ),
        "schema_mismatch": (
            "Schema mismatch|cannot resolve",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Schema 不匹配，请分析数据结构问题"
        ),
        "partition_not_found": (
            "Partition not found|partition.*does not exist",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 分区不存在，请检查分区配置"
        ),
        "corrupt_data": (
            "Corrupt block|corrupt data",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 数据损坏，请检查数据文件"
        ),
        "null_value": (
            "Null value|NullPointerException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 空值问题，请分析空值处理逻辑"
        ),
        "datetime_parse": (
            "DateTimeParseException|cannot parse date",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 日期解析失败，请检查日期格式"
        ),

        # Execution errors
        "spark_sql_error": (
            "SparkSQLException|AnalysisException",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark SQL 错误，请分析 SQL 语法和语义问题"
        ),
        "job_aborted": (
            "SparkException: Job aborted",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Job 被中止，请分析具体中止原因"
        ),
        "stage_failed": (
            "Stage \\d+ failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Stage 失败，请分析失败的具体 Stage 和原因"
        ),
        "task_failed": (
            "Task failed|TaskSetManager.*failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Task 失败，请分析失败原因"
        ),
        "app_submission_failed": (
            "Application submission failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 应用提交失败，请检查提交配置"
        ),

        # SQL errors
        "sql_syntax": (
            "SQL syntax error|parse exception",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark SQL 语法错误，请分析 SQL 语法"
        ),
        "sql_column_not_found": (
            "Column.*not found|cannot resolve column",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark SQL 列不存在，请检查列名"
        ),
        "sql_table_not_found": (
            "Table.*not found|table does not exist",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark SQL 表不存在，请检查表名"
        ),

        # Resource errors
        "container_killed": (
            "Container killed by YARN|Container killed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 容器被 YARN 终止，请分析资源使用情况"
        ),
        "container_killed_memory": (
            "Container killed due to memory|exceeding memory limits|memory limits",
            ErrorCategory.AUTO_FIXABLE,
            "Spark 容器因内存超限被终止，需要增加内存配置"
        ),
        "executor_lost": (
            "Executor lost",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Executor 丢失，请分析 Executor 状态"
        ),
        "executor_crash": (
            "Executor crashed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark Executor 崩溃，请分析崩溃原因"
        ),
        "yarn_resource": (
            "YARN.*resource.*insufficient",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark YARN 资源不足，请检查资源配额"
        ),
        "yarn_container_exit": (
            "Container.*exit.*code",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "YARN Container 异常退出，请分析退出原因"
        ),
        "queue_full": (
            "Queue.*full|queue capacity",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark YARN 队列满，请检查队列状态"
        ),

        # User action
        "killed_by_user": (
            "Killed by user",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Spark 任务被手动终止，无需自动修复"
        ),
    }

    # 建议模板（用于 KNOWN_NEEDS_LLM 的补充）
    suggestion_templates = {
        "class_not_found": "检查依赖包是否已上传到资源中心",
        "no_class_def": "检查依赖包是否正确加载",
        "shuffle_failed": "检查 Shuffle Service 状态或增加 shuffle service",
        "hdfs_not_found": "检查输入文件路径是否存在",
        "schema_mismatch": "检查数据 Schema 是否匹配",
    }

    def _get_scripts_dir(self) -> Optional[Path]:
        """获取 scripts 目录"""
        scripts_dir = Path(__file__).parent / "scripts"
        if scripts_dir.exists():
            return scripts_dir
        return None

    def _get_patterns_file(self) -> Optional[Path]:
        """获取 patterns.md 文件路径"""
        patterns_file = Path(__file__).parent / "patterns.md"
        if patterns_file.exists():
            return patterns_file
        return None

    def _call_script(self, script_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用脚本并返回结果

        Args:
            script_name: 脚本文件名 (如 match_error.py, build_fix.py)
            args: 脚本参数

        Returns:
            脚本输出的 JSON 解析结果
        """
        scripts_dir = self._get_scripts_dir()
        if not scripts_dir:
            return {"error": "scripts_dir_not_found"}

        script_path = scripts_dir / script_name
        if not script_path.exists():
            return {"error": "script_not_found"}

        try:
            # 使用 subprocess 调用脚本
            cmd = ["python", str(script_path)]
            for key, value in args.items():
                cmd.extend([f"--{key}", str(value)])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return {"error": "script_failed", "stderr": result.stderr}

            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        except json.JSONDecodeError:
            return {"error": "invalid_json", "stdout": result.stdout}
        except Exception as e:
            return {"error": str(e)}

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 Spark 任务错误 - 使用脚本化流程"""
        # 1. 日志预处理
        preprocessed = preprocess_log(log_content, task_type="spark")
        error_blocks = preprocessed.get("error_blocks", [])
        app_info = preprocessed.get("app_info", {})
        data_metrics = preprocessed.get("data_metrics", {})

        if not error_blocks:
            # 没有错误块，使用 fallback
            return self._legacy_analyze(log_content, context)

        # 合并错误块
        error_text = "\n".join(error_blocks)

        # 2. 尝试使用 match_error.py 脚本
        scripts_dir = self._get_scripts_dir()
        if scripts_dir:
            # 动态导入 match_error
            try:
                import importlib.util
                match_error_path = scripts_dir / "match_error.py"
                if match_error_path.exists():
                    spec = importlib.util.spec_from_file_location(
                        "match_error",
                        match_error_path
                    )
                    match_error_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(match_error_module)

                    patterns_file = self._get_patterns_file()
                    if patterns_file:
                        match_result = match_error_module.match_error(error_text, str(patterns_file))

                        if match_result.get("error_type") != "unknown":
                            category = ErrorCategory(match_result["category"])

                            # 构建当前配置（从预处理中提取）
                            current_config = {}
                            for line in preprocessed.get("config_lines", []):
                                if "=" in line:
                                    key, value = line.split("=", 1)
                                    key = key.strip()
                                    value = value.strip()
                                    if key.startswith("spark."):
                                        current_config[key] = value

                            quick_fix = None
                            skill_suggestion = None
                            fix_result = None

                            # 3. 如果是 AUTO_FIXABLE，直接构建修复方案
                            if category == ErrorCategory.AUTO_FIXABLE:
                                build_fix_path = scripts_dir / "build_fix.py"
                                if build_fix_path.exists():
                                    spec = importlib.util.spec_from_file_location("build_fix", build_fix_path)
                                    build_fix_module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(build_fix_module)

                                    fix_result = build_fix_module.build_fix(
                                        match_result["error_type"],
                                        current_config,
                                        {},
                                        None
                                    )
                                    if fix_result.get("status") == "success":
                                        quick_fix = {
                                            "action_type": "modify_config",
                                            "config_changes": fix_result.get("config_changes", {}),
                                        }
                                else:
                                    extra = match_result.get("extra", "")
                                    if extra and extra.startswith("{"):
                                        try:
                                            config_changes = json.loads(extra)
                                            quick_fix = {
                                                "action_type": "modify_config",
                                                "config_changes": config_changes,
                                            }
                                        except json.JSONDecodeError:
                                            pass

                            # 4. 如果是 RESOURCE_SUGGESTED，智能计算初步建议
                            elif category == ErrorCategory.RESOURCE_SUGGESTED:
                                build_fix_path = scripts_dir / "build_fix.py"
                                if build_fix_path.exists():
                                    spec = importlib.util.spec_from_file_location("build_fix", build_fix_path)
                                    build_fix_module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(build_fix_module)

                                    # 调用增强版的资源计算（传入数据量）
                                    fix_result = build_fix_module.build_resource_suggestion(
                                        match_result["error_type"],
                                        current_config,
                                        data_metrics,  # 传入数据量指标
                                        app_info,
                                    )
                                    if fix_result.get("status") == "success":
                                        skill_suggestion = {
                                            "config_changes": fix_result.get("config_changes", {}),
                                            "reasoning": fix_result.get("reasoning", ""),
                                            "data_analysis": fix_result.get("data_analysis", {}),
                                        }

                            # 构建透明化分析报告
                            original_log_error = error_blocks[0] if error_blocks else error_text[:300]

                            analysis_process_parts = []
                            if preprocessed.get("config_lines"):
                                analysis_process_parts.append(f"提取配置项 {len(preprocessed['config_lines'])} 条")
                            if error_blocks:
                                analysis_process_parts.append(f"提取错误块 {len(error_blocks)} 个")
                            if app_info.get("app_id"):
                                analysis_process_parts.append(f"识别 AppId: {app_info['app_id']}")
                            if match_result.get("matched_pattern"):
                                analysis_process_parts.append(f"匹配模式: {match_result['matched_pattern']}")
                            analysis_process = "，".join(analysis_process_parts) if analysis_process_parts else "通过错误模式库匹配"

                            reasoning = ""
                            if category == ErrorCategory.AUTO_FIXABLE:
                                if fix_result:
                                    reasoning = fix_result.get("message", "")
                                    source = fix_result.get("source", "default")
                                    if source == "historical":
                                        reasoning += "（基于历史成功配置）"
                                    elif source == "limited":
                                        reasoning += "（受集群资源限制调整）"
                                else:
                                    reasoning = "根据错误模式匹配结果，提供标准修复方案"
                            elif category == ErrorCategory.RESOURCE_SUGGESTED:
                                if skill_suggestion:
                                    reasoning = skill_suggestion.get("reasoning", "根据数据量和配置智能计算")
                                else:
                                    reasoning = match_result.get("extra", "") or "资源类问题，需结合数据量分析"
                            elif category == ErrorCategory.KNOWN_NEEDS_LLM:
                                reasoning = match_result.get("extra", "") or "已知错误类型，需进一步分析具体原因"
                            else:
                                reasoning = "未知错误类型，建议人工分析或查阅相关文档"

                            # === 智能 OSS 验证 ===
                            # 路径相关错误类型，自动验证 OSS/HDFS 路径
                            PATH_ERROR_TYPES = [
                                "hdfs_not_found", "file_not_found", "partition_not_found",
                                "path_not_found", "input_path_error", "output_path_error",
                            ]

                            oss_validation = None
                            if match_result.get("error_type") in PATH_ERROR_TYPES:
                                # 从预处理结果获取 OSS 路径
                                oss_paths = preprocessed.get("oss_paths", [])
                                if oss_paths:
                                    print(f"  >> OSS paths detected: {oss_paths}")
                                    # 验证第一个路径（最主要的）
                                    oss_validation = {}
                                    for path in oss_paths[:2]:  # 最多验证2个
                                        result = self.check_oss_path(path)
                                        oss_validation[path] = {
                                            "exists": result.exists if result else None,
                                            "files": result.files[:3] if result and result.files else [],
                                            "error": result.error if result else None,
                                        }
                                        print(f"  >> OSS validation: {path} -> exists={result.exists if result else 'N/A'}")

                                    # 根据验证结果调整判断
                                    if oss_validation:
                                        first_path = oss_paths[0]
                                        first_result = oss_validation[first_path]
                                        if first_result.get("exists") == True:
                                            # 文件存在，可能是路径拼写问题 → 改为 AUTO_FIXABLE
                                            category = ErrorCategory.AUTO_FIXABLE
                                            reasoning = f"ossutil 验证：文件存在于 {first_path}，可能是路径配置错误"
                                            quick_fix = {
                                                "action_type": "path_verification",
                                                "verified_path": first_path,
                                                "suggestion": "请检查任务配置中的路径是否与此路径一致",
                                            }
                                        elif first_result.get("exists") == False:
                                            # 文件不存在，数据缺失
                                            reasoning = f"ossutil 验证：文件不存在于 {first_path}，数据确实缺失"
                                            if category == ErrorCategory.KNOWN_NEEDS_LLM:
                                                reasoning += "，请检查数据生成流程"

                            return ErrorAnalysis(
                                error_type=match_result["error_type"],
                                category=category,
                                error_message=match_result.get("error_message", error_text[:500]),
                                matched_pattern=match_result.get("matched_pattern", ""),
                                llm_hint=match_result.get("extra", "") if category in [ErrorCategory.KNOWN_NEEDS_LLM, ErrorCategory.RESOURCE_SUGGESTED] else "",
                                quick_fix=quick_fix,
                                skill_suggestion=skill_suggestion,
                                original_log_error=original_log_error,
                                analysis_process=analysis_process,
                                reasoning=reasoning,
                                spark_app_id=app_info.get("app_id"),
                                data_metrics=data_metrics,
                                oss_validation=oss_validation,
                            )
            except Exception:
                pass  # Fallback to legacy

        # 4. Fallback: 使用 legacy 分析
        return self._legacy_analyze(log_content, context)

    def _legacy_analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """Legacy 分析方法 - 作为 fallback"""
        # 遍历错误模式
        for error_type, (pattern, category, llm_hint) in self.error_patterns.items():
            # 使用 re.DOTALL (re.S) 让 .* 匹配换行符，处理跨行日志
            if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
                error_message = self._extract_error_message(log_content, pattern)

                # AUTO_FIXABLE 类型
                if category == ErrorCategory.AUTO_FIXABLE:
                    quick_fix = self._build_quick_fix(error_type)
                    return ErrorAnalysis(
                        error_type=error_type,
                        category=ErrorCategory.AUTO_FIXABLE,
                        error_message=error_message,
                        matched_pattern=pattern,
                        quick_fix=quick_fix,
                        original_log_error=error_message,
                        analysis_process=f"通过内置模式库匹配: {error_type}",
                        reasoning="根据错误模式匹配结果，提供标准修复方案",
                        spark_app_id=self._extract_app_id(log_content),
                    )

                # KNOWN_NEEDS_LLM 类型
                return ErrorAnalysis(
                    error_type=error_type,
                    category=ErrorCategory.KNOWN_NEEDS_LLM,
                    error_message=error_message,
                    matched_pattern=pattern,
                    llm_hint=llm_hint,
                    original_log_error=error_message,
                    analysis_process=f"通过内置模式库匹配: {error_type}",
                    reasoning=llm_hint or "已知错误类型，需进一步分析具体原因",
                    spark_app_id=self._extract_app_id(log_content),
                )

        # 未匹配
        return ErrorAnalysis(
            error_type="unknown",
            category=ErrorCategory.UNKNOWN,
            error_message=log_content[:500],
            original_log_error=log_content[:300],
            analysis_process="无匹配错误模式",
            reasoning="未知错误类型，建议人工分析或查阅相关文档",
        )

    def _build_quick_fix(self, error_type: str) -> Optional[Dict]:
        """构建快速修复方案"""
        fixes = {
            "driver_memory_insufficient": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.driver.memory": "512m",
                    "spark.driver.memoryOverhead": "128m",
                },
            },
            "executor_memory_insufficient": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.executor.memory": "1g",
                    "spark.executor.memoryOverhead": "256m",
                },
            },
            "oom_executor": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.executor.memory": "4g",
                    "spark.executor.memoryOverhead": "1g",
                },
            },
            "oom_driver": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.driver.memory": "2g",
                    "spark.driver.maxResultSize": "2g",
                },
            },
            "oom_driver_direct": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.driver.maxResultSize": "2g",
                },
            },
            "oom_offheap": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.memory.offHeap.enabled": "true",
                    "spark.memory.offHeap.size": "2g",
                },
            },
            "oom_storage": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.memory.storageFraction": "0.3",
                },
            },
            "broadcast_timeout": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.sql.autoBroadcastJoinThreshold": "-1",
                },
            },
            "shuffle_timeout": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.shuffle.io.timeout": "120s",
                },
            },
            "network_timeout": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.network.timeout": "300s",
                },
            },
            "rpc_timeout": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.rpc.timeout": "300s",
                },
            },
            "executor_lost_heartbeat": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.executor.heartbeatInterval": "60s",
                    "spark.network.timeout": "300s",
                },
            },
            "gc_overhead": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.executor.memory": "8g",
                    "spark.executor.memoryOverhead": "2g",
                    "spark.driver.memory": "4g",
                },
            },
            "container_killed_memory": {
                "action_type": "modify_config",
                "config_changes": {
                    "spark.executor.memory": "4g",
                    "spark.executor.memoryOverhead": "1g",
                    "spark.driver.memory": "2g",
                },
            },
        }
        return fixes.get(error_type)

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息片段"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                return "\n".join(lines[start:end])

        # 如果单行没匹配到，可能是跨行匹配，提取整个相关部分
        match = re.search(pattern, log_content, re.IGNORECASE | re.DOTALL)
        if match:
            return log_content[max(0, match.start()-200):match.end()+200]

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

    def suggest(self, analysis: ErrorAnalysis) -> list[str]:
        """补充建议"""
        if analysis.error_type in self.suggestion_templates:
            return [self.suggestion_templates[analysis.error_type]]
        return []


__all__ = ["SparkSkill"]