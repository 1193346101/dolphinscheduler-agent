"""
Timeout Skill - 工作流超时告警分析专家

Skill 是"智能分析师":
- 识别超时根因（任务重试、资源等待、执行缓慢等）
- RESOURCE_SUGGESTED: 集群过载，智能计算资源建议
- KNOWN_NEEDS_LLM: 任务重试等，给 LLM 提供上下文
- UNKNOWN: 无匹配，调用 LLM 深度分析

重构版: 使用 patterns.md 定义超时类型，符合 anthropics/skills 规范
"""

from pathlib import Path
from typing import Optional, Dict, Any, List

from ...models.analysis import ErrorAnalysis, ErrorCategory
from ...models.risk import RiskLevel
from ...models.alert import AlertContext
from ..base import BaseSkill
from ..common.pattern_matcher import PatternMatcher


class TimeoutSkill(BaseSkill):
    """
    工作流超时分析 Skill - 重构版

    超时分析特殊性：基于指标计算而非正则匹配
    使用 patterns.md 定义超时类型和阈值配置
    """

    skill_name = "timeout"
    task_types = ["WORKFLOW", "TASK_TIMEOUT"]

    # Pattern Matcher（延迟初始化）
    _matcher: Optional[PatternMatcher] = None

    # 默认阈值配置
    DEFAULT_THRESHOLDS = {
        "task_retry": {
            "min_retry_count": 3,
            "retry_time_ratio": 0.3,
        },
        "execution_time": {
            "slow_multiplier": 3,
        },
        "queue_wait": {
            "long_multiplier": 2,
            "min_absolute_seconds": 300,
        },
        "cluster": {
            "utilization_threshold": 85,
            "pending_containers": 100,
        },
        "queue": {
            "capacity_threshold": 90,
            "pending_apps": 10,
        },
    }

    def _get_matcher(self) -> PatternMatcher:
        """获取模式匹配器"""
        if self._matcher is None:
            patterns_file = str(Path(__file__).parent / "patterns.md")
            self._matcher = PatternMatcher("timeout", patterns_file)
        return self._matcher

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """
        分析超时告警 - 基于指标计算

        Args:
            log_content: 日志内容（包含超时任务信息）
            context: 告警上下文（包含任务列表、集群指标等）

        Returns:
            ErrorAnalysis 分析结果
        """
        # 1. 从上下文提取任务信息和集群指标
        tasks = self._extract_tasks(context)
        historical_metrics = self._extract_historical_metrics(context)
        cluster_metrics = self._extract_cluster_metrics(context)

        # 2. 计算超时指标
        timeout_metrics = self._calculate_timeout_metrics(tasks, historical_metrics)

        # 3. 基于指标判断超时类型
        match_result = self._match_timeout_type(timeout_metrics, cluster_metrics)

        # 4. 构建 ErrorAnalysis
        initial = self._build_analysis(
            match_result,
            tasks,
            timeout_metrics,
            cluster_metrics,
        )

        # 5. UNKNOWN -> LLM fallback
        if initial.category == ErrorCategory.UNKNOWN:
            return self.analyze_with_llm_fallback(
                self._build_timeout_log(tasks, timeout_metrics),
                initial,
                context
            )

        return initial

    def _extract_tasks(self, context: AlertContext) -> List[Dict[str, Any]]:
        """从上下文提取任务列表"""
        # 从 raw_payload 或其他字段提取
        raw_payload = context.alert_info.raw_payload if context.alert_info else {}
        tasks = raw_payload.get("tasks", [])
        if not tasks:
            # 尝试从其他位置提取
            tasks = context.alert_info.raw_payload.get("workflow_tasks", [])
        return tasks

    def _extract_historical_metrics(self, context: AlertContext) -> Dict[str, Any]:
        """提取历史指标"""
        raw_payload = context.alert_info.raw_payload if context.alert_info else {}
        return raw_payload.get("historical_metrics", {
            "avg_queue_wait_time": 120,
            "avg_execution_time": 600,
            "avg_data_size": 1000,
        })

    def _extract_cluster_metrics(self, context: AlertContext) -> Dict[str, Any]:
        """提取集群指标"""
        raw_payload = context.alert_info.raw_payload if context.alert_info else {}
        return raw_payload.get("cluster_metrics", {
            "memory_utilization": 50,
            "vcore_utilization": 50,
            "pending_containers": 20,
            "queue_used_capacity": 60,
            "pending_apps": 5,
        })

    def _calculate_timeout_metrics(
        self,
        tasks: List[Dict[str, Any]],
        historical: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        计算超时相关指标

        Returns:
            指标字典，用于匹配超时类型
        """
        metrics = {
            "max_retry_count": 0,
            "retry_task_name": None,
            "retry_duration_total": 0,
            "max_execution_time": 0,
            "slow_task_name": None,
            "max_queue_wait_time": 0,
            "queue_wait_task_name": None,
            "upstream_delay": False,
            "data_volume_spike": False,
            "task_count": len(tasks),
            "avg_execution_time": historical.get("avg_execution_time", 600),
            "avg_queue_wait_time": historical.get("avg_queue_wait_time", 120),
            "avg_data_size": historical.get("avg_data_size", 1000),
        }

        if not tasks:
            return metrics

        # 计算重试指标
        retry_tasks = [t for t in tasks if t.get("retry_count", 0) > 0]
        if retry_tasks:
            max_retry_task = max(retry_tasks, key=lambda t: t.get("retry_count", 0))
            metrics["max_retry_count"] = max_retry_task.get("retry_count", 0)
            metrics["retry_task_name"] = max_retry_task.get("name")
            # 估算重试总时间（假设每次重试间隔60秒）
            retry_interval = max_retry_task.get("retry_interval", 60)
            metrics["retry_duration_total"] = metrics["max_retry_count"] * retry_interval

        # 计算执行时间指标
        for task in tasks:
            execution_time = self._calculate_execution_time(task)
            if execution_time > metrics["max_execution_time"]:
                metrics["max_execution_time"] = execution_time
                metrics["slow_task_name"] = task.get("name")

        # 计算排队时间指标
        for task in tasks:
            queue_wait = task.get("queue_wait_time", 0)
            if queue_wait > metrics["max_queue_wait_time"]:
                metrics["max_queue_wait_time"] = queue_wait
                metrics["queue_wait_task_name"] = task.get("name")

        # 检查上游延迟（第一个任务的执行时间）
        if tasks and metrics["max_execution_time"] > metrics["avg_execution_time"] * 2:
            metrics["upstream_delay"] = True

        # 检查数据量激增（从任务配置中提取）
        max_data_size = max(t.get("data_size", 0) for t in tasks)
        if max_data_size > metrics["avg_data_size"] * 5:
            metrics["data_volume_spike"] = True

        return metrics

    def _calculate_execution_time(self, task: Dict[str, Any]) -> int:
        """计算任务执行时间"""
        start = task.get("start_time")
        end = task.get("end_time")
        if start and end:
            try:
                from datetime import datetime
                start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                return int((end_dt - start_dt).total_seconds())
            except:
                pass
        return task.get("execution_time", 0)

    def _match_timeout_type(
        self,
        timeout_metrics: Dict[str, Any],
        cluster_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        基于指标匹配超时类型

        Returns:
            match_result 包含:
            - error_type: 超时类型
            - category: 类别
            - hint: 提示
            - confidence: 置信度
        """
        thresholds = self.DEFAULT_THRESHOLDS

        # 优先级1: 检查集群过载（RESOURCE_SUGGESTED）
        cluster_util = max(
            cluster_metrics.get("memory_utilization", 0),
            cluster_metrics.get("vcore_utilization", 0)
        )
        pending_containers = cluster_metrics.get("pending_containers", 0)

        if cluster_util > thresholds["cluster"]["utilization_threshold"]:
            return {
                "error_type": "cluster_overloaded",
                "category": "RESOURCE_SUGGESTED",
                "hint": f"集群利用率过高 ({cluster_util}%)，建议检查YARN队列配置或降低并发任务数",
                "confidence": 0.85,
                "metrics": {"cluster_utilization": cluster_util},
            }

        if pending_containers > thresholds["cluster"]["pending_containers"]:
            return {
                "error_type": "cluster_overloaded",
                "category": "RESOURCE_SUGGESTED",
                "hint": f"待分配容器过多 ({pending_containers})，集群资源紧张",
                "confidence": 0.80,
                "metrics": {"pending_containers": pending_containers},
            }

        # 优先级2: 检查队列拥堵（RESOURCE_SUGGESTED）
        queue_capacity = cluster_metrics.get("queue_used_capacity", 0)
        pending_apps = cluster_metrics.get("pending_apps", 0)

        if queue_capacity > thresholds["queue"]["capacity_threshold"]:
            return {
                "error_type": "queue_congested",
                "category": "RESOURCE_SUGGESTED",
                "hint": f"YARN队列容量使用率过高 ({queue_capacity}%)，建议调整队列容量或错峰调度",
                "confidence": 0.80,
                "metrics": {"queue_used_capacity": queue_capacity},
            }

        if pending_apps > thresholds["queue"]["pending_apps"]:
            return {
                "error_type": "queue_congested",
                "category": "RESOURCE_SUGGESTED",
                "hint": f"队列待处理应用过多 ({pending_apps})，建议错峰调度",
                "confidence": 0.75,
                "metrics": {"pending_apps": pending_apps},
            }

        # 优先级3: 检查任务重试（KNOWN_NEEDS_LLM）
        retry_count = timeout_metrics.get("max_retry_count", 0)
        retry_task = timeout_metrics.get("retry_task_name")

        if retry_count >= thresholds["task_retry"]["min_retry_count"]:
            return {
                "error_type": "task_retry_timeout",
                "category": "KNOWN_NEEDS_LLM",
                "hint": f"任务 {retry_task} 重试 {retry_count} 次导致超时，请分析任务错误日志确定失败原因",
                "confidence": 0.90,
                "metrics": {
                    "retry_count": retry_count,
                    "task_name": retry_task,
                    "retry_duration": timeout_metrics.get("retry_duration_total"),
                },
            }

        # 优先级4: 检查排队等待过长（KNOWN_NEEDS_LLM）
        queue_wait = timeout_metrics.get("max_queue_wait_time", 0)
        queue_wait_task = timeout_metrics.get("queue_wait_task_name")
        avg_queue_wait = timeout_metrics.get("avg_queue_wait_time", 120)

        queue_ratio = queue_wait / max(avg_queue_wait, 1)
        if queue_wait > thresholds["queue_wait"]["min_absolute_seconds"] and \
           queue_ratio > thresholds["queue_wait"]["long_multiplier"]:
            return {
                "error_type": "queue_wait_long",
                "category": "KNOWN_NEEDS_LLM",
                "hint": f"任务 {queue_wait_task} 排队等待 {queue_wait} 秒（历史均值 {avg_queue_wait} 秒的 {queue_ratio:.1f} 倍），请检查集群资源状态",
                "confidence": 0.85,
                "metrics": {
                    "queue_wait_time": queue_wait,
                    "historical_avg": avg_queue_wait,
                    "task_name": queue_wait_task,
                },
            }

        # 优先级5: 检查执行时间过长（KNOWN_NEEDS_LLM）
        execution_time = timeout_metrics.get("max_execution_time", 0)
        slow_task = timeout_metrics.get("slow_task_name")
        avg_execution = timeout_metrics.get("avg_execution_time", 600)

        exec_ratio = execution_time / max(avg_execution, 1)
        if exec_ratio > thresholds["execution_time"]["slow_multiplier"]:
            return {
                "error_type": "task_execution_slow",
                "category": "KNOWN_NEEDS_LLM",
                "hint": f"任务 {slow_task} 执行时间 {execution_time} 秒（历史均值 {avg_execution} 秒的 {exec_ratio:.1f} 倍），请分析日志判断是否有性能问题或数据量变化",
                "confidence": 0.80,
                "metrics": {
                    "execution_time": execution_time,
                    "historical_avg": avg_execution,
                    "task_name": slow_task,
                },
            }

        # 优先级6: 检查数据量激增（KNOWN_NEEDS_LLM）
        if timeout_metrics.get("data_volume_spike"):
            return {
                "error_type": "data_volume_spike",
                "category": "KNOWN_NEEDS_LLM",
                "hint": "数据量激增导致处理时间变长，请分析数据来源变化或调整资源配置",
                "confidence": 0.70,
                "metrics": {"data_volume_spike": True},
            }

        # 优先级7: 检查上游延迟传导（KNOWN_NEEDS_LLM）
        if timeout_metrics.get("upstream_delay"):
            return {
                "error_type": "upstream_delay",
                "category": "KNOWN_NEEDS_LLM",
                "hint": "上游任务延迟传导，请分析上游任务超时原因",
                "confidence": 0.65,
                "metrics": {"upstream_delay": True},
            }

        # 未匹配 -> UNKNOWN
        return {
            "error_type": "unknown",
            "category": "UNKNOWN",
            "hint": "超时原因未知，建议检查任务执行日志和网络状态",
            "confidence": 0.0,
            "metrics": timeout_metrics,
        }

    def _build_analysis(
        self,
        match_result: Dict[str, Any],
        tasks: List[Dict[str, Any]],
        timeout_metrics: Dict[str, Any],
        cluster_metrics: Dict[str, Any],
    ) -> ErrorAnalysis:
        """构建 ErrorAnalysis"""
        category = ErrorCategory(match_result.get("category", "UNKNOWN"))

        # 构建分析过程
        analysis_parts = []
        if tasks:
            analysis_parts.append(f"分析 {len(tasks)} 个任务")
        if timeout_metrics.get("max_retry_count", 0) > 0:
            analysis_parts.append(f"发现重试任务")
        if timeout_metrics.get("max_queue_wait_time", 0) > 300:
            analysis_parts.append(f"发现长时间排队")
        if cluster_metrics:
            util = max(cluster_metrics.get("memory_utilization", 0),
                      cluster_metrics.get("vcore_utilization", 0))
            analysis_parts.append(f"集群利用率 {util}%")

        analysis_process = ", ".join(analysis_parts) if analysis_parts else "基于指标计算"

        # 构建分析说明
        reasoning = match_result.get("hint", "")

        # 构建 llm_hint（KNOWN_NEEDS_LLM 类型）
        llm_hint = None
        if category == ErrorCategory.KNOWN_NEEDS_LLM:
            llm_hint = match_result.get("hint")

        # 构建 skill_suggestion（RESOURCE_SUGGESTED 类型）
        skill_suggestion = None
        if category == ErrorCategory.RESOURCE_SUGGESTED:
            skill_suggestion = self._build_resource_suggestion(match_result, cluster_metrics)

        # 构建 quick_fix（AUTO_FIXABLE 类型）
        quick_fix = None
        if category == ErrorCategory.AUTO_FIXABLE:
            quick_fix = self._build_quick_fix(match_result)

        return ErrorAnalysis(
            error_type=match_result.get("error_type", "unknown"),
            category=category,
            error_message=self._build_timeout_summary(tasks, timeout_metrics),
            matched_pattern=None,  # 超时分析不使用正则模式
            quick_fix=quick_fix,
            skill_suggestion=skill_suggestion,
            llm_hint=llm_hint,
            original_log_error=self._build_timeout_log(tasks, timeout_metrics),
            analysis_process=analysis_process,
            reasoning=reasoning,
            data_metrics={
                "timeout_metrics": timeout_metrics,
                "cluster_metrics": cluster_metrics,
            },
        )

    def _build_resource_suggestion(
        self,
        match_result: Dict[str, Any],
        cluster_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建资源建议"""
        error_type = match_result.get("error_type")

        if error_type == "cluster_overloaded":
            return {
                "action": "reduce_concurrency",
                "reasoning": f"集群利用率 {cluster_metrics.get('memory_utilization', 0)}%，建议降低并发任务数",
                "suggested_max_concurrent": max(5, 20 - cluster_metrics.get("running_applications", 10)),
            }

        elif error_type == "queue_congested":
            return {
                "action": "adjust_queue_capacity",
                "reasoning": f"队列容量使用率 {cluster_metrics.get('queue_used_capacity', 0)}%",
                "suggested_capacity_increase": 20,  # 建议增加20%容量
            }

        elif error_type in ["memory_pressure", "vcore_pressure"]:
            return {
                "action": "add_resources",
                "reasoning": match_result.get("hint"),
                "suggested_action": "增加集群节点或调整任务资源配置",
            }

        return {"reasoning": match_result.get("hint")}

    def _build_quick_fix(self, match_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """构建快速修复方案"""
        error_type = match_result.get("error_type")

        if error_type == "timeout_config_too_short":
            return {
                "action_type": "modify_config",
                "config_changes": {
                    "timeout": "建议增加到当前值的1.5倍",
                },
            }

        elif error_type == "retry_config_too_aggressive":
            return {
                "action_type": "modify_config",
                "config_changes": {
                    "retry_interval": "建议增加到60秒",
                },
            }

        return None

    def _build_timeout_summary(
        self,
        tasks: List[Dict[str, Any]],
        metrics: Dict[str, Any]
    ) -> str:
        """构建超时摘要"""
        if not tasks:
            return "无任务信息"

        parts = []
        parts.append(f"任务数: {len(tasks)}")

        retry_count = metrics.get("max_retry_count", 0)
        if retry_count > 0:
            retry_task = metrics.get("retry_task_name")
            parts.append(f"重试: {retry_task} ({retry_count}次)")

        queue_wait = metrics.get("max_queue_wait_time", 0)
        if queue_wait > 60:
            queue_task = metrics.get("queue_wait_task_name")
            parts.append(f"排队: {queue_task} ({queue_wait}s)")

        return " | ".join(parts)

    def _build_timeout_log(
        self,
        tasks: List[Dict[str, Any]],
        metrics: Dict[str, Any]
    ) -> str:
        """构建超时日志供LLM分析"""
        lines = []
        lines.append("=== Workflow Timeout Analysis ===")
        lines.append(f"Tasks: {len(tasks)}")

        for task in tasks[:5]:  # 最多显示5个任务
            name = task.get("name", "unknown")
            status = task.get("status", "unknown")
            retry = task.get("retry_count", 0)
            queue = task.get("queue_wait_time", 0)
            lines.append(f"  - {name}: status={status}, retry={retry}, queue_wait={queue}s")

        lines.append(f"Max retry: {metrics.get('max_retry_count', 0)}")
        lines.append(f"Max queue wait: {metrics.get('max_queue_wait_time', 0)}s")
        lines.append(f"Max execution time: {metrics.get('max_execution_time', 0)}s")

        return "\n".join(lines)

    def suggest(self, analysis: ErrorAnalysis) -> List[str]:
        """补充建议"""
        suggestions = []

        if analysis.error_type == "task_retry_timeout":
            suggestions.append("检查失败任务的日志，确定错误原因")
            suggestions.append("考虑调整重试间隔，避免频繁重试占用时间")

        elif analysis.error_type == "queue_wait_long":
            suggestions.append("检查YARN集群资源状态")
            suggestions.append("考虑错峰调度，避开高峰时段")

        elif analysis.error_type == "task_execution_slow":
            suggestions.append("分析任务性能瓶颈（数据量、代码效率）")
            suggestions.append("考虑增加任务资源配置")

        elif analysis.error_type == "cluster_overloaded":
            suggestions.append("降低并发任务数")
            suggestions.append("调整任务优先级，优先执行关键任务")

        elif analysis.error_type == "data_volume_spike":
            suggestions.append("分析数据来源变化")
            suggestions.append("调整任务资源配置以适应数据量增长")

        return suggestions


__all__ = ["TimeoutSkill"]