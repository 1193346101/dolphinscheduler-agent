"""
Format Response Node - 格式化响应内容

将查询结果格式化为 Markdown 格式，适配钉钉消息显示
"""

from typing import Dict, Any, Optional, List

from ..state import ChatState


def format_response_node(state: ChatState) -> ChatState:
    """
    Format result_data as Markdown for DingTalk.

    Handles different query_types with appropriate formatting:
    - downstream: List downstream workflows
    - upstream: List upstream workflows
    - workflow_nodes: List tasks in workflow
    - table_consumer: List consumers of table
    - table_producer: List producers of table

    Also handles error messages and non-lineage intents.

    Args:
        state: Current ChatState with result_data or error_message

    Returns:
        Updated ChatState with response_content populated
    """
    intent_type = state.get("intent_type")
    query_type = state.get("query_type")
    result_data = state.get("result_data")
    error_message = state.get("error_message")

    response_content: Optional[str] = None

    # Handle error first
    if error_message:
        response_content = format_error_response(state, error_message)
        return {
            **state,
            "response_content": response_content,
        }

    # Handle non-lineage intents
    if intent_type != "lineage_query":
        response_content = format_non_lineage_response(state)
        return {
            **state,
            "response_content": response_content,
        }

    # Handle lineage query results
    if not result_data:
        response_content = "查询无结果"
        return {
            **state,
            "response_content": response_content,
        }

    # Format based on query_type
    if query_type == "downstream":
        response_content = format_downstream_response(state, result_data)
    elif query_type == "upstream":
        response_content = format_upstream_response(state, result_data)
    elif query_type == "workflow_nodes":
        response_content = format_workflow_nodes_response(state, result_data)
    elif query_type == "table_consumer":
        response_content = format_table_consumer_response(state, result_data)
    elif query_type == "table_producer":
        response_content = format_table_producer_response(state, result_data)
    else:
        response_content = f"未知的查询类型: {query_type}"

    return {
        **state,
        "response_content": response_content,
    }


def format_error_response(state: ChatState, error_message: str) -> str:
    """Format error message as Markdown."""
    workflow_code = state.get("workflow_code")
    table_name = state.get("table_name")

    if workflow_code:
        return f"### 查询失败\n\n**工作流**: {workflow_code}\n\n**错误**: {error_message}"
    elif table_name:
        return f"### 查询失败\n\n**表**: {table_name}\n\n**错误**: {error_message}"
    else:
        return f"### 查询失败\n\n**错误**: {error_message}"


def format_non_lineage_response(state: ChatState) -> str:
    """Format response for non-lineage intents."""
    intent_type = state.get("intent_type")
    project_name = state.get("project_name")
    workflow_code = state.get("workflow_code")

    if intent_type == "scan_graph":
        return f"### 扫描图谱\n\n正在扫描项目 **{project_name}** 的知识图谱...\n\n请稍候，扫描完成后将通知您。"
    elif intent_type == "visualize_lineage":
        return f"### 血缘可视化\n\n工作流 **{workflow_code}** 的血缘链路图正在生成...\n\n请稍候。"
    elif intent_type == "help":
        return format_help_response()
    elif intent_type == "unknown":
        return "抱歉，我不理解您的消息。请发送 **帮助** 查看可用命令。"
    else:
        return f"收到您的消息，意图类型: {intent_type}"


def format_help_response() -> str:
    """Format help message as Markdown."""
    return """### 帮助

**支持的命令:**

1. **血缘查询**
   - `工作流 <code> 的下游` - 查询下游依赖
   - `工作流 <code> 的上游` - 查询上游依赖
   - `工作流 <code> 有哪些节点` - 查询任务节点

2. **表血缘**
   - `表 <name> 被谁消费` - 查询表的消费者
   - `表 <name> 被谁产出` - 查询表的生产者

3. **图谱管理**
   - `扫描项目 <name> 图谱` - 扫描项目图谱
   - `展示 <code> 的影响链路` - 可视化血缘

4. **其他**
   - `帮助` - 显示帮助信息

**示例:**
- `工作流 wf_12345 的下游`
- `表 hive.db.dwd_order 被谁消费`
- `扫描项目 my_project 图谱`"""


