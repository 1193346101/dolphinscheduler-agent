"""
store_results 节点

存储结果 - 完整实现
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from ..state import AgentState


def store_results(state: AgentState, base_path: str = "data/logs") -> AgentState:
    """
    存储结果

    存储内容:
    - driver_logs, spark_logs, yarn_logs, k8s_logs
    - error_category, risk_level, error_patterns
    - suggested_actions, execution_results

    Args:
        state: 当前状态
        base_path: 存储目录根路径

    Returns:
        更新后的状态 (log_stored, result_stored, log_store_path)
    """
    workflow_code = state.get("workflow_code", "")
    task_code = state.get("task_code", "")

    # 检查是否有日志需要存储
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

    # 创建存储目录
    date_str = datetime.now().strftime("%Y%m%d")
    log_dir = os.path.join(base_path, date_str, str(workflow_code))
    os.makedirs(log_dir, exist_ok=True)

    # 构建存储数据
    log_data = {
        "workflow_code": workflow_code,
        "task_code": task_code,
        "task_type": state.get("task_type", ""),
        "error_category": state.get("error_category", ""),
        "risk_level": state.get("risk_level", ""),
        "error_patterns": state.get("error_patterns", []),
        "suggested_actions": state.get("suggested_actions", []),
        "execution_results": state.get("execution_results", []),
        "confidence_score": state.get("confidence_score", 0.0),
        "stored_at": datetime.now().isoformat(),
    }

    # 添加日志
    if state.get("driver_logs"):
        log_data["driver_logs"] = state["driver_logs"]
    if state.get("spark_logs"):
        log_data["spark_logs"] = state["spark_logs"]
    if state.get("yarn_logs"):
        log_data["yarn_logs"] = state["yarn_logs"]
    if state.get("k8s_logs"):
        log_data["k8s_logs"] = state["k8s_logs"]

    # 存储文件
    filename = f"{task_code}_{datetime.now().strftime('%H%M%S')}.json"
    filepath = os.path.join(log_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return {
        **state,
        "log_stored": True,
        "result_stored": True,
        "log_store_path": filepath,
    }


__all__ = ["store_results"]