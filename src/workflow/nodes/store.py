"""
store_results node

Store results - full implementation

新增功能：
- 生成完整的错误分析报告（HTML + JSON）
- 添加报告链接到 state，供通知使用
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