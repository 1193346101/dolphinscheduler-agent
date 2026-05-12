"""Intent parser for extracting structured intent from natural language messages.

重构版：
1. 支持自然语言表达（不限制固定格式）
2. 模糊匹配（相似意图识别）
3. 代词引用支持
4. 多种表达方式
"""

import re
from typing import Dict, Optional, List

# 意图类型定义
INTENT_TYPES = [
    "scan_graph",
    "lineage_query",
    "visualize_lineage",
    "query_workflow",
    "query_workflow_instances",
    "query_status",
    "query_logs",
    "query_task_instances",
    "recover_failure",
    "run_workflow",
    "help",
    "unknown",
]

# 模糊意图映射（多种表达方式对应同一意图）
FUZZY_INTENT_MAP = {
    # help的多种表达
    "help": ["帮助", "help", "怎么用", "使用方法", "指令", "命令", "能做什么", "功能", "用法", "介绍一下"],
    # query_status的多种表达
    "query_status": ["状态", "运行情况", "进度", "执行情况", "怎么样", "情况如何", "现在", "看看", "情况", "查状态"],
    # query_logs的多种表达
    "query_logs": ["日志", "log", "输出", "报错", "错误信息", "运行日志", "执行日志", "查看日志", "看日志", "错误"],
    # recover_failure的多种表达
    "recover_failure": ["恢复", "重跑", "重新运行", "retry", "重试", "再跑一次", "恢复失败", "恢复一下"],
    # run_workflow的多种表达
    "run_workflow": ["运行", "执行", "启动", "跑一下", "开始", "触发", "手动运行", "立即执行", "跑"],
    # query_workflow的多种表达
    "query_workflow": ["有哪些工作流", "工作流列表", "什么工作流", "workflow", "工作流", "查工作流"],
    # query_workflow_instances的多种表达
    "query_workflow_instances": ["实例", "执行记录", "运行记录", "运行历史", "今天", "昨天", "执行了", "运行了", "历史"],
    # lineage_query的多种表达
    "lineage_query": ["下游", "上游", "依赖", "血缘", "影响", "节点", "消费", "产出"],
}


