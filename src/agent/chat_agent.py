"""
Chat Agent - 对话交互

★ 真正的 Agent，使用 LLM 决策 + 用户确认流程

核心能力:
- 使用 LLM 智能解析用户意图
- 提取参数（项目、工作流、日期等）
- 发送钉钉确认消息
- 用户确认后执行操作
- 知识图谱查询（scan_graph, lineage_query, visualize_lineage）

改进：
- 意图理解不再依赖死板的关键词匹配
- 解析后发送钉钉让用户确认
- 确认后再执行，避免误操作
"""

import json
from typing import Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import settings
from ..integrations import DSCLIClient
from ..integrations.dsctl_wrapper import CLIResult
from ..security.approval import ApprovalWorkflow
from ..chat.graph import create_chat_graph
from ..chat.state import create_chat_state
from ..tools.dingtalk_enterprise import DingTalkEnterpriseTool


class ChatAgent:
    """
    对话交互 Agent

    支持的意图:
    - run_workflow: "运行/执行 a项目的工作流xxx"
    - backfill: "补数日期 2026-01-01 到 2026-01-10"
    - query_status: "工作流xxx现在什么状态"
    - query_logs: "查看工作流xxx的最新日志"
    - recover_failure: "恢复工作流xxx的失败任务"
    - query_workflow: "项目有哪些工作流"
    - query_workflow_instances: "今天运行了哪些工作流"
    - scan_graph: "扫描项目X图谱"
    - lineage_query: "工作流Y下游/表T消费者"
    - visualize_lineage: "展示工作流Y的影响链路"

    流程：
    1. LLM 解析意图和参数
    2. 发送钉钉确认消息
    3. 用户确认后执行
    """

    # 确认请求缓存（等待用户确认）
    _pending_confirmations: dict = {}

    def __init__(self):
        self.llm = self._create_llm()
        self.ds_cli = DSCLIClient()
        self.approval_workflow = ApprovalWorkflow()
        self.chat_graph = create_chat_graph()
        self.dingtalk_tool = None

    def _create_llm(self):
        """创建 LLM"""
        if not settings.LLM_API_KEY:
            return None
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_URL,
            temperature=0,
        )

    def _init_dingtalk_tool(self):
        """初始化钉钉工具"""
        if self.dingtalk_tool is None:
            # 从配置获取钉钉参数
            self.dingtalk_tool = DingTalkEnterpriseTool(
                client_id=settings.DINGTALK_CLIENT_ID,
                client_secret=settings.DINGTALK_CLIENT_SECRET
            )
        return self.dingtalk_tool

    def handle_chat(self, chat_payload: dict) -> dict:
        """
        处理对话请求

        Args:
            chat_payload: 对话数据 {"message": "...", "user_id": "...", ...}

        Returns:
            处理结果
        """
        message = chat_payload.get("message", "")
        user_id = chat_payload.get("user_id", "")

        # 1. 检查是否是确认/拒绝回复
        if message.strip() in ["确认", "✅", "同意", "执行", "是"]:
            return self._handle_confirmation(user_id)
        elif message.strip() in ["取消", "❌", "拒绝", "不", "否"]:
            return self._handle_rejection(user_id)

        # 2. 识别是否为图谱相关意图（直接执行，无需确认）
        intent_type = self._detect_graph_intent(message)
        if intent_type in ("scan_graph", "lineage_query", "visualize_lineage"):
            return self._handle_graph_intent(chat_payload, intent_type)

        # 3. 使用 LLM 解析意图和参数
        if self.llm is None:
            return {"status": "error", "message": "LLM 未配置，无法解析意图"}

        try:
            intent_result = self._parse_intent_with_llm(message)

            # 4. 根据意图类型处理
            intent = intent_result.get("intent", "unknown")

            if intent == "unknown":
                return {
                    "status": "unknown",
                    "message": "无法理解您的请求，请提供更详细的信息",
                    "response": intent_result.get("response", ""),
                }

            # 5. 查询类意图（直接执行，无需确认）
            if intent in ("query_workflow", "query_status", "query_logs", "query_workflow_instances"):
                return self._execute_directly(intent_result, chat_payload)

            # 6. 执行类意图（需要用户确认）
            return self._request_confirmation(intent_result, chat_payload)

        except Exception as e:
            return {"status": "error", "message": f"解析失败: {str(e)}"}

    def _parse_intent_with_llm(self, message: str) -> dict:
        """
        使用 LLM 智能解析用户意图和参数

        Args:
            message: 用户消息

        Returns:
            解析结果，包含:
            - intent: 意图类型
            - params: 提取的参数
            - response: 给用户的响应
            - command: 建议执行的命令
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_PARSE_PROMPT),
            ("human", "{input}"),
        ])

        chain = prompt | self.llm

        response = chain.invoke({"input": message})
        content = response.content

        # 解析 LLM 返回的 JSON
        try:
            # 尝试直接解析 JSON
            if "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
                result = json.loads(json_str)
                return result
        except json.JSONDecodeError:
            pass

        # JSON 解析失败，返回原始内容
        return {
            "intent": "unknown",
            "params": {},
            "response": content,
        }

    def _request_confirmation(self, intent_result: dict, chat_payload: dict) -> dict:
        """
        发送钉钉确认请求

        Args:
            intent_result: LLM 解析结果
            chat_payload: 对话数据

        Returns:
            确认请求状态
        """
        intent = intent_result.get("intent", "")
        params = intent_result.get("params", {})
        response = intent_result.get("response", "")
        command = intent_result.get("command", "")
        user_id = chat_payload.get("user_id", "unknown")

        # 生成确认 ID
        confirm_id = f"confirm_{user_id}_{intent}"

        # 缓存确认请求
        self._pending_confirmations[confirm_id] = {
            "intent": intent,
            "params": params,
            "command": command,
            "chat_payload": chat_payload,
        }

        # 构建钉钉确认消息
        dingtalk = self._init_dingtalk_tool()

        # 构建确认内容
        confirm_text = f"""## 操作确认

