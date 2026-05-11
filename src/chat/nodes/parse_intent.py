"""
Parse Intent Node - 智能意图解析

使用关键词+规则匹配，不依赖 LLM
"""

import re
from typing import Dict, Any, List, Tuple

from ..state import ChatState


def parse_intent_node(state: ChatState) -> ChatState:
    """
    解析用户消息意图

    Args:
        state: Current ChatState with message field populated

    Returns:
        Updated ChatState with intent fields populated
    """
    message = state.get("message", "")

    if not message or not message.strip():
        return {
            **state,
            "intent_type": "unknown",
            "query_type": None,
            "workflow_code": None,
            "table_name": None,
            "project_name": None,
        }

    message = message.strip()
    print(f"[parse_intent] 解析消息: {message}")

    # 智能意图匹配
    result = match_intent(message)

    print(f"[parse_intent] 解析结果: {result}")

    return {
        **state,
        "intent_type": result.get("intent_type", "unknown"),
        "query_type": result.get("query_type"),
        "workflow_code": result.get("workflow_code"),
        "workflow_name": result.get("workflow_name"),
        "table_name": result.get("table_name"),
        "project_name": result.get("project_name"),
    }


def match_intent(message: str) -> Dict:
    """
    智能匹配意图

    使用关键词识别 + 参数提取，比正则更灵活
    """
    # 按优先级匹配意图
    matchers = [
        match_help,
        match_recover,
        match_scan_graph,
        match_visualize,
        match_table_lineage,
        match_workflow_lineage,
        match_workflow_status,
        match_workflow_logs,
        match_query_workflows,
    ]

    for matcher in matchers:
        result = matcher(message)
        if result:
            return result

    return {"intent_type": "unknown"}


def match_help(message: str) -> Dict:
    """匹配帮助意图"""
    help_words = ["帮助", "help", "怎么用", "使用方法", "指令", "命令"]
    if any(word in message.lower() for word in help_words):
        return {"intent_type": "help"}
    return None


def match_recover(message: str) -> Dict:
    """匹配恢复失败意图"""
    recover_words = ["恢复", "重跑", "重新运行", "retry"]
    if not any(word in message for word in recover_words):
        return None

    # 提取工作流
    workflow = extract_workflow(message)
    if workflow:
        return {"intent_type": "recover_failure", "workflow_code": workflow}
    return {"intent_type": "recover_failure"}


def match_scan_graph(message: str) -> Dict:
    """匹配扫描图谱意图"""
    if "图谱" not in message:
        return None

    scan_words = ["扫描", "更新", "刷新", "重建"]
    if not any(word in message for word in scan_words):
        # 检查 "项目xxx图谱"
        project = extract_project(message)
        if project:
            return {"intent_type": "scan_graph", "project_name": project}
        return None

    project = extract_project(message)
    if project:
        return {"intent_type": "scan_graph", "project_name": project}
    return {"intent_type": "scan_graph"}


def match_visualize(message: str) -> Dict:
    """匹配可视化意图"""
    viz_words = ["展示", "可视化", "影响链路", "链路图", "依赖图"]
    if not any(word in message for word in viz_words):
        return None

    workflow = extract_workflow(message)
    if workflow:
        return {"intent_type": "visualize_lineage", "workflow_code": workflow}
    return {"intent_type": "visualize_lineage"}


def match_table_lineage(message: str) -> Dict:
    """匹配表血缘查询"""
    if "表" not in message:
        return None

    table_name = extract_table(message)
    if not table_name:
        return None

    if "消费" in message or "使用" in message:
        return {"intent_type": "lineage_query", "query_type": "table_consumer", "table_name": table_name}
    if "产出" in message or "生产" in message:
        return {"intent_type": "lineage_query", "query_type": "table_producer", "table_name": table_name}
    return None


def match_workflow_lineage(message: str) -> Dict:
    """匹配工作流血缘查询"""
    if "工作流" not in message:
        return None

    workflow = extract_workflow(message)
    if not workflow:
        return None

    if "下游" in message:
        return {"intent_type": "lineage_query", "query_type": "downstream", "workflow_code": workflow}
    if "上游" in message or "依赖" in message:
        return {"intent_type": "lineage_query", "query_type": "upstream", "workflow_code": workflow}
    if "节点" in message or "任务" in message:
        return {"intent_type": "lineage_query", "query_type": "workflow_nodes", "workflow_code": workflow}
    return None


def match_workflow_status(message: str) -> Dict:
    """匹配查询状态意图"""
    status_words = ["状态", "运行情况", "进度", "执行情况"]
    if not any(word in message for word in status_words):
        return None

    workflow = extract_workflow(message)
    if workflow:
        return {"intent_type": "query_status", "workflow_code": workflow}
    return {"intent_type": "query_status"}


def match_workflow_logs(message: str) -> Dict:
    """匹配查询日志意图"""
    log_words = ["日志", "log", "输出", "报错信息"]
    if not any(word in message for word in log_words):
        return None

    workflow = extract_workflow(message)
    if workflow:
        return {"intent_type": "query_logs", "workflow_code": workflow}
    return {"intent_type": "query_logs"}


def match_query_workflows(message: str) -> Dict:
    """匹配查询项目工作流意图"""
    workflow_words = ["工作流", "有哪些", "列表", "workflow"]
    project_words = ["项目"]

    has_workflow_context = any(word in message for word in workflow_words)
    has_project_context = any(word in message for word in project_words)

    if not (has_workflow_context and has_project_context):
        return None

    project = extract_project(message)
    if project:
        return {"intent_type": "query_workflow", "project_name": project}
    return {"intent_type": "query_workflow"}


# ============ 参数提取函数 ============

def extract_project(message: str) -> str:
    """从消息中提取项目名"""
    # 移除常见干扰词
    clean_msg = message
    for word in ["查询", "项目", "的", "下", "有哪些", "工作流", "图谱", "扫描"]:
        clean_msg = clean_msg.replace(word, " ")

    # 提取连续的字母数字下划线
    matches = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', clean_msg)
    if matches:
        return matches[0]

    # 尝试提取中文项目名
    match = re.search(r'项目\s*(\S+)', message)
    if match:
        return match.group(1)

    return ""


def extract_workflow(message: str) -> str:
    """从消息中提取工作流"""
    # 先匹配 "工作流 xxx"
    match = re.search(r'工作流\s+(\S+)', message)
    if match:
        return match.group(1)

    # 匹配纯数字/代码
    match = re.search(r'(\d{5,})', message)
    if match:
        return match.group(1)

    # 匹配字母数字组合
    match = re.search(r'[a-zA-Z_][a-zA-Z0-9_]{4,}', message)
    if match:
        return match.group(0)

    return ""


def extract_table(message: str) -> str:
    """从消息中提取表名"""
    match = re.search(r'表\s+(\S+)', message)
    if match:
        return match.group(1)
    return ""


__all__ = ["parse_intent_node"]