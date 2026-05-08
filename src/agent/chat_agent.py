"""
Chat Agent - 对话交互

★ 真正的 Agent，使用 LLM 决策 + LangGraph 流程

核心能力:
- 理解用户意图
- 提取参数
- 构建 CLI 命令
- 风险评估
- 执行或审批
- 知识图谱查询（scan_graph, lineage_query, visualize_lineage）
"""

from typing import Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import settings
from ..integrations import DSCLIClient
from ..security.approval import ApprovalWorkflow
from ..chat.graph import create_chat_graph
from ..chat.state import create_chat_state


class ChatAgent:
    """
    对话交互 Agent

    支持的意图:
    - run_workflow: "运行 a项目的工作流xxx"
    - backfill: "补数日期 2026-01-01 到 2026-01-10"
    - query_status: "工作流xxx现在什么状态"
    - query_logs: "查看工作流xxx的最新日志"
    - recover_failure: "恢复工作流xxx的失败任务"
    - analyze_lineage: "分析表xxx的上下游血缘"
    - scan_graph: "扫描项目X图谱"
    - lineage_query: "工作流Y下游/表T消费者"
    - visualize_lineage: "展示工作流Y的影响链路"
    """

    def __init__(self):
        self.llm = self._create_llm()
        self.ds_cli = DSCLIClient()
        self.approval_workflow = ApprovalWorkflow()
        # 创建 LangGraph 流程（用于图谱相关意图）
        self.chat_graph = create_chat_graph()

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

    def handle_chat(self, chat_payload: dict) -> dict:
        """
        处理对话请求

        Args:
            chat_payload: 对话数据 {"message": "...", "user_id": "...", ...}

        Returns:
            处理结果
        """
        message = chat_payload.get("message", "")

        # 识别是否为图谱相关意图
        intent_type = self._detect_graph_intent(message)

        if intent_type in ("scan_graph", "lineage_query", "visualize_lineage"):
            # 使用 LangGraph 流程处理图谱相关意图
            return self._handle_graph_intent(chat_payload, intent_type)

        # 其他意图使用原有的 LLM 处理
        if self.llm is None:
            return self._handle_without_llm(message, chat_payload)

        # 使用 LLM 理解意图
        prompt = ChatPromptTemplate.from_messages([
            ("system", CHAT_AGENT_PROMPT),
            ("human", "{input}"),
        ])

        chain = prompt | self.llm

        try:
            response = chain.invoke({"input": message})
            intent_result = self._parse_intent(response.content)

            # 根据意图执行操作
            return self._execute_intent(intent_result, chat_payload)
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }

    def _detect_graph_intent(self, message: str) -> Optional[str]:
        """
        检测图谱相关意图

        Args:
            message: 用户消息

        Returns:
            intent_type 或 None
        """
        from ..chat.tools.intent_parser import IntentParser
        parser = IntentParser()
        intent = parser.parse(message)

        if intent.intent_type in ("scan_graph", "lineage_query", "visualize_lineage"):
            return intent.intent_type

        return None

    def _handle_graph_intent(self, chat_payload: dict, intent_type: str) -> dict:
        """
        使用 LangGraph 处理图谱相关意图

        Args:
            chat_payload: 对话数据
            intent_type: 意图类型

        Returns:
            处理结果
        """
        message = chat_payload.get("message", "")
        user_id = chat_payload.get("user_id", "unknown")

        # 创建初始状态
        state = create_chat_state(
            message=message,
            user_id=user_id,
            conversation_id=chat_payload.get("conversation_id", ""),
        )

        # 执行 LangGraph 流程
        result_state = self.chat_graph.invoke(state)

        # 提取结果
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

    def _handle_without_llm(self, message: str, payload: dict) -> dict:
        """无 LLM 时使用简单规则处理"""
        # 简单关键词匹配
        if "运行" in message or "run" in message.lower():
            return {"status": "need_info", "message": "请提供项目和工作流信息"}
        elif "状态" in message or "status" in message.lower():
            return {"status": "need_info", "message": "请提供工作流信息"}
        elif "日志" in message or "log" in message.lower():
            return {"status": "need_info", "message": "请提供任务实例 ID"}
        elif "恢复" in message or "recover" in message.lower():
            return {"status": "need_info", "message": "请提供工作流实例 ID"}
        else:
            return {"status": "unknown", "message": "无法理解请求，请提供更多信息"}

    def _parse_intent(self, llm_response: str) -> dict:
        """解析 LLM 返回的意图"""
        # 简单解析
        intent = "unknown"
        params = {}

        response_lower = llm_response.lower()

        if "run_workflow" in response_lower or "运行工作流" in llm_response:
            intent = "run_workflow"
        elif "backfill" in response_lower or "补数" in llm_response:
            intent = "backfill"
        elif "query_status" in response_lower or "查询状态" in llm_response:
            intent = "query_status"
        elif "query_logs" in response_lower or "查看日志" in llm_response:
            intent = "query_logs"
        elif "recover" in response_lower or "恢复" in llm_response:
            intent = "recover_failure"
        elif "lineage" in response_lower or "血缘" in llm_response:
            intent = "analyze_lineage"

        return {"intent": intent, "params": params, "raw_response": llm_response}

    def _execute_intent(self, intent_result: dict, payload: dict) -> dict:
        """执行意图"""
        intent = intent_result.get("intent", "unknown")

        if intent == "unknown":
            return {
                "status": "unknown_intent",
                "message": intent_result.get("raw_response", "无法理解请求"),
            }

        # 需要更多信息
        return {
            "status": "need_params",
            "intent": intent,
            "message": f"检测到意图: {intent}，请提供必要的参数",
        }


CHAT_AGENT_PROMPT = """
你是 DolphinScheduler 对话助手。

用户可以通过你执行以下操作：

## 支持的意图

1. **运行工作流**: "运行 a项目的工作流xxx"
   - 提取: project_code, workflow_code
   - 执行: dsctl workflow run

2. **补数**: "补数日期 2026-01-01 到 2026-01-10，worker分组xxx"
   - 提取: project_code, workflow_code, start_date, end_date, worker_group
   - 执行: dsctl workflow backfill

3. **查询状态**: "工作流xxx现在什么状态"
   - 提取: project_code, workflow_code
   - 执行: dsctl workflow-instance get

4. **查看日志**: "查看工作流xxx的最新日志"
   - 提取: project_code, instance_id
   - 执行: dsctl workflow-instance log

5. **恢复失败**: "恢复工作流xxx的失败任务"
   - 提取: project_code, instance_id
   - 执行: dsctl workflow-instance recover

6. **血缘分析**: "分析表xxx的上下游血缘"
   - 提取: table_name
   - 执行: 血缘分析逻辑

## 图谱相关意图（自动识别）

- **扫描图谱**: "扫描项目X图谱" → 自动触发图谱扫描
- **血缘查询**: "工作流Y下游" → 查询下游依赖
- **可视化**: "展示工作流Y的影响链路" → 生成Mermaid图

## 处理流程

1. 理解用户意图
2. 提取参数（项目、工作流、日期、worker分组等）
3. 构建 CLI 命令
4. 评估风险等级：
   - LOW/MEDIUM: 查询、运行工作流 → 直接执行
   - HIGH/CRITICAL: 补数、删除 → 需确认或审批
5. 执行或发起审批
6. 返回结果

注意：
- 补数操作影响较大，需用户确认
- 删除操作必须审批
"""


__all__ = ["ChatAgent"]