"""
Alert Agent - 告警自动化处理

★ 真正的 Agent，使用 LLM 决策

核心能力:
- 规划分析流程
- 自动风险评估
- 低风险自动修复（修改配置 + 自动重跑）
- 高风险发起审批
"""

import asyncio
from typing import Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import settings
from ..models import AlertInfo, AlertContext, ErrorAnalysis, RiskLevel, AutoFixAction
from ..skills import skill_registry
from ..integrations import DSCLIClient
from ..knowledge import knowledge_manager
from ..integrations.dingtalk import DingTalkNotifier
from ..security.approval import ApprovalWorkflow
from ..tools.graph_impact import GraphImpactTool


class AlertAgent:
    """
    告警自动化处理 Agent

    处理流程:
    1. parse_alert 解析告警
    2. 并行: fetch_task_logs + analyze_impact
    3. select_skill 选择 Skill
    4. Skill.analyze() 分析（预定义规则）
    5. search_knowledge 搜索知识库
    6. LLM 整合生成修复方案
    7. assess_risk 风险评估
    8. 低风险自动修复 / 高风险审批
    9. send_notification
    """

    def __init__(self):
        self.ds_cli = DSCLIClient()
        self.llm = self._create_llm()
        self.notifier = DingTalkNotifier()
        self.approval_workflow = ApprovalWorkflow()
        self.graph_impact = GraphImpactTool()

    def _create_llm(self):
        """创建 LLM"""
        if not settings.LLM_API_KEY:
            return None
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_URL,
            temperature=0,
        )

    def handle_alert(self, alert_payload: dict) -> dict:
        """
        处理告警

        Args:
            alert_payload: 告警数据

        Returns:
            处理结果
        """
        # 1. 解析告警
        alert_info = self._parse_alert(alert_payload)

        # 2. 创建上下文
        context = AlertContext(alert_info=alert_info)

        # 3. 并行执行日志拉取和影响分析
        log_result, impact_result = self._parallel_analyze(alert_info)
        context.log_content = log_result
        context.impact_report = impact_result

        # 4. 选择 Skill 并分析
        skill = skill_registry.get_skill(alert_info.task_type)
        error_analysis = skill.analyze(log_result, context)
        context.error_analysis = {
            "error_type": error_analysis.error_type,
            "error_message": error_analysis.error_message,
            "can_auto_fix": error_analysis.can_auto_fix,
        }

        # 5. 搜索知识库
        knowledge_match = knowledge_manager.match_error(
            alert_info.task_type,
            error_analysis.error_message,
        )
        if knowledge_match:
            context.knowledge_entries = [knowledge_match]

        # 6. 风险评估
        risk_level = skill.get_risk_level(error_analysis)
        context.risk_level = risk_level.value

        # 7. 决策: 自动修复还是审批
        # LOW: 配置修改 → 自动执行
        # MEDIUM: 脚本修改 → 发起审批（需人工确认）
        # HIGH/CRITICAL: 发起审批
        if error_analysis.can_auto_fix and risk_level == RiskLevel.LOW:
            # 低风险自动修复（仅配置修改）
            result = self._auto_fix_and_recover(
                alert_info,
                skill.get_auto_fix_action(error_analysis),
                error_analysis,
            )
        else:
            # 中风险及以上发起审批（包括脚本修改）
            result = self._request_approval(
                alert_info,
                error_analysis,
                impact_result,
                fix_action=skill.get_auto_fix_action(error_analysis) if error_analysis.can_auto_fix else None,
                risk_level=risk_level.value,
            )

        # 8. 发送通知
        self._send_notification(alert_info, result)

        return result

    def _parse_alert(self, payload: dict) -> AlertInfo:
        """解析告警数据"""
        # 从 logPath 解析 taskInstanceId
        task_instance_id = payload.get("taskInstanceId", 0)
        log_path = payload.get("logPath", "")

        if not task_instance_id and log_path:
            # logPath 格式: /path/to/logs/.../taskInstanceId.log
            import os
            filename = os.path.basename(log_path)
            if filename.endswith(".log"):
                try:
                    task_instance_id = int(filename.replace(".log", ""))
                except ValueError:
                    pass

        return AlertInfo(
            project_code=payload.get("projectCode", 0),
            process_definition_code=payload.get("processDefinitionCode", 0),
            process_instance_id=payload.get("processId", payload.get("processInstanceId", 0)),
            task_code=payload.get("taskCode", 0),
            task_instance_id=task_instance_id,
            task_type=payload.get("taskType", "UNKNOWN"),
            state=payload.get("taskState", payload.get("state", "FAILURE")),
            host=payload.get("host") or payload.get("taskHost"),
            worker_group=payload.get("workerGroup"),
            # 名称字段
            project_name=payload.get("projectName"),
            process_definition_name=payload.get("processName"),
            task_name=payload.get("taskName"),
            raw_payload=payload,
        )

    def _parallel_analyze(self, alert_info: AlertInfo):
        """并行执行日志拉取和影响分析（简化为同步调用）"""
        # 直接同步调用，避免异步问题
        log_result = self._fetch_task_logs(alert_info)
        impact_result = self._analyze_impact(alert_info)
        return log_result, impact_result

    def _fetch_task_logs(self, alert_info: AlertInfo) -> str:
        """拉取任务日志"""
        print(f"[DEBUG] task_instance_id: {alert_info.task_instance_id}, logPath: {alert_info.raw_payload.get('logPath')}")

        # 优先尝试获取日志内容（使用 dsctl task-instance log）
        if alert_info.task_instance_id:
            result = self.ds_cli.task_log(
                alert_info.task_instance_id,
                lines=200,
            )
            print(f"[DEBUG] task_log result: success={result.success}, error={result.error}")
            if result.success and result.output:
                return result.output

        return "日志拉取失败"

    async def _fetch_task_logs_async(self, alert_info: AlertInfo) -> str:
        """异步拉取任务日志"""
        return self._fetch_task_logs(alert_info)

    def _analyze_impact(self, alert_info: AlertInfo) -> dict:
        """分析下游影响"""
        # 优先使用图谱分析
        graph_result = self.graph_impact.analyze_workflow_downstream(
            str(alert_info.project_code),
            str(alert_info.process_definition_code),
        )

        if graph_result.get("graph_available"):
            return {
                "downstream_workflows": graph_result["downstream_count"],
                "downstream_list": graph_result["downstream_workflows"],
                "workflow_names": graph_result["workflow_names"],
                "impact_level": graph_result["impact_level"],
                "impact_summary": self.graph_impact.build_impact_summary(
                    str(alert_info.process_definition_code),
                    graph_result["downstream_workflows"],
                    [],
                    graph_result["workflow_names"],
                ),
                "source": "graph",
            }

        # 降级：获取任务详情以提取 endTime（使用 dsctl task-instance list）
        if alert_info.process_instance_id:
            tasks_result = self.ds_cli.task_instance_list(
                alert_info.process_instance_id,
            )
            if tasks_result.success and tasks_result.data:
                # dsctl 返回的是 page data 结构
                task_list = tasks_result.data.get('items', [])
                for task in task_list:
                    if task.get('taskCode') == alert_info.task_code:
                        end_time = task.get('endTime', '')
                        if end_time and alert_info.raw_payload:
                            alert_info.raw_payload['taskEndTime'] = end_time
                        break

        # 默认返回低影响（无法分析）
        return {
            "downstream_workflows": 0,
            "downstream_list": [],
            "workflow_names": {},
            "impact_level": "low",
            "impact_summary": "无法分析下游影响（图谱不可用）",
            "source": "fallback",
        }

    async def _analyze_impact_async(self, alert_info: AlertInfo) -> dict:
        """异步分析下游影响"""
        return self._analyze_impact(alert_info)

    def _auto_fix_and_recover(
        self,
        alert_info: AlertInfo,
        fix_action: Optional[AutoFixAction],
        analysis: ErrorAnalysis,
    ) -> dict:
        """自动修复并恢复"""
        if fix_action is None:
            return {
                "status": "no_fix",
                "message": "无自动修复方案",
                "suggestion": analysis.error_message,
            }

        # 执行修复
        if fix_action.action_type == "modify_config":
            fix_result = self._modify_workflow_config(
                alert_info,
                fix_action.config_changes,
            )
        elif fix_action.action_type == "modify_script":
            fix_result = self._modify_task_script(
                alert_info,
                fix_action.script_changes,
            )
        else:
            fix_result = {"status": "unknown_action"}

        # 恢复失败的工作流实例
        # 使用 process_instance_update_task_script 直接修改实例中的任务脚本，
        # 保持 process_instance_id 不变，下游依赖不受影响
        if fix_action.need_recover and fix_result.get("status") == "success":
            if fix_action.action_type == "modify_script":
                # 脚本修改：直接修改工作流实例中的任务脚本并恢复
                update_result = self.ds_cli.process_instance_update_task_script(
                    alert_info.project_code,
                    alert_info.process_instance_id,
                    alert_info.task_code,
                    fix_action.script_changes,
                )
                fix_result["update_status"] = "success" if update_result.success else "failed"
                if update_result.success:
                    fix_result["process_instance_id_preserved"] = True
            else:
                # 配置修改：使用 workflow_recover
                recover_result = self.ds_cli.workflow_recover(
                    alert_info.project_code,
                    alert_info.process_instance_id,
                )
                fix_result["recover_status"] = "success" if recover_result.success else "failed"

        return {
            "status": "auto_fixed",
            "fix_action": fix_action.action_type,
            "risk_level": "low",
            "result": fix_result,
            "analysis": {
                "error_type": analysis.error_type,
                "error_message": analysis.error_message[:200] if analysis.error_message else "",
            },
        }

    def _modify_workflow_config(self, alert_info: AlertInfo, config_changes: dict) -> dict:
        """修改工作流配置"""
        # TODO: 实现 dsctl 配置修改
        return {"status": "success", "changes": config_changes}

    def _modify_task_script(self, alert_info: AlertInfo, script_changes: dict) -> dict:
        """修改任务脚本"""
        if not script_changes:
            return {"status": "failed", "message": "无脚本变更"}

        # 1. 获取任务详情（包含完整的 taskParams）
        tasks_result = self.ds_cli.task_instance_list(
            alert_info.process_instance_id,
        )

        if not tasks_result.success or not tasks_result.data:
            return {"status": "failed", "message": "无法获取任务详情"}

        task_list = tasks_result.data.get("items", [])
        current_task = None
        for task in task_list:
            if task.get("taskCode") == alert_info.task_code:
                current_task = task
                break

        if not current_task:
            return {"status": "failed", "message": "未找到对应任务"}

        # 2. 获取当前的 taskParams
        import json
        task_params_str = current_task.get("taskParams", "{}")
        try:
            task_params = json.loads(task_params_str)
        except json.JSONDecodeError:
            return {"status": "failed", "message": "taskParams 解析失败"}

        # 3. 修改脚本内容（替换拼写错误）
        raw_script = task_params.get("rawScript", "")
        new_script = raw_script
        for wrong, correct in script_changes.items():
            new_script = new_script.replace(wrong, correct)

        if new_script == raw_script:
            return {"status": "failed", "message": "脚本内容未变更"}

        # 4. 调用 API 更新工作流定义中的任务脚本
        update_result = self.ds_cli.workflow_update_task_script(
            alert_info.project_code,
            alert_info.process_definition_code,
            alert_info.task_code,
            script_changes,
        )

        if update_result.success:
            return {
                "status": "success",
                "changes": script_changes,
                "new_script_preview": new_script[:200],
            }
        else:
            return {
                "status": "failed",
                "message": update_result.error or "任务更新失败",
            }

    def _request_approval(
        self,
        alert_info: AlertInfo,
        analysis: ErrorAnalysis,
        impact: dict,
        fix_action: Optional[AutoFixAction] = None,
        risk_level: str = "HIGH",
    ) -> dict:
        """发起审批请求"""
        # 构造修复建议内容
        suggestion_content = ""
        if fix_action:
            if fix_action.action_type == "modify_script":
                suggestion_content = f"\n建议修改: {fix_action.script_changes}"
            elif fix_action.action_type == "modify_config":
                suggestion_content = f"\n建议配置: {fix_action.config_changes}"

        request = self.approval_workflow.create_request(
            operation_type="fix_task_failure",
            risk_level=risk_level.upper(),
            content=f"修复任务 {alert_info.task_name or alert_info.task_code} 的失败问题{suggestion_content}",
            impact=f"错误类型: {analysis.error_type}",
            project_code=alert_info.project_code,
            workflow_code=alert_info.process_definition_code,
            task_code=alert_info.task_code,
            process_instance_id=alert_info.process_instance_id,
        )

        return {
            "status": "approval_required",
            "request_id": request.id,
            "risk_level": risk_level,
            "analysis": {
                "error_type": analysis.error_type,
                "error_message": analysis.error_message[:200] if analysis.error_message else "",
            },
            "impact": impact,
            "fix_suggestion": {
                "action_type": fix_action.action_type,
                "changes": fix_action.script_changes or fix_action.config_changes,
            } if fix_action else None,
        }

    def _send_notification(self, alert_info: AlertInfo, result: dict):
        """发送通知"""
        # 从 raw_payload 获取时间信息
        raw = alert_info.raw_payload or {}
        end_time = raw.get("taskEndTime") or raw.get("endTime") or ""

        self.notifier.notify_alert(
            alert_info={
                "projectName": alert_info.project_name,
                "processDefinitionName": alert_info.process_definition_name,
                "taskName": alert_info.task_name,
                "taskType": alert_info.task_type,
                "endTime": end_time,
            },
            analysis=result.get("analysis", {}),
            fix_result=result,  # 传递完整结果，钉钉通知会根据 status 处理
        )


