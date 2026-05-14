"""
Webhook API - 接收 DolphinScheduler 告警

使用 LangGraph 状态机处理告警流程
"""

# 加载 .env 文件的环境变量
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..workflow.graph import AlertWorkflowGraph
from ..workflow.state import AgentState
from ..config.projects import projects_registry
from ..knowledge.manager import knowledge_manager
from ..security.approval import ApprovalWorkflow
from ..tools.approval_tool import ApprovalTool


# 创建 FastAPI 应用
app = FastAPI(title="DolphinScheduler Agent API")

# 注册钉钉对话路由
from ..chat.api import router as dingtalk_router
app.include_router(dingtalk_router)

# 注册报告路由
from ..api.report_api import router as report_router
app.include_router(report_router)

# 初始化组件
approval_workflow = ApprovalWorkflow()
approval_tool = ApprovalTool()

# 创建工作流实例
workflow = AlertWorkflowGraph()


# ============ 请求模型 ============

class AlertRequest(BaseModel):
    """告警请求"""
    projectCode: int
    processDefinitionCode: int
    processInstanceId: int
    taskCode: int
    taskInstanceId: int
    taskType: str
    state: str
    host: Optional[str] = None
    workerGroup: Optional[str] = None
    tenantCode: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None


class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    user_id: Optional[str] = None
    project_code: Optional[int] = None


class FeedbackRequest(BaseModel):
    """反馈请求"""
    entry_id: str
    feedback: str  # valid, invalid
    human_suggestion: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    """审批操作请求"""
    action: str  # approve, reject
    approver: Optional[str] = None
    reject_reason: Optional[str] = None


# ============ API 端点 ============

