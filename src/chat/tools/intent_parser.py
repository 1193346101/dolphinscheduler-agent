"""Intent parser for extracting structured intent from natural language messages.

重构版：统一意图解析逻辑，与parse_intent_node保持一致
移除冗余正则模式，使用关键词匹配+LLM备用模式
"""

import re
from typing import Dict, Optional, List

# 意图类型定义
INTENT_TYPES = [
    "scan_graph",           # 扫描项目图谱
    "lineage_query",        # 血缘查询（downstream/upstream/table_consumer/table_producer/workflow_nodes）
    "visualize_lineage",    # 可视化血缘
    "query_workflow",       # 查询项目工作流列表
    "query_workflow_instances",  # 查询工作流实例列表（运行记录）
    "query_status",         # 查询工作流状态
    "query_logs",           # 查看日志
    "query_task_instances", # 查询任务实例详情
    "recover_failure",      # 恢复失败工作流
    "run_workflow",         # 手动运行工作流
    "help",                 # 帮助
    "unknown",              # 未知意图
]


class IntentParser:
    """Parser that extracts structured intent and parameters from user messages.

    统一意图解析器，与parse_intent_node逻辑保持一致
    """

    # 关键词映射（用于快速匹配）
    INTENT_KEYWORDS = {
        "help": ["帮助", "help", "怎么用", "使用方法", "指令", "命令"],
        "scan_graph": ["图谱", "扫描", "更新图谱"],
        "visualize_lineage": ["展示", "可视化", "影响链路", "链路图", "依赖图"],
        "recover_failure": ["恢复", "重跑", "重新运行", "retry"],
        "run_workflow": ["运行", "执行", "启动", "跑一下"],
    }

    def __init__(self):
        """Initialize parser."""
        pass

    def parse(self, message: str) -> Dict:
        """Parse user message to extract intent and parameters.

        Args:
            message: User's natural language message

        Returns:
            Dictionary containing:
                - intent_type: str
                - query_type: str (optional, for lineage_query)
                - project_name: str (optional)
                - workflow_code: str (optional)
                - workflow_name: str (optional)
                - workflow_instance_id: str (optional)
                - table_name: str (optional)
                - query_date: str (optional)
        """
        if not message or not message.strip():
            return {"intent_type": "unknown"}

        message = message.strip()

        # 1. 快速关键词匹配
        result = self._match_keywords(message)
        if result.get("intent_type") != "unknown":
            return result

        # 2. 复杂模式匹配（工作流、表血缘等）
        result = self._match_complex_patterns(message)
        if result.get("intent_type") != "unknown":
            return result

        # 3. 默认unknown
        return {"intent_type": "unknown"}

    def _match_keywords(self, message: str) -> Dict:
        """基于关键词快速匹配意图"""
        message_lower = message.lower()

        # help
        if any(word in message_lower for word in self.INTENT_KEYWORDS["help"]):
            return {"intent_type": "help"}

        # scan_graph
        if any(word in message for word in ["图谱"]):
            project = self._extract_project(message)
            return {"intent_type": "scan_graph", "project_name": project}

        # visualize_lineage
        if any(word in message for word in self.INTENT_KEYWORDS["visualize_lineage"]):
            workflow = self._extract_workflow(message)
            return {"intent_type": "visualize_lineage", "workflow_code": workflow}

        # recover_failure
        if any(word in message for word in self.INTENT_KEYWORDS["recover_failure"]):
            workflow = self._extract_workflow(message)
            return {"intent_type": "recover_failure", "workflow_code": workflow}

        # run_workflow
        if any(word in message for word in self.INTENT_KEYWORDS["run_workflow"]):
            workflow = self._extract_workflow(message)
            return {"intent_type": "run_workflow", "workflow_code": workflow}

        return {"intent_type": "unknown"}

    def _match_complex_patterns(self, message: str) -> Dict:
        """复杂模式匹配"""
        # query_workflow_instances（运行记录）
        instance_words = ["实例", "执行了", "运行记录", "运行情况", "任务执行"]
        time_words = ["今天", "今日", "昨天", "昨日"]
        if any(word in message for word in instance_words) or any(word in message for word in time_words):
            project = self._extract_project(message)
            if project:
                query_date = self._extract_date(message)
                return {
                    "intent_type": "query_workflow_instances",
                    "project_name": project,
                    "query_date": query_date,
                }

        # query_workflow（工作流列表）
        if any(word in message for word in ["工作流", "有哪些", "列表"]) and any(word in message for word in ["项目"]):
            project = self._extract_project(message)
            return {"intent_type": "query_workflow", "project_name": project}

        # query_status
        if any(word in message for word in ["状态", "运行情况", "进度"]):
            workflow = self._extract_workflow(message)
            return {"intent_type": "query_status", "workflow_code": workflow}

        # query_logs
        if any(word in message for word in ["日志", "log", "输出", "报错信息"]):
            workflow = self._extract_workflow(message)
            return {"intent_type": "query_logs", "workflow_code": workflow}

        # query_task_instances
        if "任务实例" in message or "任务详情" in message:
            instance_id = self._extract_instance_id(message)
            return {"intent_type": "query_task_instances", "workflow_instance_id": instance_id}

        # lineage_query - workflow
        if "工作流" in message:
            workflow = self._extract_workflow(message)
            if workflow:
                if "下游" in message:
                    return {"intent_type": "lineage_query", "query_type": "downstream", "workflow_code": workflow}
                if "上游" in message or "依赖" in message:
                    return {"intent_type": "lineage_query", "query_type": "upstream", "workflow_code": workflow}
                if "节点" in message or "任务" in message:
                    return {"intent_type": "lineage_query", "query_type": "workflow_nodes", "workflow_code": workflow}

        # lineage_query - table
        if "表" in message:
            table_name = self._extract_table(message)
            if table_name:
                if "消费" in message or "使用" in message:
                    return {"intent_type": "lineage_query", "query_type": "table_consumer", "table_name": table_name}
                if "产出" in message or "生产" in message:
                    return {"intent_type": "lineage_query", "query_type": "table_producer", "table_name": table_name}

        return {"intent_type": "unknown"}

    def _extract_project(self, message: str) -> str:
        """提取项目名"""
        # 移除干扰词
        clean_msg = re.sub(r'@[a-zA-Z_][a-zA-Z0-9_]*', '', message)
        for word in ["查询", "项目", "的", "下", "有哪些", "工作流", "图谱", "扫描", "今天", "昨天", "实例", "运行"]:
            clean_msg = clean_msg.replace(word, " ")
        # 匹配英文/数字项目名
        matches = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', clean_msg)
        if matches:
            return matches[0]
        # 匹配中文后的项目名
        match = re.search(r'项目\s*(\S+)', message)
        if match:
            return match.group(1)
        return ""

    def _extract_workflow(self, message: str) -> str:
        """提取工作流code/name"""
        # "工作流 xxx" 格式
        match = re.search(r'工作流\s+(\S+)', message)
        if match:
            return match.group(1)
        # 数字code（5位以上）
        match = re.search(r'(\d{5,})', message)
        if match:
            return match.group(1)
        # 英文名（4位以上）
        match = re.search(r'[a-zA-Z_][a-zA-Z0-9_]{4,}', message)
        if match:
            return match.group(0)
        return ""

    def _extract_table(self, message: str) -> str:
        """提取表名"""
        match = re.search(r'表\s+(\S+)', message)
        if match:
            return match.group(1)
        return ""

    def _extract_date(self, message: str) -> Optional[str]:
        """提取日期"""
        from datetime import date, timedelta
        if "今天" in message or "今日" in message:
            return date.today().strftime("%Y-%m-%d")
        elif "昨天" in message or "昨日" in message:
            return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        # YYYY-MM-DD格式
        match = re.search(r'(\d{4}-\d{2}-\d{2})', message)
        if match:
            return match.group(1)
        return None

    def _extract_instance_id(self, message: str) -> str:
        """提取实例ID"""
        match = re.search(r'实例\s+(\d+)', message)
        if match:
            return match.group(1)
        match = re.search(r'(\d{5,})', message)
        if match:
            return match.group(1)
        return ""


__all__ = ["IntentParser", "INTENT_TYPES"]