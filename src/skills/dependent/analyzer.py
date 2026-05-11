"""
DEPENDENT Skill - 依赖检查失败追踪

DEPENDENT 任务检查其他工作流的执行状态，如果依赖的工作流失败，
DEPENDENT 任务也会失败，但日志中只有"依赖检查失败"的信息。

本 Skill 实现：
1. 从日志中提取依赖的工作流列表
2. 分析依赖结果 (FAILED)
3. 给出追踪指引：需要查看哪个依赖工作流失败

Edge Cases:
- JSON 解析失败: 返回空列表，给出手动查询指引
- 多个依赖工作流: 列出所有依赖，需逐个排查
- 跨项目依赖: 提取 projectCode，提示跨项目查询
- 时序问题: 依赖工作流实例尚未生成，给出等待或手动检查指引
- Timeout vs Failure: 区分 dependent_waiting_timeout 和 dependent_check_failed
- 无 dsctl 连接: 返回手动追踪指引
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.preprocess_log import preprocess_log


class DependentSkill(BaseSkill):
    """
    DEPENDENT 任务分析 Skill

    DEPENDENT 任务不执行具体逻辑，而是检查其他工作流的执行状态。
    当依赖的工作流失败时，DEPENDENT 任务标记为失败。
    """

    skill_name = "dependent"
    task_types = ["DEPENDENT"]

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 DEPENDENT 任务失败"""
        # 1. 预处理日志
        preprocessed = preprocess_log(log_content, task_type="dependent")
        error_blocks = preprocessed.get("error_blocks", [])

        # 2. 从日志中提取依赖信息
        dependent_info = self._extract_dependent_info(log_content)

        # 3. 提取原始错误信息
        # DEPENDENT 日志通常没有 error_blocks，需要从日志中提取关键信息
        original_error = self._extract_original_error(log_content)

        # 4. 构建分析过程说明
        analysis_process = self._build_analysis_process(dependent_info, log_content)

        # 5. 构建建议理由
        reasoning = self._build_reasoning(dependent_info, log_content)

        # 6. 尝试追踪依赖工作流失败（可选）
        track_result = self._track_dependent_workflow_failure(dependent_info, context)

        # 7. 构建 llm_hint（优先使用追踪结果）
        llm_hint = ""
        if track_result.get("failed_tasks"):
            failed_tasks_str = ", ".join(track_result["failed_tasks"])
            wf_name = track_result.get("failed_workflow_name", "未知")
            llm_hint = f"依赖工作流 [{wf_name}] 中以下任务失败: [{failed_tasks_str}]。请获取这些任务的日志进行详细分析。"
        elif track_result.get("error_hint"):
            llm_hint = track_result["error_hint"]
        else:
            llm_hint = self._build_llm_hint(dependent_info)

        # 8. 确定错误类型
        error_type = "dependent_check_failed"
        if "timeout" in log_content.lower():
            error_type = "dependent_waiting_timeout"

        return ErrorAnalysis(
            error_type=error_type,
            category=ErrorCategory.KNOWN_NEEDS_LLM,
            error_message=log_content[:500],
            matched_pattern="Dependent result is: FAILED",
            llm_hint=llm_hint,
            original_log_error=original_error,
            analysis_process=analysis_process,
            reasoning=reasoning,
            data_metrics={
                "dependent_workflows": dependent_info.get("workflows", []),
                "dependent_project_code": dependent_info.get("project_code"),
                "check_interval": dependent_info.get("check_interval"),
                "tracked": track_result.get("tracked", False),
                "failed_workflow_name": track_result.get("failed_workflow_name"),
                "failed_tasks": track_result.get("failed_tasks", []),
                "failed_instance_id": track_result.get("failed_instance_id"),
            },
        )

    def _extract_dependent_info(self, log_content: str) -> Dict[str, Any]:
        """
        从日志中提取依赖信息

        提取:
        - 依赖的工作流列表 (definitionCode, projectCode, depTaskCode)
        - checkInterval
        - projectCode

        日志格式示例：
        {
          "taskParams": "{\"dependence\":{\"checkInterval\":300,\"dependTaskList\":[{\"dependItemList\":[{\"definitionCode\":xxx,\"projectCode\":xxx,\"depTaskCode\":xxx}]}}]}"
        }
        """
        info = {"workflows": []}

        # 方法1: 从 taskParams JSON 字符串中提取
        # taskParams 是嵌套在日志 JSON 结构中的字符串，需要正确处理转义引号
        try:
            # 找到 taskParams 字段的起始位置
            start_pattern = '"taskParams" : "'
            start_idx = log_content.find(start_pattern)
            if start_idx != -1:
                start_idx += len(start_pattern)

                # 找到 taskParams 字符串的结束位置
                # 需要处理转义引号的情况
                end_idx = start_idx
                while end_idx < len(log_content):
                    if log_content[end_idx] == '"':
                        # 检查这个引号是否被转义
                        # 计算前面的连续反斜杠数量
                        backslash_count = 0
                        i = end_idx - 1
                        while i >= start_idx and log_content[i] == '\\':
                            backslash_count += 1
                            i -= 1

                        # 如果反斜杠数量是偶数，说明这个引号没有被转义
                        if backslash_count % 2 == 0:
                            break
                    end_idx += 1

                task_params_escaped = log_content[start_idx:end_idx]
                # 替换转义引号
                task_params_str = task_params_escaped.replace('\\"', '"')

                task_params = json.loads(task_params_str)
                dependence = task_params.get("dependence", {})

                info["check_interval"] = dependence.get("checkInterval")

                # 提取依赖的工作流列表
                depend_task_list = dependence.get("dependTaskList", [])
                for task in depend_task_list:
                    depend_item_list = task.get("dependItemList", [])
                    for item in depend_item_list:
                        workflow = {
                            "definition_code": item.get("definitionCode"),
                            "project_code": item.get("projectCode"),
                            "dep_task_code": item.get("depTaskCode"),
                            "cycle": item.get("cycle"),
                            "date_value": item.get("dateValue"),
                        }
                        info["workflows"].append(workflow)
                        if workflow.get("project_code"):
                            info["project_code"] = workflow["project_code"]

        except (json.JSONDecodeError, ValueError):
            # 方法2: 直接从日志文本中提取 definitionCode
            # 格式: definitionCode:xxx 或 "definitionCode":xxx
            definition_codes = re.findall(
                r'definitionCode["\s:]+(\d+)',
                log_content
            )
            project_codes = re.findall(
                r'projectCode["\s:]+(\d+)',
                log_content
            )
            dep_task_codes = re.findall(
                r'depTaskCode["\s:]+(\d+)',
                log_content
            )

            for i, def_code in enumerate(definition_codes):
                workflow = {
                    "definition_code": int(def_code),
                    "project_code": int(project_codes[i]) if i < len(project_codes) else None,
                    "dep_task_code": int(dep_task_codes[i]) if i < len(dep_task_codes) else None,
                }
                info["workflows"].append(workflow)

        # 方法3: 从日志行中提取工作流名称
        # 格式: WorkflowName: xxx
        workflow_names = re.findall(r'WorkflowName\s*:\s*(.+)', log_content)
        for i, name in enumerate(workflow_names):
            if i < len(info["workflows"]):
                info["workflows"][i]["definition_name"] = name.strip()

        # 方法4: 从日志行中提取项目名称
        # 格式: ProjectName: xxx
        project_names = re.findall(r'ProjectName\s*:\s*(.+)', log_content)
        for i, name in enumerate(project_names):
            if i < len(info["workflows"]):
                info["workflows"][i]["project_name"] = name.strip()

        return info

    def _extract_original_error(self, log_content: str) -> str:
        """提取原始错误信息"""
        # DEPENDENT 日志的关键信息
        # "The Dependent result is: FAILED"
        lines = []
        for line in log_content.split('\n'):
            if 'Dependent result' in line:
                lines.append(line.strip())
            elif 'Add dependent task' in line:
                lines.append(line.strip())
            elif 'WorkflowName' in line:
                lines.append(line.strip())
            elif 'FAILURE' in line:
                lines.append(line.strip())

        return '\n'.join(lines) if lines else log_content[:300]

    def _build_analysis_process(
        self, dependent_info: Dict, log_content: str
    ) -> str:
        """构建分析过程说明"""
        parts = []

        if dependent_info.get("workflows"):
            workflow_count = len(dependent_info["workflows"])
            parts.append(f"识别 {workflow_count} 个依赖工作流")

            for wf in dependent_info["workflows"]:
                if wf.get("definition_name"):
                    parts.append(f"依赖: {wf['definition_name']}")
                elif wf.get("definition_code"):
                    parts.append(f"依赖定义: {wf['definition_code']}")

        if "FAILED" in log_content:
            parts.append("依赖检查结果: FAILED")

        return ", ".join(parts) if parts else "DEPENDENT 任务失败，依赖工作流执行失败"

    def _build_reasoning(
        self, dependent_info: Dict, log_content: str
    ) -> str:
        """构建建议理由"""
        if dependent_info.get("workflows"):
            workflow_names = []
            for wf in dependent_info["workflows"]:
                if wf.get("definition_name"):
                    workflow_names.append(wf["definition_name"])
                elif wf.get("definition_code"):
                    workflow_names.append(f"工作流{wf['definition_code']}")

            if workflow_names:
                return (
                    f"DEPENDENT 任务检查依赖工作流 [{', '.join(workflow_names)}] 的执行状态失败。"
                    f"真正的错误在依赖工作流的失败任务中，需要查看依赖工作流实例的任务日志。"
                )

        if "FAILED" in log_content:
            return (
                "DEPENDENT 任务依赖检查失败。"
                "请检查 DolphinScheduler 控制台，查看依赖的工作流执行状态和失败任务。"
            )

        return "DEPENDENT 任务失败，建议查看 DolphinScheduler 控制台获取依赖工作流详情"

    def _build_llm_hint(self, dependent_info: Dict) -> str:
        """构建 LLM 提示"""
        if dependent_info.get("workflows"):
            workflows = dependent_info["workflows"]
            workflow_names = []
            for wf in workflows:
                if wf.get("definition_name"):
                    workflow_names.append(wf["definition_name"])
                elif wf.get("definition_code"):
                    workflow_names.append(f"定义{wf['definition_code']}")

            if workflow_names:
                return (
                    f"请查看依赖工作流 {', '.join(workflow_names)} 的最近失败实例，"
                    f"获取具体失败任务日志进行错误分析"
                )

        return "请查看 DolphinScheduler 控制台，获取依赖工作流的失败任务详情"

    def _track_dependent_workflow_failure(
        self, dependent_info: Dict, context: AlertContext
    ) -> Dict[str, Any]:
        """
        追踪依赖工作流的失败任务（可选，需要 dsctl 连接）

        追踪流程：
        1. 获取依赖工作流的 definitionCode 和 projectCode
        2. 根据告警时间计算查询时间范围（前后1小时）
        3. 查询该工作流在时间范围内的实例
        4. 找到失败实例并获取失败任务

        Args:
            dependent_info: 依赖工作流信息
            context: 告警上下文

        Returns:
            {
                "tracked": True/False,
                "failed_workflow_name": 失败的依赖工作流名称,
                "failed_tasks": 失败任务列表,
                "error_hint": 错误提示,
            }
        """
        result = {
            "tracked": False,
            "failed_workflow_name": None,
            "failed_tasks": [],
            "failed_instance_id": None,
            "error_hint": None,
        }

        workflows = dependent_info.get("workflows", [])
        if not workflows:
            result["error_hint"] = "无法从日志中提取依赖工作流信息，请手动在控制台查看"
            return result

        try:
            from ...integrations.dsctl_wrapper import DSCLIClient
            from datetime import datetime, timedelta
            import os

            api_url = os.environ.get("DS_API_URL")
            api_token = os.environ.get("DS_API_TOKEN")

            if not api_url or not api_token:
                result["error_hint"] = (
                    "未配置 DS_API_URL 或 DS_API_TOKEN，无法自动追踪依赖工作流。"
                    "请在 DolphinScheduler 控制台手动查看依赖工作流的失败实例。"
                )
                return result

            dsctl = DSCLIClient(api_url=api_url, api_token=api_token)

            # 计算查询时间范围：告警时间前后6小时
            alert_time = None
            if hasattr(context, "alert_info"):
                alert_time = context.alert_info.start_time or context.alert_info.end_time

            start_time_str = None
            end_time_str = None
            if alert_time:
                start_time = alert_time - timedelta(hours=6)
                end_time = alert_time + timedelta(hours=6)
                start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
                end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            # 遍历所有依赖工作流，查找失败实例
            for wf in workflows:
                definition_code = wf.get("definition_code")
                project_code = wf.get("project_code")

                if not definition_code or not project_code:
                    continue

                # 查询该工作流在时间范围内的实例（优先查询失败状态）
                instances_result = dsctl.list_workflow_instances(
                    project_code, definition_code,
                    page_size=10,
                    start_time=start_time_str,
                    end_time=end_time_str,
                    state="FAILURE"
                )

                if not instances_result.success:
                    # 尝试不带状态过滤
                    instances_result = dsctl.list_workflow_instances(
                        project_code, definition_code,
                        page_size=10,
                        start_time=start_time_str,
                        end_time=end_time_str
                    )

                if not instances_result.success:
                    continue

                try:
                    instances = json.loads(instances_result.stdout)
                    if isinstance(instances, dict) and "data" in instances:
                        instances = instances["data"]
                    elif isinstance(instances, dict) and "totalList" in instances:
                        instances = instances["totalList"]

                    # 找到失败实例
                    for inst in instances:
                        if inst.get("state") == "FAILURE":
                            result["failed_workflow_name"] = inst.get("name", inst.get("processDefinitionName", ""))
                            result["failed_instance_id"] = inst.get("id")
                            result["tracked"] = True

                            # 获取失败任务
                            digest_result = dsctl.workflow_instance_digest(inst.get("id"))
                            if digest_result.success:
                                digest = json.loads(digest_result.stdout)
                                failed_tasks = digest.get("failedTasks", [])
                                for task in failed_tasks:
                                    task_name = task.get("name", "")
                                    if task_name:
                                        result["failed_tasks"].append(task_name)
                            break

                    if result["tracked"]:
                        break

                except json.JSONDecodeError:
                    continue

        except ImportError:
            result["error_hint"] = "dsctl_wrapper 模块未安装，无法自动追踪依赖工作流"
        except Exception as e:
            result["error_hint"] = f"追踪依赖工作流时发生异常: {str(e)[:100]}"

        return result


__all__ = ["DependentSkill"]