def format_downstream_response(state: ChatState, result_data: Dict) -> str:
    """Format downstream query result as Markdown."""
    workflow_code = state.get("workflow_code", "未知")
    found = result_data.get("found", False)

    if not found:
        return f"### 工作流 {workflow_code} 下游查询\n\n未找到下游依赖"

    direct = result_data.get("direct", [])
    all_deps = result_data.get("all", [])
    count = result_data.get("count", 0)

    lines = [
        f"### 工作流 {workflow_code} 下游依赖",
        "",
        f"**总数**: {count}",
        "",
        "**直接依赖**:",
    ]

    if direct:
        for wf in direct:
            lines.append(f"- {wf}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("**所有下游**:")

    if all_deps:
        for wf in all_deps:
            lines.append(f"- {wf}")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def format_upstream_response(state: ChatState, result_data: Dict) -> str:
    """Format upstream query result as Markdown."""
    workflow_code = state.get("workflow_code", "未知")
    found = result_data.get("found", False)

    if not found:
        return f"### 工作流 {workflow_code} 上游查询\n\n未找到上游依赖"

    upstream = result_data.get("upstream", [])

    lines = [
        f"### 工作流 {workflow_code} 上游依赖",
        "",
        f"**总数**: {len(upstream)}",
        "",
        "**上游工作流**:",
    ]

    if upstream:
        for wf in upstream:
            lines.append(f"- {wf}")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def format_workflow_nodes_response(state: ChatState, result_data: Dict) -> str:
    """Format workflow nodes query result as Markdown."""
    workflow_code = state.get("workflow_code", "未知")
    found = result_data.get("found", False)

    if not found:
        return f"### 工作流 {workflow_code} 节点查询\n\n未找到任务节点"

    tasks = result_data.get("tasks", [])
    task_names = result_data.get("task_names", {})
    task_types = result_data.get("task_types", {})
    spark_classes = result_data.get("spark_classes", {})

    lines = [
        f"### 工作流 {workflow_code} 任务节点",
        "",
        f"**总数**: {len(tasks)}",
        "",
        "**任务列表**:",
    ]

    for task_code in tasks:
        task_name = task_names.get(task_code, "未知")
        task_type = task_types.get(task_code, "未知")
        spark_class = spark_classes.get(task_code)

        if spark_class:
            lines.append(f"- **{task_name}** ({task_type}): `{spark_class}`")
        else:
            lines.append(f"- **{task_name}** ({task_type})")

    return "\n".join(lines)


def format_table_consumer_response(state: ChatState, result_data: Dict) -> str:
    """Format table consumer query result as Markdown."""
    table_name = state.get("table_name", "未知")
    found = result_data.get("found", False)

    if not found:
        return f"### 表 {table_name} 消费者查询\n\n未找到消费此表的任务"

    workflows = result_data.get("workflows", [])
    tasks = result_data.get("tasks", [])
    classes = result_data.get("classes", [])

    lines = [
        f"### 表 {table_name} 的消费者",
        "",
        f"**消费工作流**: {len(workflows)}",
        f"**消费任务**: {len(tasks)}",
        f"**消费类**: {len(classes)}",
        "",
        "**工作流**:",
    ]

    if workflows:
        for wf in workflows:
            lines.append(f"- {wf}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("**任务**:")

    if tasks:
        for task in tasks:
            lines.append(f"- {task}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("**类**:")

    if classes:
        for cls in classes:
            lines.append(f"- `{cls}`")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def format_table_producer_response(state: ChatState, result_data: Dict) -> str:
    """Format table producer query result as Markdown."""
    table_name = state.get("table_name", "未知")
    found = result_data.get("found", False)

    if not found:
        return f"### 表 {table_name} 生产者查询\n\n未找到生产此表的任务"

    workflows = result_data.get("workflows", [])
    tasks = result_data.get("tasks", [])
    classes = result_data.get("classes", [])

    lines = [
        f"### 表 {table_name} 的生产者",
        "",
        f"**生产工作流**: {len(workflows)}",
        f"**生产任务**: {len(tasks)}",
        f"**生产类**: {len(classes)}",
        "",
        "**工作流**:",
    ]

    if workflows:
        for wf in workflows:
            lines.append(f"- {wf}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("**任务**:")

    if tasks:
        for task in tasks:
            lines.append(f"- {task}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("**类**:")

    if classes:
        for cls in classes:
            lines.append(f"- `{cls}`")
    else:
        lines.append("- 无")

    return "\n".join(lines)


__all__ = ["format_response_node"]