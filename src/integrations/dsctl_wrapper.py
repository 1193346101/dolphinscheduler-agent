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
        task_code: int = None,
        from_node: int = None
    ) -> CLIResult:
        """
        从失败任务恢复工作流实例

        支持两种模式：
        1. 恢复指定失败任务：--task <task_code>
        2. 从指定节点开始恢复：--from-node <node_code>

        Args:
            instance_id: 工作流实例 ID
            task_code: 失败任务编码（可选，用于恢复失败任务）
            from_node: 从此节点开始恢复（可选，用于从指定节点继续）

        Returns:
            CLIResult
        """
        args = [
            "workflow-instance", "recover",
            str(instance_id)
        ]

        if task_code:
            args.extend(["--task", str(task_code)])
        elif from_node:
            args.extend(["--from-node", str(from_node)])

        return self._run_command(args)

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

    def workflow_instance_edit_and_recover(
        self,
        instance_id: int,
        task_code: int,
        script_changes: dict
    ) -> CLIResult:
        """
        编辑工作流实例中的任务脚本并恢复失败

        使用 dsctl workflow-instance edit 修改实例中的任务定义，
        然后使用 recover-failed 恢复。

        Args:
            instance_id: 工作流实例 ID
            task_code: 任务编码
            script_changes: 脚本修改映射 {"wrong": "correct"}

        Returns:
            CLIResult
        """
        # 1. 先编辑实例中的任务脚本
        # 构造 edit 参数（需要 JSON 格式的修改内容）
        import json

        # dsctl workflow-instance edit 支持修改 taskParams
        # 格式: --task <task_code> --params '{"rawScript": "..."}'
        edit_changes = {}
        for wrong, correct in script_changes.items():
            # 这里简化处理，实际需要获取当前脚本然后替换
            edit_changes["script_fix"] = {"replace": {wrong: correct}}

        edit_result = self._run_command([
            "workflow-instance", "edit",
            str(instance_id),
            "--task", str(task_code),
            "--changes", json.dumps(edit_changes)
        ], timeout=60)

        if not edit_result.success:
            return edit_result

        # 2. 恢复失败任务
        return self.workflow_instance_recover(instance_id, task_code)

    def workflow_update_config(
        self,
        project_code: int,
        workflow_code: int,
        task_code: int,
        config_changes: dict
    ) -> CLIResult:
        """
        更新工作流定义中的任务配置

        使用 dsctl workflow update 修改工作流定义中的任务参数，
        然后重新上线。

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码
            task_code: 任务编码
            config_changes: 配置修改 {"spark.executor.memory": "4g"}

        Returns:
            CLIResult
        """
        import json

        # dsctl workflow update 支持修改任务配置
        update_result = self._run_command([
            "workflow", "update",
            str(workflow_code),
            "--project", str(project_code),
            "--task", str(task_code),
            "--config", json.dumps(config_changes)
        ], timeout=60)

        if not update_result.success:
            return update_result

        # 重新上线工作流
        return self._run_command([
            "workflow", "release",
            str(workflow_code),
            "--project", str(project_code),
            "--state", "online"
        ])

    def workflow_run(
        self,
        project_code: int,
        workflow_code: int,
        params: dict = None
    ) -> CLIResult:
        """
        启动新的工作流实例

        使用 dsctl workflow run 启动工作流。

        Args:
            project_code: 项目编码
            workflow_code: 工作流编码
            params: 启动参数（可选）

        Returns:
            CLIResult
        """
        import json

        args = [
            "workflow", "run",
            str(workflow_code),
            "--project", str(project_code)
        ]

        if params:
            args.extend(["--params", json.dumps(params)])

        return self._run_command(args, timeout=60)

    def workflow_instance_recover_from_subworkflow(
        self,
        parent_instance_id: int,
        subworkflow_node_code: int
    ) -> CLIResult:
        """
        从父工作流实例的子工作流节点恢复

        用于子工作流需要修改定义后重新执行的场景：
        1. 修改子工作流定义并上线
        2. 从父工作流的子工作流节点开始恢复
        3. 会创建新的子工作流实例，但属于父工作流实例

        Args:
            parent_instance_id: 父工作流实例 ID
            subworkflow_node_code: 子工作流节点编码（在父工作流中的任务编码）

        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "recover",
            str(parent_instance_id),
            "--from-node", str(subworkflow_node_code)
        ])


__all__ = ["DSCLIClient", "CLIResult"]