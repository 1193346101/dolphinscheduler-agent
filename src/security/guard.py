# src/security/guard.py

"""
命令安全拦截器

检查 CLI 命令、HTTP 请求、OSS 操作是否允许执行
"""

from dataclasses import dataclass
from typing import List

from .constants import DS_FORBIDDEN_COMMANDS, OSS_FORBIDDEN_OPERATIONS, HTTP_FORBIDDEN_METHODS


@dataclass
class GuardResult:
    """安全检查结果"""
    allowed: bool                      # 是否允许执行
    blocked: bool                      # 是否被拦截
    reason: str                        # 拦截原因
    operation_type: str                # dsctl/ossutil/http
    operation_detail: str              # 命令详情
    risk_level: str = "LOW"            # LOW/MEDIUM/HIGH/CRITICAL


class CommandGuard:
    """命令安全拦截器"""

    def check_cli_command(self, args: List[str]) -> GuardResult:
        """
        检查 CLI 命令

        Args:
            args: 命令参数列表，如 ["workflow", "delete", "123"]

        Returns:
            GuardResult: 安全检查结果
        """
        if not args:
            return GuardResult(
                allowed=True,
                blocked=False,
                reason="",
                operation_type="dsctl",
                operation_detail="",
                risk_level="LOW"
            )

        operation_detail = " ".join(args)

        # 检查禁止命令（delete, remove）
        for arg in args:
            arg_lower = arg.lower()
            if arg_lower in DS_FORBIDDEN_COMMANDS:
                return GuardResult(
                    allowed=False,
                    blocked=True,
                    reason=f"命令 '{arg}' 在禁止列表中",
                    operation_type="dsctl",
                    operation_detail=operation_detail,
                    risk_level="CRITICAL"
                )

        # 风险评估
        risk_level = "LOW"
        for arg in args:
            arg_lower = arg.lower()
            if arg_lower == "recover":
                risk_level = "HIGH"
                break
            elif arg_lower in ("edit", "modify"):
                risk_level = "MEDIUM"
                break

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="dsctl",
            operation_detail=operation_detail,
            risk_level=risk_level
        )

    def check_http_request(self, method: str, url: str) -> GuardResult:
        """
        检查 HTTP 请求

        Args:
            method: HTTP 方法，如 GET, POST
            url: 请求 URL

        Returns:
            GuardResult: 安全检查结果
        """
        method_upper = method.upper()

        # 检查禁止方法
        if method_upper in HTTP_FORBIDDEN_METHODS:
            return GuardResult(
                allowed=False,
                blocked=True,
                reason=f"HTTP 方法 '{method_upper}' 在禁止列表中",
                operation_type="http",
                operation_detail=f"{method_upper} {url}",
                risk_level="CRITICAL"
            )

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="http",
            operation_detail=f"{method_upper} {url}",
            risk_level="LOW"
        )

    def check_oss_command(self, args: List[str]) -> GuardResult:
        """
        检查 OSS 命令

        Args:
            args: OSS 命令参数列表，如 ["rm", "oss://bucket/key"]

        Returns:
            GuardResult: 安全检查结果
        """
        if not args:
            return GuardResult(
                allowed=True,
                blocked=False,
                reason="",
                operation_type="ossutil",
                operation_detail="",
                risk_level="LOW"
            )

        operation_detail = " ".join(args)

        # 第一个参数通常是操作类型
        operation = args[0].lower()
        if operation in OSS_FORBIDDEN_OPERATIONS:
            return GuardResult(
                allowed=False,
                blocked=True,
                reason=f"ossutil 操作 '{args[0]}' 在禁止列表中",
                operation_type="ossutil",
                operation_detail=operation_detail,
                risk_level="CRITICAL"
            )

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="ossutil",
            operation_detail=operation_detail,
            risk_level="LOW"
        )