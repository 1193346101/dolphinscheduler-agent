"""
analyze_error node

Analyze error patterns - Skill quick pre-check + LLM deep analysis

Process:
1. Preprocess log (提取 config_lines, error_blocks, data_metrics)
2. Skill quick error pattern recognition
   - AUTO_FIXABLE: Return fix solution directly (typo, OOM config)
   - KNOWN_NEEDS_LLM: Return error type + LLM hint
   - UNKNOWN: Return to LLM for full analysis

3. LLM deep analysis (only when category is not AUTO_FIXABLE)
   - Analyze specific cause, locate problem
   - Return fix suggestions and script_changes/config_changes
"""

from typing import Dict, List
from ..state import AgentState
from ...tools.llm_client import LLMClient
from ...models.alert import AlertContext, AlertInfo
from ...models.analysis import ErrorCategory
from ...config import settings
from ...tools.dingtalk_progress import get_notifier_from_settings
from ...skills.common.preprocess_log import preprocess_log


def analyze_error(state: AgentState) -> AgentState:
    """
    Analyze error
    """
    print("\n" + "="*50)
    print("[4/10] analyze_error - Analyze error")
    print("="*50)

    task_type = state.get("task_type", "SPARK")
    print(f"  >> Task type: {task_type}")

    driver_logs = state.get("driver_logs", "") or ""
    spark_logs = state.get("spark_logs", "") or ""
    yarn_logs = state.get("yarn_logs", "") or ""

    # Combine logs (driver_logs + spark_logs + yarn_logs)
    logs = _combine_logs(driver_logs, spark_logs, yarn_logs)
    print(f"  >> Log length: {len(logs)} chars")

    # 初始化 Token 消耗统计
    token_consumption = state.get("token_consumption", 0)
    token_details = state.get("token_details", {})

    if not logs:
        print("[WARN] No log content, skip analysis")
        return {
            **state,
            "error_patterns": [],
            "error_category": "",
            "suggested_actions": [],
            "knowledge_match": None,
            "error_analysis": {
                "error_type": "unknown",
                "error_message": "",
                "category": "UNKNOWN",
            },
        }

    # 预处理日志（提取配置、错误块、数据指标等）
    preprocessed = preprocess_log(logs, task_type=task_type.lower())
    config_lines = preprocessed.get("config_lines", [])
    error_blocks = preprocessed.get("error_blocks", [])
    data_metrics = preprocessed.get("data_metrics", {})
    app_info = preprocessed.get("app_info", {})
    print(f"  >> Preprocessed: {len(config_lines)} config lines, {len(error_blocks)} error blocks")

    # 先检查 YARN diagnostics 是否有明确的错误信息
    yarn_error = None
    if yarn_logs and "[YARN Diagnostics]" in yarn_logs:
        import re
        # 提取诊断部分
        diagnostics_match = re.search(r'\[YARN Diagnostics\]\n(.+)', yarn_logs, re.DOTALL)
        if diagnostics_match:
            diagnostics = diagnostics_match.group(1)
            # 检查常见 YARN 错误
            if "Container killed" in diagnostics or "memory" in diagnostics.lower():
                yarn_error = diagnostics[:300]
                print(f"  >> YARN diagnostics indicates resource issue")

    # Build AlertContext
    context = AlertContext(
        alert_info=AlertInfo(
            project_code=int(state.get("project_code", 0) or 0),
            process_definition_code=int(state.get("workflow_code", 0) or 0),
            process_instance_id=0,
            task_code=int(state.get("task_code", 0) or 0),
            task_instance_id=0,
            task_type=task_type,
            state="FAILURE",
        )
    )

    # 1. Skill quick pre-check
    skill = _get_skill_for_task_type(task_type)
    skill_result = None

    # 如果 YARN diagnostics 有明确的资源错误，先尝试 Skill 分析
    if yarn_error:
        print(f"  >> YARN diagnostics detected, trying Skill...")
        if skill:
            # 构建 YARN 错误日志给 Skill
            yarn_error_log = f"[YARN Diagnostics]\n{yarn_error}"
            try:
                skill_result = skill.analyze(yarn_error_log, context)
                if skill_result.category == ErrorCategory.AUTO_FIXABLE:
                    print(f"  >> Skill detected YARN resource issue: {skill_result.error_type}")
            except Exception as e:
                print(f"[ERROR] Skill analysis on YARN failed: {e}")

    # 如果 YARN 没有检测到可修复问题，用完整日志分析
    if not skill_result or skill_result.category == ErrorCategory.UNKNOWN:
        if skill:
            try:
                skill_result = skill.analyze(logs, context)
            except Exception as e:
                print(f"[ERROR] Skill analysis failed: {e}")

    # 2. Determine follow-up process based on category
    if skill_result:
        print(f"  >> Skill result: {skill_result.error_type}")
        print(f"  >> Category: {skill_result.category.value}")

        if skill_result.category == ErrorCategory.AUTO_FIXABLE:
            # Skill can fix directly
            print("[OK] AUTO_FIXABLE - Skill can fix directly")
            error_patterns = [skill_result.error_type]
            error_category = _map_error_category(skill_result.error_type)
            suggested_actions = _build_actions_from_skill(skill, skill_result)

            error_analysis = {
                "error_type": skill_result.error_type,
                "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
                "category": "AUTO_FIXABLE",
                "quick_fix": skill_result.quick_fix,
                "analysis_process": skill_result.analysis_process,
                "reasoning": skill_result.reasoning,
            }

        elif skill_result.category == ErrorCategory.RESOURCE_SUGGESTED:
            # Skill 已智能计算初步建议，调用 LLM 验证和补充
            print(f"[INFO] RESOURCE_SUGGESTED - Skill calculated, LLM validates")
            skill_suggestion = skill_result.skill_suggestion or {}
            print(f"  >> Skill suggestion: {skill_suggestion.get('config_changes', {})}")
            print(f"  >> Skill reasoning: {skill_suggestion.get('reasoning', '')}")

            llm_client = LLMClient()
            llm_result = llm_client.analyze(
                log_excerpt=logs[:2000],
                task_type=task_type,
                skill_result={
                    "error_type": skill_result.error_type,
                    "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
                    "llm_hint": f"资源类问题，Skill 已计算初步建议：{skill_suggestion.get('reasoning', '')}，请验证并补充优化建议",
                    # Skill 计算的初步建议
                    "skill_suggestion": skill_suggestion,
                    # 传递预处理结果
                    "config_lines": config_lines[:10],
                    "error_blocks": error_blocks[:2],
                    "data_metrics": data_metrics,
                    "app_info": app_info,
                }
            )

            if llm_result.get("error_category"):
                print(f"  >> LLM validated: {llm_result.get('error_description', '')[:100]}")

                # 累计 Token 消耗
                token_usage = llm_result.get("token_usage", {})
                if token_usage:
                    token_consumption += token_usage.get("total_tokens", 0)
                    token_details["analyze_resource"] = token_usage

                error_patterns = [skill_result.error_type]
                error_category = "RESOURCE"

                # 合并 Skill 建议和 LLM 补充
                suggested_actions = llm_result.get("suggested_actions", [])
                if skill_suggestion.get("config_changes"):
                    suggested_actions.append({
                        "action_type": "modify_config",
                        "description": skill_suggestion.get("reasoning", "Skill 智能计算"),
                        "config_changes": skill_suggestion.get("config_changes"),
                        "source": "skill_calculated",
                    })

                error_analysis = {
                    "error_type": skill_result.error_type,
                    "error_message": llm_result.get("error_description", skill_result.error_message[:200] if skill_result.error_message else ""),
                    "category": "RESOURCE_SUGGESTED",
                    "skill_suggestion": skill_suggestion,
                    "llm_validation": llm_result,
                    "analysis_process": skill_result.analysis_process,
                    "reasoning": f"Skill计算: {skill_suggestion.get('reasoning', '')}，LLM验证: {llm_result.get('error_description', '')[:100]}",
                }
            else:
                # LLM 验证失败，使用 Skill 建议
                print("[WARN] LLM validation failed, use Skill suggestion")

                # 累计 Token 消耗（即使失败也记录）
                token_usage = llm_result.get("token_usage", {})
                if token_usage:
                    token_consumption += token_usage.get("total_tokens", 0)
                    token_details["analyze_resource_failed"] = token_usage

                error_patterns = [skill_result.error_type]
                error_category = "RESOURCE"
                suggested_actions = [{
                    "action_type": "modify_config",
                    "description": skill_suggestion.get("reasoning", "Skill 智能计算（LLM验证失败）"),
                    "config_changes": skill_suggestion.get("config_changes", {}),
                }]

                error_analysis = {
                    "error_type": skill_result.error_type,
                    "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
                    "category": "RESOURCE_SUGGESTED",
                    "skill_suggestion": skill_suggestion,
                    "analysis_process": skill_result.analysis_process,
                    "reasoning": skill_suggestion.get("reasoning", ""),
                }

        elif skill_result.category == ErrorCategory.KNOWN_NEEDS_LLM:
            # Known type, needs LLM deep analysis
            print(f"  >> LLM hint: {skill_result.llm_hint}")
            llm_client = LLMClient()
            llm_result = llm_client.analyze(
                log_excerpt=logs[:2000],
                task_type=task_type,
                skill_result={
                    "error_type": skill_result.error_type,
                    "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
                    "llm_hint": skill_result.llm_hint,
                    # 传递预处理结果
                    "config_lines": config_lines[:10],  # 只传前10条配置
                    "error_blocks": error_blocks[:2],   # 只传前2个错误块
                    "data_metrics": data_metrics,
                    "app_info": app_info,
                }
            )

            if llm_result.get("error_category"):
                print(f"  >> LLM analysis complete: {llm_result.get('error_description', '')[:100]}")

                # 累计 Token 消耗
                token_usage = llm_result.get("token_usage", {})
                if token_usage:
                    token_consumption += token_usage.get("total_tokens", 0)
                    token_details["analyze_known"] = token_usage

                error_patterns = [skill_result.error_type] + llm_result.get("error_patterns", [])
                error_category = llm_result.get("error_category", _map_error_category(skill_result.error_type))
                suggested_actions = llm_result.get("suggested_actions", [])

                error_analysis = {
                    "error_type": skill_result.error_type,
                    "error_message": llm_result.get("error_description", skill_result.error_message[:200] if skill_result.error_message else ""),
                    "category": llm_result.get("can_auto_fix", False) and "AUTO_FIXABLE" or "KNOWN_NEEDS_LLM",
                    "llm_result": llm_result,
                }
            else:
                # LLM also cannot analyze, use Skill hint
                print("[WARN] LLM analysis failed, use Skill hint")

                # 累计 Token 消耗
                token_usage = llm_result.get("token_usage", {})
                if token_usage:
                    token_consumption += token_usage.get("total_tokens", 0)
                    token_details["analyze_known_failed"] = token_usage

                error_patterns = [skill_result.error_type]
                error_category = _map_error_category(skill_result.error_type)

                # 检查 skill_result.llm_hint 是否包含具体修复信息
                llm_hint_text = skill_result.llm_hint or ""
                script_changes = None

                # 尝试从 llm_hint 中提取拼写修正（如 "ech -> echo"）
                import re
                fix_pattern = re.search(r"['\"](\w+)['\"]\s*(?:->|改为|修改为|应为)\s*['\"](\w+)['\"]", llm_hint_text)
                if fix_pattern:
                    wrong_cmd = fix_pattern.group(1)
                    correct_cmd = fix_pattern.group(2)
                    script_changes = {wrong_cmd: correct_cmd}
                    print(f"  >> Extracted script fix from hint: {wrong_cmd} -> {correct_cmd}")

                if script_changes:
                    # 有具体的修复方案，生成 modify_script action
                    suggested_actions = [{
                        "action_type": "modify_script",
                        "description": f"脚本拼写错误修正: {script_changes}",
                        "script_changes": script_changes,
                        "risk_level": "LOW",
                    }]
                else:
                    # 无具体修复方案，只通知不执行
                    suggested_actions = [{
                        "action_type": "notify-only",
                        "description": skill_result.llm_hint or "需要人工分析处理",
                        "risk_level": "HIGH",
                    }]

                error_analysis = {
                    "error_type": skill_result.error_type,
                    "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
                    "category": "KNOWN_NEEDS_LLM",
                }

        else:  # UNKNOWN
            # Unknown error, fully交给 LLM
            print("[INFO] UNKNOWN - Fully交给 LLM analysis")
            llm_client = LLMClient()
            print(f"  >> LLM API URL: {llm_client.api_url}")
            print(f"  >> LLM Model: {llm_client.model}")
            llm_result = llm_client.analyze(
                log_excerpt=logs[:2000],
                task_type=task_type,
                skill_result={
                    "error_type": "unknown",
                    # 传递预处理结果
                    "config_lines": config_lines[:10],
                    "error_blocks": error_blocks[:2],
                    "data_metrics": data_metrics,
                    "app_info": app_info,
                }
            )

            print(f"  >> LLM returned: {llm_result}")
            if llm_result.get("error_category"):

                # 累计 Token 消耗
                token_usage = llm_result.get("token_usage", {})
                if token_usage:
                    token_consumption += token_usage.get("total_tokens", 0)
                    token_details["analyze_unknown"] = token_usage

                error_patterns = llm_result.get("error_patterns", [])
                error_category = llm_result.get("error_category", "")
                suggested_actions = llm_result.get("suggested_actions", [])

                error_analysis = {
                    "error_type": llm_result.get("error_category", "unknown"),
                    "error_message": llm_result.get("error_description", logs[:200]),
                    "category": llm_result.get("can_auto_fix", False) and "AUTO_FIXABLE" or "UNKNOWN",
                    "llm_result": llm_result,
                }
            else:
                error_patterns = []
                error_category = ""
                suggested_actions = []

                error_analysis = {
                    "error_type": "unknown",
                    "error_message": "",
                    "category": "UNKNOWN",
                }
    else:
        # No Skill, call LLM directly
        print("[INFO] No matching Skill, call LLM analysis")
        llm_client = LLMClient()
        llm_result = llm_client.analyze(
            log_excerpt=logs[:2000],
            task_type=task_type,
            skill_result={
                "error_type": "unknown",
                # 传递预处理结果
                "config_lines": config_lines[:10],
                "error_blocks": error_blocks[:2],
                "data_metrics": data_metrics,
                "app_info": app_info,
            }
        )

        if llm_result.get("error_category"):
            # 累计 Token 消耗
            token_usage = llm_result.get("token_usage", {})
            if token_usage:
                token_consumption += token_usage.get("total_tokens", 0)
                token_details["analyze_no_skill"] = token_usage

            error_patterns = llm_result.get("error_patterns", [])
            error_category = llm_result.get("error_category", "")
            suggested_actions = llm_result.get("suggested_actions", [])

            error_analysis = {
                "error_type": llm_result.get("error_category", "unknown"),
                "error_message": llm_result.get("error_description", logs[:200]),
                "category": llm_result.get("can_auto_fix", False) and "AUTO_FIXABLE" or "UNKNOWN",
                "llm_result": llm_result,
            }
        else:
            error_patterns = []
            error_category = ""
            suggested_actions = []

            error_analysis = {
                "error_type": "unknown",
                "error_message": "",
                "category": "UNKNOWN",
            }

    # Send error analysis notification
    notifier = get_notifier_from_settings()
    project_name = state.get("project_name", state.get("project_code", "N/A"))
    workflow_name = state.get("workflow_name", state.get("workflow_code", "N/A"))
    task_name = state.get("task_name", "N/A")
    task_type = state.get("task_type", "UNKNOWN")

    # 从 skill_result 获取透明化报告
    original_log_error = None
    analysis_process = None
    reasoning = None

    if skill_result:
        original_log_error = getattr(skill_result, 'original_log_error', None)
        analysis_process = getattr(skill_result, 'analysis_process', None)
        reasoning = getattr(skill_result, 'reasoning', None)

    # Build error summary for notification
    error_type_display = error_analysis.get("error_type", "unknown") if error_analysis else "unknown"
    category = error_analysis.get("category", "UNKNOWN") if error_analysis else "UNKNOWN"
    error_message = (error_analysis.get("error_message", "")[:150] if error_analysis else "").replace("\n", " ")

    # Extract specific log error lines (find ERROR/FATAL/syntax error lines)
    log_error_lines = ""
    if logs:
        # Find lines containing error keywords
        error_keywords = ["error", "ERROR", "failed", "FAILED", "exception", "Exception", "fatal", "FATAL", "syntax"]
        lines = logs.split("\n")
        error_lines = []
        for line in lines:
            if any(kw in line for kw in error_keywords):
                error_lines.append(line.strip())
        # Take last 5 error lines (most relevant)
        if error_lines:
            log_error_lines = "\n".join(error_lines[-5:])

    # Build fix suggestions
    fix_text = ""
    if suggested_actions:
        fix_text = "**建议修复方案:**\n\n"
        for i, action in enumerate(suggested_actions[:3], 1):
            action_type = action.get("action_type", "unknown")
            desc = action.get("description", "").replace("\n", " ")
            fix_text += f"{i}. **{action_type}**: {desc}\n"

    # Build notification text
    notification_text = f"## 🔍 错误分析结果\n\n"
    notification_text += f"| 项目 | 工作流实例 | 任务节点名称 |\n"
    notification_text += f"| --- | --- | --- |\n"
    notification_text += f"| {project_name} | {workflow_name} | {task_name} |\n\n"
    notification_text += f"**任务类型:** {task_type}\n\n"
    notification_text += f"**错误类型:** `{error_type_display}`\n\n"
    notification_text += f"**错误类别:** {category}\n\n"

    if analysis_process:
        notification_text += f"**分析过程:**\n> {analysis_process}\n\n"

    if reasoning:
        notification_text += f"**建议理由:**\n> {reasoning}\n\n"

    notification_text += "---\n\n"

    if original_log_error:
        display_log = original_log_error[:500] if len(original_log_error) > 500 else original_log_error
        notification_text += f"**原始日志错误信息:**\n```\n{display_log}\n```\n\n"
        notification_text += "---\n\n"
    elif log_error_lines:
        notification_text += f"**日志错误信息:**\n```\n{log_error_lines[:500]}{'...' if len(log_error_lines) > 500 else ''}\n```\n\n"
        notification_text += "---\n\n"

    if error_message:
        error_message_display = (error_analysis.get("error_message", "")[:200] if error_analysis else "").replace("\n", " ")
        notification_text += f"**错误分析摘要:**\n> {error_message_display}\n\n"
        notification_text += "---\n\n"

    notification_text += fix_text

    notifier.send_markdown(
        title=f"错误分析 - {task_name}",
        text=notification_text
    )

    # 输出 Token 消耗统计
    print(f"\n[Token] 分析阶段消耗: {token_consumption} tokens")
    for detail_name, detail in token_details.items():
        print(f"  - {detail_name}: input={detail.get('input_tokens', 0)}, output={detail.get('output_tokens', 0)}, total={detail.get('total_tokens', 0)}")

    return {
        **state,
        "error_patterns": error_patterns,
        "error_category": error_category,
        "suggested_actions": suggested_actions,
        "knowledge_match": None,
        "error_analysis": error_analysis,
        "skill_result": {"error_type": error_type_display} if error_analysis else None,
        "token_consumption": token_consumption,
        "token_details": token_details,
    }


