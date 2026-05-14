"""
Parse Intent Node - 纯 LLM 智能意图解析

重构版：
1. 移除关键词匹配，完全使用 LLM 解析
2. 自然语言理解增强
3. 上下文参数补全（多轮对话）
4. 记录 Token 消耗
"""

import json
import requests
from typing import Dict, Any

from ..state import ChatState
from ..tools.intent_context import intent_context
from ...tools.llm_client import LLMClient


def parse_intent_node(state: ChatState) -> ChatState:
    """
    解析用户消息意图（纯 LLM 解析模式）

    流程:
    1. 直接使用 LLM 解析意图
    2. 上下文参数补全
    3. 记录对话记忆
    4. 记录 Token 消耗

    Args:
        state: Current ChatState with message field populated

    Returns:
        Updated ChatState with intent fields populated
    """
    message = state.get("message", "")
    conversation_id = state.get("conversation_id", "default")

    # 初始化 Token 消耗统计
    token_consumption = state.get("token_consumption", 0)
    token_details = state.get("token_details", {})

    if not message or not message.strip():
        return _empty_result(state)

    message = message.strip()
    print(f"[parse_intent] 解析消息: {message}")

    # 获取上下文摘要（用于LLM）
    context_summary = intent_context.get_context_summary(conversation_id)
    print(f"[parse_intent] {context_summary}")

    # 纯 LLM 解析（移除关键词匹配）
    result = parse_with_llm(message, context_summary)
    print(f"[parse_intent] LLM解析: {result}")

    # 累计 Token 消耗
    token_usage = result.get("token_usage", {})
    if token_usage:
        token_consumption += token_usage.get("total_tokens", 0)
        token_details["parse_intent"] = token_usage
        print(f"[Token] parse_intent 消耗: input={token_usage.get('input_tokens', 0)}, output={token_usage.get('output_tokens', 0)}, total={token_usage.get('total_tokens', 0)}")

    # 参数补全（从上下文）
    result = intent_context.complete_parameters(conversation_id, result)

    # 记录对话记忆
    intent_context.update_memory(conversation_id, result, message)

    print(f"[parse_intent] 最终结果: {result}")

    # 输出累计 Token 消耗
    print(f"[Token] parse_intent_node 总消耗: {token_consumption} tokens")

    return {
        **state,
        "intent_type": result.get("intent_type", "unknown"),
        "query_type": result.get("query_type"),
        "workflow_code": result.get("workflow_code"),
        "workflow_name": result.get("workflow_name"),
        "workflow_instance_id": result.get("workflow_instance_id"),
        "table_name": result.get("table_name"),
        "project_name": result.get("project_name"),
        "project_code": result.get("project_code"),
        "query_date": result.get("query_date"),
        "confirmation_params": result.get("params", {}),  # 保存参数供确认流程使用
        "token_consumption": token_consumption,
        "token_details": token_details,
    }


def parse_with_llm(message: str, context_summary: str) -> Dict:
    """
    LLM 纯意图解析（无关键词匹配）

    特点：
    1. 支持自然语言表达（不限制固定格式）
    2. 理解上下文
    3. 智能补全参数
    """
    llm_client = LLMClient()

    # 构建提示词
    prompt = f"""分析用户消息，理解用户意图，返回JSON格式。

## 对话上下文
{context_summary}

## 用户消息
{message}

## 支持的意图类型
1. run_workflow - 执行/运行工作流（需要workflow_code或workflow_name，project_name）
   - 关键词: 执行、运行、启动、run
2. query_workflow - 查询项目工作流列表（需要project_name）
   - 关键词: 工作流列表、有哪些工作流
3. query_workflow_instances - 查工作流实例/运行记录（需要project_name，可选query_date）
   - 关键词: 实例、执行了、运行记录、今天/昨天运行
4. query_status - 查询工作流状态（需要workflow_code）
   - 关键词: 状态、运行情况、进度
5. query_logs - 查看工作流日志（需要workflow_code）
   - 关键词: 日志、log、报错信息
6. recover_failure - 恢复失败工作流（需要workflow_code或workflow_instance_id）
   - 关键词: 恢复、重跑、重新运行、retry
7. lineage_query - 血缘查询（需要query_type+workflow_code或table_name）
   - query_type: downstream/upstream/workflow_nodes/table_consumer/table_producer
   - 关键词: 下游、上游、依赖、消费、产出
8. scan_graph - 扫描项目图谱（需要project_name）
   - 关键词: 图谱、扫描项目
9. visualize_lineage - 可视化血缘（需要workflow_code）
   - 关键词: 展示、可视化、影响链路
10. help - 显示帮助
    - 关键词: 帮助、help、怎么用
11. unknown - 无法理解

## 理解规则
1. **意图区分**:
   - "执行工作流" = run_workflow（执行操作）
   - "工作流列表" = query_workflow（查询操作）
   - "有哪些工作流" = query_workflow（查询操作）
   - "运行了什么" = query_workflow_instances（查询实例）
2. **代词引用**: 用户可能说"它的状态"，需从上下文推断workflow_code
3. **简化表达**: 用户可能说"状态"、"日志"，需从上下文补全
4. **默认参数**:
   - worker_group 默认: all_worker
   - tenant 默认: 项目名称（如 ad_monitor 项目用 ad_monitor 租户）

## 返回格式
JSON:
{
  "intent_type": "主要意图",
  "project_name": "项目名（如果推断出来）",
  "project_code": "项目编码（数字）",
  "workflow_code": "工作流code（如果推断出来，数字）",
  "workflow_name": "工作流名（如果有）",
  "workflow_instance_id": "工作流实例ID（如果有）",
  "query_type": "血缘查询类型",
  "table_name": "表名",
  "query_date": "日期YYYY-MM-DD",
  "params": {
    "worker_group": "all_worker",
    "tenant": "项目名称"
  },
  "confidence": 0.0-1.0,
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
            return {"intent_type": "unknown"}

        data = response.json()

        # 获取 token 使用量
        usage = data.get("usage", {})
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
            print(f"[parse_intent] LLM解析结果: {parsed}")

            # 添加 token 使用量到结果
            if usage:
                input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
                parsed["token_usage"] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
                print(f"[parse_intent] Token usage: input={input_tokens}, output={output_tokens}")
            else:
                # 估算 token 使用量
                input_tokens = len(prompt) // 4
                output_tokens = len(text) // 4
                parsed["token_usage"] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
                print(f"[parse_intent] Estimated token usage: input={input_tokens}, output={output_tokens}")

            return parsed

    except Exception as e:
        print(f"[parse_intent] LLM异常: {e}")

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
        "project_code": None,
        "query_date": None,
        "confirmation_params": None,
        "token_consumption": state.get("token_consumption", 0),
        "token_details": state.get("token_details", {}),
    }


__all__ = ["parse_intent_node"]