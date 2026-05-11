"""
Daily Metrics Collection Script

使用 dsctl CLI 收集 DolphinScheduler 每日指标数据

功能:
- 收集工作流执行统计 (成功率、失败率、平均执行时间)
- 收集任务类型分布统计
- 收集错误类型分布统计
- 输出到 data/metrics/ 目录

使用方式:
    python scripts/collect_metrics.py --date 2026-05-11
    python scripts/collect_metrics.py --range 7  # 最近7天
    python scripts/collect_metrics.py --project 12345678  # 指定项目
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from integrations.dsctl_wrapper import DSCLIClient, CLIResult


@dataclass
class WorkflowMetrics:
    """工作流执行指标"""

    total_instances: int = 0
    success_count: int = 0
    failure_count: int = 0
    running_count: int = 0
    other_count: int = 0

    success_rate: float = 0.0
    failure_rate: float = 0.0

    avg_duration_seconds: float = 0.0
    max_duration_seconds: float = 0.0
    min_duration_seconds: float = 0.0


@dataclass
class TaskTypeMetrics:
    """任务类型分布指标"""

    task_type: str
    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_seconds: float = 0.0


@dataclass
class ErrorTypeMetrics:
    """错误类型分布指标"""

    error_type: str
    count: int = 0
    task_types: List[str] = field(default_factory=list)
    example_instance_ids: List[int] = field(default_factory=list)


@dataclass
class DailyMetricsReport:
    """每日指标报告"""

    date: str
    project_code: Optional[int] = None

    workflow_metrics: WorkflowMetrics = field(default_factory=WorkflowMetrics)
    task_type_metrics: Dict[str, TaskTypeMetrics] = field(default_factory=dict)
    error_type_metrics: Dict[str, ErrorTypeMetrics] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "date": self.date,
            "project_code": self.project_code,
            "workflow_metrics": asdict(self.workflow_metrics),
            "task_type_metrics": {
                k: asdict(v) for k, v in self.task_type_metrics.items()
            },
            "error_type_metrics": {
                k: asdict(v) for k, v in self.error_type_metrics.items()
            },
        }


class MetricsCollector:
    """指标收集器"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        version: str = "3.2.0",
    ):
        """
        初始化指标收集器

        Args:
            api_url: DolphinScheduler API URL
            api_token: DolphinScheduler API Token
            version: DolphinScheduler 版本
        """
        self.client = DSCLIClient(api_url=api_url, api_token=api_token, version=version)
        self.output_dir = Path(__file__).parent.parent / "data" / "metrics"

    def collect_workflow_metrics(
        self,
        project_code: int,
        start_date: datetime,
        end_date: datetime,
    ) -> WorkflowMetrics:
        """
        收集工作流执行指标

        使用 dsctl workflow-instance list 命令获取实例列表

        Args:
            project_code: 项目编码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            WorkflowMetrics
        """
        metrics = WorkflowMetrics()

        # TODO: 使用 dsctl 收集工作流实例数据
        # dsctl workflow-instance list --project <project_code> --state FAILURE --page-size 100

        # 当前返回空数据，等待 dsctl 扩展日期过滤功能
        # dsctl workflow-instance list --project <project_code> --start-time <start> --end-time <end>

        return metrics

    def collect_task_type_metrics(
        self,
        project_code: int,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, TaskTypeMetrics]:
        """
        收集任务类型分布指标

        Args:
            project_code: 项目编码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict[task_type, TaskTypeMetrics]
        """
        metrics: Dict[str, TaskTypeMetrics] = {}

        # TODO: 使用 dsctl 收集任务实例数据
        # 需要先获取工作流实例列表，然后获取每个实例的 task-instances

        # 主要任务类型: SPARK, SHELL, PYTHON, DATAX, SQL, FLINK

        return metrics

    def collect_error_type_metrics(
        self,
        project_code: int,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, ErrorTypeMetrics]:
        """
        收集错误类型分布指标

        Args:
            project_code: 项目编码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict[error_type, ErrorTypeMetrics]
        """
        metrics: Dict[str, ErrorTypeMetrics] = {}

        # TODO: 使用 dsctl 收集失败任务实例的日志
        # 1. 获取失败的工作流实例
        # 2. 获取每个失败实例的 digest (failedTasks)
        # 3. 获取失败任务的日志
        # 4. 使用 Skill Registry 分析错误类型

        return metrics

    def collect_daily_metrics(
        self,
        project_code: int,
        date: datetime,
    ) -> DailyMetricsReport:
        """
        收集指定日期的指标

        Args:
            project_code: 项目编码
            date: 收集日期

        Returns:
            DailyMetricsReport
        """
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)

        report = DailyMetricsReport(
            date=date.strftime("%Y-%m-%d"),
            project_code=project_code,
        )

        # 收集各类型指标
        report.workflow_metrics = self.collect_workflow_metrics(
            project_code, start_date, end_date
        )
        report.task_type_metrics = self.collect_task_type_metrics(
            project_code, start_date, end_date
        )
        report.error_type_metrics = self.collect_error_type_metrics(
            project_code, start_date, end_date
        )

        return report

    def save_report(self, report: DailyMetricsReport) -> Path:
        """
        保存指标报告到文件

        Args:
            report: 指标报告

        Returns:
            保存的文件路径
        """
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        filename = f"metrics_{report.date}.json"
        if report.project_code:
            filename = f"metrics_{report.project_code}_{report.date}.json"

        filepath = self.output_dir / filename

        # 写入 JSON
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        return filepath

    def collect_range_metrics(
        self,
        project_code: int,
        days: int,
        end_date: Optional[datetime] = None,
    ) -> List[Path]:
        """
        收集最近 N 天的指标

        Args:
            project_code: 项目编码
            days: 收集天数
            end_date: 结束日期，默认为今天

        Returns:
            保存的文件路径列表
        """
        if end_date is None:
            end_date = datetime.now()

        saved_files = []

        for i in range(days):
            date = end_date - timedelta(days=i)
            report = self.collect_daily_metrics(project_code, date)
            filepath = self.save_report(report)
            saved_files.append(filepath)

        return saved_files


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Collect DolphinScheduler daily metrics using dsctl CLI"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Collect metrics for specific date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--range",
        type=int,
        default=1,
        help="Collect metrics for last N days (default: 1)",
    )
    parser.add_argument(
        "--project",
        type=int,
        required=True,
        help="Project code to collect metrics from",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="DolphinScheduler API URL (default: from env DS_API_URL)",
    )
    parser.add_argument(
        "--api-token",
        type=str,
        help="DolphinScheduler API Token (default: from env DS_API_TOKEN)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="3.2.0",
        help="DolphinScheduler version (default: 3.2.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory (default: data/metrics)",
    )

    args = parser.parse_args()

    # 创建收集器
    collector = MetricsCollector(
        api_url=args.api_url,
        api_token=args.api_token,
        version=args.version,
    )

    # 设置输出目录
    if args.output:
        collector.output_dir = Path(args.output)

    # 解析日期
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
        report = collector.collect_daily_metrics(args.project, target_date)
        filepath = collector.save_report(report)
        print(f"Metrics saved to: {filepath}")
    else:
        # 收集最近 N 天
        saved_files = collector.collect_range_metrics(args.project, args.range)
        print(f"Collected metrics for {len(saved_files)} days:")
        for f in saved_files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()