def _combine_logs(driver_logs: str, spark_logs: str, yarn_logs: str = "") -> str:
    """
    Combine logs for analysis

    日志优先级：
    1. driver_logs (dsctl) - 包含完整错误堆栈
    2. spark_logs (Spark History) - 包含配置和错误事件
    3. yarn_logs (YARN) - 包含诊断信息

    分析策略：
    - 从 driver_logs 提取错误堆栈
    - 从 spark_logs 提取 Spark 配置信息
    - 从 yarn_logs 提取 YARN 层面的诊断（如 Container killed）
    """
    parts = []

    # Driver logs 包含最完整的错误信息
    if driver_logs:
        parts.append(driver_logs)

    # Spark History 补充配置和执行统计
    if spark_logs:
        parts.append("\n" + spark_logs)

    # YARN 补充诊断信息
    if yarn_logs:
        parts.append("\n" + yarn_logs)

    return "\n".join(parts)


def _get_skill_for_task_type(task_type: str):
    """Get Skill based on task type"""
    try:
        if task_type == "SPARK":
            from ...skills.spark.analyzer import SparkSkill
            return SparkSkill()
        elif task_type == "SHELL":
            from ...skills.shell.analyzer import ShellSkill
            return ShellSkill()
        elif task_type == "PYTHON":
            from ...skills.python.analyzer import PythonSkill
            return PythonSkill()
        elif task_type == "DATAX":
            from ...skills.datax.analyzer import DataXSkill
            return DataXSkill()
    except ImportError:
        return None
    return None


