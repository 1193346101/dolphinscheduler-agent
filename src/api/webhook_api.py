"""
Webhook API - 接收 DolphinScheduler 告警

使用 LangGraph 状态机处理告警流程
"""

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


# 创建 FastAPI 应用
app = FastAPI(title="DolphinScheduler Agent API")

# 初始化组件
approval_workflow = ApprovalWorkflow()

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
    接收 DolphinScheduler 告警 Webhook

    使用 LangGraph 状态机执行完整处理流程:
    解析告警 -> 验证项目 -> 获取日志 -> 分析错误
    -> 查询知识库 -> 风险评估 -> 审批/自动修复
    -> 钉钉通知 -> 存储结果

    DS 告警格式: {"alerts": "[{\"projectCode\":..., ...}]"}
    其中 alerts 是 JSON 字符串，需要解析
    """
    try:
        payload = await request.json()

        # 打印原始 payload 用于调试
        print(f"[webhook] Received payload: {payload}")

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
                    "taskInstanceId": 0,  # DS webhook 不包含此字段
                    "taskType": alert.get("taskType", "UNKNOWN"),
                    "state": alert.get("taskState", "FAILURE"),
                    "host": alert.get("taskHost"),
                    "projectName": alert.get("projectName"),
                    "processName": alert.get("processName"),
                    "taskName": alert.get("taskName"),
                    "workerGroup": alert.get("workerGroup"),
                    "logPath": alert.get("logPath"),
                    "taskEndTime": alert.get("taskEndTime"),  # 任务结束时间
                }
                # 执行 LangGraph 工作流
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
            from ..security.approval import ApprovalWorkflow
            wf = ApprovalWorkflow()
            req = wf._load_request(request_id)
            if req:
                return JSONResponse(content={"status": "success", "request": req.__dict__})
            else:
                raise HTTPException(status_code=404, detail="审批请求不存在")

        if action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'reject'")

        # 审批状态
        approval_status = "approved" if action == "approve" else "rejected"

        # TODO: 从 ApprovalTool 获取 pending state 并继续工作流
        # pending_state = approval_workflow.get_pending_state(request_id)
        # result = workflow.continue_from_approval(pending_state, approval_status)

        if action == "approve":
            result = approval_workflow.approve(request_id, "user")
        elif action == "reject":
            result = approval_workflow.reject(request_id, "用户拒绝")

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
        if body.action == "approve":
            result = approval_workflow.approve(request_id, body.approver or "user")
            approval_status = "approved"
        elif body.action == "reject":
            result = approval_workflow.reject(request_id, body.reject_reason or "无")
            approval_status = "rejected"
        else:
            raise HTTPException(status_code=400, detail="无效的 action")

        # TODO: 从 ApprovalTool 获取 pending state 并继续工作流
        # pending_state = approval_workflow.get_pending_state(request_id)
        # result = workflow.continue_from_approval(pending_state, approval_status)

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