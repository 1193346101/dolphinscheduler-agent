"""Intent parser for extracting structured intent from natural language messages."""

import re
from typing import Dict, Optional


class IntentParser:
    """Parser that extracts structured intent and parameters from user messages.

    Supported intents:
        - scan_graph: "扫描项目 X 图谱" / "更新 X 图谱"
        - lineage_query: downstream, upstream, workflow_nodes, table_consumer, table_producer
        - visualize_lineage: "展示 Y 的影响链路"
        - query_workflow: "查询项目 X 有哪些工作流" / "项目 X 的工作流"
        - query_status: "工作流 X 的状态" / "工作流 X 现在什么状态"
        - query_logs: "查看工作流 X 的日志" / "任务 X 的日志"
        - recover_failure: "恢复工作流 X" / "重跑工作流 X"
        - help: "帮助" / "help"
        - unknown: unrecognized messages
    """

    # Regex patterns for intent matching
    SCAN_GRAPH_PATTERN = r'扫描项目\s+(\S+)\s*图谱|更新\s+(\S+)\s*图谱'
    WORKFLOW_DOWNSTREAM_PATTERN = r'工作流\s+(\S+)\s*的下游|工作流\s+(\S+)\s+下游'
    WORKFLOW_UPSTREAM_PATTERN = r'工作流\s+(\S+)\s*的上游|工作流\s+(\S+)\s+上游依赖'
    WORKFLOW_NODES_PATTERN = r'工作流\s+(\S+)\s*有哪些节点|工作流\s+(\S+)\s*的节点'
    TABLE_CONSUMER_PATTERN = r'表\s+(\S+)\s*被谁消费|表\s+(\S+)\s+的消费'
    TABLE_PRODUCER_PATTERN = r'表\s+(\S+)\s*被谁产出|表\s+(\S+)\s+的生产'
    VISUALIZE_PATTERN = r'展示\s+(\S+)\s*的影响链路|可视化\s+(\S+)\s+的下游'
    # 新增：查询项目工作流（支持 "查询项目X" 和 "项目X"）
    QUERY_PROJECT_WORKFLOWS_PATTERN = r'(?:查询)?\s*(\S+)\s*项目(?:下)?有哪些工作流'
    # 新增：查询工作流状态
    QUERY_STATUS_PATTERN = r'工作流\s+(\S+)\s*的状态|工作流\s+(\S+)\s*现在什么状态|查询工作流\s+(\S+)\s*状态'
    # 新增：查看日志
    QUERY_LOGS_PATTERN = r'查看\s*工作流\s+(\S+)\s*的日志|工作流\s+(\S+)\s*的日志|任务\s+(\S+)\s*的日志'
    # 新增：恢复失败
    RECOVER_FAILURE_PATTERN = r'恢复\s*工作流\s+(\S+)|重跑\s*工作流\s+(\S+)|恢复失败\s*工作流\s+(\S+)'
    HELP_PATTERN = r'^帮助$|^help$'

    def __init__(self):
        """Initialize regex patterns."""
        self._scan_graph_re = re.compile(self.SCAN_GRAPH_PATTERN)
        self._workflow_downstream_re = re.compile(self.WORKFLOW_DOWNSTREAM_PATTERN)
        self._workflow_upstream_re = re.compile(self.WORKFLOW_UPSTREAM_PATTERN)
        self._workflow_nodes_re = re.compile(self.WORKFLOW_NODES_PATTERN)
        self._table_consumer_re = re.compile(self.TABLE_CONSUMER_PATTERN)
        self._table_producer_re = re.compile(self.TABLE_PRODUCER_PATTERN)
        self._visualize_re = re.compile(self.VISUALIZE_PATTERN)
        self._query_project_workflows_re = re.compile(self.QUERY_PROJECT_WORKFLOWS_PATTERN)
        self._query_status_re = re.compile(self.QUERY_STATUS_PATTERN)
        self._query_logs_re = re.compile(self.QUERY_LOGS_PATTERN)
        self._recover_failure_re = re.compile(self.RECOVER_FAILURE_PATTERN)
        self._help_re = re.compile(self.HELP_PATTERN, re.IGNORECASE)

    def parse(self, message: str) -> Dict:
        """Parse user message to extract intent and parameters.

        Args:
            message: User's natural language message

        Returns:
            Dictionary containing:
                - intent_type: str (scan_graph, lineage_query, visualize_lineage,
                                   query_workflow, query_status, query_logs,
                                   recover_failure, help, unknown)
                - query_type: str (optional, for lineage_query)
                - project_name: str (optional)
                - workflow_code: str (optional)
                - table_name: str (optional)
        """
        if not message or not message.strip():
            return {"intent_type": "unknown"}

        message = message.strip()

        # Check for help intent
        if self._help_re.match(message):
            return {"intent_type": "help"}

        # Check for scan_graph intent
        match = self._scan_graph_re.search(message)
        if match:
            project_name = match.group(1) or match.group(2)
            return {
                "intent_type": "scan_graph",
                "project_name": project_name
            }

        # Check for query project workflows intent
        match = self._query_project_workflows_re.search(message)
        if match:
            project_name = match.group(1)
            return {
                "intent_type": "query_workflow",
                "project_name": project_name
            }

        # Check for workflow status intent
        match = self._query_status_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2) or match.group(3)
            return {
                "intent_type": "query_status",
                "workflow_code": workflow_code
            }

        # Check for query logs intent
        match = self._query_logs_re.search(message)
        if match:
            workflow_or_task = match.group(1) or match.group(2) or match.group(3)
            return {
                "intent_type": "query_logs",
                "workflow_code": workflow_or_task
            }

        # Check for recover failure intent
        match = self._recover_failure_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2) or match.group(3)
            return {
                "intent_type": "recover_failure",
                "workflow_code": workflow_code
            }

        # Check for workflow downstream query
        match = self._workflow_downstream_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "downstream",
                "workflow_code": workflow_code
            }

        # Check for workflow upstream query
        match = self._workflow_upstream_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "upstream",
                "workflow_code": workflow_code
            }

        # Check for workflow nodes query
        match = self._workflow_nodes_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "workflow_nodes",
                "workflow_code": workflow_code
            }

        # Check for table consumer query
        match = self._table_consumer_re.search(message)
        if match:
            table_name = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "table_consumer",
                "table_name": table_name
            }

        # Check for table producer query
        match = self._table_producer_re.search(message)
        if match:
            table_name = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "table_producer",
                "table_name": table_name
            }

        # Check for visualize lineage intent
        match = self._visualize_re.search(message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "visualize_lineage",
                "workflow_code": workflow_code
            }

        # Default to unknown intent
        return {"intent_type": "unknown"}