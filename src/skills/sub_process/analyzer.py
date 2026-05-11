"""
SUB_PROCESS Skill - 子工作流失败追踪

告警场景：
- 告警系统发送的是主工作流实例的告警
- SUB_PROCESS 任务日志只有 "子工作流执行失败"，没有具体错误
- 真正的错误在子工作流的失败任务日志中

追踪流程：
1. 从告警获取主工作流实例 ID (process_instance_id)
2. 从 SUB_PROCESS 任务日志提取子工作流 definitionCode
3. 通过 dsctl workflow-instance parent 查找主工作流实例下的子工作流实例
4. 获取子工作流实例的失败任务列表
5. 如果无法连接 dsctl，给出明确的追踪指引
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

        # 7. 构建 llm_hint（基于追踪结果）
        llm_hint = ""
        if trace_result.get("failed_tasks"):
            failed_tasks_str = ", ".join(trace_result["failed_tasks"])
            sub_wf_name = sub_workflow_info.get("definition_name", trace_result.get("sub_workflow_names", ["未知"])[0])
            llm_hint = f"子工作流 [{sub_wf_name}] 中以下任务失败: [{failed_tasks_str}]。请获取这些任务的日志进行详细分析。"
        elif trace_result.get("sub_workflow_names"):
            # 多个子工作流失败，但未获取到具体任务
            llm_hint = f"多个子工作流失败: [{', '.join(trace_result['sub_workflow_names'])}]。请分别查看这些子工作流实例的失败任务。"
        elif trace_result.get("error_hint"):
            # 追踪失败，使用 error_hint
            llm_hint = trace_result["error_hint"]
        elif sub_workflow_info.get("definition_code"):
            # 未连接 dsctl，但有 definition_code
            llm_hint = (
                f"SUB_PROCESS 调用子工作流定义 {sub_workflow_info['definition_code']} 失败。"
                f"请在 DolphinScheduler 控制台查看该子工作流的最近失败实例，获取具体失败任务日志。"
            )
        else:
            llm_hint = "SUB_PROCESS 任务失败，请在 DolphinScheduler 控制台查看子工作流详情"

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
                "failed_task_codes": trace_result.get("failed_task_codes", []),
                "sub_workflow_instance_id": trace_result.get("sub_workflow_instance_id"),
                "tracked": trace_result.get("tracked", False),
                "all_failed_sub_workflows": trace_result.get("sub_workflow_names", []),
                "all_sub_instances": trace_result.get("all_sub_instances", []),
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
        追踪子工作流的失败任务

        追踪流程：
        1. 从告警上下文获取 SUB_PROCESS 任务实例 ID
        2. 通过 dsctl task-instance sub-workflow 获取子工作流实例 ID
        3. 获取子工作流实例的失败任务

        Edge Cases:
        - 无 dsctl 连接: 返回 tracked=False, llm_hint 提供手动追踪指引
        - get_task_sub_workflow 失败: 返回 tracked=False, error_hint 包含错误信息
        - 子工作流实例不存在: SUB_PROCESS 任务在子工作流创建前失败
        - digest 无 failedTasks: 可能任务状态已变更，给出 state_changed hint
        - definitionCode 缺失: 无法作为 fallback 查询，给出 manual hint
        - API 方法不存在: 捕获特定错误，给出 upgrade hint

        Args:
            sub_workflow_info: 子工作流信息（包含 definition_code）
            context: 告警上下文（包含任务实例 ID）

        Returns:
            {
                "failed_tasks": ["失败任务名称列表"],
                "failed_task_codes": [任务code列表],
                "sub_workflow_instance_id": 子工作流实例ID,
                "tracked": True/False,
                "error_hint": 错误提示（当 tracked=False 时）,
                "sub_workflow_name": 子工作流名称,
            }
        """
        result = {
            "failed_tasks": [],
            "failed_task_codes": [],
            "sub_workflow_instance_id": None,
            "tracked": False,
            "error_hint": None,
            "sub_workflow_names": [],
            "all_sub_instances": [],
        }

        # 获取 SUB_PROCESS 任务实例 ID
        task_instance_id = None
        main_instance_id = None
        if hasattr(context, "alert_info"):
            task_instance_id = context.alert_info.task_instance_id
            main_instance_id = context.alert_info.process_instance_id

        if not task_instance_id:
            result["error_hint"] = "告警信息中缺少任务实例 ID，无法追踪子工作流"
            return result

        # 尝试连接 dsctl
        try:
            from ...integrations.dsctl_wrapper import DSCLIClient
            import os

            api_url = os.environ.get("DS_API_URL")
            api_token = os.environ.get("DS_API_TOKEN")

            if not api_url or not api_token:
                result["error_hint"] = (
                    "未配置 DS_API_URL 或 DS_API_TOKEN，无法自动追踪子工作流。"
                    "请在 DolphinScheduler 控制台手动查看主工作流实例的子工作流详情。"
                )
                return result

            dsctl = DSCLIClient(api_url=api_url, api_token=api_token)

            # 方法1：通过 task-instance sub-workflow 获取子工作流实例
            sub_wf_result = dsctl.get_task_sub_workflow(task_instance_id)

            if not sub_wf_result.success:
                # API 调用失败
                if "not found" in sub_wf_result.stderr.lower() or "not a sub" in sub_wf_result.stderr.lower():
                    result["error_hint"] = (
                        "该任务实例不是 SUB_PROCESS 类型或子工作流实例不存在。"
                        "可能原因：1) SUB_PROCESS 任务在子工作流创建前失败；2) 任务类型判断错误。"
                    )
                elif "unknown command" in sub_wf_result.stderr.lower():
                    result["error_hint"] = (
                        "dsctl 版本不支持 task-instance sub-workflow 命令，"
                        "请升级 dsctl 或手动在控制台查看子工作流实例。"
                    )
                else:
                    result["error_hint"] = (
                        f"查询子工作流实例失败: {sub_wf_result.stderr[:100] if sub_wf_result.stderr else '未知错误'}"
                    )
                return result

            sub_wf_data = None
            try:
                sub_wf_data = json.loads(sub_wf_result.stdout)
            except json.JSONDecodeError:
                result["error_hint"] = "子工作流实例数据解析失败，请检查 dsctl 输出格式"
                return result

            # 提取子工作流实例 ID
            sub_instance_id = None
            if isinstance(sub_wf_data, dict):
                sub_instance_id = sub_wf_data.get("subWorkflowInstanceId")
                if not sub_instance_id:
                    # 尝试其他字段名
                    sub_instance_id = sub_wf_data.get("id") or sub_wf_data.get("workflowInstanceId")

            if not sub_instance_id:
                result["error_hint"] = (
                    "子工作流实例 ID 不存在。"
                    "可能原因：SUB_PROCESS 任务配置错误或子工作流实例未创建。"
                )
                return result

            result["sub_workflow_instance_id"] = sub_instance_id
            result["tracked"] = True

            # 获取子工作流实例详情（名称、状态）
            digest_result = dsctl.workflow_instance_digest(sub_instance_id)
            if digest_result.success:
                try:
                    digest = json.loads(digest_result.stdout)
                    # 提取工作流名称
                    wf_name = digest.get("name") or digest.get("processDefinitionName") or f"子工作流实例{sub_instance_id}"
                    result["sub_workflow_names"] = [wf_name]

                    # 获取失败任务
                    failed_tasks = digest.get("failedTasks", [])
                    for task in failed_tasks:
                        task_name = task.get("name", "")
                        task_code = task.get("code")
                        if task_name:
                            result["failed_tasks"].append(task_name)
                        if task_code:
                            result["failed_task_codes"].append(task_code)
                except json.JSONDecodeError:
                    pass

            # 如果 digest 没有返回失败任务，尝试查询实例详情
            if not result["failed_tasks"]:
                # 可能有失败任务但 digest 没返回，给出提示
                result["error_hint"] = (
                    f"已追踪到子工作流实例 {sub_instance_id}，但未获取到失败任务列表。"
                    "可能原因：任务状态已变更或 digest 数据不完整。"
                    "请手动查看子工作流实例详情。"
                )

        except ImportError:
            result["error_hint"] = "dsctl_wrapper 模块未安装，无法自动追踪子工作流"
        except Exception as e:
            result["error_hint"] = f"追踪子工作流时发生异常: {str(e)[:100]}"

        return result

__all__ = ["SubProcessSkill"]