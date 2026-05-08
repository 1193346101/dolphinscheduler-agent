"""
parse_alert 节点

从 webhook JSON 提取关键信息：project_code, workflow_code, task_code, task_type
支持识别子工作流并查询父工作流信息
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...graph.storage import GraphStorage
from ...graph.models import Graph
from ...config import settings


def parse_alert(state: AgentState) -> AgentState:
    """
    解析告警数据

    从 alert_raw 提取:
    - project_code
    - workflow_code (process_definition_code)
    - task_code
    - task_type
    - error_time
    - is_sub_workflow (是否为子工作流)
    - parent_workflow_code (父工作流编码，如果是子工作流)
    - process_instance_id (工作流实例ID)
    - parent_process_instance_id (父工作流实例ID，如果是子工作流)

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

    # 提取工作流实例ID
    process_instance_id = alert_raw.get("processId") or alert_raw.get("processInstanceId") or 0

    # 提取父工作流实例ID（如果是子工作流）
    # DS 3.2.0 可能使用 rootProcessInstanceId 或需要查询
    parent_process_instance_id = alert_raw.get("rootProcessInstanceId") or alert_raw.get("parentProcessInstanceId") or None

    # 检查是否为子工作流并查询父工作流
    is_sub_workflow = False
    parent_workflow_code: Optional[str] = None
    workflow_name = ""
    sub_workflow_node_code: Optional[str] = None  # 子工作流节点在父工作流中的任务编码

    # 尝试从图谱查询工作流信息
    graph_storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    graph_data = graph_storage.load_graph(project_code)

    if graph_data:
        graph = Graph.from_dict(graph_data)

        # 查找工作流节点
        for workflow in graph.nodes.workflows:
            if workflow.code == workflow_code:
                workflow_name = workflow.name
                is_sub_workflow = workflow.is_sub_workflow
                parent_workflow_code = workflow.parent_workflow
                break

        # 如果没有找到子工作流标记，检查边关系
        if not is_sub_workflow:
            for edge in graph.edges.workflow_calls_subworkflow:
                if edge.get("target") == workflow_code or edge.get("child") == workflow_code:
                    is_sub_workflow = True
                    parent_workflow_code = edge.get("source") or edge.get("parent")
                    sub_workflow_node_code = edge.get("node_code") or edge.get("task_code")
                    break
        else:
            # 已经识别为子工作流，查找边关系获取节点编码
            for edge in graph.edges.workflow_calls_subworkflow:
                if edge.get("target") == workflow_code or edge.get("child") == workflow_code:
                    sub_workflow_node_code = edge.get("node_code") or edge.get("task_code")
                    break

    # 如果是子工作流但没有从 webhook 获取到父实例ID，尝试从 API 查询
    if is_sub_workflow and parent_process_instance_id is None and process_instance_id:
        # 通过子工作流实例查询父工作流实例
        # 这里可以调用 dsctl 或 API 查询
        pass  # 暂时保持 None，后续节点可以查询

    # 更新状态
    return {
        **state,
        "project_code": project_code,
        "workflow_code": workflow_code,
        "workflow_name": workflow_name,
        "task_code": task_code,
        "task_type": task_type,
        "error_time": error_time,
        "is_sub_workflow": is_sub_workflow,
        "parent_workflow_code": parent_workflow_code,
        "process_instance_id": process_instance_id,
        "parent_process_instance_id": parent_process_instance_id,
        "sub_workflow_node_code": sub_workflow_node_code,
    }


__all__ = ["parse_alert"]