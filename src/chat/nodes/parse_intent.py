"""
Parse Intent Node - 智能意图解析（LLM-first）

重构版：
1. LLM优先理解（更灵活）
2. 关键词快速备用（效率）
3. 上下文参数补全（多轮对话）
4. 自然语言理解增强
"""

import json
import requests
from typing import Dict, Any

from ..state import ChatState
from ..tools.intent_parser import IntentParser
from ..tools.intent_context import intent_context
from ...tools.llm_client import LLMClient


def parse_intent_node(state: ChatState) -> ChatState:
    """
    解析用户消息意图（LLM-first模式）

    流程:
    1. 快速关键词检测（秒级响应）
    2. 如果关键词明确，直接返回
    3. 如果模糊，调用LLM深度理解
    4. 上下文参数补全
    5. 记录对话记忆

    Args:
        state: Current ChatState with message field populated

    Returns:
        Updated ChatState with intent fields populated
    """
    message = state.get("message", "")
    conversation_id = state.get("conversation_id", "default")

    if not message or not message.strip():
        return _empty_result(state)

    message = message.strip()
    print(f"[parse_intent] 解析消息: {message}")

    # 获取上下文摘要（用于LLM）
    context_summary = intent_context.get_context_summary(conversation_id)
    print(f"[parse_intent] {context_summary}")

    # 1. 快速关键词检测（明确意图直接返回）
    parser = IntentParser()
    quick_result = parser.parse(message)

    # 2. 如果是明确的简单意图（help、scan_graph等），直接返回
    if quick_result.get("intent_type") in ["help", "scan_graph", "unknown"]:
        # 即使是unknown，也可能是复杂表达，继续LLM
        if quick_result.get("intent_type") != "unknown":
            result = quick_result
            print(f"[parse_intent] 快速匹配: {result}")
        else:
            # 3. 模糊表达 -> LLM深度理解
            result = parse_with_llm_flexible(message, context_summary)
            print(f"[parse_intent] LLM理解: {result}")
    else:
        # 4. 检查是否需要参数补全
        result = quick_result
        if needs_more_parameters(result):
            # 尝试LLM补充参数
            enhanced = parse_with_llm_flexible(message, context_summary, result)
            if enhanced.get("intent_type") != "unknown":
                result = enhanced

    # 5. 参数补全（从上下文）
    result = intent_context.complete_parameters(conversation_id, result)

    # 6. 记录对话记忆
    intent_context.update_memory(conversation_id, result, message)

    print(f"[parse_intent] 最终结果: {result}")

    return {
        **state,
        "intent_type": result.get("intent_type", "unknown"),
        "query_type": result.get("query_type"),
        "workflow_code": result.get("workflow_code"),
        "workflow_name": result.get("workflow_name"),
        "workflow_instance_id": result.get("workflow_instance_id"),
        "table_name": result.get("table_name"),
        "project_name": result.get("project_name"),
        "query_date": result.get("query_date"),
    }


def needs_more_parameters(result: Dict) -> bool:
    """检查是否缺少必要参数"""
    intent_type = result.get("intent_type", "unknown")

    # 需要workflow_code的意图
    if intent_type in ["query_status", "query_logs", "recover_failure",
                       "run_workflow", "lineage_query", "visualize_lineage"]:
        return not result.get("workflow_code")

    # 需要project_name的意图
    if intent_type in ["query_workflow", "query_workflow_instances", "scan_graph"]:
        return not result.get("project_name")

    # 需要table_name的意图
    if intent_type == "lineage_query" and result.get("query_type") in ["table_consumer", "table_producer"]:
        return not result.get("table_name")

    return False


