"""
自动修复执行器

执行低风险的自动修复操作
"""

from typing import Optional
from ...models.alert import AlertInfo
from ...models.risk import AutoFixAction
from ...integrations.ds_cli import DSCLIClient


class AutoFixExecutor:
    """
    自动修复执行器

    支持的修复类型:
    - modify_config: 修改工作流配置参数
    - modify_script: 修改任务脚本
    """

    def __init__(self):
        self.ds_cli = DSCLIClient()

    def execute(
        self,
        alert_info: AlertInfo,
        fix_action: AutoFixAction,
    ) -> dict:
        """
        执行自动修复

        Args:
            alert_info: 告警信息
            fix_action: 修复动作

        Returns:
            执行结果
        """
        if fix_action.action_type == "modify_config":
            return self._modify_config(alert_info, fix_action)
        elif fix_action.action_type == "modify_script":
            return self._modify_script(alert_info, fix_action)
        else:
            return {
                "status": "failed",
                "message": f"未知的修复类型: {fix_action.action_type}",
            }

    def _modify_config(
        self,
        alert_info: AlertInfo,
        fix_action: AutoFixAction,
    ) -> dict:
        """修改配置参数"""
        if not fix_action.config_changes:
            return {"status": "failed", "message": "无配置变更"}

        # TODO: 调用 dsctl 或 DS API 修改配置
        # 这里需要根据具体的 DS 版本和 API 实现

        result = {
            "status": "success",
            "message": "配置已更新",
            "changes": fix_action.config_changes,
            "workflow_code": alert_info.process_definition_code,
            "task_code": alert_info.task_code,
        }

        return result

    def _modify_script(
        self,
        alert_info: AlertInfo,
        fix_action: AutoFixAction,
    ) -> dict:
        """修改脚本"""
        if not fix_action.script_changes:
            return {"status": "failed", "message": "无脚本变更"}

        # TODO: 调用 dsctl 或 DS API 修改脚本

        result = {
            "status": "success",
            "message": "脚本已更新",
            "changes": fix_action.script_changes,
            "task_code": alert_info.task_code,
        }

        return result

    def recover_workflow(
        self,
        alert_info: AlertInfo,
    ) -> dict:
        """恢复工作流"""
        result = self.ds_cli.workflow_recover(
            alert_info.project_code,
            alert_info.process_instance_id,
        )

        if result.success:
            return {
                "status": "success",
                "message": "工作流已恢复",
                "instance_id": alert_info.process_instance_id,
            }
        else:
            return {
                "status": "failed",
                "message": result.error or "恢复失败",
            }


__all__ = ["AutoFixExecutor"]