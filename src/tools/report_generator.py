"""
错误分析报告生成器

生成完整的错误分析报告，包含：
- 分析过程（每个节点的输入/输出）
- Skill 预判结果
- LLM 分析结果（如果有）
- 资源数据（YARN/Spark History）
- 风险评估
- 修复建议
- 执行结果
- Token 消耗

报告格式：HTML（用户友好）+ JSON（程序可解析）
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class ReportGenerator:
    """错误分析报告生成器"""

    def __init__(self, report_dir: str = None):
        """
        初始化

        Args:
            report_dir: 报告存储目录（默认 data/reports）
        """
        self.report_dir = report_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "reports"
        )
        os.makedirs(self.report_dir, exist_ok=True)

    def generate_report(self, state: Dict[str, Any]) -> str:
        """
        生成错误分析报告

        Args:
            state: AgentState 完整状态（包含所有分析结果）

        Returns:
            报告 ID（用于查询）
        """
        # 生成报告 ID
        report_id = self._generate_report_id(state)

        # 创建报告目录
        report_path = os.path.join(
            self.report_dir,
            datetime.now().strftime("%Y-%m-%d"),
            str(state.get("workflow_code", "unknown")),
            report_id
        )
        os.makedirs(report_path, exist_ok=True)

        # 提取报告数据
        report_data = self._extract_report_data(state)

        # 保存 JSON 报告
        json_path = os.path.join(report_path, "report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # 生成 HTML 报告
        html_content = self._generate_html(report_data)
        html_path = os.path.join(report_path, "report.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return report_id

    def _generate_report_id(self, state: Dict[str, Any]) -> str:
        """生成报告 ID"""
        timestamp = datetime.now().strftime("%H%M%S")
        task_code = state.get("task_code", "0")
        return f"report_{timestamp}_{task_code}"

    def _extract_report_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """从 state 提取报告数据"""
        return {
            # 基本信息
            "basic_info": {
                "report_time": datetime.now().isoformat(),
                "project_name": state.get("project_name", ""),
                "project_code": state.get("project_code", ""),
                "workflow_name": state.get("workflow_name", ""),
                "workflow_code": state.get("workflow_code", ""),
                "task_name": state.get("task_name", ""),
                "task_code": state.get("task_code", ""),
                "task_type": state.get("task_type", ""),
                "process_instance_id": state.get("process_instance_id", 0),
                "error_time": state.get("error_time", ""),
                "is_sub_workflow": state.get("is_sub_workflow", False),
            },

            # 分析流程
            "analysis_process": {
                "error_patterns": state.get("error_patterns", []),
                "error_category": state.get("error_category", ""),
                "analysis_process_text": self._build_analysis_process_text(state),
            },

            # 错误分析结果
            "error_analysis": state.get("error_analysis", {}),

            # Skill 结果
            "skill_result": state.get("skill_result", {}),

            # 日志预处理结果
            "log_preprocess": {
                "driver_logs_length": len(state.get("driver_logs", "") or ""),
                "spark_logs_length": len(state.get("spark_logs", "") or ""),
                "yarn_logs_length": len(state.get("yarn_logs", "") or ""),
                "driver_logs_excerpt": (state.get("driver_logs", "") or "")[:500],
            },

            # 资源数据（如果有）
            "resource_data": {
                "data_metrics": state.get("error_analysis", {}).get("data_metrics", {}),
                "yarn_info": state.get("error_analysis", {}).get("yarn_info", {}),
                "spark_metrics": state.get("error_analysis", {}).get("spark_metrics", {}),
            },

            # 风险评估
            "risk_assessment": {
                "risk_level": state.get("risk_level", ""),
                "risk_factors": state.get("risk_factors", []),
                "downstream_tasks": state.get("downstream_tasks", 0),
                "downstream_list": state.get("downstream_list", []),
                "impact_summary": state.get("impact_summary", ""),
            },

            # 修复建议
            "suggested_actions": state.get("suggested_actions", []),

            # 执行结果
            "execution_result": {
                "executed_actions": state.get("executed_actions", []),
                "execution_results": state.get("execution_results", []),
                "execution_success": state.get("execution_success", False),
            },

            # Token 消耗
            "token_consumption": {
                "total": state.get("token_consumption", 0),
                "details": state.get("token_details", {}),
            },

            # 审批状态（如果有）
            "approval_status": state.get("approval_status", None),
        }

    def _build_analysis_process_text(self, state: Dict[str, Any]) -> str:
        """构建分析过程描述"""
        steps = []

        # Step 1: 解析告警
        steps.append("1. 解析告警: 提取 project_code, workflow_code, task_code, task_type")

        # Step 2: 获取日志
        driver_len = len(state.get("driver_logs", "") or "")
        spark_len = len(state.get("spark_logs", "") or "")
        yarn_len = len(state.get("yarn_logs", "") or "")
        steps.append(f"2. 获取日志: driver_logs={driver_len} chars, spark_logs={spark_len} chars, yarn_logs={yarn_len} chars")

        # Step 3: 日志预处理
        error_patterns = state.get("error_patterns", [])
        steps.append(f"3. 日志预处理: 提取 error_patterns={len(error_patterns)} 个")

        # Step 4: Skill 分析
        skill_result = state.get("skill_result", {})
        if skill_result:
            steps.append(f"4. Skill 分析: error_type={skill_result.get('error_type', 'unknown')}, confidence={skill_result.get('confidence', 0)}")

        # Step 5: LLM 分析（如果有）
        token_details = state.get("token_details", {})
        if token_details:
            steps.append(f"5. LLM 验证: Token 消耗={state.get('token_consumption', 0)}")

        # Step 6: 风险评估
        steps.append(f"6. 风险评估: risk_level={state.get('risk_level', 'unknown')}")

        # Step 7: 生成建议
        suggested_actions = state.get("suggested_actions", [])
        steps.append(f"7. 生成建议: {len(suggested_actions)} 个修复动作")

        return "\n".join(steps)

    def _generate_html(self, data: Dict[str, Any]) -> str:
        """生成 HTML 报告"""
        basic = data["basic_info"]
        process = data["analysis_process"]
        analysis = data["error_analysis"]
        risk = data["risk_assessment"]
        token = data["token_consumption"]

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>错误分析报告 - {basic['task_name']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a1a1a; border-bottom: 2px solid #1890ff; padding-bottom: 10px; }}
        h2 {{ color: #1890ff; margin-top: 30px; }}
        .section {{ margin: 20px 0; padding: 15px; background: #fafafa; border-radius: 4px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
        .info-item {{ padding: 8px; background: white; border: 1px solid #e8e8e8; }}
        .info-label {{ color: #666; font-size: 12px; }}
        .info-value {{ color: #1a1a1a; font-weight: bold; }}
        .error-box {{ background: #fff2f0; border: 1px solid #ffccc7; padding: 10px; border-radius: 4px; }}
        .success-box {{ background: #f6ffed; border: 1px solid #b7eb8f; padding: 10px; border-radius: 4px; }}
        .warning-box {{ background: #fffbe6; border: 1px solid #ffe58f; padding: 10px; border-radius: 4px; }}
        .process-step {{ margin: 5px 0; padding: 8px; background: white; border-left: 3px solid #1890ff; }}
        pre {{ background: #282c34; color: #abb2bf; padding: 15px; border-radius: 4px; overflow-x: auto; }}
        .token-stats {{ display: inline-block; background: #e6f7ff; padding: 5px 10px; border-radius: 4px; margin: 5px; }}
        .risk-low {{ color: #52c41a; }}
        .risk-medium {{ color: #faad14; }}
        .risk-high {{ color: #f5222d; }}
        .action-item {{ margin: 5px 0; padding: 10px; background: white; border: 1px solid #d9d9d9; }}
    </style>
</head>
<body>
<div class="container">
    <h1>🔍 DolphinScheduler Agent 错误分析报告</h1>
    <p>生成时间: {basic['report_time']}</p>

    <h2>📋 基本信息</h2>
    <div class="section">
        <div class="info-grid">
            <div class="info-item"><span class="info-label">项目</span><br><span class="info-value">{basic['project_name']} ({basic['project_code']})</span></div>
            <div class="info-item"><span class="info-label">工作流</span><br><span class="info-value">{basic['workflow_name']} ({basic['workflow_code']})</span></div>
            <div class="info-item"><span class="info-label">任务</span><br><span class="info-value">{basic['task_name']} ({basic['task_code']})</span></div>
            <div class="info-item"><span class="info-label">任务类型</span><br><span class="info-value">{basic['task_type']}</span></div>
            <div class="info-item"><span class="info-label">实例 ID</span><br><span class="info-value">{basic['process_instance_id']}</span></div>
            <div class="info-item"><span class="info-label">错误时间</span><br><span class="info-value">{basic['error_time']}</span></div>
        </div>
    </div>

    <h2>🔄 分析流程</h2>
    <div class="section">
        {self._render_process_steps(process['analysis_process_text'])}
    </div>

    <h2>🎯 错误分析结果</h2>
    <div class="section">
        <div class="error-box">
            <strong>错误类型:</strong> {analysis.get('error_type', 'unknown')}<br>
            <strong>错误分类:</strong> {analysis.get('category', 'UNKNOWN')}<br>
            <strong>分析过程:</strong> {analysis.get('analysis_process', 'N/A')}<br>
            <strong>推理依据:</strong> {analysis.get('reasoning', 'N/A')}
        </div>
        <h3>原始日志片段</h3>
        <pre>{data['log_preprocess']['driver_logs_excerpt']}</pre>
    </div>

    <h2>📊 资源数据</h2>
    <div class="section">
        {self._render_resource_data(data['resource_data'])}
    </div>

    <h2>⚠️ 风险评估</h2>
    <div class="section {self._get_risk_box_class(risk['risk_level'])}">
        <strong>风险等级:</strong> <span class="{self._get_risk_class(risk['risk_level'])}">{risk['risk_level']}</span><br>
        <strong>下游任务数:</strong> {risk['downstream_tasks']}<br>
        <strong>风险因素:</strong> {', '.join(risk['risk_factors']) or '无'}<br>
        <strong>影响摘要:</strong> {risk['impact_summary'] or '无'}
    </div>

    <h2>💡 修复建议</h2>
    <div class="section">
        {self._render_suggested_actions(data['suggested_actions'])}
    </div>

    <h2>✅ 执行结果</h2>
    <div class="section {self._get_execution_box_class(data['execution_result']['execution_success'])}">
        <strong>执行状态:</strong> {data['execution_result']['execution_success'] and '成功' or '失败'}<br>
        {self._render_execution_results(data['execution_result']['execution_results'])}
    </div>

    <h2>📈 Token 消耗统计</h2>
    <div class="section">
        <span class="token-stats">总计: {token['total']} tokens</span>
        {self._render_token_details(token['details'])}
    </div>
</div>
</body>
</html>"""
        return html

    def _render_process_steps(self, process_text: str) -> str:
        """渲染分析流程步骤"""
        steps = process_text.split("\n")
        html = ""
        for step in steps:
            if step:
                html += f"<div class='process-step'>{step}</div>"
        return html

    def _render_resource_data(self, resource: Dict) -> str:
        """渲染资源数据"""
        if not resource.get("data_metrics") and not resource.get("yarn_info"):
            return "<p>无资源数据（本次分析未调用 YARN/Spark History API）</p>"

        html = ""
        if resource.get("data_metrics"):
            html += "<strong>数据指标:</strong><br>"
            for key, value in resource["data_metrics"].items():
                html += f"- {key}: {value}<br>"

        if resource.get("yarn_info"):
            html += "<strong>YARN 信息:</strong><br>"
            for key, value in resource["yarn_info"].items():
                html += f"- {key}: {value}<br>"

        return html

    def _get_risk_class(self, level: str) -> str:
        """获取风险等级 CSS class"""
        if level == "LOW":
            return "risk-low"
        elif level == "MEDIUM":
            return "risk-medium"
        else:
            return "risk-high"

    def _get_risk_box_class(self, level: str) -> str:
        """获取风险 box CSS class"""
        if level == "LOW":
            return "success-box"
        elif level == "MEDIUM":
            return "warning-box"
        else:
            return "error-box"

    def _render_suggested_actions(self, actions: list) -> str:
        """渲染修复建议"""
        if not actions:
            return "<p>无修复建议</p>"

        html = ""
        for i, action in enumerate(actions, 1):
            action_type = action.get("action_type", "unknown")
            desc = action.get("description", "")
            risk = action.get("risk_level", "")

            html += f"""
<div class="action-item">
    <strong>{i}. {action_type}</strong> (风险: {risk})<br>
    {desc}
    {self._render_action_changes(action)}
</div>"""
        return html

    def _render_action_changes(self, action: Dict) -> str:
        """渲染动作变更内容"""
        if action.get("config_changes"):
            changes = action["config_changes"]
            return f"<br><strong>配置变更:</strong> {json.dumps(changes, ensure_ascii=False)}"
        if action.get("script_changes"):
            changes = action["script_changes"]
            return f"<br><strong>脚本变更:</strong> {json.dumps(changes, ensure_ascii=False)}"
        return ""

    def _get_execution_box_class(self, success: bool) -> str:
        """获取执行结果 box class"""
        return "success-box" if success else "error-box"

    def _render_execution_results(self, results: list) -> str:
        """渲染执行结果"""
        if not results:
            return ""

        html = "<br><strong>执行详情:</strong><br>"
        for r in results:
            action = r.get("action", {})
            status = r.get("status", "unknown")
            output = r.get("output", "")[:100]
            html += f"- {action.get('action_type', 'unknown')}: {status} - {output}<br>"
        return html

    def _render_token_details(self, details: Dict) -> str:
        """渲染 Token 详情"""
        if not details:
            return ""

        html = ""
        for name, detail in details.items():
            input_t = detail.get("input_tokens", 0)
            output_t = detail.get("output_tokens", 0)
            html += f'<span class="token-stats">{name}: input={input_t}, output={output_t}</span>'
        return html

    def get_report_path(self, report_id: str, workflow_code: str, date: str = None) -> Optional[str]:
        """
        获取报告路径

        Args:
            report_id: 报告 ID
            workflow_code: 工作流 code
            date: 日期（默认今天）

        Returns:
            报告目录路径或 None
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        report_path = os.path.join(self.report_dir, date, str(workflow_code), report_id)
        if os.path.exists(report_path):
            return report_path
        return None


__all__ = ["ReportGenerator"]