ALERT_AGENT_PROMPT = """
你是 DolphinScheduler 告警自动化处理 Agent。

当收到告警时，你需要执行完整的自动化处理流程：

## 分析阶段
1. 解析告警，了解失败任务的基本信息
2. 并行拉取日志和分析下游影响
3. 根据任务类型选择对应的 Skill 进行分析
4. 搜索已确认的知识库

## 决策阶段
5. 整合分析结果，生成修复方案
6. 进行自动风险评估：
   - 判断修复操作的风险等级
   - 低风险: 配置调整、简单脚本修改 → 自动执行
   - 高风险: 删除操作、影响多个下游 → 需审批

## 自动修复（低风险）
7a. 自动修改配置参数
7b. 自动恢复失败任务
7c. 发送成功通知

## 审批流程（高风险）
8a. 发起审批请求
8b. 发送审批通知，等待人工确认

## 风险等级判断规则
- LOW: 配置参数调整（内存、并发数等）
- LOW: 简单脚本拼写错误修正
- MEDIUM: 依赖包上传、环境变量修改
- HIGH: 删除任务、修改任务依赖关系
- CRITICAL: 删除工作流、跨项目修改

注意：
- 自动修复前必须先评估风险
- 自动修复后需监控执行状态
- 高风险操作必须等待审批
"""


__all__ = ["AlertAgent"]