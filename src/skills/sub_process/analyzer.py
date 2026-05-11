"""
SUB_PROCESS Skill - 子工作流失败追踪

SUB_PROCESS 任务失败时，日志中只有子工作流执行失败的信息，
真正的错误在子工作流的失败任务日志中。

本 Skill 实现：
1. 从日志中提取子工作流的 definitionCode
2. 尝试调用 dsctl 获取子工作流的失败实例和失败任务
3. 如果无法连接 dsctl，给出明确的追踪指引
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any
from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log


class SubProcessSkill(BaseSkill):
    """
    SUB_PROCESS 任务分析 Skill

    SUB_PROCESS 任务本身不执行具体逻辑，而是调用子工作流。
    当子工作流失败时，SUB_PROCESS 任务标记为失败，但日志中没有具体错误。
    """

    skill_name = "sub_process"
    task_types = ["SUB_PROCESS"]

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 SUB_PROCESS 任务失败"""
        # 1. 预处理日志
        preprocessed = preprocess_log(log_content, task_type="sub_process")
        error_blocks = preprocessed.get("error_blocks", [])

        # 2. 从日志中提取子工作流信息
        sub_workflow_info = self._extract_sub_workflow_info(log_content)

        # 3. 提取原始错误信息（如果有）
        original_error = error_blocks[0] if error_blocks else log_content[:300]

        # 4. 构建分析过程说明
        analysis_process_parts = []
        if sub_workflow_info.get("definition_code"):
            analysis_process_parts.append(
                f"识别子工作流定义: {sub_workflow_info['definition_code']}"
            )
        if sub_workflow_info.get("definition_name"):
            analysis_process_parts.append(
                f"子工作流名称: {sub_workflow_info['definition_name']}"
            )
        analysis_process = (
            ", ".join(analysis_process_parts)
            if analysis_process_parts
            else "SUB_PROCESS 任务失败，需追踪子工作流"
        )

        # 5. 构建建议理由
        reasoning = self._build_reasoning(sub_workflow_info, log_content)

        # 6. 尝试追踪子工作流失败任务（如果有 dsctl 连接）
        trace_result = self._trace_sub_workflow_failure(sub_workflow_info, context)

        # 7. 构建 llm_hint
        llm_hint = ""
        if trace_result.get("failed_tasks"):
            llm_hint = f"子工作流 {sub_workflow_info.get('definition_name', '未知')} 中以下任务失败: {', '.join(trace_result['failed_tasks'])}"
        elif sub_workflow_info.get("definition_code"):
            llm_hint = f"请查看子工作流 {sub_workflow_info['definition_code']} 的最近失败实例，获取具体失败任务日志"

        return ErrorAnalysis(
            error_type="sub_workflow_failed",
            category=ErrorCategory.KNOWN_NEEDS_LLM,
            error_message=log_content[:500],
            matched_pattern="FAILURE",
            llm_hint=llm_hint,
            original_log_error=original_error,
            analysis_process=analysis_process,
            reasoning=reasoning,
            data_metrics={
                "sub_workflow_definition_code": sub_workflow_info.get("definition_code"),
                "sub_workflow_definition_name": sub_workflow_info.get("definition_name"),
                "failed_tasks": trace_result.get("failed_tasks", []),
            },
        )

    def _extract_sub_workflow_info(self, log_content: str) -> Dict[str, Any]:
        """
        从日志中提取子工作流信息

        提取:
        - processDefinitionCode: 子工作流定义 code
        - 子工作流名称（如果有）
        """
        info = {}

        # 从 taskParams 中提取 processDefinitionCode
        # 格式: "processDefinitionCode":12901280341824
        match = re.search(
            r'"processDefinitionCode"\s*:\s*(\d+)',
            log_content
        )
        if match:
            info["definition_code"] = int(match.group(1))

        # 尝试从日志中提取子工作流名称
        # 格式: The sub workflow instance doesn't created
        # 或其他提示信息中

        return info

    def _build_reasoning(
        self, sub_workflow_info: Dict, log_content: str
    ) -> str:
        """构建建议理由"""
        if sub_workflow_info.get("definition_code"):
            return (
                f"SUB_PROCESS 任务调用子工作流 {sub_workflow_info['definition_code']} 失败。"
                f"真正的错误在子工作流的失败任务中，需要查看子工作流实例的任务日志才能确定具体原因。"
            )

        # 检查是否有明确的错误信息
        if "FAILURE" in log_content:
            return (
                "SUB_PROCESS 任务执行失败，子工作流未能成功完成。"
                "请检查 DolphinScheduler 控制台，查看子工作流的失败任务详情。"
            )

        return "SUB_PROCESS 任务失败，建议查看 DolphinScheduler 控制台获取子工作流详情"

    def _trace_sub_workflow_failure(
        self, sub_workflow_info: Dict, context: AlertContext
    ) -> Dict[str, Any]:
        """
        尝试追踪子工作流的失败任务

        如果可以连接 dsctl，获取子工作流的最近失败实例和失败任务列表。

        Args:
            sub_workflow_info: 子工作流信息
            context: 告警上下文

        Returns:
            {
                "failed_tasks": ["失败任务名称列表"],
                "failed_task_codes": [任务code列表],
                "instance_id": 子工作流实例ID,
                "tracked": True/False
            }
        """
        result = {
            "failed_tasks": [],
            "failed_task_codes": [],
            "instance_id": None,
            "tracked": False,
        }

        definition_code = sub_workflow_info.get("definition_code")
        if not definition_code:
            return result

        # 尝试连接 dsctl
        try:
            from ...integrations.dsctl_wrapper import DSCLIClient

            # 从 context 或环境变量获取 API 信息
            api_url = getattr(context, "api_url", None)
            api_token = getattr(context, "api_token", None)

            if not api_url or not api_token:
                return result

            dsctl = DSCLIClient(api_url=api_url, api_token=api_token)

            # 获取项目 code
            project_code = context.alert_info.project_code if hasattr(context, "alert_info") else None
            if not project_code:
                return result

            # 1. 获取该工作流定义的最近实例
            instances_result = dsctl.list_workflow_instances(
                project_code, definition_code, page_size=5
            )
            if not instances_result.success:
                return result

            instances = json.loads(instances_result.stdout)
            if isinstance(instances, dict) and "data" in instances:
                instances = instances["data"]

            # 找到失败的实例
            failed_instance = None
            for inst in instances:
                if inst.get("state") == "FAILURE":
                    failed_instance = inst
                    break

            if not failed_instance:
                return result

            result["instance_id"] = failed_instance.get("id")

            # 2. 获取失败实例的 digest（失败任务列表）
            digest_result = dsctl.workflow_instance_digest(result["instance_id"])
            if digest_result.success:
                digest = json.loads(digest_result.stdout)
                failed_tasks = digest.get("failedTasks", [])
                for task in failed_tasks:
                    result["failed_tasks"].append(task.get("name", ""))
                    result["failed_task_codes"].append(task.get("code"))

            result["tracked"] = True

        except Exception:
            # 无法连接 dsctl，返回空结果
            pass

        return result


__all__ = ["SubProcessSkill"]