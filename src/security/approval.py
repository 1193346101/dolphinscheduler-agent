"""
审批流程管理
"""

import json
import os
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

from ..config import settings
from ..integrations.dingtalk import DingTalkNotifier


@dataclass
class ApprovalRequest:
    """审批请求"""

    id: str
    operation_type: str               # modify_config, delete_workflow, etc.
    risk_level: str                   # HIGH, CRITICAL
    content: str                      # 操作内容描述
    impact: str                       # 影响范围

    # 关联信息
    project_code: int
    workflow_code: Optional[int] = None
    task_code: Optional[int] = None
    process_instance_id: Optional[int] = None  # 工作流实例 ID（用于恢复）

    # 状态
    status: str = "pending"           # pending, approved, rejected, expired

    # 时间
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    expires_at: Optional[str] = None

    # 审批人
    approver: Optional[str] = None
    reject_reason: Optional[str] = None


class ApprovalWorkflow:
    """
    审批流程管理

    流程:
    1. 创建审批请求
    2. 发送钉钉/飞书审批通知
    3. 等待审批结果
    4. 执行或取消操作
    """

    def __init__(self):
        self.notifier = DingTalkNotifier()
        self.pending_dir = "logs/approvals"
        os.makedirs(self.pending_dir, exist_ok=True)

    def create_request(
        self,
        operation_type: str,
        risk_level: str,
        content: str,
        impact: str,
        project_code: int,
        workflow_code: Optional[int] = None,
        task_code: Optional[int] = None,
        process_instance_id: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        创建审批请求

        Args:
            operation_type: 操作类型
            risk_level: 风险等级
            content: 操作内容
            impact: 影响范围
            project_code: 项目编码
            workflow_code: 工作流编码
            task_code: 任务编码
            process_instance_id: 工作流实例 ID

        Returns:
            ApprovalRequest
        """
        request_id = f"approval-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        expires_minutes = settings.APPROVAL_TIMEOUT_MINUTES
        expires_at = datetime.now() + timedelta(minutes=expires_minutes)

        request = ApprovalRequest(
            id=request_id,
            operation_type=operation_type,
            risk_level=risk_level,
            content=content,
            impact=impact,
            project_code=project_code,
            workflow_code=workflow_code,
            task_code=task_code,
            process_instance_id=process_instance_id,
            status="pending",
            created_at=datetime.now().isoformat(),
            expires_at=expires_at.isoformat(),
        )

        # 保存请求
        self._save_request(request)

        # 发送通知
        self._send_notification(request)

        return request

    def _save_request(self, request: ApprovalRequest) -> None:
        """保存审批请求"""
        file_path = os.path.join(self.pending_dir, f"{request.id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(request), f, ensure_ascii=False, indent=2)

    def _load_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """加载审批请求"""
        file_path = os.path.join(self.pending_dir, f"{request_id}.json")
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ApprovalRequest(**data)

    def _send_notification(self, request: ApprovalRequest) -> bool:
        """发送审批通知"""
        # 构造审批 URL
        base_url = f"http://{settings.API_HOST}:{settings.API_PORT}"
        approve_url = f"{base_url}/approval/{request.id}?action=approve"
        reject_url = f"{base_url}/approval/{request.id}?action=reject"

        return self.notifier.send_action_card(
            title=f"操作审批请求 - {request.risk_level}",
            text=f"""### 待审批操作

**操作类型**: {request.operation_type}
**风险等级**: {request.risk_level}
**内容**: {request.content}
**影响范围**: {request.impact}

**创建时间**: {request.created_at}
**过期时间**: {request.expires_at}

请确认是否执行此操作。
""",
            buttons=[
                {"title": "批准 ✓", "actionURL": approve_url},
                {"title": "拒绝 ✗", "actionURL": reject_url},
            ],
        )

    def approve(self, request_id: str, approver: str) -> dict:
        """
        批准审批

        Args:
            request_id: 请求 ID
            approver: 审批人

        Returns:
            操作结果
        """
        request = self._load_request(request_id)
        if not request:
            return {"status": "failed", "message": "审批请求不存在"}

        if request.status != "pending":
            return {"status": "failed", "message": f"审批已处理: {request.status}"}

        # 检查是否过期
        if datetime.now() > datetime.fromisoformat(request.expires_at):
            request.status = "expired"
            self._save_request(request)
            return {"status": "failed", "message": "审批已过期"}

        # 执行操作
        result = self._execute_approved_operation(request)

        # 更新状态
        request.status = "approved"
        request.approved_at = datetime.now().isoformat()
        request.approver = approver
        self._save_request(request)

        return {
            "status": "success",
            "message": "审批已批准",
            "execution_result": result,
            "request": asdict(request),
        }

    def reject(self, request_id: str, reject_reason: str) -> dict:
        """拒绝审批"""
        request = self._load_request(request_id)
        if not request:
            return {"status": "failed", "message": "审批请求不存在"}

        if request.status != "pending":
            return {"status": "failed", "message": f"审批已处理: {request.status}"}

        request.status = "rejected"
        request.reject_reason = reject_reason
        self._save_request(request)

        return {
            "status": "success",
            "message": "审批已拒绝",
            "request": asdict(request),
        }

    def _execute_approved_operation(self, request: ApprovalRequest) -> dict:
        """执行已批准的操作"""
        if request.operation_type == "fix_task_failure":
            # 执行任务修复
            from ..integrations.ds_cli import DSCLIClient
            ds_cli = DSCLIClient()

            # 从审批请求中获取修复信息
            # content 格式: "修复任务 xxx 的失败问题\n建议修改: {'ech': 'echo'}"
            content = request.content
            if "建议修改:" in content:
                # 解析脚本修改
                import json
                changes_str = content.split("建议修改:")[-1].strip()
                try:
                    script_changes = json.loads(changes_str.replace("'", "\""))
                except json.JSONDecodeError:
                    script_changes = {}

                if script_changes:
                    # 使用 process_instance_update_task_script 直接修改实例中的任务
                    # 保持 process_instance_id 不变，下游依赖不受影响
                    if request.process_instance_id and request.task_code:
                        result = ds_cli.process_instance_update_task_script(
                            request.project_code,
                            request.process_instance_id,
                            request.task_code,
                            script_changes,
                        )

                        if result.success:
                            return {
                                "status": "success",
                                "message": "工作流实例任务脚本已修改并恢复失败任务",
                                "changes": script_changes,
                                "process_instance_id_preserved": True,
                                "process_instance_id": request.process_instance_id,
                            }
                        else:
                            return {
                                "status": "failed",
                                "message": result.error or "任务修改失败",
                            }
                    else:
                        return {
                            "status": "failed",
                            "message": "缺少 process_instance_id 或 task_code",
                        }

            return {
                "status": "pending",
                "message": "无自动修复方案",
            }

        return {
            "status": "pending",
            "message": "等待执行",
        }

    def check_expired(self) -> list[str]:
        """检查并处理过期的审批"""
        expired_ids = []
        now = datetime.now()

        for filename in os.listdir(self.pending_dir):
            if not filename.endswith(".json"):
                continue

            request_id = filename[:-5]
            request = self._load_request(request_id)

            if request and request.status == "pending":
                if now > datetime.fromisoformat(request.expires_at):
                    request.status = "expired"
                    self._save_request(request)
                    expired_ids.append(request_id)

        return expired_ids


# 需要导入 timedelta
from datetime import timedelta


__all__ = ["ApprovalRequest", "ApprovalWorkflow"]