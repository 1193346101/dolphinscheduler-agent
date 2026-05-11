"""
DEPENDENT Skill - 依赖检查失败追踪

DEPENDENT 任务检查其他工作流的执行状态，如果依赖的工作流失败，
DEPENDENT 任务也会失败，但日志中只有"依赖检查失败"的信息。

本 Skill 实现：
1. 从日志中提取依赖的工作流列表
2. 分析依赖结果 (FAILED)
3. 给出追踪指引：需要查看哪个依赖工作流失败
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

        # 6. 构建 llm_hint
        llm_hint = self._build_llm_hint(dependent_info)

        # 7. 确定错误类型
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
            },
        )

    def _extract_dependent_info(self, log_content: str) -> Dict[str, Any]:
        """
        从日志中提取依赖信息

        提取:
        - 依赖的工作流列表 (definitionCode, definitionName)
        - checkInterval
        - projectCode
        """
        info = {"workflows": []}

        # 方法1: 从 taskParams JSON 字符串中提取
        # taskParams 是一个 JSON 字符串，需要先解析外层 JSON，再解析 taskParams
        try:
            # 找到外层 JSON 对象
            start = log_content.find('{')
            if start == -1:
                return info

            brace_count = 0
            json_end = start
            for i, c in enumerate(log_content[start:], start):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            outer_json = json.loads(log_content[start:json_end])
            task_params_str = outer_json.get("taskParams", "")

            if task_params_str:
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
                            "cycle": item.get("cycle"),
                            "date_value": item.get("dateValue"),
                        }
                        info["workflows"].append(workflow)
                        info["project_code"] = item.get("projectCode")

        except (json.JSONDecodeError, ValueError):
            pass

        # 方法2: 从日志行中提取工作流名称
        # 格式: WorkflowName: xxx
        workflow_names = re.findall(r'WorkflowName\s*:\s*(.+)', log_content)
        for i, name in enumerate(workflow_names):
            if i < len(info["workflows"]):
                info["workflows"][i]["definition_name"] = name.strip()

        # 方法3: 从日志行中提取项目名称
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


__all__ = ["DependentSkill"]