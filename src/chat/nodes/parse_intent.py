"""
Parse Intent Node - 智能意图解析

使用关键词匹配，LLM 备用（统一使用 LLMClient）
"""

import re
import json
from typing import Dict, Any

from ..state import ChatState
from ...tools.llm_client import LLMClient


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

    # 先用规则匹配（快速）
    result = match_intent(message)

    # 如果规则匹配失败，尝试 LLM
    if result.get("intent_type") == "unknown":
        llm_result = parse_with_llm(message)
        if llm_result and llm_result.get("intent_type") != "unknown":
            result = llm_result

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


def parse_with_llm(message: str) -> Dict:
    """
    使用 LLM 解析意图（统一使用 LLMClient）

    继承 LLMClient 的默认配置，无需单独配置环境变量
    """
    llm_client = LLMClient()

    prompt = f"""分析用户消息，提取意图类型和参数，返回 JSON 格式。

支持的意图类型：
- query_workflow: 查询项目工作流列表，参数 project_name
- query_status: 查询工作流状态，参数 workflow_code
- query_logs: 查看日志，参数 workflow_code
- recover_failure: 恢复失败工作流，参数 workflow_code
- lineage_query: 血缘查询，参数 query_type(downstream/upstream/table_consumer/table_producer), workflow_code/table_name
- scan_graph: 扫描项目图谱，参数 project_name
- visualize_lineage: 可视化血缘链路，参数 workflow_code
- help: 帮助
- unknown: 未知意图

用户消息：{message}

返回 JSON：{{"intent_type": "xxx", "project_name": "xxx", "workflow_code": "xxx", "query_type": "xxx", "table_name": "xxx"}}"""

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_client.api_token}",
            "x-api-key": llm_client.api_token,
        }

        payload = {
            "model": llm_client.model,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}]
        }

        print(f"[parse_intent] Calling LLM: {llm_client.api_url}/v1/messages")
        print(f"[parse_intent] Model: {llm_client.model}")

        import requests
        response = requests.post(
            f"{llm_client.api_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            print(f"[parse_intent] LLM error: {response.status_code}")
            return {"intent_type": "unknown"}

        data = response.json()
        content = data.get("content", [])
        text = ""
        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                break

        # 解析 JSON
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(text[json_start:json_end])
            print(f"[parse_intent] LLM result: {parsed}")
            return parsed

    except Exception as e:
        print(f"[parse_intent] LLM exception: {e}")

    return {"intent_type": "unknown"}


def match_intent(message: str) -> Dict:
    """智能匹配意图"""
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
    help_words = ["帮助", "help", "怎么用", "使用方法", "指令", "命令"]
    if any(word in message.lower() for word in help_words):
        return {"intent_type": "help"}
    return None


def match_recover(message: str) -> Dict:
    recover_words = ["恢复", "重跑", "重新运行", "retry"]
    if not any(word in message for word in recover_words):
        return None
    workflow = extract_workflow(message)
    return {"intent_type": "recover_failure", "workflow_code": workflow or ""}


def match_scan_graph(message: str) -> Dict:
    if "图谱" not in message:
        return None
    project = extract_project(message)
    return {"intent_type": "scan_graph", "project_name": project or ""}


def match_visualize(message: str) -> Dict:
    viz_words = ["展示", "可视化", "影响链路", "链路图", "依赖图"]
    if not any(word in message for word in viz_words):
        return None
    workflow = extract_workflow(message)
    return {"intent_type": "visualize_lineage", "workflow_code": workflow or ""}


def match_table_lineage(message: str) -> Dict:
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
    status_words = ["状态", "运行情况", "进度", "执行情况"]
    if not any(word in message for word in status_words):
        return None
    workflow = extract_workflow(message)
    return {"intent_type": "query_status", "workflow_code": workflow or ""}


def match_workflow_logs(message: str) -> Dict:
    log_words = ["日志", "log", "输出", "报错信息"]
    if not any(word in message for word in log_words):
        return None
    workflow = extract_workflow(message)
    return {"intent_type": "query_logs", "workflow_code": workflow or ""}


def match_query_workflows(message: str) -> Dict:
    workflow_words = ["工作流", "有哪些", "列表", "workflow"]
    project_words = ["项目"]
    has_workflow_context = any(word in message for word in workflow_words)
    has_project_context = any(word in message for word in project_words)
    if not (has_workflow_context and has_project_context):
        return None
    project = extract_project(message)
    return {"intent_type": "query_workflow", "project_name": project or ""}


def extract_project(message: str) -> str:
    clean_msg = message
    for word in ["查询", "项目", "的", "下", "有哪些", "工作流", "图谱", "扫描"]:
        clean_msg = clean_msg.replace(word, " ")
    matches = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', clean_msg)
    if matches:
        return matches[0]
    match = re.search(r'项目\s*(\S+)', message)
    if match:
        return match.group(1)
    return ""


def extract_workflow(message: str) -> str:
    match = re.search(r'工作流\s+(\S+)', message)
    if match:
        return match.group(1)
    match = re.search(r'(\d{5,})', message)
    if match:
        return match.group(1)
    match = re.search(r'[a-zA-Z_][a-zA-Z0-9_]{4,}', message)
    if match:
        return match.group(0)
    return ""


def extract_table(message: str) -> str:
    match = re.search(r'表\s+(\S+)', message)
    if match:
        return match.group(1)
    return ""


__all__ = ["parse_intent_node"]