@app.post("/webhook")
async def webhook_alert(request: Request):
    """
    统一 Webhook 端点 - 接收 DolphinScheduler 告警和钉钉对话

    根据消息格式自动区分处理：

    1. 钉钉对话格式: {"msgtype": "text", "text": {"content": "..."}, ...}
       → 跳转到对话处理流程

    2. DolphinScheduler 告警格式: {"alerts": "[{\"projectCode\":..., ...}]"}
       → 使用 LangGraph 状态机执行告警处理流程

    DS 告警处理流程:
    解析告警 -> 验证项目 -> 获取日志 -> 分析错误
    -> 查询知识库 -> 风险评估 -> 审批/自动修复
    -> 钉钉通知 -> 存储结果
    """
    try:
        payload = await request.json()

        # 打印原始 payload 用于调试
        print(f"[webhook] Received payload: {payload}")

        # === 判断消息类型 ===

        # 钉钉对话消息：有 msgtype 字段
        if "msgtype" in payload:
            return await handle_dingtalk_chat(payload)

        # DolphinScheduler 告警：有 alerts 字段或告警特征字段
        return await handle_ds_alert(payload)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def handle_dingtalk_chat(payload: dict) -> JSONResponse:
    """
    处理钉钉对话消息

    通过 LangGraph 流程执行查询意图
    """
    from ..chat.graph import get_chat_graph
    from ..chat.state import create_chat_state

    # 提取消息内容
    msgtype = payload.get("msgtype", "text")
    content = extract_dingtalk_content(payload, msgtype)

    if not content or not content.strip():
        return JSONResponse(content={
            "msgtype": "text",
            "text": {"content": "请输入有效消息"}
        })

    # 提取用户和会话信息
    user_id = payload.get("senderId", "unknown")
    conversation_id = payload.get("conversationId", "unknown")

    # 创建初始状态
    state = create_chat_state(
        message=content,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    # 设置 project_name (从会话标题获取，用户在消息中也可以指定)
    project_name = extract_project_code_from_dingtalk(payload)  # 函数名不变，但返回的是项目名
    if project_name:
        state["project_name"] = project_name

    # 通过 LangGraph 流程图执行
    graph = get_chat_graph()
    result_state = graph.invoke(state)

    # 构建钉钉响应
    response_content = result_state.get("response_content", "处理完成")

    return JSONResponse(content={
        "msgtype": "markdown",
        "markdown": {
            "title": "查询结果",
            "text": response_content
        }
    })


def extract_dingtalk_content(payload: dict, msgtype: str) -> str:
    """从钉钉消息中提取消息内容"""
    if msgtype == "text":
        text_data = payload.get("text", {})
        return text_data.get("content", "")
    elif msgtype == "markdown":
        markdown_data = payload.get("markdown", {})
        return markdown_data.get("text", "") or markdown_data.get("title", "")
    else:
        return payload.get("text", {}).get("content", "")


def extract_project_code_from_dingtalk(payload: dict) -> str:
    """从钉钉请求中提取项目名称（不再返回 project_code）"""
    import re

    conversation_title = payload.get("conversationTitle", "")

    # 从会话标题解析项目名称
    # 例如: "项目-ad_monitor-告警群" -> "ad_monitor"
    if conversation_title:
        match = re.search(r'项目[^\w]*([a-zA-Z0-9_-]+)', conversation_title)
        if match:
            return match.group(1)

    # 不再使用 DEFAULT_PROJECT_CODE 配置
    # 用户需要在消息中明确指定项目名称
    return None


async def handle_ds_alert(payload: dict) -> JSONResponse:
    """
    处理 DolphinScheduler 告警

    使用 LangGraph 状态机执行完整处理流程
    """
    # 立即发送原始告警到钉钉
    from ..tools.dingtalk_progress import get_notifier_from_settings
    notifier = get_notifier_from_settings()

    # 发送原始JSON
    import json as json_module
    raw_json_str = json_module.dumps(payload, indent=2, ensure_ascii=False)
    notifier.send_text(f"[原始告警]\n{raw_json_str}")

    # 解析 DolphinScheduler 的 alerts 字段
    if "alerts" in payload:
        alerts_str = payload.get("alerts", "")
        import json
        alerts_list = json.loads(alerts_str)
        # 处理每个告警
        results = []
        for alert in alerts_list:
            # 转换字段名以匹配 Agent 预期格式
            normalized = {
                "projectCode": alert.get("projectCode", 0),
                "processDefinitionCode": alert.get("processDefinitionCode", 0),
                "processInstanceId": alert.get("processId", 0),
                "taskCode": alert.get("taskCode", 0),
                "taskInstanceId": alert.get("taskInstanceId", 0),
                "taskType": alert.get("taskType", "UNKNOWN"),
                "state": alert.get("taskState", "FAILURE"),
                "host": alert.get("taskHost"),
                "projectName": alert.get("projectName"),
                "processName": alert.get("processName"),
                "taskName": alert.get("taskName"),
                "workerGroup": alert.get("workerGroup"),
                "logPath": alert.get("logPath"),
                "taskEndTime": alert.get("taskEndTime"),
            }
            print(f"[webhook] Normalized alert: {normalized}")

            # Execute LangGraph workflow
            result = workflow.run(normalized)
            results.append({
                "project_valid": result.get("project_valid"),
                "risk_level": result.get("risk_level"),
                "approval_required": result.get("approval_required"),
                "execution_success": result.get("execution_success"),
            })

        # 返回所有告警的处理结果
        return JSONResponse(content={
            "status": "processed",
            "count": len(results),
            "results": results,
        })

    # 如果没有 alerts 字段，直接处理
    result = workflow.run(payload)
    return JSONResponse(content={
        "status": "processed",
        "project_valid": result.get("project_valid"),
        "risk_level": result.get("risk_level"),
        "approval_required": result.get("approval_required"),
        "execution_success": result.get("execution_success"),
    })


@app.post("/chat")
async def chat_message(request: ChatRequest):
    """
    处理对话消息

    支持的意图:
    - 运行工作流
    - 补数
    - 查询状态
    - 查看日志
    - 恢复失败
    - 血缘分析
    """
    try:
        # 对话请求暂时不使用工作流，保持原有逻辑
        from ..dispatcher import dispatch_request
        payload = {
            "message": request.message,
            "user_id": request.user_id,
            "project_code": request.project_code,
        }
        result = dispatch_request(payload)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    提交知识库反馈

    用于确认或拒绝 Agent 生成的建议
    """
    try:
        success = knowledge_manager.confirm(
            request.entry_id,
            request.feedback,
            request.human_suggestion,
        )

        if success:
            return JSONResponse(content={
                "status": "success",
                "message": "反馈已提交",
            })
        else:
            raise HTTPException(status_code=404, detail="知识条目不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/approval")
async def approval_callback(request: Request):
    """
    处理审批回调（钉钉按钮点击）

    URL 参数:
    - id: 审批请求 ID
    - action: allow / deny / allow_all

    返回 HTML 页面显示结果
    """
    from fastapi.responses import HTMLResponse

    try:
        approval_id = request.query_params.get("id", "")
        action = request.query_params.get("action", "")

        if not approval_id or not action:
            return HTMLResponse(content="<h1>错误：缺少参数</h1><p>需要 id 和 action 参数</p>", status_code=400)

        if action not in ["allow", "deny"]:
            return HTMLResponse(content=f"<h1>错误：无效操作</h1><p>action 必须是 allow 或 deny</p>", status_code=400)

        # 更新审批状态
        if action == "allow":
            approval_status = "approved"
        elif action == "deny":
            approval_status = "rejected"

        success = approval_tool.update_status(approval_id, approval_status)

        # 返回 HTML 结果页面
        if action == "allow":
            html = """
            <html>
            <head><title>审批结果</title></head>
            <body style="font-family: Arial; padding: 20px;">
                <h1 style="color: green;">✅ 已允许</h1>
                <p>Agent 将执行此操作。</p>
                <p>你可以关闭此页面。</p>
            </body>
            </html>
            """
        elif action == "deny":
            html = """
            <html>
            <head><title>审批结果</title></head>
            <body style="font-family: Arial; padding: 20px;">
                <h1 style="color: red;">❌ 已拒绝</h1>
                <p>Agent 将不会执行此操作。</p>
                <p>你可以关闭此页面。</p>
            </body>
            </html>
            """

        # 尝试继续工作流
        approval_request = approval_tool.get_request(approval_id)
        if approval_request and approval_request.workflow_state:
            pending_state = approval_request.workflow_state
            pending_state["approval_status"] = approval_status
            workflow.continue_from_approval(pending_state, approval_status)

        return HTMLResponse(content=html)

    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(e)}</p>", status_code=500)


@app.get("/approval/{request_id}")
async def get_approval(request_id: str, action: Optional[str] = None):
    """
    处理审批回调

    URL 参数:
    - request_id: 审批请求 ID
    - action: approve 或 reject

    继续执行工作流:
    - approve: 继续执行
    - reject: 通知拒绝并结束
    """
    try:
        if not action:
            # 返回审批详情
            request = approval_tool.get_request(request_id)
            if request:
                return JSONResponse(content={
                    "status": "success",
                    "request": {
                        "request_id": request.request_id,
                        "status": request.status,
                        "created_at": request.created_at,
                        "expires_at": request.expires_at,
                        "workflow_state": request.workflow_state,
                    }
                })
            else:
                raise HTTPException(status_code=404, detail="审批请求不存在")

        if action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'reject'")

        # 更新审批状态
        approval_status = "approved" if action == "approve" else "rejected"
        success = approval_tool.update_status(request_id, approval_status)

        if not success:
            raise HTTPException(status_code=400, detail="审批请求已处理或不存在")

        # 获取 pending state 并继续工作流
        request = approval_tool.get_request(request_id)
        if request and request.workflow_state:
            # 继续执行工作流
            pending_state = request.workflow_state
            pending_state["approval_status"] = approval_status
            result = workflow.continue_from_approval(pending_state, approval_status)

            return JSONResponse(content={
                "status": "processed",
                "request_id": request_id,
                "action": action,
                "approval_status": approval_status,
                "execution_success": result.get("execution_success"),
            })

        return JSONResponse(content={
            "status": "acknowledged",
            "request_id": request_id,
            "action": action,
            "approval_status": approval_status,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approval/{request_id}")
async def process_approval(request_id: str, body: ApprovalActionRequest):
    """处理审批请求（POST）"""
    try:
        if body.action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="无效的 action")

        approval_status = "approved" if body.action == "approve" else "rejected"
        success = approval_tool.update_status(request_id, approval_status)

        if not success:
            raise HTTPException(status_code=400, detail="审批请求已处理或不存在")

        # 获取 pending state 并继续工作流
        request = approval_tool.get_request(request_id)
        if request and request.workflow_state:
            pending_state = request.workflow_state
            pending_state["approval_status"] = approval_status
            result = workflow.continue_from_approval(pending_state, approval_status)

            return JSONResponse(content={
                "status": "processed",
                "request_id": request_id,
                "action": body.action,
                "approval_status": approval_status,
                "execution_success": result.get("execution_success"),
            })

        return JSONResponse(content={
            "status": "acknowledged",
            "request_id": request_id,
            "action": body.action,
            "approval_status": approval_status,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """
    健康检查

    返回服务状态和时间戳
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "workflow": "LangGraph",
    }


