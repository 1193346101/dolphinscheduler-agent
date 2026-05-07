"""
ApprovalTool 测试
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from src.tools.approval_tool import ApprovalTool, ApprovalRequest
from src.workflow.state import create_initial_state


class TestApprovalTool:

    def test_init_with_data_dir(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            assert tool.data_dir == tmpdir

    def test_create_request(self):
        """测试创建审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            request_id = tool.create_request(state, timeout_minutes=30)

            assert request_id is not None
            assert len(request_id) == 36  # UUID 格式

    def test_get_request(self):
        """测试获取审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            request_id = tool.create_request(state)
            request = tool.get_request(request_id)

            assert request is not None
            assert request.status == "pending"

    def test_update_status_approved(self):
        """测试更新状态为已批准"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            request_id = tool.create_request(state)
            result = tool.update_status(request_id, "approved")

            assert result is True
            request = tool.get_request(request_id)
            assert request.status == "approved"

    def test_update_status_rejected(self):
        """测试更新状态为已拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            request_id = tool.create_request(state)
            result = tool.update_status(request_id, "rejected")

            assert result is True
            request = tool.get_request(request_id)
            assert request.status == "rejected"

    def test_update_status_already_processed(self):
        """测试已处理请求不能再次更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            request_id = tool.create_request(state)
            tool.update_status(request_id, "approved")

            # 再次更新应该失败
            result = tool.update_status(request_id, "rejected")
            assert result is False

    def test_check_expired(self):
        """测试检查过期请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "project_code": "123",
                "workflow_code": "456",
                "task_code": "789",
                "task_type": "SPARK",
            })

            # 创建一个已过期的请求
            request_id = tool.create_request(state, timeout_minutes=-1)

            expired = tool.check_expired()

            assert request_id in expired

    def test_get_request_not_found(self):
        """测试获取不存在的请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            request = tool.get_request("nonexistent-id")

            assert request is None