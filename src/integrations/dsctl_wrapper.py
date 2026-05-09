"""
DSCLIClient - dsctl CLI 封装

通过 subprocess 调用 dsctl CLI 执行 DolphinScheduler 操作

主要命令：
- workflow-instance recover-failed: 恢复失败的工作流实例
- workflow-instance export: 导出实例 YAML
- workflow-instance edit --patch: 编辑实例（带 --sync-definition 同步到定义）
- task-instance log: 获取任务日志
"""

import subprocess
import os
import tempfile
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

    正确使用 dsctl 命令执行 DolphinScheduler 操作
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        version: str = "3.2.0"
    ):
        self.api_url = api_url or os.environ.get("DS_API_URL", "")
        self.api_token = api_token or os.environ.get("DS_API_TOKEN", "")
        self.version = version

    def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
        """执行 dsctl 命令"""
        env = os.environ.copy()
        env["DS_API_URL"] = self.api_url
        env["DS_API_TOKEN"] = self.api_token
        env["DS_VERSION"] = self.version

        cmd = ["python", "-m", "dsctl"] + args

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

    # ============ Task Instance ============

    def get_task_logs(self, task_instance_id: int, tail: int = 1000) -> CLIResult:
        """
        获取任务日志（全量获取足够行数以包含配置和错误）

        用户要求：
        - 前200行是任务配置信息
        - 后300行是错误信息

        Args:
            task_instance_id: 任务实例 ID
            tail: 返回最后 N 行（默认1000行，包含配置+错误）

        Returns:
            CLIResult
        """
        return self._run_command([
            "task-instance", "log",
            "--raw",
            "--tail", str(tail),
            str(task_instance_id)
        ], timeout=60)

    # ============ Workflow Instance ============

    def list_workflows(self, project_code: int) -> CLIResult:
        """
        列出项目中的所有工作流

        Args:
            project_code: 项目编码

        Returns:
            CLIResult (stdout 是 JSON 格式的工作流列表)
        """
        return self._run_command([
            "workflow", "list",
            "--project", str(project_code)
        ], timeout=60)

    def describe_workflow(self, project_code: int, workflow_code: int) -> CLIResult:
        """
        获取工作流详细信息（包含任务和关系）

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码

        Returns:
            CLIResult (stdout 是 JSON 格式的工作流详情)
        """
        return self._run_command([
            "workflow", "describe",
            "--project", str(project_code),
            str(workflow_code)
        ], timeout=60)

    def list_schedules(self, project_code: int) -> CLIResult:
        """
        列出项目中的所有调度

        Args:
            project_code: 项目编码

        Returns:
            CLIResult (stdout 是 JSON 格式的调度列表)
        """
        return self._run_command([
            "schedule", "list",
            "--project", str(project_code)
        ], timeout=60)

    def list_workflow_instances(self, project_code: int, workflow_code: int, page_size: int = 20) -> CLIResult:
        """
        列出工作流的最近实例

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码
            page_size: 返回数量

        Returns:
            CLIResult (stdout 是 JSON 格式的实例列表)
        """
        return self._run_command([
            "workflow-instance", "list",
            "--project", str(project_code),
            "--workflow", str(workflow_code),
            "--page-size", str(page_size)
        ], timeout=60)

    def workflow_instance_recover_failed(self, instance_id: int) -> CLIResult:
        """
        恢复失败的工作流实例

        Args:
            instance_id: 工作流实例 ID

        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "recover-failed",
            str(instance_id)
        ])

    def workflow_instance_export(self, instance_id: int) -> CLIResult:
        """
        导出工作流实例为 YAML

        Args:
            instance_id: 工作流实例 ID

        Returns:
            CLIResult (YAML content in stdout)
        """
        return self._run_command([
            "workflow-instance", "export",
            str(instance_id)
        ])

    def workflow_instance_edit_patch(
        self,
        instance_id: int,
        patch_yaml: str,
        sync_definition: bool = True
    ) -> CLIResult:
        """
        使用 patch YAML 编辑工作流实例

        Args:
            instance_id: 工作流实例 ID
            patch_yaml: patch YAML 内容
            sync_definition: 是否同步到工作流定义

        Returns:
            CLIResult
        """
        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(patch_yaml)
            patch_file = f.name

        try:
            args = [
                "workflow-instance", "edit",
                str(instance_id),
                "--patch", patch_file
            ]

            if sync_definition:
                args.append("--sync-definition")

            result = self._run_command(args, timeout=60)
            return result
        finally:
            os.unlink(patch_file)

    def workflow_instance_edit_task_script(
        self,
        instance_id: int,
        task_name: str,
        new_script: str,
        sync_definition: bool = True
    ) -> CLIResult:
        """
        编辑工作流实例中的任务脚本

        Args:
            instance_id: 工作流实例 ID
            task_name: 任务名称
            new_script: 新脚本内容
            sync_definition: 是否同步到工作流定义

        Returns:
            CLIResult
        """
        # 构建 patch YAML
        patch_yaml = f'''patch:
  tasks:
    update:
      - match:
          name: {task_name}
        set:
          command: |
'''

        # 添加脚本内容（每行缩进）
        for line in new_script.split('\n'):
            patch_yaml += f'            {line}\n'

        return self.workflow_instance_edit_patch(instance_id, patch_yaml, sync_definition)

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

    def workflow_instance_parent(self, sub_workflow_instance_id: int) -> CLIResult:
        """
        Query parent workflow instance of sub-workflow instance

        Args:
            sub_workflow_instance_id: Sub-workflow instance ID

        Returns:
            CLIResult (JSON with parentWorkflowInstance field)
        """
        return self._run_command([
            "workflow-instance", "parent",
            str(sub_workflow_instance_id)
        ])

    def workflow_instance_digest(self, instance_id: int) -> CLIResult:
        """
        Get workflow instance digest (failed tasks, progress etc)

        Args:
            instance_id: Workflow instance ID

        Returns:
            CLIResult (JSON with failedTasks, progress etc)
        """
        return self._run_command([
            "workflow-instance", "digest",
            str(instance_id)
        ])

    # ============ Workflow Definition ============

    def workflow_get(self, project_code: int, workflow_code: int) -> CLIResult:
        """获取工作流定义"""
        return self._run_command([
            "workflow", "get",
            str(workflow_code),
            "--project", str(project_code)
        ])

    def workflow_run(self, project_code: int, workflow_code: int) -> CLIResult:
        """启动工作流"""
        return self._run_command([
            "workflow", "run",
            str(workflow_code),
            "--project", str(project_code)
        ])


__all__ = ["DSCLIClient", "CLIResult"]