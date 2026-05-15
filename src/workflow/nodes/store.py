"""
store_results node

Store results - full implementation

新增功能：
- 生成完整的错误分析报告（HTML + JSON）
- 添加报告链接到 state，供通知使用
- 发送包含报告链接和人工反馈提示的最终通知
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional
from ..state import AgentState
from ...config.settings import settings
from ...tools.report_generator import ReportGenerator


def _sanitize_path_component(value: str) -> str:
    """Sanitize path component, prevent path traversal attack"""
    if not value:
        return "unknown"
    # Only keep letters, numbers, underscores, hyphens
    sanitized = re.sub(r'[^\w\-]', '_', str(value))
    # Prevent path traversal
    if sanitized in ('.', '..', '') or sanitized.startswith('..'):
        return "unknown"
    return sanitized


def store_results(state: AgentState, base_path: str = "data/logs") -> AgentState:
    """
    Store results

    Store content:
    - driver_logs, spark_logs, yarn_logs, k8s_logs
    - error_category, risk_level, error_patterns
    - suggested_actions, execution_results

    Args:
        state: Current state
        base_path: Storage directory root path

    Returns:
        Updated state (log_stored, result_stored, log_store_path)
    """
    workflow_code = state.get("workflow_code", "")
    task_code = state.get("task_code", "")

    # Check if there are logs to store
    has_logs = any([
        state.get("driver_logs"),
        state.get("spark_logs"),
        state.get("yarn_logs"),
        state.get("k8s_logs"),
    ])

    if not has_logs:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
        }

    # Sanitize path components
    workflow_code_safe = _sanitize_path_component(str(workflow_code))
    task_code_safe = _sanitize_path_component(str(task_code))

    # Create storage directory
    date_str = datetime.now().strftime("%Y%m%d")
    log_dir = os.path.join(base_path, date_str, workflow_code_safe)

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
            "log_store_error": f"Create directory failed: {str(e)}",
        }

    # Build storage data
    log_data = {
        "workflow_code": workflow_code,
        "task_code": task_code,
        "task_type": state.get("task_type", ""),
        "error_category": state.get("error_category", ""),
        "risk_level": state.get("risk_level", ""),
        "error_patterns": state.get("error_patterns", []),
        "suggested_actions": state.get("suggested_actions", []),
        "execution_results": state.get("execution_results", []),
        "stored_at": datetime.now().isoformat(),
    }

    # Add logs
    if state.get("driver_logs"):
        log_data["driver_logs"] = state["driver_logs"]
    if state.get("spark_logs"):
        log_data["spark_logs"] = state["spark_logs"]
    if state.get("yarn_logs"):
        log_data["yarn_logs"] = state["yarn_logs"]
    if state.get("k8s_logs"):
        log_data["k8s_logs"] = state["k8s_logs"]

    # Store file
    filename = f"{task_code_safe}_{datetime.now().strftime('%H%M%S')}.json"
    filepath = os.path.join(log_dir, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
    except (IOError, OSError, json.JSONEncodeError) as e:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
            "log_store_error": f"Write file failed: {str(e)}",
            "report_id": None,
            "report_url": None,
        }

    # 生成错误分析报告
    report_id = None
    report_url = None
    try:
        report_generator = ReportGenerator()
        report_id = report_generator.generate_report(state)

        # 构建报告 URL
        # 使用 API 服务地址 + /report/{report_id}
        api_host = settings.API_HOST or "localhost"
        api_port = settings.API_PORT or 8080
        report_url = f"http://{api_host}:{api_port}/report/{report_id}?workflow={workflow_code}&date={date_str}"

        print(f"[store] 生成分析报告: {report_id}")
        print(f"[store] 报告链接: {report_url}")
    except Exception as e:
        print(f"[store] 报告生成失败: {e}")

    # 发送最终结果通知（包含报告链接和反馈按钮）
    execution_success = state.get("execution_success", False)
    knowledge_entry_id = state.get("knowledge_entry_id")
    task_name = state.get("task_name", "N/A")
    error_type = state.get("error_type") or state.get("skill_result", {}).get("error_type", "")
    script_changes = None
    action_type = None

    executed_actions = state.get("executed_actions", [])
    if executed_actions:
        first_action = executed_actions[0]
        action_type = first_action.get("action_type")
        script_changes = first_action.get("script_changes")

    if execution_success:
        # 发送执行成功通知，包含报告链接和反馈按钮
        from ...tools.dingtalk_progress import get_notifier_from_settings

        notifier = get_notifier_from_settings()
        project_name = state.get("project_name", state.get("project_code", "N/A"))

        # 错误类型中文映射
        ERROR_TYPE_CN_MAP = {
            "syntax_error": "语法错误",
            "command_not_found": "命令未找到",
            "oom_executor": "Executor内存溢出",
            "oom_driver": "Driver内存溢出",
            "container_killed": "容器被终止",
            "executor_lost": "Executor丢失",
            "shuffle_failed": "Shuffle失败",
            "connection_refused": "连接被拒绝",
            "hdfs_not_found": "HDFS文件不存在",
            "unknown": "未知错误",
        }
        error_type_cn = ERROR_TYPE_CN_MAP.get(error_type, error_type)

        # 执行动作中文映射
        ACTION_TYPE_CN_MAP = {
            "modify_script": "修改脚本",
            "modify_config": "修改配置",
            "script-fix": "修复脚本",
            "recover-failed": "恢复失败任务",
            "rerun": "重新运行",
        }
        action_type_cn = ACTION_TYPE_CN_MAP.get(action_type, action_type or "执行")

        # 构建成功通知
        text = f"## ✅ 执行结果通知\n\n"
        text += f"| 项目 | 工作流实例 | 任务节点 |\n"
        text += f"| --- | --- | --- |\n"
        text += f"| {project_name} | {state.get('workflow_name', 'N/A')} | {task_name} |\n\n"
        text += f"**错误类型:** {error_type_cn}\n\n"
        text += f"**执行动作:** {action_type_cn}\n\n"

        if script_changes:
            text += "**修复内容:**\n"
            for wrong, correct in script_changes.items():
                wrong_display = wrong[:60] + "..." if len(wrong) > 60 else wrong
                correct_display = correct[:60] + "..." if len(correct) > 60 else correct
                text += f"- `{wrong_display}` → `{correct_display}`\n"
            text += "\n"

        if report_url:
            text += f"**详细报告:** [点击查看]({report_url})\n\n"

        text += "---\n\n"

        # 人工反馈提示
        if knowledge_entry_id:
            text += "💡 **修复确认**\n\n"
            text += "请确认修复是否正确，帮助 Agent 学习改进：\n"
            text += "- 回复 ✅ 或 \"修复正确\" → 确认有效\n"
            text += "- 回复 ❌ 或 \"修复错误\" + 正确做法 → 标记无效\n"

        notifier.send_markdown("执行结果", text)
        print(f"[store] 发送执行成功通知")

    return {
        **state,
        "log_stored": True,
        "result_stored": True,
        "log_store_path": filepath,
        "report_id": report_id,
        "report_url": report_url,
        "token_consumption": state.get("token_consumption", 0),
        "token_details": state.get("token_details", {}),
    }


__all__ = ["store_results"]