# ============ 图谱 API ============

@app.get("/graph/viewer")
async def graph_viewer():
    """图谱 HTML 可视化页面"""
    from fastapi.responses import FileResponse
    graph_dir = os.environ.get("GRAPH_STORAGE_PATH", "data/graph")
    viewer_path = os.path.join(graph_dir, "graph_viewer.html")
    if os.path.exists(viewer_path):
        return FileResponse(viewer_path)
    return HTMLResponse(content="<h1>图谱未生成</h1><p>请先执行图谱扫描: POST /graph/scan</p>")


@app.get("/graph/data")
async def get_graph_data(project_code: Optional[str] = None):
    """获取图谱数据 JSON"""
    import json
    graph_dir = os.environ.get("GRAPH_STORAGE_PATH", "data/graph")

    # 查找图谱文件
    if project_code:
        graph_file = os.path.join(graph_dir, f"{project_code}_graph.json")
    else:
        # 返回第一个找到的图谱
        import glob
        graph_files = glob.glob(os.path.join(graph_dir, "*_graph.json"))
        if graph_files:
            graph_file = graph_files[0]
        else:
            return JSONResponse(content={"error": "No graph data found"})

    if os.path.exists(graph_file):
        with open(graph_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)

    return JSONResponse(content={"error": f"Graph not found for project {project_code}"})


