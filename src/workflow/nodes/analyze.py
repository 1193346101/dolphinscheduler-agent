"""
analyze_error 节点

分析错误模式 - Skill 分发 + LLM 辅助
"""

from typing import Dict, List
from ..state import AgentState
from ...tools.llm_client import LLMClient
from ...models.alert import AlertContext, AlertInfo


def analyze_error(state: AgentState) -> AgentState:
    """
    分析错误

    流程:
    1. 根据 task_type 选择 Skill
    2. Skill 分析日志，匹配错误模式
    3. 低置信度时调用 LLM 辅助
    4. 合并结果

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (error_patterns, error_category, suggested_actions, confidence_score, error_analysis)
    """
    task_type = state.get("task_type", "SPARK")
    driver_logs = state.get("driver_logs", "") or ""
    spark_logs = state.get("spark_logs", "") or ""

    # 合并日志
    logs = _combine_logs(driver_logs, spark_logs)

    if not logs:
        return {
            **state,
            "error_patterns": [],
            "error_category": "",
            "suggested_actions": [],
            "knowledge_match": None,
            "confidence_score": 0.0,
            "error_analysis": {
                "error_type": "unknown",
                "error_message": "",
                "can_auto_fix": False,
            },
        }

    # 构建 AlertContext
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

    # 1. Skill 分发
    skill = _get_skill_for_task_type(task_type)
    skill_result = None

    if skill:
        try:
            skill_result = skill.analyze(logs, context)
        except Exception:
            pass

    # 2. 处理 Skill 结果
    if skill_result and skill_result.confidence >= 0.8:
        # 高置信度直接使用
        error_patterns = [skill_result.error_type]
        error_category = _map_error_category(skill_result.error_type)
        suggested_actions = _build_actions_from_skill(skill, skill_result)
        confidence_score = skill_result.confidence

        # 构建 error_analysis 字段
        error_analysis = {
            "error_type": skill_result.error_type,
            "error_message": skill_result.error_message[:500] if skill_result.error_message else "",
            "can_auto_fix": skill_result.can_auto_fix,
        }
    else:
        # 低置信度调用 LLM 辅助
        llm_client = LLMClient()
        llm_result = llm_client.analyze(
            log_excerpt=logs[:2000],
            task_type=task_type,
            skill_result={"error_type": getattr(skill_result, 'error_type', 'unknown'), "confidence": getattr(skill_result, 'confidence', 0.5)}
        )

        if llm_result.get("confidence", 0) > 0:
            error_patterns = llm_result.get("error_patterns", [])
            error_category = llm_result.get("error_category", "")
            suggested_actions = llm_result.get("suggested_actions", [])
            confidence_score = llm_result.get("confidence", 0.5)

            error_analysis = {
                "error_type": error_category,
                "error_message": logs[:200] if logs else "",
                "can_auto_fix": False,
            }
        else:
            error_patterns = []
            error_category = ""
            suggested_actions = []
            confidence_score = 0.0

            error_analysis = {
                "error_type": "unknown",
                "error_message": "",
                "can_auto_fix": False,
            }

    return {
        **state,
        "error_patterns": error_patterns,
        "error_category": error_category,
        "suggested_actions": suggested_actions,
        "knowledge_match": None,
        "confidence_score": confidence_score,
        "error_analysis": error_analysis,
    }


def _combine_logs(driver_logs: str, spark_logs: str) -> str:
    """合并日志"""
    parts = []
    if driver_logs:
        parts.append(driver_logs)
    if spark_logs:
        parts.append(spark_logs)
    return "\n".join(parts)


def _get_skill_for_task_type(task_type: str):
    """根据任务类型获取 Skill"""
    try:
        if task_type == "SPARK":
            from ...skills.spark_skill import SparkSkill
            return SparkSkill()
        elif task_type == "SHELL":
            from ...skills.shell_skill import ShellSkill
            return ShellSkill()
        elif task_type == "PYTHON":
            from ...skills.python_skill import PythonSkill
            return PythonSkill()
        elif task_type == "DATAX":
            from ...skills.datax_skill import DataXSkill
            return DataXSkill()
    except ImportError:
        return None
    return None


def _map_error_category(error_type: str) -> str:
    """将错误类型映射到分类"""
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
        "broadcast_timeout": "EXECUTION",
        "stage_failed": "EXECUTION",
    }
    return mapping.get(error_type, "EXECUTION")


def _build_actions_from_skill(skill, skill_result) -> List[Dict]:
    """从 Skill 结果构建动作"""
    actions = []

    if skill_result.can_auto_fix:
        fix_action = skill._build_auto_fix_action(skill_result)
        if fix_action:
            actions.append({
                "action_type": fix_action.action_type,
                "description": str(fix_action.config_changes) if hasattr(fix_action, 'config_changes') else "auto fix",
                "risk_level": "LOW"
            })

    # 添加建议
    suggestions = skill.suggest(skill_result) if hasattr(skill, 'suggest') else []
    for suggestion in suggestions[:2]:
        actions.append({
            "action_type": "suggested",
            "description": suggestion,
            "risk_level": "MEDIUM"
        })

    return actions


__all__ = ["analyze_error"]