class IntentParser:
    """Parser that extracts structured intent and parameters from user messages.

    支持多种自然表达方式，更灵活的意图识别
    """

    def __init__(self):
        """Initialize parser."""
        pass

    def parse(self, message: str) -> Dict:
        """Parse user message to extract intent and parameters.

        支持多种表达方式：
        - 固定格式：工作流12345的状态
        - 自然表达：12345怎么样
        - 代词引用：它的状态（需要上下文）
        - 模糊表达：状态（需要上下文补全）

        Args:
            message: User's natural language message

        Returns:
            Dictionary with intent and parameters
        """
        if not message or not message.strip():
            return {"intent_type": "unknown"}

        message = message.strip()

        # 1. 快速匹配（明确意图）
        result = self._quick_match(message)
        if result.get("intent_type") != "unknown":
            return result

        # 2. 模糊匹配（多种表达）
        result = self._fuzzy_match(message)
        if result.get("intent_type") != "unknown":
            return result

        # 3. 实体提取（尝试从消息中提取实体）
        result = self._extract_entities(message)
        if result.get("intent_type") != "unknown":
            return result

        # 4. 默认unknown（交给LLM处理）
        return {"intent_type": "unknown", "need_llm": True}

    def _quick_match(self, message: str) -> Dict:
        """快速匹配明确意图"""

        # help
        for word in FUZZY_INTENT_MAP["help"]:
            if word in message.lower():
                return {"intent_type": "help"}

        # scan_graph
        if "图谱" in message:
            project = self._extract_project(message)
            return {"intent_type": "scan_graph", "project_name": project}

        # visualize
        viz_words = ["展示", "可视化", "影响链路", "链路图", "依赖图", "血缘图"]
        if any(word in message for word in viz_words):
            workflow = self._extract_workflow(message)
            return {"intent_type": "visualize_lineage", "workflow_code": workflow}

        return {"intent_type": "unknown"}

    def _fuzzy_match(self, message: str) -> Dict:
        """模糊匹配（根据关键词推断意图）"""

        # 优先级：时间相关意图优先（避免语义歧义）
        # 例如："昨天执行了"应该是query_workflow_instances，而不是run_workflow

        # 检查时间相关意图优先
        time_keywords = FUZZY_INTENT_MAP.get("query_workflow_instances", [])
        matched_time = [k for k in time_keywords if k in message and k in ["今天", "昨天", "执行了", "运行了", "历史"]]
        if matched_time:
            project = self._extract_project(message)
            date = self._extract_date(message)
            return {
                "intent_type": "query_workflow_instances",
                "project_name": project,
                "query_date": date,
            }

        # 检测各意图的关键词组
        for intent_type, keywords in FUZZY_INTENT_MAP.items():
            if intent_type in ["help", "scan_graph", "query_workflow_instances"]:  # 已在其他逻辑处理
                continue

            # 检查是否包含关键词
            matched_keywords = [k for k in keywords if k in message]
            if matched_keywords:
                # 根据意图类型提取参数
                result = {"intent_type": intent_type}

                if intent_type in ["query_status", "query_logs", "recover_failure", "run_workflow"]:
                    workflow = self._extract_workflow(message)
                    if workflow:
                        result["workflow_code"] = workflow
                    else:
                        # 可能需要从上下文补全
                        result["need_context"] = True

                elif intent_type == "query_workflow":
                    project = self._extract_project(message)
                    if project:
                        result["project_name"] = project
                    else:
                        result["need_context"] = True

                elif intent_type == "lineage_query":
                    # 判断具体query_type
                    workflow = self._extract_workflow(message)
                    table = self._extract_table(message)

                    if "下游" in message:
                        result["query_type"] = "downstream"
                        result["workflow_code"] = workflow or ""
                    elif "上游" in message or "依赖" in message:
                        result["query_type"] = "upstream"
                        result["workflow_code"] = workflow or ""
                    elif "节点" in message:
                        result["query_type"] = "workflow_nodes"
                        result["workflow_code"] = workflow or ""
                    elif table and ("消费" in message or "使用" in message):
                        result["query_type"] = "table_consumer"
                        result["table_name"] = table
                    elif table and ("产出" in message or "生产" in message):
                        result["query_type"] = "table_producer"
                        result["table_name"] = table
                    else:
                        result["need_context"] = True

                return result

        return {"intent_type": "unknown"}

    def _extract_entities(self, message: str) -> Dict:
        """尝试从消息中提取实体"""

        # 检查是否有工作流相关内容
        if "工作流" in message:
            workflow = self._extract_workflow(message)
            if workflow:
                # 根据后续词判断意图
                if "下游" in message:
                    return {"intent_type": "lineage_query", "query_type": "downstream", "workflow_code": workflow}
                if "上游" in message or "依赖" in message:
                    return {"intent_type": "lineage_query", "query_type": "upstream", "workflow_code": workflow}
                if "节点" in message or "任务" in message:
                    return {"intent_type": "lineage_query", "query_type": "workflow_nodes", "workflow_code": workflow}

        # 检查是否有表相关内容
        if "表" in message:
            table = self._extract_table(message)
            if table:
                if "消费" in message or "使用" in message:
                    return {"intent_type": "lineage_query", "query_type": "table_consumer", "table_name": table}
                if "产出" in message or "生产" in message:
                    return {"intent_type": "lineage_query", "query_type": "table_producer", "table_name": table}

        # 检查是否有项目相关内容
        if "项目" in message and "工作流" in message:
            project = self._extract_project(message)
            if project:
                return {"intent_type": "query_workflow", "project_name": project}

        return {"intent_type": "unknown"}

    def _extract_project(self, message: str) -> str:
        """提取项目名（支持多种格式）"""
        # 移除干扰词
        clean_msg = re.sub(r'@[a-zA-Z_][a-zA-Z0-9_]*', '', message)
        for word in ["查询", "项目", "的", "下", "有哪些", "工作流", "图谱", "扫描",
                     "今天", "昨天", "实例", "运行", "状态", "日志", "帮助"]:
            clean_msg = clean_msg.replace(word, " ")

        # 匹配英文项目名
        matches = re.findall(r'[a-zA-Z_][a-zA-Z0-9_-]*', clean_msg)
        if matches:
            for m in matches:
                if len(m) >= 2:  # 至少2个字符
                    return m

        # 匹配中文项目名
        match = re.search(r'项目\s*[:：]?\s*([^\s，。！？]+)', message)
        if match:
            return match.group(1).strip()

        return ""

    def _extract_workflow(self, message: str) -> str:
        """提取工作流code/name（支持多种格式）"""

        # "工作流 xxx" 格式
        match = re.search(r'工作流\s*[:：]?\s*(\S+)', message)
        if match:
            return match.group(1)

        # 数字code（5位以上）
        match = re.search(r'(\d{5,})', message)
        if match:
            return match.group(1)

        # wf_xxx格式
        match = re.search(r'(wf_[a-zA-Z0-9_]+)', message)
        if match:
            return match.group(1)

        # 英文名（包含下划线或数字，4位以上）
        match = re.search(r'[a-zA-Z][a-zA-Z0-9_]{3,}', message)
        if match:
            candidate = match.group(0)
            # 过滤掉常见的干扰词
            if candidate.lower() not in ["今天", "昨天", "项目", "工作", "下游", "上游", "状态", "日志"]:
                return candidate

        return ""

    def _extract_table(self, message: str) -> str:
        """提取表名"""
        # "表 xxx" 格式
        match = re.search(r'表\s*[:：]?\s*(\S+)', message)
        if match:
            return match.group(1)

        # hive.db.table格式
        match = re.search(r'[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+', message)
        if match:
            return match.group(0)

        # db.table格式
        match = re.search(r'[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+', message)
        if match:
            return match.group(0)

        return ""

    def _extract_date(self, message: str) -> Optional[str]:
        """提取日期"""
        from datetime import date, timedelta

        # 自然语言日期
        if "今天" in message or "今日" in message:
            return date.today().strftime("%Y-%m-%d")
        if "昨天" in message or "昨日" in message:
            return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        # YYYY-MM-DD格式
        match = re.search(r'(\d{4}-\d{2}-\d{2})', message)
        if match:
            return match.group(1)

        # YYYYMMDD格式
        match = re.search(r'(\d{8})', message)
        if match:
            try:
                d = match.group(1)
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            except:
                pass

        return None


__all__ = ["IntentParser", "INTENT_TYPES", "FUZZY_INTENT_MAP"]