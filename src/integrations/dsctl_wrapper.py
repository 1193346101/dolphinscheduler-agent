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

        # 初始化安全模块
        from ..security import CommandGuard, AuditLogger, SecurityAlert
        self.guard = CommandGuard()
        self.audit = AuditLogger()
        self.alert = SecurityAlert()

    # ============ Project ============

    def list_projects(self, page_size: int = 100) -> CLIResult:
        """
        列出所有项目

        Args:
            page_size: 返回数量（默认100）

        Returns:
            CLIResult (stdout 是 JSON 格式的项目列表)
        """
        return self._run_command([
            "project", "list",
            "--page-size", str(page_size)
        ], timeout=60)

    def get_project(self, project: str) -> CLIResult:
        """
        获取项目信息（通过名称或代码）

        Args:
            project: 项目名称或项目代码

        Returns:
            CLIResult (stdout 是 JSON 格式的项目信息)
        """
        return self._run_command([
            "project", "get",
            project
        ], timeout=30)

    def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
        """执行 dsctl 命令（增加安全检查）"""
        import time

        # 1. 安全检查
        guard_result = self.guard.check_cli_command(args)

        if guard_result.blocked:
            # 记录拦截日志
            self.audit.log_blocked(
                operation_type="dsctl",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
                risk_level=guard_result.risk_level,
            )
            # 发送拦截告警
            self.alert.send_blocked_alert(
                operation_type="dsctl",
                operation_detail=guard_result.operation_detail,
                reason=guard_result.reason,
            )
            # 返回错误结果
            return CLIResult(
                success=False,
                stdout="",
                stderr=guard_result.reason,
                returncode=-1,
            )

        # 2. 执行命令
        env = os.environ.copy()
        env["DS_API_URL"] = self.api_url
        env["DS_API_TOKEN"] = self.api_token
        env["DS_VERSION"] = self.version

        cmd = ["python", "-m", "dsctl"] + args

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            cli_result = CLIResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode
            )

            # 3. 记录审计日志
            self.audit.log(
                operation_type="dsctl",
                operation_detail=guard_result.operation_detail,
                result="success" if cli_result.success else "failed",
                result_detail=cli_result.stderr[:200] if cli_result.stderr else "",
                risk_level=guard_result.risk_level,
                duration_ms=elapsed_ms,
            )

            # 4. 高风险操作发送告警
            if guard_result.risk_level == "HIGH":
                self.alert.send_high_risk_execution_alert(
                    operation_type="dsctl",
                    operation_detail=guard_result.operation_detail,
                    result="success" if cli_result.success else "failed",
                    error=cli_result.stderr if not cli_result.success else None,
                )

            return cli_result

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            self.audit.log_failed(
                operation_type="dsctl",
                operation_detail=guard_result.operation_detail,
                error="Command timed out",
                risk_level=guard_result.risk_level,
                duration_ms=elapsed_ms,
            )
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

    def list_workflow_instances(
        self,
        project_code: int,
        workflow_code: Optional[int] = None,
        page_size: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        state: Optional[str] = None
    ) -> CLIResult:
        """
        列出工作流实例（支持项目级别或工作流级别查询）

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码（可选，不传则查询项目所有实例）
            page_size: 返回数量（默认100）
            start_time: 开始时间下限，格式 'YYYY-MM-DD HH:MM:SS'
            end_time: 开始时间上限，格式 'YYYY-MM-DD HH:MM:SS'
            state: 状态过滤，如 'FAILURE', 'SUCCESS'

        Returns:
            CLIResult (stdout 是 JSON 格式的实例列表)
        """
        args = [
            "workflow-instance", "list",
            "--project", str(project_code),
            "--page-size", str(page_size)
        ]

        # workflow_code 可选，不传则查询项目所有实例
        if workflow_code:
            args.extend(["--workflow", str(workflow_code)])

        if start_time:
            args.extend(["--start", start_time])
        if end_time:
            args.extend(["--end", end_time])
        if state:
            args.extend(["--state", state])

        return self._run_command(args, timeout=60)

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

    def workflow_instance_children(self, main_workflow_instance_id: int) -> CLIResult:
        """
        Query sub-workflow instances of a main workflow instance

        NOTE: This method is deprecated. Use get_task_sub_workflow instead.

        Args:
            main_workflow_instance_id: Main workflow instance ID

        Returns:
            CLIResult (JSON with subWorkflowInstances list)
        """
        return self._run_command([
            "workflow-instance", "children",
            str(main_workflow_instance_id)
        ])

    def get_task_sub_workflow(self, task_instance_id: int) -> CLIResult:
        """
        Get sub-workflow instance from a SUB_PROCESS task instance

        Args:
            task_instance_id: SUB_PROCESS task instance ID

        Returns:
            CLIResult (JSON with subWorkflowInstanceId)
        """
        return self._run_command([
            "task-instance", "sub-workflow",
            str(task_instance_id)
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