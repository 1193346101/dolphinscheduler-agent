"""
报告 API - 提供错误分析报告查看服务

支持两种方式查看报告：
1. HTML 页面（用户友好）
2. JSON 数据（程序可解析）
"""

from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from ..tools.report_generator import ReportGenerator

# 创建路由
router = APIRouter(prefix="/report", tags=["报告"])

# 报告生成器实例
report_generator = ReportGenerator()


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    workflow: str = Query(..., description="工作流 code"),
    date: str = Query(None, description="日期，格式 YYYY-MM-DD，默认今天"),
    format: str = Query("html", description="返回格式：html 或 json")
):
    """
    获取错误分析报告

    Args:
        report_id: 报告 ID
        workflow: 工作流 code
        date: 日期（可选）
        format: 返回格式（html 或 json）

    Returns:
        HTML 页面或 JSON 数据
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # 查找报告路径
    report_path = report_generator.get_report_path(report_id, workflow, date)

    if not report_path:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")

    # 根据格式返回不同内容
    if format == "json":
        json_path = Path(report_path) / "report.json"
        if not json_path.exists():
            raise HTTPException(status_code=404, detail="JSON 报告文件不存在")
        return JSONResponse(content=json_path.read_text(encoding="utf-8"))

    else:  # html
        html_path = Path(report_path) / "report.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="HTML 报告文件不存在")
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@router.get("/{report_id}/html")
async def get_report_html(
    report_id: str,
    workflow: str = Query(..., description="工作流 code"),
    date: str = Query(None, description="日期")
):
    """
    获取 HTML 格式的报告（直接返回 HTML 页面）
    """
    return await get_report(report_id, workflow, date, "html")


@router.get("/{report_id}/json")
async def get_report_json(
    report_id: str,
    workflow: str = Query(..., description="工作流 code"),
    date: str = Query(None, description="日期")
):
    """
    获取 JSON 格式的报告（程序可解析）
    """
    return await get_report(report_id, workflow, date, "json")


@router.get("/list")
async def list_reports(
    workflow: str = Query(None, description="工作流 code（可选）"),
    date: str = Query(None, description="日期（可选）"),
    limit: int = Query(20, description="返回数量限制")
):
    """
    列出报告

    Args:
        workflow: 工作流 code（可选，不指定则列出所有）
        date: 日期（可选，不指定则列出今天）
        limit: 返回数量限制

    Returns:
        报告列表
    """
    report_dir = Path(report_generator.report_dir)

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    date_dir = report_dir / date
    if not date_dir.exists():
        return {"reports": [], "total": 0}

    reports = []

    # 遍历工作流目录
    for workflow_dir in date_dir.iterdir():
        if not workflow_dir.is_dir():
            continue

        # 如果指定了 workflow，只返回该工作流的报告
        if workflow and workflow_dir.name != workflow:
            continue

        # 遍历报告目录
        for report_dir_item in workflow_dir.iterdir():
            if not report_dir_item.is_dir():
                continue

            # 检查报告文件是否存在
            json_path = report_dir_item / "report.json"
            if json_path.exists():
                try:
                    import json
                    report_data = json.loads(json_path.read_text(encoding="utf-8"))
                    basic_info = report_data.get("basic_info", {})

                    reports.append({
                        "report_id": report_dir_item.name,
                        "workflow_code": workflow_dir.name,
                        "task_name": basic_info.get("task_name", ""),
                        "task_type": basic_info.get("task_type", ""),
                        "report_time": basic_info.get("report_time", ""),
                        "risk_level": report_data.get("risk_assessment", {}).get("risk_level", ""),
                    })
                except Exception:
                    pass

        if len(reports) >= limit:
            break

    return {
        "reports": reports[:limit],
        "total": len(reports),
        "date": date,
    }


__all__ = ["router"]