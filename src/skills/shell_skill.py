"""
Shell Skill - Shell 任务错误分析

○ 不是 Agent，使用预定义规则
○ 可自动修复: 命令拼写错误
"""

import re
from typing import Optional
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .base import BaseSkill


class ShellSkill(BaseSkill):
    """
    Shell 任务分析 Skill

    常见错误类型:
    - syntax_error: Shell 语法错误
    - command_not_found: 命令不存在（可能是拼写错误）
    - permission_denied: 权限不足
    - no_such_file: 文件不存在
    """

    skill_name = "shell"
    task_types = ["SHELL"]

    # 预定义的错误模式
    error_patterns = {
        "syntax_error": "syntax error",
        "unexpected_token": "unexpected token",
        "command_not_found": "command not found",
        "permission_denied": "Permission denied",
        "no_such_file": "No such file or directory",
        "directory_not_exist": "cannot access",
        "variable_unset": "parameter null or not set",
    }

    # 预定义的建议模板
    suggestion_templates = {
        "syntax_error": "检查 Shell 脚本语法，特别是引号、括号和分号",
        "unexpected_token": "检查脚本中是否有未闭合的引号或括号",
        "command_not_found": "检查命令是否安装，或是否是拼写错误",
        "permission_denied": "使用 chmod +x 赋予执行权限",
        "no_such_file": "检查文件路径是否正确",
        "directory_not_exist": "检查目录是否存在",
        "variable_unset": "检查变量是否已定义",
    }

    # 可自动修复的错误类型（仅拼写错误）
    auto_fixable_errors = ["command_not_found"]

    # 常见命令拼写错误映射
    common_spell_errors = {
        "giit": "git",
        "gti": "git",
        "gut": "git",
        "pyton": "python",
        "pyhton": "python",
        "pthon": "python",
        "npmi": "npm",
        "npn": "npm",
        "catt": "cat",
        "cta": "cat",
        "lsr": "ls",
        "sl": "ls",
        "cdl": "cd",
        "dc": "cd",
        "mdkir": "mkdir",
        "mkdr": "mkdir",
        "ech": "echo",
        "ecoh": "echo",
        "ehco": "echo",
    }

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """使用预定义规则分析日志"""
        for error_type, pattern in self.error_patterns.items():
            if pattern in log_content:
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=self._extract_error_message(log_content, pattern),
                    matched_pattern=pattern,
                    can_auto_fix=error_type in self.auto_fixable_errors,
                    confidence=0.85,
                )

        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            can_auto_fix=False,
            confidence=0.5,
        )

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if pattern in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                return "\n".join(lines[start:end])
        return pattern

    def _extract_wrong_command(self, error_message: str) -> Optional[str]:
        """提取错误的命令"""
        # 格式1: "command not found: xxx" (某些 shell)
        pattern1 = r"command not found:\s+(\w+)"
        match = re.search(pattern1, error_message)
        if match:
            return match.group(1)

        # 格式2: "xxx: command not found" (bash 标准)
        pattern2 = r"(\w+):\s+command not found"
        match = re.search(pattern2, error_message)
        if match:
            return match.group(1)

        return None

    def can_auto_fix(self, analysis: ErrorAnalysis) -> bool:
        """判断是否可以自动修复（仅拼写错误）"""
        if analysis.error_type != "command_not_found":
            return False

        wrong_cmd = self._extract_wrong_command(analysis.error_message)
        if wrong_cmd and wrong_cmd in self.common_spell_errors:
            return True
        return False

    def _build_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """构建自动修复动作（拼写修正）"""
        wrong_cmd = self._extract_wrong_command(analysis.error_message)
        if wrong_cmd and wrong_cmd in self.common_spell_errors:
            correct_cmd = self.common_spell_errors[wrong_cmd]
            return AutoFixAction(
                action_type="modify_script",
                script_changes={wrong_cmd: correct_cmd},
                need_recover=True,
            )
        return None


__all__ = ["ShellSkill"]