@app.post("/graph/scan")
async def scan_graph(project_code: Optional[str] = None):
    """
    扫描项目图谱

    Args:
        project_code: 项目编码（可选，不传则扫描所有配置的项目）

    Returns:
        扫描结果统计
    """
    from ..graph.scanner import GraphScanner
    from ..graph.storage import GraphStorage
    from ..config.projects import projects_registry

    # 配置
    graph_dir = os.environ.get("GRAPH_STORAGE_PATH", "data/graph")
    code_root = os.environ.get("CODE_ROOT_PATH", "/opt/spark-etl")
    ds_api_url = settings.DS_API_URL
    ds_api_token = settings.DS_API_TOKEN

    # 初始化
    storage = GraphStorage(graph_dir)
    scanner = GraphScanner(storage, code_root)

    results = []

    if project_code:
        # 扫描单个项目
        project_config = projects_registry.get_by_code(project_code)
        if not project_config:
            return JSONResponse(content={"error": f"Project {project_code} not found"})

        result = scanner.scan_project(
            project_code=project_code,
            project_name=project_config.name,
            ds_api_url=project_config.ds_api_url or ds_api_url,
            ds_api_token=ds_api_token,
        )
        results.append({"project": project_config.name, **result})
    else:
        # 扫描所有配置的项目
        for project in projects_registry.projects:
            try:
                result = scanner.scan_project(
                    project_code=project.code,
                    project_name=project.name,
                    ds_api_url=project.ds_api_url or ds_api_url,
                    ds_api_token=ds_api_token,
                )
                results.append({"project": project.name, **result})
            except Exception as e:
                results.append({"project": project.name, "error": str(e)})

    # 生成 graph_data.js 用于 HTML 可视化
    generate_graph_js(graph_dir)

    return JSONResponse(content={
        "status": "success",
        "scanned_at": datetime.now().isoformat(),
        "results": results,
    })


def generate_graph_js(graph_dir: str):
    """生成 graph_data.js 文件用于 HTML 可视化"""
    import json
    import glob

    graph_files = glob.glob(os.path.join(graph_dir, "*_graph.json"))
    if not graph_files:
        return

    # 合并所有图谱数据
    all_workflows = []
    all_tasks = []
    all_tables = []
    all_classes = []
    all_edges = {
        "workflow_contains_task": [],
        "task_depends_task": [],
        "workflow_calls_subworkflow": [],
        "workflow_depends_workflow": [],
        "task_consumes_table": [],
        "task_produces_table": [],
        "class_maps_to_task": [],
    }

    for graph_file in graph_files:
        with open(graph_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", {})
        edges = data.get("edges", {})

        all_workflows.extend(nodes.get("workflows", []))
        all_tasks.extend(nodes.get("tasks", []))
        all_tables.extend(nodes.get("tables", []))
        all_classes.extend(nodes.get("classes", []))

        for key in all_edges:
            all_edges[key].extend(edges.get(key, []))

    # 写入 graph_data.js
    graph_data = {
        "nodes": {
            "workflows": all_workflows,
            "tasks": all_tasks,
            "tables": all_tables,
            "classes": all_classes,
        },
        "edges": all_edges,
    }

    js_content = f"const graphData = {json.dumps(graph_data, ensure_ascii=False)};"

    js_file = os.path.join(graph_dir, "graph_data.js")
    with open(js_file, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"[graph] Generated graph_data.js with {len(all_workflows)} workflows, {len(all_tasks)} tasks")


@app.get("/graph/projects")
async def list_graph_projects():
    """列出已扫描的项目"""
    import glob
    graph_dir = os.environ.get("GRAPH_STORAGE_PATH", "data/graph")
    graph_files = glob.glob(os.path.join(graph_dir, "*_graph.json"))

    projects = []
    for f in graph_files:
        # 提取项目编码
        import os
        filename = os.path.basename(f)
        project_code = filename.replace("_graph.json", "")

        # 获取扫描时间
        import json
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            scanned_at = data.get("scanned_at", "unknown")
            project_name = data.get("project_name", project_code)

        projects.append({
            "code": project_code,
            "name": project_name,
            "scanned_at": scanned_at,
            "file": filename,
        })

    return JSONResponse(content={"projects": projects})


def run_server():
    """启动 API 服务"""
    import uvicorn
    from ..config import settings

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
    )


__all__ = ["app", "run_server", "workflow"]