"""
DSCLIClient - dsctl CLI 封装

通过 subprocess 调用 dsctl CLI 执行 DolphinScheduler 操作
"""

import subprocess
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class CLIResult:
    """CLI 执行结果"""
    success: bool
    stdout: str
    stderr: str
    returncode: int


class DSCLIClient:
    """
    dsctl CLI 封装

    支持操作:
    - workflow-instance rerun
    - workflow-instance recover
    - task-instance logs
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        version: str = "3.2.0"
    ):
        """
        初始化

        Args:
            api_url: DolphinScheduler API URL
            api_token: API Token
            version: DS 版本
        """
        self.api_url = api_url or os.environ.get("DS_API_URL", "")
        self.api_token = api_token or os.environ.get("DS_API_TOKEN", "")
        self.version = version

    def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
        """执行 dsctl 命令"""
        env = os.environ.copy()
        env["DS_API_URL"] = self.api_url
        env["DS_API_TOKEN"] = self.api_token
        env["DS_VERSION"] = self.version

        cmd = ["py", "-m", "dsctl"] + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )

            return CLIResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode
            )
        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                stdout="",
                stderr="Command timed out",
                returncode=-1
            )

    def workflow_instance_rerun(self, instance_id: int) -> CLIResult:
        """
        重跑工作流实例

        Args:
            instance_id: 工作流实例 ID

        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "rerun",
            str(instance_id)
        ])

    def workflow_instance_recover(
        self,
        instance_id: int,
        task_code: int
    ) -> CLIResult:
        """
        从失败任务恢复

        Args:
            instance_id: 工作流实例 ID
            task_code: 失败任务编码

        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "recover",
            str(instance_id),
            "--task", str(task_code)
        ])

    def get_task_logs(self, task_instance_id: int) -> CLIResult:
        """
        获取任务日志

        Args:
            task_instance_id: 任务实例 ID

        Returns:
            CLIResult
        """
        return self._run_command([
            "task-instance", "logs",
            str(task_instance_id)
        ])

    def workflow_get(self, project_code: int, workflow_code: int) -> CLIResult:
        """
        获取工作流定义

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码

        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow", "get",
            str(workflow_code),
            "--project", str(project_code)
        ])

    def list_workflows(self, project_code: int) -> CLIResult:
        """
        列出项目中的所有工作流

        Args:
            project_code: 项目编码

        Returns:
            CLIResult (JSON array of workflows)
        """
        return self._run_command([
            "workflow", "list",
            "--project", str(project_code)
        ])

    def describe_workflow(self, project_code: int, workflow_code: int) -> CLIResult:
        """
        获取工作流详细定义（包含任务和依赖关系）

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码

        Returns:
            CLIResult (JSON with workflow, tasks, relations)
        """
        return self._run_command([
            "workflow", "describe",
            str(workflow_code),
            "--project", str(project_code)
        ])


__all__ = ["DSCLIClient", "CLIResult"]