def parse_with_llm_flexible(
    message: str,
    context_summary: str,
    current_result: Dict = None
) -> Dict:
    """
    LLM灵活意图理解

    特点：
    1. 支持自然语言表达（不限制固定格式）
    2. 理解上下文
    3. 智能补全参数
    4. 支持意图组合（如"查状态和日志")
    """
    llm_client = LLMClient()

    # 构建灵活的提示词
    prompt = f"""分析用户消息，理解用户意图，返回JSON格式。

## 对话上下文
{context_summary}

## 用户消息
{message}

## 支持的意图类型
1. query_workflow - 查询项目工作流列表（需要project_name）
2. query_workflow_instances - 查询工作流实例/运行记录（需要project_name，可选query_date）
3. query_status - 查询工作流状态（需要workflow_code）
4. query_logs - 查看工作流日志（需要workflow_code）
5. recover_failure - 恢复失败工作流（需要workflow_code）
6. run_workflow - 运行工作流（需要workflow_code）
7. lineage_query - 血缘查询（需要query_type+workflow_code或table_name）
   - query_type: downstream/upstream/workflow_nodes/table_consumer/table_producer
8. scan_graph - 扫描项目图谱（需要project_name）
9. visualize_lineage - 可视化血缘（需要workflow_code）
10. help - 显示帮助
11. unknown - 无法理解

## 理解规则
1. 自然表达：用户可能说"看看xxx的情况"、"xxx怎么样"、"查一下xxx"
2. 代词引用：用户可能说"它的状态"、"那个工作流"，需从上下文推断
3. 简化表达：用户可能说"状态"、"日志"、"下游"，需从上下文补全
4. 多意图：用户可能说"状态和日志"，返回primary_intent和secondary_intents

## 返回格式
JSON:
{
  "intent_type": "主要意图",
  "project_name": "项目名（如果推断出来）",
  "workflow_code": "工作流code（如果推断出来）",
  "workflow_name": "工作流名（如果有）",
  "query_type": "血缘查询类型",
  "table_name": "表名",
  "query_date": "日期YYYY-MM-DD",
  "parameter_inferred": true/false,  # 是否从上下文推断参数
  "confidence": 0.0-1.0,  # 理解置信度
  "reasoning": "理解过程简述"
}

只返回JSON，不要其他文字。"""

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_client.api_token}",
            "x-api-key": llm_client.api_token,
        }

        payload = {
            "model": llm_client.model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}]
        }

        print(f"[parse_intent] LLM API: {llm_client.api_url}/v1/messages")

        response = requests.post(
            f"{llm_client.api_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            print(f"[parse_intent] LLM error: {response.status_code}")
            # 备用：返回关键词匹配结果或unknown
            if current_result:
                return current_result
            return {"intent_type": "unknown"}

        data = response.json()
        content = data.get("content", [])
        text = ""
        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                break

        # 解析JSON
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(text[json_start:json_end])
            print(f"[parse_intent] LLM解析: {parsed}")

            # 如果置信度低于0.5，可能理解不准确
            confidence = parsed.get("confidence", 0.5)
            if confidence < 0.5:
                print(f"[parse_intent] 低置信度: {confidence}")
                # 尝试关键词备用
                if current_result and current_result.get("intent_type") != "unknown":
                    return current_result

            return parsed

    except Exception as e:
        print(f"[parse_intent] LLM异常: {e}")
        if current_result:
            return current_result

    return {"intent_type": "unknown"}


def _empty_result(state: ChatState) -> ChatState:
    """空消息结果"""
    return {
        **state,
        "intent_type": "unknown",
        "query_type": None,
        "workflow_code": None,
        "workflow_name": None,
        "workflow_instance_id": None,
        "table_name": None,
        "project_name": None,
        "query_date": None,
    }


__all__ = ["parse_intent_node"]


def match_intent(message: str) -> Dict:
    """智能匹配意图"""
    matchers = [
        match_help,
        match_recover,
        match_query_workflow_instances,  # 新增：优先匹配实例查询
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


def match_query_workflow_instances(message: str) -> Dict:
    """匹配工作流实例查询（运行记录）"""
    # 关键词：实例、执行、运行、今天、昨天
    instance_words = ["实例", "执行了", "运行记录", "运行情况", "任务执行"]
    time_words = ["今天", "今日", "昨天", "昨日"]

    has_instance_context = any(word in message for word in instance_words)
    has_time_context = any(word in message for word in time_words)

    # 必须有实例关键词或时间关键词
    if not (has_instance_context or has_time_context):
        return None

    # 提取项目名
    project = extract_project(message)
    if not project:
        return None

    # 提取日期
    query_date = None
    if "今天" in message or "今日" in message:
        from datetime import date
        query_date = date.today().strftime("%Y-%m-%d")
    elif "昨天" in message or "昨日" in message:
        from datetime import date, timedelta
        query_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    return {
        "intent_type": "query_workflow_instances",
        "project_name": project,
        "query_date": query_date,
    }


def extract_project(message: str) -> str:
    clean_msg = message
    # 先移除 @机器人名 格式
    clean_msg = re.sub(r'@[a-zA-Z_][a-zA-Z0-9_]*', '', clean_msg)
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