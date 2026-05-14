"""
隐式依赖检测器

检测工作流之间的隐式依赖关系：
1. 分析血缘数据：工作流 A 产出表 T，工作流 B 消费表 T
2. 获取 DolphinScheduler 显式依赖配置
3. 比对：隐式依赖 - 显式依赖 = 缺失的依赖
4. 检查隐式依赖是否正在执行（时间冲突风险）

用途：
- 首次检测：给出完整报告，验证血缘准确性
- 定时检测：每日扫描，告警有问题的隐式依赖
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录（支持多种运行方式）
try:
    # 从 src/graph/ 目录运行
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
except:
    # 备选路径
    PROJECT_ROOT = Path(os.getcwd())

DATA_DIR = PROJECT_ROOT / "data" / "graph"

# 如果 DATA_DIR 不存在，尝试其他路径
if not DATA_DIR.exists():
    alt_paths = [
        Path("D:/Project/dolphinscheduler-agent/data/graph"),
        Path("../data/graph"),
        Path("../../data/graph"),
    ]
    for alt in alt_paths:
        if alt.exists():
            DATA_DIR = alt
            break


@dataclass
class ImplicitDependency:
    """隐式依赖关系"""
    source_workflow_code: str
    source_workflow_name: str
    target_workflow_code: str
    target_workflow_name: str
    via_tables: List[str] = field(default_factory=list)
    via_tasks: List[Dict[str, str]] = field(default_factory=list)
    is_explicit: bool = False  # 是否已在 DS 中配置
    risk_level: str = "LOW"  # LOW/MEDIUM/HIGH
    evidence: str = ""


@dataclass
class DependencyCheckResult:
    """依赖检测结果"""
    project_code: str
    project_name: str
    total_workflows: int
    implicit_dependencies: List[ImplicitDependency] = field(default_factory=list)
    missing_dependencies: List[ImplicitDependency] = field(default_factory=list)
    explicit_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    lineage_accuracy_issues: List[Dict[str, Any]] = field(default_factory=list)
    scan_time: str = ""
    summary: str = ""


class ImplicitDependencyDetector:
    """隐式依赖检测器"""

    def __init__(self, data_dir: str = str(DATA_DIR)):
        """
        初始化检测器

        Args:
            data_dir: 图谱数据目录
        """
        self.data_dir = data_dir

    def load_graph(self, project_code: str) -> Optional[Dict]:
        """加载图谱数据"""
        graph_path = os.path.join(self.data_dir, f"{project_code}_graph.json")
        if not os.path.exists(graph_path):
            return None

        with open(graph_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_index(self, project_code: str, index_type: str) -> Optional[Dict]:
        """加载索引数据"""
        index_path = os.path.join(self.data_dir, f"{project_code}_index_{index_type}.json")
        if not os.path.exists(index_path):
            return None

        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def detect_all_implicit_dependencies(self, project_code: str) -> DependencyCheckResult:
        """
        检测项目中的所有隐式依赖

        Args:
            project_code: 项目代码

        Returns:
            DependencyCheckResult 检测结果
        """
        # 加载图谱
        graph_data = self.load_graph(project_code)
        if graph_data is None:
            return DependencyCheckResult(
                project_code=project_code,
                project_name="Unknown",
                total_workflows=0,
                summary=f"Graph not found for project: {project_code}",
            )

        project_name = graph_data.get("project_name", "Unknown")
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})

        workflows = nodes.get("workflows", [])
        tasks = nodes.get("tasks", [])
        tables = nodes.get("tables", [])

        # 构建任务-工作流映射
        task_to_workflow: Dict[str, str] = {}
        workflow_names: Dict[str, str] = {}
        task_names: Dict[str, str] = {}

        for wf in workflows:
            workflow_names[wf["code"]] = wf["name"]

        for task in tasks:
            task_to_workflow[task["code"]] = task["workflow_code"]
            task_names[task["code"]] = task["name"]

        # 构建表名映射
        table_names: Dict[str, str] = {}
        for table in tables:
            table_names[table["full_name"]] = table["full_name"]

        # 1. 获取显式依赖
        explicit_deps = edges.get("workflow_depends_workflow", [])
        explicit_dependency_map: Dict[str, Set[str]] = {}

        for dep in explicit_deps:
            source = dep.get("source") or dep.get("pre_workflow") or dep.get("pre")
            target = dep.get("target") or dep.get("post_workflow") or dep.get("post")
            if source and target:
                if source not in explicit_dependency_map:
                    explicit_dependency_map[source] = set()
                explicit_dependency_map[source].add(target)

        # 2. 分析隐式依赖（通过表血缘）
        task_produces_table = edges.get("task_produces_table", [])
        task_consumes_table = edges.get("task_consumes_table", [])

        # 注意：如果 task_produces_table 为空，可能需要从 task_consumes_table 推断产出
        # 检查 task_consumes_table 中的目标是否为 ADS/DWS 层（产出层）
        output_layer_patterns = ["ads", "dws", "report", "result", "output"]

        # 构建：表 -> 生产者工作流
        table_producers: Dict[str, Set[str]] = {}
        table_producer_tasks: Dict[str, List[Dict]] = {}

        # 如果 task_produces_table 有数据，使用它
        for edge in task_produces_table:
            task_code = edge.get("source") or edge.get("task") or edge.get("from")
            table_name = edge.get("target") or edge.get("table") or edge.get("to")
            if task_code and table_name:
                workflow_code = task_to_workflow.get(task_code, "")
                if workflow_code:
                    if table_name not in table_producers:
                        table_producers[table_name] = set()
                        table_producer_tasks[table_name] = []
                    table_producers[table_name].add(workflow_code)
                    table_producer_tasks[table_name].append({
                        "task_code": task_code,
                        "task_name": task_names.get(task_code, "Unknown"),
                        "workflow_code": workflow_code,
                        "workflow_name": workflow_names.get(workflow_code, "Unknown"),
                    })

        # 如果 task_produces_table 为空，尝试从 task_consumes_table 推断产出
        # 检查目标是否为输出层路径（ADS/DWS 等）
        if not task_produces_table:
            for edge in task_consumes_table:
                task_code = edge.get("source") or edge.get("task") or edge.get("from")
                table_name = edge.get("target") or edge.get("table") or edge.get("to")
                if task_code and table_name:
                    # 判断是否为输出层路径
                    is_output_path = any(
                        pattern in table_name.lower()
                        for pattern in output_layer_patterns
                    )
                    if is_output_path:
                        workflow_code = task_to_workflow.get(task_code, "")
                        if workflow_code:
                            if table_name not in table_producers:
                                table_producers[table_name] = set()
                                table_producer_tasks[table_name] = []
                            table_producers[table_name].add(workflow_code)
                            table_producer_tasks[table_name].append({
                                "task_code": task_code,
                                "task_name": task_names.get(task_code, "Unknown"),
                                "workflow_code": workflow_code,
                                "workflow_name": workflow_names.get(workflow_code, "Unknown"),
                            })

        # 构建：表 -> 消费者工作流
        table_consumers: Dict[str, Set[str]] = {}
        table_consumer_tasks: Dict[str, List[Dict]] = {}

        # 输入层路径模式
        input_layer_patterns = ["ods", "dwd", "original", "raw", "source", "input"]

        for edge in task_consumes_table:
            task_code = edge.get("source") or edge.get("task") or edge.get("from")
            table_name = edge.get("target") or edge.get("table") or edge.get("to")
            if task_code and table_name:
                # 判断是否为输入层路径
                is_input_path = any(
                    pattern in table_name.lower()
                    for pattern in input_layer_patterns
                )
                # 如果是输入层路径，或者 task_produces_table 有数据（正常情况）
                if is_input_path:
                    workflow_code = task_to_workflow.get(task_code, "")
                    if workflow_code:
                        if table_name not in table_consumers:
                            table_consumers[table_name] = set()
                            table_consumer_tasks[table_name] = []
                        table_consumers[table_name].add(workflow_code)
                        table_consumer_tasks[table_name].append({
                            "task_code": task_code,
                            "task_name": task_names.get(task_code, "Unknown"),
                            "workflow_code": workflow_code,
                            "workflow_name": workflow_names.get(workflow_code, "Unknown"),
                        })

        # 3. 检测隐式依赖
        implicit_deps: List[ImplicitDependency] = []
        seen_pairs: Set[str] = set()

        for table_name in table_producers:
            producer_wfs = table_producers[table_name]
            consumer_wfs = table_consumers.get(table_name, set())

            # 对于每个生产者-消费者组合
            for producer_wf in producer_wfs:
                for consumer_wf in consumer_wfs:
                    # 跳过自己依赖自己
                    if producer_wf == consumer_wf:
                        continue

                    # 唯一键
                    pair_key = f"{producer_wf}->{consumer_wf}"
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    # 检查是否已显式配置
                    is_explicit = consumer_wf in explicit_dependency_map.get(producer_wf, set())

                    # 构建证据
                    producer_tasks = table_producer_tasks.get(table_name, [])
                    consumer_tasks = table_consumer_tasks.get(table_name, [])

                    evidence = (
                        f"表 {table_name}: "
                        f"生产者 {workflow_names.get(producer_wf, producer_wf)} "
                        f"-> 消费者 {workflow_names.get(consumer_wf, consumer_wf)}"
                    )

                    dep = ImplicitDependency(
                        source_workflow_code=producer_wf,
                        source_workflow_name=workflow_names.get(producer_wf, "Unknown"),
                        target_workflow_code=consumer_wf,
                        target_workflow_name=workflow_names.get(consumer_wf, "Unknown"),
                        via_tables=[table_name],
                        via_tasks=[
                            {
                                "producer_task": producer_tasks[0].get("task_name", "Unknown") if producer_tasks else "Unknown",
                                "consumer_task": consumer_tasks[0].get("task_name", "Unknown") if consumer_tasks else "Unknown",
                            }
                        ],
                        is_explicit=is_explicit,
                        risk_level="MEDIUM" if not is_explicit else "LOW",
                        evidence=evidence,
                    )
                    implicit_deps.append(dep)

        # 4. 筛选缺失的依赖（未显式配置的隐式依赖）
        missing_deps = [d for d in implicit_deps if not d.is_explicit]

        # 5. 检查血缘准确性问题
        accuracy_issues = self._check_lineage_accuracy(
            graph_data, task_to_workflow, workflow_names
        )

        # 6. 构建结果
        summary = self._build_summary(
            len(workflows), len(implicit_deps), len(missing_deps), len(accuracy_issues)
        )

        return DependencyCheckResult(
            project_code=project_code,
            project_name=project_name,
            total_workflows=len(workflows),
            implicit_dependencies=implicit_deps,
            missing_dependencies=missing_deps,
            explicit_dependencies=explicit_deps,
            lineage_accuracy_issues=accuracy_issues,
            scan_time=datetime.now().isoformat(),
            summary=summary,
        )

    def _check_lineage_accuracy(
        self,
        graph_data: Dict,
        task_to_workflow: Dict[str, str],
        workflow_names: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        检查血缘准确性问题

        检测项：
        1. 任务没有关联工作流
        2. 表没有生产者或消费者（孤立表）
        3. 工作流没有任务
        4. 血缘关系不完整

        Args:
            graph_data: 图谱数据
            task_to_workflow: 任务-工作流映射
            workflow_names: 工作流名称映射

        Returns:
            准确性问题列表
        """
        issues = []
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})

        tasks = nodes.get("tasks", [])
        workflows = nodes.get("workflows", [])
        tables = nodes.get("tables", [])

        # 1. 检查任务是否关联工作流
        for task in tasks:
            if task["code"] not in task_to_workflow:
                issues.append({
                    "type": "TASK_NO_WORKFLOW",
                    "severity": "HIGH",
                    "task_code": task["code"],
                    "task_name": task["name"],
                    "message": f"任务 {task['name']} 未关联到任何工作流",
                })

        # 2. 检查孤立表（既无生产者也无消费者）
        # 注意：ADS/DWS 层表无生产者可能是数据问题，但 ODS/DWD 层表无消费者可能是正常的
        task_produces_table = edges.get("task_produces_table", [])
        task_consumes_table = edges.get("task_consumes_table", [])

        tables_with_producers = set()
        tables_with_consumers = set()

        # 输入/输出层判断
        output_layer_patterns = ["ads", "dws", "report", "result", "output"]
        input_layer_patterns = ["ods", "dwd", "original", "raw", "source", "input"]

        # 如果 task_produces_table 有数据
        for edge in task_produces_table:
            table_name = edge.get("target") or edge.get("table") or edge.get("to")
            if table_name:
                tables_with_producers.add(table_name)

        # 如果 task_produces_table 为空，从 task_consumes_table 推断产出
        if not task_produces_table:
            for edge in task_consumes_table:
                table_name = edge.get("target") or edge.get("table") or edge.get("to")
                if table_name:
                    is_output_path = any(
                        pattern in table_name.lower()
                        for pattern in output_layer_patterns
                    )
                    if is_output_path:
                        tables_with_producers.add(table_name)
                    else:
                        tables_with_consumers.add(table_name)
        else:
            for edge in task_consumes_table:
                table_name = edge.get("target") or edge.get("table") or edge.get("to")
                if table_name:
                    tables_with_consumers.add(table_name)

        for table in tables:
            full_name = table["full_name"]
            has_producer = full_name in tables_with_producers
            has_consumer = full_name in tables_with_consumers

            # 判断是输出层还是输入层
            is_output_layer = any(
                pattern in full_name.lower()
                for pattern in output_layer_patterns
            )
            is_input_layer = any(
                pattern in full_name.lower()
                for pattern in input_layer_patterns
            )

            if not has_producer and not has_consumer:
                issues.append({
                    "type": "ORPHAN_TABLE",
                    "severity": "MEDIUM",
                    "table_name": full_name,
                    "message": f"表 {full_name} 既无生产者也无消费者",
                })
            elif not has_producer and is_output_layer:
                # 输出层表应该有生产者
                issues.append({
                    "type": "OUTPUT_TABLE_NO_PRODUCER",
                    "severity": "HIGH",
                    "table_name": full_name,
                    "message": f"输出层表 {full_name} 无生产者（数据来源不明）",
                })
            elif not has_producer and is_input_layer:
                # 输入层表可能来自外部数据源，不一定是问题
                issues.append({
                    "type": "INPUT_TABLE_NO_PRODUCER",
                    "severity": "LOW",
                    "table_name": full_name,
                    "message": f"输入层表 {full_name} 无生产者（可能来自外部数据源）",
                })
            elif not has_consumer and is_output_layer:
                # 输出层表无消费者可能是正常的（如报表表）
                issues.append({
                    "type": "OUTPUT_TABLE_NO_CONSUMER",
                    "severity": "LOW",
                    "table_name": full_name,
                    "message": f"输出层表 {full_name} 无消费者（可能是最终报表）",
                })
            elif not has_consumer and is_input_layer:
                # 输入层表应该有消费者
                issues.append({
                    "type": "INPUT_TABLE_NO_CONSUMER",
                    "severity": "HIGH",
                    "table_name": full_name,
                    "message": f"输入层表 {full_name} 无消费者（数据未被使用）",
                })

        # 3. 检查工作流是否有任务
        workflow_tasks: Dict[str, int] = {}
        workflow_contains_task = edges.get("workflow_contains_task", [])

        for edge in workflow_contains_task:
            workflow_code = edge.get("source") or edge.get("workflow")
            if workflow_code:
                workflow_tasks[workflow_code] = workflow_tasks.get(workflow_code, 0) + 1

        for wf in workflows:
            if wf["code"] not in workflow_tasks:
                issues.append({
                    "type": "WORKFLOW_NO_TASKS",
                    "severity": "MEDIUM",
                    "workflow_code": wf["code"],
                    "workflow_name": wf["name"],
                    "message": f"工作流 {wf['name']} 无任务",
                })

        return issues

    def _build_summary(
        self,
        workflow_count: int,
        implicit_count: int,
        missing_count: int,
        accuracy_issue_count: int
    ) -> str:
        """构建摘要"""
        parts = [
            f"项目共 {workflow_count} 个工作流",
            f"检测到 {implicit_count} 个隐式依赖",
            f"其中 {missing_count} 个未显式配置（需关注）",
        ]

        if accuracy_issue_count > 0:
            parts.append(f"发现 {accuracy_issue_count} 个血缘准确性问题")

        return " | ".join(parts)

    def generate_report(self, result: DependencyCheckResult) -> str:
        """
        生成检测报告

        Args:
            result: 检测结果

        Returns:
            报告文本
        """
        lines = []
        lines.append("=" * 80)
        lines.append("隐式依赖检测报告")
        lines.append("=" * 80)
        lines.append(f"项目: {result.project_name} ({result.project_code})")
        lines.append(f"扫描时间: {result.scan_time}")
        lines.append(f"总工作流数: {result.total_workflows}")
        lines.append("")
        lines.append("摘要: " + result.summary)
        lines.append("")
        lines.append("=" * 80)

        # 1. 缺失的依赖（重点）
        if result.missing_dependencies:
            lines.append("缺失的隐式依赖（需配置）")
            lines.append("=" * 80)
            lines.append(f"共 {len(result.missing_dependencies)} 个缺失依赖:")
            lines.append("")

            for i, dep in enumerate(result.missing_dependencies, 1):
                lines.append(f"[{i}] {dep.source_workflow_name} -> {dep.target_workflow_name}")
                lines.append(f"    工作流代码: {dep.source_workflow_code} -> {dep.target_workflow_code}")
                lines.append(f"    中间表: {', '.join(dep.via_tables[:3])}")
                if dep.via_tasks:
                    task_info = dep.via_tasks[0]
                    lines.append(f"    任务: {task_info.get('producer_task', '?')} -> {task_info.get('consumer_task', '?')}")
                lines.append(f"    风险等级: {dep.risk_level}")
                lines.append(f"    证据: {dep.evidence}")
                lines.append("")

        # 2. 血缘准确性问题
        if result.lineage_accuracy_issues:
            lines.append("=" * 80)
            lines.append("血缘准确性问题")
            lines.append("=" * 80)
            lines.append(f"共 {len(result.lineage_accuracy_issues)} 个问题:")
            lines.append("")

            # 按类型分组
            by_type: Dict[str, List] = {}
            for issue in result.lineage_accuracy_issues:
                type_ = issue["type"]
                if type_ not in by_type:
                    by_type[type_] = []
                by_type[type_].append(issue)

            for type_, issues in by_type.items():
                lines.append(f"{type_} ({len(issues)} 个):")
                for issue in issues[:5]:  # 只显示前5个
                    lines.append(f"  - {issue['message']}")
                if len(issues) > 5:
                    lines.append(f"  ... 还有 {len(issues) - 5} 个")
                lines.append("")

        # 3. 已配置的隐式依赖（验证）
        configured_deps = [d for d in result.implicit_dependencies if d.is_explicit]
        if configured_deps:
            lines.append("=" * 80)
            lines.append("已配置的隐式依赖（血缘与配置一致）")
            lines.append("=" * 80)
            lines.append(f"共 {len(configured_deps)} 个已配置:")
            lines.append("")

            for dep in configured_deps[:10]:  # 只显示前10个
                lines.append(f"  {dep.source_workflow_name} -> {dep.target_workflow_name}")
            if len(configured_deps) > 10:
                lines.append(f"  ... 还有 {len(configured_deps) - 10} 个")
            lines.append("")

        # 4. 建议
        lines.append("=" * 80)
        lines.append("建议")
        lines.append("=" * 80)

        if result.missing_dependencies:
            lines.append("1. 为缺失的隐式依赖配置工作流依赖关系")
            lines.append("   - 在 DolphinScheduler 中编辑工作流定义")
            lines.append("   - 添加依赖关系：源工作流 -> 目标工作流")
            lines.append("")

        if result.lineage_accuracy_issues:
            lines.append("2. 检查并修复血缘准确性问题")
            high_issues = [i for i in result.lineage_accuracy_issues if i["severity"] == "HIGH"]
            if high_issues:
                lines.append(f"   - 优先处理 {len(high_issues)} 个 HIGH 级别问题")
            lines.append("")

        lines.append("3. 定期执行隐式依赖检测")
        lines.append("   - 建议每日执行，及时发现新增的隐式依赖")
        lines.append("")

        return "\n".join(lines)

    def export_json_report(self, result: DependencyCheckResult, output_path: str) -> None:
        """导出 JSON 格式报告"""
        report_data = {
            "project_code": result.project_code,
            "project_name": result.project_name,
            "scan_time": result.scan_time,
            "summary": result.summary,
            "statistics": {
                "total_workflows": result.total_workflows,
                "implicit_dependencies": len(result.implicit_dependencies),
                "missing_dependencies": len(result.missing_dependencies),
                "configured_dependencies": len([d for d in result.implicit_dependencies if d.is_explicit]),
                "accuracy_issues": len(result.lineage_accuracy_issues),
            },
            "missing_dependencies": [
                {
                    "source_workflow": {
                        "code": d.source_workflow_code,
                        "name": d.source_workflow_name,
                    },
                    "target_workflow": {
                        "code": d.target_workflow_code,
                        "name": d.target_workflow_name,
                    },
                    "via_tables": d.via_tables,
                    "via_tasks": d.via_tasks,
                    "risk_level": d.risk_level,
                    "evidence": d.evidence,
                }
                for d in result.missing_dependencies
            ],
            "accuracy_issues": result.lineage_accuracy_issues,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)


def detect_implicit_dependencies(project_code: str) -> DependencyCheckResult:
    """
    检测项目隐式依赖（便捷入口）

    Args:
        project_code: 项目代码

    Returns:
        DependencyCheckResult 检测结果
    """
    detector = ImplicitDependencyDetector()
    return detector.detect_all_implicit_dependencies(project_code)


def generate_detection_report(project_code: str, output_dir: str = None) -> str:
    """
    生成检测报告

    Args:
        project_code: 项目代码
        output_dir: 输出目录（默认为 data/graph）

    Returns:
        报告路径
    """
    if output_dir is None:
        output_dir = str(DATA_DIR)

    detector = ImplicitDependencyDetector()
    result = detector.detect_all_implicit_dependencies(project_code)

    # 生成文本报告
    report_text = detector.generate_report(result)
    text_path = os.path.join(output_dir, f"{project_code}_implicit_dep_report.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # 生成 JSON 报告
    json_path = os.path.join(output_dir, f"{project_code}_implicit_dep_report.json")
    detector.export_json_report(result, json_path)

    return text_path


__all__ = [
    "ImplicitDependencyDetector",
    "ImplicitDependency",
    "DependencyCheckResult",
    "detect_implicit_dependencies",
    "generate_detection_report",
]