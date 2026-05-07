"""
parse_alert 节点

从 webhook JSON 提取关键信息：project_code, workflow_code, task_code, task_type
"""

from typing import Dict, Any
from ..state import AgentState


def parse_alert(state: AgentState) -> AgentState:
    """
    解析告警数据

    从 alert_raw 提取:
    - project_code
    - workflow_code (process_definition_code)
    - task_code
    - task_type
    - error_time

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    alert_raw = state["alert_raw"]

    # 提取项目编码
    project_code = str(alert_raw.get("projectCode", 0))

    # 提取工作流编码 (DS 3.2.0 使用 processDefinitionCode)
    workflow_code = str(alert_raw.get("processDefinitionCode", 0))

    # 提取任务编码
    task_code = str(alert_raw.get("taskCode", 0))

    # 提取任务类型
    task_type = alert_raw.get("taskType", "UNKNOWN").upper()
    # 规范化任务类型
    if task_type not in ["SHELL", "SPARK", "PYTHON", "DATAX"]:
        task_type = "SHELL"  # 默认

    # 提取错误时间
    error_time = alert_raw.get("endTime") or alert_raw.get("taskEndTime") or ""

    # 更新状态
    return {
        **state,
        "project_code": project_code,
        "workflow_code": workflow_code,
        "task_code": task_code,
        "task_type": task_type,
        "error_time": error_time,
    }


__all__ = ["parse_alert"]