def _map_error_category(error_type: str) -> str:
    """Map error type to category"""
    mapping = {
        "oom_executor": "RESOURCE",
        "oom_driver": "RESOURCE",
        "oom_driver_direct": "RESOURCE",
        "container_killed": "RESOURCE",
        "executor_lost": "RESOURCE",
        "class_not_found": "CONFIG",
        "no_class_def": "CONFIG",
        "shuffle_failed": "NETWORK",
        "connection_refused": "NETWORK",
        "hdfs_not_found": "DATA",
        "schema_mismatch": "DATA",
        "syntax_error": "EXECUTION",
        "broadcast_timeout": "EXECUTION",
        "stage_failed": "EXECUTION",
        "command_not_found": "EXECUTION",
    }
    return mapping.get(error_type, "EXECUTION")


def _build_actions_from_skill(skill, skill_result) -> List[Dict]:
    """Build actions from Skill result"""
    actions = []

    # Build AutoFixAction
    fix_action = skill.build_auto_fix_action(skill_result)
    if fix_action:
        changes = getattr(fix_action, 'script_changes', None) or getattr(fix_action, 'config_changes', None)
        actions.append({
            "action_type": fix_action.action_type,
            "description": str(changes) if changes else "auto fix",
            "risk_level": "LOW",
            "script_changes": getattr(fix_action, 'script_changes', None),
            "config_changes": getattr(fix_action, 'config_changes', None),
        })

    # Add suggestions
    if hasattr(skill, 'suggest'):
        suggestions = skill.suggest(skill_result)
        for suggestion in suggestions[:2]:
            actions.append({
                "action_type": "suggested",
                "description": suggestion,
                "risk_level": "MEDIUM"
            })

    return actions


__all__ = ["analyze_error"]