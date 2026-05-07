"""
ApprovalTool - 审批管理工具

管理审批请求的创建、存储、状态更新和过期检查
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ApprovalRequest:
    """审批请求"""
    request_id: str
    workflow_state: Dict
    created_at: str
    expires_at: str
    status: str  # pending, approved, rejected, timeout
    dingtalk_message_id: Optional[str] = None


class ApprovalTool:
    """
    审批管理工具

    使用 JSON 文件存储审批请求
    """

    DEFAULT_DATA_DIR = "data/approvals"

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        """
        初始化

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def create_request(
        self,
        state: Dict,
        timeout_minutes: int = 30,
        dingtalk_message_id: Optional[str] = None
    ) -> str:
        """
        创建审批请求

        Args:
            state: LangGraph 状态快照
            timeout_minutes: 超时时间（分钟）
            dingtalk_message_id: 钉钉消息 ID

        Returns:
            request_id
        """
        request_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=timeout_minutes)

        request = ApprovalRequest(
            request_id=request_id,
            workflow_state=state,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="pending",
            dingtalk_message_id=dingtalk_message_id
        )

        # 存储
        self._save_request(request)

        return request_id

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        获取审批请求

        Args:
            request_id: 请求 ID

        Returns:
            ApprovalRequest 或 None
        """
        path = self._get_request_path(request_id)

        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ApprovalRequest(**data)

    def update_status(self, request_id: str, status: str) -> bool:
        """
        更新审批状态

        Args:
            request_id: 请求 ID
            status: 新状态 (approved, rejected, timeout)

        Returns:
            是否成功
        """
        request = self.get_request(request_id)

        if not request:
            return False

        if request.status != "pending":
            return False  # 只能更新 pending 状态

        request.status = status
        self._save_request(request)

        return True

    def check_expired(self) -> List[str]:
        """
        检查过期请求

        Returns:
            过期的请求 ID 列表
        """
        expired = []
        now = datetime.now()

        for filename in os.listdir(self.data_dir):
            if not filename.endswith(".json"):
                continue

            request_id = filename[:-5]
            request = self.get_request(request_id)

            if request and request.status == "pending":
                expires_at = datetime.fromisoformat(request.expires_at)
                if now > expires_at:
                    expired.append(request_id)

        return expired

    def _save_request(self, request: ApprovalRequest) -> None:
        """保存请求"""
        path = self._get_request_path(request.request_id)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(request), f, ensure_ascii=False, indent=2)

    def _get_request_path(self, request_id: str) -> str:
        """获取请求文件路径"""
        return os.path.join(self.data_dir, f"{request_id}.json")


__all__ = ["ApprovalTool", "ApprovalRequest"]