**意图:** {intent}
**用户消息:** {chat_payload.get('message', '')}

---

### LLM 解析结果

{response}

---

### 将执行的命令

```
{command}
```

---

请确认是否执行此操作：
- 回复 **"确认"** 执行
- 回复 **"取消"** 拒绝"""

        # 发送钉钉消息
        try:
            dingtalk.send_notification(
                robot_code=settings.DINGTALK_ROBOT_CODE,
                user_ids=[user_id] if user_id else [],
                title=f"操作确认 - {intent}",
                content=confirm_text,
            )

            return {
                "status": "need_confirm",
                "message": "已发送确认请求到钉钉，请回复确认或取消",
                "intent": intent,
                "params": params,
                "response": response,
                "confirm_id": confirm_id,
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"发送钉钉确认失败: {str(e)}",
                "response": response,
            }

    def _handle_confirmation(self, user_id: str) -> dict:
        """
        处理用户确认

        Args:
            user_id: 用户 ID

        Returns:
            执行结果
        """
        # 查找用户的待确认请求
        confirm_key = None
        for key in self._pending_confirmations:
            if key.startswith(f"confirm_{user_id}_"):
                confirm_key = key
                break

        if not confirm_key:
            return {"status": "error", "message": "没有待确认的操作"}

        # 获取缓存的请求
        cached = self._pending_confirmations.pop(confirm_key)
        intent = cached.get("intent")
        params = cached.get("params")
        command = cached.get("command")

        # 执行操作
        try:
            result = self._execute_command(intent, params, command)

            return {
                "status": "success",
                "message": "操作已执行",
                "intent": intent,
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"执行失败: {str(e)}",
            }

    def _handle_rejection(self, user_id: str) -> dict:
        """
        处理用户拒绝

        Args:
            user_id: 用户 ID

        Returns:
            拒绝结果
        """
        # 清除待确认请求
        for key in list(self._pending_confirmations.keys()):
            if key.startswith(f"confirm_{user_id}_"):
                self._pending_confirmations.pop(key)

        return {
            "status": "cancelled",
            "message": "操作已取消",
        }

    def _execute_directly(self, intent_result: dict, chat_payload: dict) -> dict:
        """
        直接执行查询类操作（无需确认）

        Args:
            intent_result: LLM 解析结果
            chat_payload: 对话数据

        Returns:
            执行结果
        """
        intent = intent_result.get("intent", "")
        params = intent_result.get("params", {})

        try:
            result = self._execute_command(intent, params, intent_result.get("command", ""))

            return {
                "status": "success",
                "intent": intent,
                "result": result,
                "response": intent_result.get("response", ""),
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"查询失败: {str(e)}",
            }

    def _execute_command(self, intent: str, params: dict, suggested_command: str) -> dict:
        """
        执行具体命令

        Args:
            intent: 意图类型
            params: 参数
            suggested_command: LLM 建议的命令

        Returns:
            执行结果
        """
        # 获取默认参数
        project_code = params.get("project_code") or params.get("project_name")
        workflow_code = params.get("workflow_code") or params.get("workflow_name")

        # 如果参数不足，尝试从项目配置获取
        if not project_code:
            # 默认项目
            project_code = self._get_default_project_code()

        if intent == "run_workflow":
            # 运行工作流 - 使用默认参数
            worker_group = params.get("worker_group", "all_worker")
            tenant = params.get("tenant", self._get_default_tenant(project_code))

            result = self.ds_cli.workflow_run(
                project_code=int(project_code) if project_code else None,
                workflow_code=int(workflow_code) if workflow_code else None,
                worker_group=worker_group,
                tenant=tenant,
            )

            return self._parse_cli_result(result, "运行工作流")

        elif intent == "query_workflow":
            # 查询工作流列表
            result = self.ds_cli.workflow_list(project_code=int(project_code) if project_code else None)
            return self._parse_cli_result(result, "查询工作流")

        elif intent == "query_status":
            # 查询状态
            instance_id = params.get("instance_id")
            if instance_id:
                result = self.ds_cli.workflow_instance_get(int(instance_id))
            else:
                result = self.ds_cli.workflow_instance_list(project_code=int(project_code) if project_code else None)
            return self._parse_cli_result(result, "查询状态")

        elif intent == "query_workflow_instances":
            # 查询实例列表
            result = self.ds_cli.workflow_instance_list(project_code=int(project_code) if project_code else None)
            return self._parse_cli_result(result, "查询实例")

        elif intent == "query_logs":
            # 查询日志
            instance_id = params.get("instance_id")
            if instance_id:
                result = self.ds_cli.get_task_logs(int(instance_id))
                return {"logs": result.stdout[:500] if result.stdout else ""}
            return {"error": "缺少 instance_id"}

        elif intent == "recover_failure":
            # 恢复失败
            instance_id = params.get("instance_id")
            if instance_id:
                result = self.ds_cli.workflow_instance_recover_failed(int(instance_id))
                return self._parse_cli_result(result, "恢复失败")
            return {"error": "缺少 instance_id"}

        else:
            return {"error": f"未知意图: {intent}"}

    def _parse_cli_result(self, result: CLIResult, action: str) -> dict:
        """解析 CLI 执行结果"""
        if result.success:
            return {
                "success": True,
                "action": action,
                "output": result.stdout[:500] if result.stdout else "",
            }
        else:
            return {
                "success": False,
                "action": action,
                "error": result.error,
            }

    def _get_default_project_code(self) -> Optional[str]:
        """获取默认项目 code"""
        # 从配置或环境变量获取
        return settings.DEFAULT_PROJECT_CODE or None

    def _get_default_tenant(self, project_code: str) -> str:
        """获取默认租户"""
        # 根据项目获取租户，默认 ad_monitor
        if project_code and "ad_monitor" in str(project_code).lower():
            return "ad_monitor"
        return "default"

    def _detect_graph_intent(self, message: str) -> Optional[str]:
        """检测图谱相关意图"""
        from ..chat.tools.intent_parser import IntentParser
        parser = IntentParser()
        intent = parser.parse(message)
        intent_type = intent.get("intent_type")
        if intent_type in ("scan_graph", "lineage_query", "visualize_lineage"):
            return intent_type
        return None

    def _handle_graph_intent(self, chat_payload: dict, intent_type: str) -> dict:
        """使用 LangGraph 处理图谱相关意图"""
        message = chat_payload.get("message", "")
        user_id = chat_payload.get("user_id", "unknown")

        state = create_chat_state(
            message=message,
            user_id=user_id,
            conversation_id=chat_payload.get("conversation_id", ""),
        )

        result_state = self.chat_graph.invoke(state)

        if result_state.get("error_message"):
            return {
                "status": "error",
                "message": result_state["error_message"],
            }

        return {
            "status": "success",
            "intent": intent_type,
            "result_data": result_state.get("result_data", {}),
            "response": result_state.get("response_content", ""),
        }


INTENT_PARSE_PROMPT = """
你是 DolphinScheduler 对话助手的意图解析器。

