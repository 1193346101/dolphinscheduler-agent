# tests/test_security/test_guard.py

"""
CommandGuard 安全拦截器测试
"""

import pytest
from src.security.guard import GuardResult, CommandGuard


class TestGuardResult:
    """GuardResult 数据类测试"""

    def test_guard_result_dataclass(self):
        """测试 GuardResult 数据类创建"""
        result = GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="dsctl",
            operation_detail="workflow list",
            risk_level="LOW"
        )
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "dsctl"
        assert result.operation_detail == "workflow list"
        assert result.risk_level == "LOW"


class TestCheckCliCommand:
    """CLI 命令检查测试"""

    def test_check_cli_command_allowed(self):
        """测试允许的命令"""
        guard = CommandGuard()
        result = guard.check_cli_command(["workflow", "list"])
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "dsctl"
        assert result.operation_detail == "workflow list"
        assert result.risk_level == "LOW"

    def test_check_cli_command_blocked_delete(self):
        """测试禁止 delete 命令"""
        guard = CommandGuard()
        result = guard.check_cli_command(["workflow", "delete", "123"])
        assert result.allowed is False
        assert result.blocked is True
        assert "delete" in result.reason
        assert result.operation_type == "dsctl"
        assert result.risk_level == "CRITICAL"

    def test_check_cli_command_blocked_remove(self):
        """测试禁止 remove 命令"""
        guard = CommandGuard()
        result = guard.check_cli_command(["worktree", "remove", "test"])
        assert result.allowed is False
        assert result.blocked is True
        assert "remove" in result.reason
        assert result.operation_type == "dsctl"
        assert result.risk_level == "CRITICAL"

    def test_check_cli_command_high_risk_recover(self):
        """测试 recover 为 HIGH 风险"""
        guard = CommandGuard()
        result = guard.check_cli_command(["workflow", "recover", "123"])
        assert result.allowed is True
        assert result.blocked is False
        assert result.risk_level == "HIGH"

    def test_check_cli_command_medium_risk_edit(self):
        """测试 edit 为 MEDIUM 风险"""
        guard = CommandGuard()
        result = guard.check_cli_command(["workflow", "edit", "123"])
        assert result.allowed is True
        assert result.blocked is False
        assert result.risk_level == "MEDIUM"


class TestCheckHttpRequest:
    """HTTP 请求检查测试"""

    def test_check_http_request_allowed_get(self):
        """测试 GET 方法允许"""
        guard = CommandGuard()
        result = guard.check_http_request("GET", "http://example.com/api/workflows")
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "http"
        assert result.risk_level == "LOW"

    def test_check_http_request_blocked_post(self):
        """测试 POST 方法禁止"""
        guard = CommandGuard()
        result = guard.check_http_request("POST", "http://example.com/api/workflows")
        assert result.allowed is False
        assert result.blocked is True
        assert "POST" in result.reason
        assert result.operation_type == "http"
        assert result.risk_level == "CRITICAL"

    def test_check_http_request_blocked_delete(self):
        """测试 DELETE 方法禁止"""
        guard = CommandGuard()
        result = guard.check_http_request("DELETE", "http://example.com/api/workflows/123")
        assert result.allowed is False
        assert result.blocked is True
        assert "DELETE" in result.reason
        assert result.operation_type == "http"
        assert result.risk_level == "CRITICAL"


class TestCheckOssCommand:
    """OSS 命令检查测试"""

    def test_check_oss_command_allowed_ls(self):
        """测试 ls 操作允许"""
        guard = CommandGuard()
        result = guard.check_oss_command(["ls", "oss://bucket/path/"])
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "ossutil"
        assert result.risk_level == "LOW"

    def test_check_oss_command_allowed_stat(self):
        """测试 stat 操作允许"""
        guard = CommandGuard()
        result = guard.check_oss_command(["stat", "oss://bucket/file.txt"])
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "ossutil"
        assert result.risk_level == "LOW"

    def test_check_oss_command_blocked_rm(self):
        """测试 rm 操作禁止"""
        guard = CommandGuard()
        result = guard.check_oss_command(["rm", "oss://bucket/file.txt"])
        assert result.allowed is False
        assert result.blocked is True
        assert "rm" in result.reason
        assert result.operation_type == "ossutil"
        assert result.risk_level == "CRITICAL"

    def test_check_oss_command_blocked_cp(self):
        """测试 cp 操作禁止"""
        guard = CommandGuard()
        result = guard.check_oss_command(["cp", "local.txt", "oss://bucket/file.txt"])
        assert result.allowed is False
        assert result.blocked is True
        assert "cp" in result.reason
        assert result.operation_type == "ossutil"
        assert result.risk_level == "CRITICAL"

    def test_check_oss_command_blocked_sync(self):
        """测试 sync 操作禁止"""
        guard = CommandGuard()
        result = guard.check_oss_command(["sync", "local/", "oss://bucket/path/"])
        assert result.allowed is False
        assert result.blocked is True
        assert "sync" in result.reason
        assert result.operation_type == "ossutil"
        assert result.risk_level == "CRITICAL"

    def test_check_oss_command_empty_args(self):
        """测试空参数允许"""
        guard = CommandGuard()
        result = guard.check_oss_command([])
        assert result.allowed is True
        assert result.blocked is False
        assert result.reason == ""
        assert result.operation_type == "ossutil"
        assert result.risk_level == "LOW"