"""
Shell Skill - Shell 任务错误分析专家

Skill 是快速预判器:
- 快速识别常见 Shell 错误模式
- AUTO_FIXABLE: 拼写错误，直接返回修复方案
- KNOWN_NEEDS_LLM: 已知类型（语法错误等），给 LLM 提供提示
- UNKNOWN: 无匹配，完全交给 LLM
"""

import re
from typing import Optional, Dict, Tuple
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .base import BaseSkill


class ShellSkill(BaseSkill):
    """
    Shell 任务分析 Skill
    """

    skill_name = "shell"
    task_types = ["SHELL"]

    # 错误模式: (pattern, category, llm_hint)
    # category: AUTO_FIXABLE / KNOWN_NEEDS_LLM
    # llm_hint: 给 LLM 的分析提示
    error_patterns: Dict[str, Tuple[str, str, str]] = {
        # === 可自动修复 ===
        "command_not_found": (
            "command not found",
            ErrorCategory.AUTO_FIXABLE,
            ""
        ),

        # === 已知类型，需 LLM 分析 ===
        "syntax_error": (
            "syntax error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 语法错误，请分析具体位置和原因（如引号不闭合、括号不匹配等）"
        ),
        "unexpected_eof": (
            "unexpected EOF",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 文件意外结束，通常是引号或括号不闭合导致"
        ),
        "unexpected_eof_quote": (
            "unexpected EOF while looking for matching",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 引号或括号不闭合，请定位具体位置"
        ),
        "unexpected_token": (
            "unexpected token",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 出现意外符号，请分析原因"
        ),
        "unexpected_end": (
            "unexpected end of file",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 文件意外结束，通常是结构不完整"
        ),
        "newline_unexpected": (
            "newline unexpected",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 新行位置错误，请分析语法结构"
        ),

        # === 变量错误 ===
        "variable_unset": (
            "parameter null or not set",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 变量为空或未定义，请分析变量来源和赋值逻辑"
        ),
        "variable_not_found": (
            "variable not found",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 变量未找到，请检查变量定义和使用"
        ),
        "bad_substitution": (
            "bad substitution",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 变量替换语法错误，请检查 ${} 语法"
        ),
        "array_index_error": (
            "array index",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 数组索引错误，请检查数组操作"
        ),

        # === 文件/路径错误 ===
        "no_such_file": (
            "No such file or directory",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 文件或目录不存在，请检查路径是否正确、文件是否存在"
        ),
        "file_not_found": (
            "File not found",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 文件不存在，请检查文件路径"
        ),
        "directory_not_exist": (
            "cannot access",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 无法访问路径，请检查路径和权限"
        ),
        "path_not_found": (
            "path not found",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 路径不存在，请检查路径配置"
        ),

        # === 权限错误 ===
        "permission_denied": (
            "Permission denied",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 权限不足，请分析需要什么权限、如何获取"
        ),
        "access_denied": (
            "Access denied",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 访问被拒绝，请检查权限配置"
        ),
        "cannot_execute": (
            "cannot execute",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 无法执行，可能是权限或文件格式问题"
        ),
        "operation_not_permitted": (
            "Operation not permitted",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 操作不被允许，请检查权限和系统限制"
        ),

        # === 参数/选项错误 ===
        "invalid_option": (
            "invalid option",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 命令参数无效，请检查参数格式和可用选项"
        ),
        "option_requires_arg": (
            "option requires an argument",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 选项需要参数，请检查参数是否缺失"
        ),
        "missing_argument": (
            "missing argument",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 缺少参数，请检查命令参数数量"
        ),
        "extra_argument": (
            "too many arguments",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 参数过多，请检查命令参数数量"
        ),

        # === 管道/重定向错误 ===
        "broken_pipe": (
            "Broken pipe",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 管道断开，请分析管道进程状态"
        ),
        "pipe_failed": (
            "pipe failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 管道创建失败，请检查系统资源"
        ),
        "redirect_error": (
            "cannot redirect",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 重定向失败，请检查输出路径和权限"
        ),
        "input_output_error": (
            "Input/output error",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell I/O 错误，可能是磁盘或文件问题"
        ),

        # === 进程/信号错误 ===
        "process_killed": (
            "Killed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 进程被终止，可能是内存不足或信号终止"
        ),
        "process_terminated": (
            "Terminated",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 进程被终止，请分析终止原因"
        ),
        "segfault": (
            "Segmentation fault",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 程序段错误，通常是代码 bug 或内存问题"
        ),
        "exit_code_error": (
            "exited with",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 命令异常退出，请分析退出原因和退出码"
        ),
        "fork_failed": (
            "fork failed",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 创建子进程失败，可能是系统资源不足"
        ),

        # === 编码/环境错误 ===
        "encoding_error": (
            "encoding",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 编码问题，请检查字符编码设置"
        ),
        "locale_error": (
            "locale",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 语言环境设置问题，请检查 locale 配置"
        ),
        "env_not_found": (
            "environment variable",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 环境变量问题，请检查环境变量是否定义"
        ),
        "home_not_set": (
            "HOME not set",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell HOME 环境变量未设置"
        ),

        # === 资源错误 ===
        "memory_error": (
            "cannot allocate",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 内存分配失败，可能是内存不足"
        ),
        "disk_full": (
            "no space left",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 磁盘空间不足，请清理磁盘或更换路径"
        ),
        "quota_exceeded": (
            "quota exceeded",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 资源配额超限，请检查配额设置"
        ),
        "resource_limit": (
            "too many",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 资源限制，可能是进程或文件数超限"
        ),

        # === 网络/连接错误 ===
        "connection_refused": (
            "Connection refused",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 网络连接被拒绝，请检查目标服务是否运行"
        ),
        "connection_timeout": (
            "Connection timed out",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 网络连接超时，请检查网络状态和超时设置"
        ),
        "host_unreachable": (
            "Host unreachable",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 主机不可达，请检查网络连通性"
        ),
        "network_error": (
            "network unreachable",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell 网络不可达，请检查网络配置"
        ),
        "dns_error": (
            "unknown host",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Shell DNS 解析失败，请检查主机名和 DNS 配置"
        ),

        # === 工具特定错误 ===
        "grep_error": (
            "grep:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "grep 命令错误，请检查 grep 参数和输入"
        ),
        "sed_error": (
            "sed:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "sed 命令错误，请检查 sed 语法和输入"
        ),
        "awk_error": (
            "awk:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "awk 命令错误，请检查 awk 语法和输入"
        ),
        "find_error": (
            "find:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "find 命令错误，请检查 find 参数和路径"
        ),
        "xargs_error": (
            "xargs:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "xargs 命令错误，请检查 xargs 参数和输入"
        ),
        "ssh_error": (
            "ssh:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "ssh 连接错误，请检查 SSH 配置和目标主机"
        ),
        "scp_error": (
            "scp:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "scp 传输错误，请检查 SCP 配置和文件路径"
        ),
        "curl_error": (
            "curl:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "curl 请求错误，请检查 URL 和参数"
        ),
        "wget_error": (
            "wget:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "wget 下载错误，请检查 URL 和网络"
        ),
        "tar_error": (
            "tar:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "tar 命令错误，请检查 tar 参数和文件"
        ),
        "zip_error": (
            "zip:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "zip 命令错误，请检查 zip 参数和文件"
        ),
        "chmod_error": (
            "chmod:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "chmod 命令错误，请检查权限模式和文件"
        ),
        "chown_error": (
            "chown:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "chown 命令错误，请检查用户组和文件"
        ),
        "rm_error": (
            "cannot remove",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "rm 删除失败，请检查文件权限和是否存在"
        ),
        "mv_error": (
            "cannot move",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "mv 移动失败，请检查源和目标路径权限"
        ),
        "cp_error": (
            "cannot copy",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "cp 复制失败，请检查源和目标路径权限"
        ),
        "mkdir_error": (
            "cannot create",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "mkdir 创建失败，请检查路径权限和父目录"
        ),
        "docker_error": (
            "docker:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "Docker 命令错误，请检查 Docker 配置和容器状态"
        ),
        "kubectl_error": (
            "kubectl:",
            ErrorCategory.KNOWN_NEEDS_LLM,
            "kubectl 命令错误，请检查 Kubernetes 配置和资源状态"
        ),
    }

    # 常见命令拼写错误映射
    common_spell_errors = {
        # echo
        "ech": "echo", "ecoh": "echo", "ehco": "echo", "echoh": "echo",
        # git
        "giit": "git", "gti": "git", "gut": "git", "gitt": "git",
        # python
        "pyton": "python", "pyhton": "python", "pthon": "python",
        "pytho": "python", "pythn": "python",
        # pip
        "piip": "pip", "ppi": "pip", "pi": "pip",
        # npm
        "npmi": "npm", "npn": "npm", "nppm": "npm",
        # cat
        "catt": "cat", "cta": "cat", "act": "cat",
        # ls
        "lsr": "ls", "sl": "ls", "lsl": "ls",
        # cd
        "cdl": "cd", "dc": "cd", "cdd": "cd",
        # mkdir
        "mdkir": "mkdir", "mkdr": "mkdir", "mkdi": "mkdir", "mkdri": "mkdir",
        # rm
        "rmm": "rm", "mr": "rm", "rem": "rm",
        # mv
        "mvv": "mv", "vm": "mv",
        # cp
        "cpp": "cp", "pc": "cp", "copy": "cp",
        # grep
        "greep": "grep", "gerp": "grep", "grpe": "grep", "gree": "grep",
        # sed
        "seed": "sed", "sde": "sed", "seedd": "sed",
        # awk
        "akw": "awk", "wak": "awk", "aawk": "awk",
        # find
        "fin": "find", "fnd": "find", "fidn": "find",
        # chmod
        "chomd": "chmod", "chmd": "chmod", "chmodd": "chmod",
        # chown
        "chwon": "chown", "chonw": "chown",
        # tar
        "tarr": "tar", "tra": "tar",
        # curl
        "curlr": "curl", "crul": "curl", "crl": "curl",
        # wget
        "wgett": "wget", "wgt": "wget", "weget": "wget",
        # docker
        "dockr": "docker", "docke": "docker", "dockerr": "docker",
        # kubectl
        "kubctl": "kubectl", "kubect": "kubectl", "kubectll": "kubectl",
        # ssh
        "sssh": "ssh", "ss": "ssh",
        # scp
        "sccp": "scp", "spp": "scp",
    }

    # 常见参数拼写错误
    common_arg_errors = {
        "-hlep": "-help", "-hlepme": "-help",
        "-versoin": "-version", "-verison": "-version",
        "-qeuit": "-quit",
        "-instal": "-install", "-instll": "-install",
        "--versoin": "--version", "--verison": "--version",
        "--instal": "--install", "--instll": "--install",
        "--hlep": "--help", "--hlepme": "--help",
    }

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 Shell 脚本错误"""
        log_lower = log_content.lower()

        # 遍历错误模式
        for error_type, (pattern, category, llm_hint) in self.error_patterns.items():
            if pattern.lower() in log_lower:
                # 提取错误消息片段
                error_message = self._extract_error_message(log_content, pattern)

                # AUTO_FIXABLE 类型：检查是否真的可以修复
                if category == ErrorCategory.AUTO_FIXABLE:
                    quick_fix = self._try_build_quick_fix(log_content, error_type)
                    if quick_fix:
                        return ErrorAnalysis(
                            error_type=error_type,
                            category=ErrorCategory.AUTO_FIXABLE,
                            error_message=error_message,
                            confidence=0.98,
                            matched_pattern=pattern,
                            quick_fix=quick_fix,
                        )
                    # 无法构建快速修复，降级为 KNOWN_NEEDS_LLM
                    return ErrorAnalysis(
                        error_type=error_type,
                        category=ErrorCategory.KNOWN_NEEDS_LLM,
                        error_message=error_message,
                        matched_pattern=pattern,
                        llm_hint="命令未找到，请分析具体原因",
                    )

                # KNOWN_NEEDS_LLM 类型
                return ErrorAnalysis(
                    error_type=error_type,
                    category=ErrorCategory.KNOWN_NEEDS_LLM,
                    error_message=error_message,
                    matched_pattern=pattern,
                    llm_hint=llm_hint,
                )

        # 未匹配任何模式
        return ErrorAnalysis(
            error_type="unknown",
            category=ErrorCategory.UNKNOWN,
            error_message=log_content[:500],
        )

    def _try_build_quick_fix(self, log_content: str, error_type: str) -> Optional[Dict]:
        """尝试构建快速修复方案"""
        if error_type == "command_not_found":
            wrong_cmd = self._extract_wrong_command(log_content)
            if wrong_cmd and wrong_cmd in self.common_spell_errors:
                correct_cmd = self.common_spell_errors[wrong_cmd]
                return {
                    "action_type": "modify_script",
                    "script_changes": {wrong_cmd: correct_cmd},
                }

            # 检查参数拼写错误
            for wrong_arg, correct_arg in self.common_arg_errors.items():
                if wrong_arg in log_content:
                    return {
                        "action_type": "modify_script",
                        "script_changes": {wrong_arg: correct_arg},
                    }

        return None

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息片段"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if pattern.lower() in line.lower():
                start = max(0, i - 3)
                end = min(len(lines), i + 5)
                return "\n".join(lines[start:end])
        return pattern

    def _extract_wrong_command(self, error_message: str) -> Optional[str]:
        """提取错误的命令"""
        patterns = [
            r"command not found:\s+(\w+)",
            r"(\w+):\s+command not found",
            r"line \d+:\s+(\w+):\s+command not found",
        ]
        for p in patterns:
            match = re.search(p, error_message)
            if match:
                return match.group(1)
        return None


__all__ = ["ShellSkill"]