你的任务是解析用户消息，提取意图和参数，并返回 JSON 格式的结果。

## 支持的意图类型

| 意图 | 示例 | 关键参数 |
|------|------|----------|
| run_workflow | 执行 ad_monitor 的 agent-test 工作流 | project_code, workflow_code, worker_group, tenant |
| query_workflow | ad_monitor 有哪些工作流 | project_code |
| query_workflow_instances | 今天运行了哪些工作流 | project_code, query_date |
| query_status | 工作流 12345 的状态 | workflow_code, instance_id |
| query_logs | 查看 12345 的日志 | instance_id |
| recover_failure | 恢复失败任务 | instance_id |
| unknown | 无法理解 | - |

## 默认参数规则

- worker_group 默认: all_worker
- tenant 默认: 项目名称（如 ad_monitor 项目用 ad_monitor 租户）
- project_code 默认: 如果用户提到项目名，查询项目 code

## 返回格式（必须是 JSON）

```json
{
    "intent": "意图类型",
    "params": {
        "project_code": "项目编码（数字）",
        "project_name": "项目名称",
        "workflow_code": "工作流编码（数字）",
        "workflow_name": "工作流名称",
        "worker_group": "worker组（默认 all_worker）",
        "tenant": "租户（默认项目名）",
        "instance_id": "实例ID",
        "query_date": "查询日期"
    },
    "response": "给用户的友好响应（说明你理解了什么）",
    "command": "建议执行的 dsctl 命令"
}
```

## 示例

用户: "执行 ad_monitor 项目下的 agent-test 工作流"

返回:
```json
{
    "intent": "run_workflow",
    "params": {
        "project_name": "ad_monitor",
        "workflow_name": "agent-test",
        "worker_group": "all_worker",
        "tenant": "ad_monitor"
    },
    "response": "理解您的请求：执行 ad_monitor 项目的 agent-test 工作流，使用 all_worker worker 组和 ad_monitor 租户",
    "command": "dsctl workflow run --project ad_monitor --workflow agent-test --worker-group all_worker --tenant ad_monitor"
}
```

用户: "ad_monitor 工作流列表"

返回:
```json
{
    "intent": "query_workflow",
    "params": {
        "project_name": "ad_monitor"
    },
    "response": "查询 ad_monitor 项目的工作流列表",
    "command": "dsctl workflow list --project ad_monitor"
}
```

注意：
- 只返回 JSON，不要其他文字
- 如果无法理解，intent 设为 "unknown"
- 尽量从用户消息中提取完整信息
"""


__all__ = ["ChatAgent"]