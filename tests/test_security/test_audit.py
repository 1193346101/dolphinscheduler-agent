# tests/test_security/test_audit.py

"""
AuditLogger 审计日志测试
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.security.audit import AuditRecord, AuditLogger


class TestAuditRecord:
    """AuditRecord 数据类测试"""

    def test_audit_record_dataclass(self):
        """测试 AuditRecord 数据类创建"""
        record = AuditRecord(
            timestamp="2024-01-15T10:30:00",
            operation_type="dsctl",
            operation_detail="workflow list",
            user="admin",
            result="success",
            result_detail="",
            risk_level="LOW",
            source_ip="192.168.1.100",
            project_code=12345,
            workflow_code=67890,
            duration_ms=150
        )
        assert record.timestamp == "2024-01-15T10:30:00"
        assert record.operation_type == "dsctl"
        assert record.operation_detail == "workflow list"
        assert record.user == "admin"
        assert record.result == "success"
        assert record.result_detail == ""
        assert record.risk_level == "LOW"
        assert record.source_ip == "192.168.1.100"
        assert record.project_code == 12345
        assert record.workflow_code == 67890
        assert record.duration_ms == 150


class TestAuditLoggerInit:
    """AuditLogger 初始化测试"""

    def test_audit_logger_init_creates_dir(self):
        """测试初始化创建目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "audit_logs")
            assert not os.path.exists(log_dir)

            logger = AuditLogger(log_dir=log_dir)

            assert os.path.exists(log_dir)
            assert logger.log_dir == Path(log_dir)


class TestAuditLoggerLog:
    """AuditLogger 日志记录测试"""

    def test_audit_logger_log(self):
        """测试记录审计日志并检查文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            logger.log(
                operation_type="dsctl",
                operation_detail="workflow list",
                result="success",
                user="admin",
                source_ip="192.168.1.100"
            )

            # 检查文件存在
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = Path(tmpdir) / f"{today}.json"
            assert log_file.exists()

            # 读取并验证内容
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                assert len(lines) == 1

                record = json.loads(lines[0])
                assert record["operation_type"] == "dsctl"
                assert record["operation_detail"] == "workflow list"
                assert record["result"] == "success"
                assert record["user"] == "admin"
                assert record["source_ip"] == "192.168.1.100"
                assert record["risk_level"] == "LOW"
                # timestamp should be valid ISO format
                datetime.fromisoformat(record["timestamp"])


class TestAuditLoggerLogBlocked:
    """AuditLogger 拦截日志测试"""

    def test_audit_logger_log_blocked(self):
        """测试记录拦截日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            logger.log_blocked(
                operation_type="dsctl",
                operation_detail="workflow delete 123",
                reason="delete operation is blocked",
                risk_level="CRITICAL"
            )

            # 读取并验证
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = Path(tmpdir) / f"{today}.json"
            with open(log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            assert record["result"] == "blocked"
            assert record["result_detail"] == "delete operation is blocked"
            assert record["risk_level"] == "CRITICAL"


class TestAuditLoggerLogSuccess:
    """AuditLogger 成功日志测试"""

    def test_audit_logger_log_success(self):
        """测试记录成功日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            logger.log_success(
                operation_type="http",
                operation_detail="GET /api/workflows",
                risk_level="LOW",
                duration_ms=200,
                user="test_user"
            )

            # 读取并验证
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = Path(tmpdir) / f"{today}.json"
            with open(log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            assert record["result"] == "success"
            assert record["risk_level"] == "LOW"
            assert record["duration_ms"] == 200
            assert record["user"] == "test_user"


class TestAuditLoggerTruncate:
    """AuditLogger 截断测试"""

    def test_audit_logger_truncates_result_detail(self):
        """测试截断超过500字符的详情"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            # 创建超过500字符的详情
            long_detail = "x" * 600

            logger.log(
                operation_type="dsctl",
                operation_detail="test operation",
                result="failed",
                result_detail=long_detail
            )

            # 读取并验证
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = Path(tmpdir) / f"{today}.json"
            with open(log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            # 应该被截断到500字符
            assert len(record["result_detail"]) == 500
            assert record["result_detail"] == "x" * 500