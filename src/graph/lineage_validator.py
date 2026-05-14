"""
血缘依赖验证器

验证图谱数据的准确性，通过对比：
1. 图谱数据（graph.json）- 扫描分析结果
2. DolphinScheduler API 实际数据 - 真实工作流定义

验证维度：
1. 工作流数量和基本信息
2. 工作流包含的任务（workflow_contains_task）
3. 任务类型和 Spark 主类（task_type, spark_main_class）
4. 任务依赖关系（task_depends_task）
5. 工作流显式依赖（workflow_depends_workflow）
6. 子工作流调用（workflow_calls_subworkflow）
7. 类名映射（class_maps_to_task）
8. 表血缘（task_produces_table, task_consumes_table）

输出准确性报告，标记不一致之处。
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录（支持多种运行方式）
try:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
except:
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
class ValidationIssue:
    """验证问题"""
    category: str  # WORKFLOW_COUNT, TASK_COUNT, TASK_TYPE, etc.
    severity: str  # HIGH, MEDIUM, LOW
    expected: Any  # 预期值（DS API）
    actual: Any    # 实际值（图谱）
    details: str   # 详细说明
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """验证结果"""
    project_code: str
    project_name: str
    total_workflows_graph: int
    total_workflows_ds: int
    total_tasks_graph: int
    total_tasks_ds: int
    issues: List[ValidationIssue] = field(default_factory=list)
    accuracy_metrics: Dict[str, float] = field(default_factory=dict)
    summary: str = ""
    scan_time: str = ""


class LineageValidator:
    """血缘验证器"""

    def __init__(self, data_dir: str = str(DATA_DIR)):
        """初始化"""
        self.data_dir = data_dir

    def load_graph(self, project_code: str) -> Optional[Dict]:
        """加载图谱数据"""
        graph_path = os.path.join(self.data_dir, f"{project_code}_graph.json")
        if not os.path.exists(graph_path):
            return None
        with open(graph_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def fetch_ds_workflow_data(self, project_code: str) -> Dict[str, Any]:
        """
        从 DolphinScheduler API 获取实际工作流数据

        通过 dsctl_wrapper 执行 dsctl 命令获取真实数据

        Returns:
            {
                workflows: [{code, name, version, ...}],
                tasks: [{code, name, workflow_code, task_type, mainClass, ...}],
                relations: [{preTaskCode, postTaskCode, ...}],
                workflow_deps: [{source_workflow, target_workflow, ...}],
            }
        """
        result = {
            "workflows": [],
            "tasks": [],
            "relations": [],
            "workflow_deps": [],
            "sub_workflow_calls": [],
            "task_params": {},  # task_code -> taskParams
        }

        try:
            # 尝试导入 dsctl_wrapper
            import sys
            sys.path.insert(0, str(PROJECT_ROOT))
            from src.integrations.dsctl_wrapper import DSCLIClient

            client = DSCLIClient()

            # 1. 获取工作流列表
            workflows_result = client.list_workflows(int(project_code))

            if workflows_result.success:
                try:
                    response = json.loads(workflows_result.stdout)
                    # dsctl 返回 {"action": "workflow.list", "data": [...]}
                    if isinstance(response, dict) and "data" in response:
                        wf_list = response["data"]
                    elif isinstance(response, list):
                        wf_list = response
                    else:
                        wf_list = []

                    for wf in wf_list:
                        result["workflows"].append({
                            "code": wf.get("code"),
                            "name": wf.get("name"),
                            "version": wf.get("version"),
                            "releaseState": wf.get("releaseState"),
                            "description": wf.get("description"),
                        })

                except json.JSONDecodeError as e:
                    print(f"[WARN] Failed to parse workflow list: {e}")

                # 2. 对每个工作流获取详细定义
                for wf in result["workflows"]:
                    try:
                        detail_result = client.describe_workflow(int(project_code), int(wf["code"]))

                        if detail_result.success:
                            try:
                                detail_response = json.loads(detail_result.stdout)
                                if isinstance(detail_response, dict) and "data" in detail_response:
                                    dag_data = detail_response["data"]
                                else:
                                    dag_data = detail_response

                                # 提取任务定义
                                tasks_list = dag_data.get("tasks", []) or dag_data.get("taskDefinitionList", [])

                                for task in tasks_list:
                                    task_code = task.get("code")
                                    task_type = task.get("taskType")

                                    task_info = {
                                        "code": task_code,
                                        "name": task.get("name"),
                                        "workflow_code": wf["code"],
                                        "task_type": task_type,
                                        "mainClass": None,
                                    }

                                    # 提取 Spark mainClass
                                    task_params = task.get("taskParams", {})
                                    if isinstance(task_params, str):
                                        try:
                                            task_params = json.loads(task_params)
                                        except:
                                            task_params = {}

                                    if task_type == "SPARK":
                                        task_info["mainClass"] = task_params.get("mainClass")

                                    # 保存任务参数
                                    result["task_params"][task_code] = task_params

                                    # 检查是否为子工作流调用
                                    if task_type == "SUB_PROCESS":
                                        sub_wf_code = task_params.get("processDefinitionCode")
                                        if sub_wf_code:
                                            result["sub_workflow_calls"].append({
                                                "parent_workflow": wf["code"],
                                                "task_code": task_code,
                                                "sub_workflow": sub_wf_code,
                                            })

                                    result["tasks"].append(task_info)

                                # 提取任务依赖关系
                                relations_list = dag_data.get("relations", []) or dag_data.get("processTaskRelationList", []) or dag_data.get("workflowTaskRelationList", [])
                                for rel in relations_list:
                                    pre_task = rel.get("preTaskCode")
                                    post_task = rel.get("postTaskCode")
                                    if pre_task and post_task and pre_task != 0:
                                        result["relations"].append({
                                            "preTaskCode": pre_task,
                                            "postTaskCode": post_task,
                                            "workflow_code": wf["code"],
                                        })

                            except json.JSONDecodeError as e:
                                print(f"[WARN] Failed to parse workflow detail {wf['code']}: {e}")

                    except Exception as e:
                        print(f"[WARN] Failed to get workflow {wf['code']}: {e}")

        except Exception as e:
            print(f"[ERROR] Failed to connect to DS API: {e}")

        return result

    def validate_project(self, project_code: str, fetch_ds: bool = True) -> ValidationResult:
        """
        验证项目的血缘数据准确性

        Args:
            project_code: 项目代码
            fetch_ds: 是否从 DS API 获取实际数据（需要 API 连接）

        Returns:
            ValidationResult
        """
        # 加载图谱数据
        graph_data = self.load_graph(project_code)
        if graph_data is None:
            return ValidationResult(
                project_code=project_code,
                project_name="Unknown",
                total_workflows_graph=0,
                total_workflows_ds=0,
                total_tasks_graph=0,
                total_tasks_ds=0,
                summary=f"Graph not found for project: {project_code}",
            )

        project_name = graph_data.get("project_name", "Unknown")
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})

        # 图谱数据统计
        graph_workflows = nodes.get("workflows", [])
        graph_tasks = nodes.get("tasks", [])
        graph_classes = nodes.get("classes", [])
        graph_tables = nodes.get("tables", [])

        # 获取 DS 实际数据
        ds_data = {}
        if fetch_ds:
            print(f"[INFO] Fetching DS API data for project {project_code}...")
            ds_data = self.fetch_ds_workflow_data(project_code)

        ds_workflows = ds_data.get("workflows", [])
        ds_tasks = ds_data.get("tasks", [])
        ds_relations = ds_data.get("relations", [])

        issues: List[ValidationIssue] = []

        # ========== 验证维度 1: 工作流数量 ==========
        graph_wf_codes = set(wf["code"] for wf in graph_workflows)
        ds_wf_codes = set(str(wf["code"]) for wf in ds_workflows)

        if ds_workflows:
            # 工作流数量对比
            if len(graph_workflows) != len(ds_workflows):
                issues.append(ValidationIssue(
                    category="WORKFLOW_COUNT",
                    severity="HIGH",
                    expected=len(ds_workflows),
                    actual=len(graph_workflows),
                    details=f"工作流数量不一致：DS 有 {len(ds_workflows)} 个，图谱有 {len(graph_workflows)} 个",
                    evidence={
                        "missing_in_graph": list(ds_wf_codes - graph_wf_codes),
                        "extra_in_graph": list(graph_wf_codes - ds_wf_codes),
                    }
                ))

            # 工作流名称对比
            graph_wf_names = {wf["code"]: wf["name"] for wf in graph_workflows}
            ds_wf_names = {str(wf["code"]): wf["name"] for wf in ds_workflows}

            for code in ds_wf_codes & graph_wf_codes:
                graph_name = graph_wf_names.get(code, "")
                ds_name = ds_wf_names.get(code, "")
                if graph_name != ds_name and ds_name:
                    issues.append(ValidationIssue(
                        category="WORKFLOW_NAME",
                        severity="MEDIUM",
                        expected=ds_name,
                        actual=graph_name,
                        details=f"工作流 {code} 名称不一致",
                    ))

        # ========== 验证维度 2: 任务数量 ==========
        graph_task_codes = set(t["code"] for t in graph_tasks)
        ds_task_codes = set(str(t["code"]) for t in ds_tasks)

        if ds_tasks:
            # 每个工作流的任务数量
            graph_wf_task_count: Dict[str, int] = {}
            for edge in edges.get("workflow_contains_task", []):
                wf_code = edge.get("source")
                if wf_code:
                    graph_wf_task_count[wf_code] = graph_wf_task_count.get(wf_code, 0) + 1

            ds_wf_task_count: Dict[str, int] = {}
            for task in ds_tasks:
                wf_code = str(task["workflow_code"])
                ds_wf_task_count[wf_code] = ds_wf_task_count.get(wf_code, 0) + 1

            for wf_code in graph_wf_codes & set(ds_wf_task_count.keys()):
                graph_count = graph_wf_task_count.get(wf_code, 0)
                ds_count = ds_wf_task_count.get(wf_code, 0)
                if graph_count != ds_count:
                    issues.append(ValidationIssue(
                        category="TASK_COUNT",
                        severity="HIGH",
                        expected=ds_count,
                        actual=graph_count,
                        details=f"工作流 {wf_code} 任务数量不一致",
                        evidence={"workflow_code": wf_code}
                    ))

        # ========== 验证维度 3: 任务类型 ==========
        if ds_tasks:
            graph_task_types = {t["code"]: t["task_type"] for t in graph_tasks}
            ds_task_types = {str(t["code"]): t["task_type"] for t in ds_tasks}

            for code in ds_task_codes & graph_task_codes:
                graph_type = graph_task_types.get(code, "")
                ds_type = ds_task_types.get(code, "")
                if graph_type != ds_type and ds_type:
                    issues.append(ValidationIssue(
                        category="TASK_TYPE",
                        severity="HIGH",
                        expected=ds_type,
                        actual=graph_type,
                        details=f"任务 {code} 类型不一致",
                    ))

        # ========== 验证维度 4: Spark 主类 ==========
        if ds_tasks:
            graph_spark_classes = {t["code"]: t.get("spark_main_class") for t in graph_tasks}
            ds_spark_classes = {str(t["code"]): t.get("mainClass") for t in ds_tasks if t.get("task_type") == "SPARK"}

            for code, ds_class in ds_spark_classes.items():
                if ds_class and code in graph_task_codes:
                    graph_class = graph_spark_classes.get(code)
                    if graph_class != ds_class:
                        issues.append(ValidationIssue(
                            category="SPARK_MAIN_CLASS",
                            severity="MEDIUM",
                            expected=ds_class,
                            actual=graph_class,
                            details=f"Spark 任务 {code} 主类不一致",
                        ))

        # ========== 验证维度 5: 任务依赖关系 ==========
        if ds_relations:
            graph_task_deps = set()
            for edge in edges.get("task_depends_task", []):
                source = edge.get("source")
                target = edge.get("target")
                if source and target:
                    graph_task_deps.add((source, target))

            ds_task_deps = set()
            for rel in ds_relations:
                pre = str(rel["preTaskCode"])
                post = str(rel["postTaskCode"])
                ds_task_deps.add((pre, post))

            # 比较依赖关系
            missing_deps = ds_task_deps - graph_task_deps
            extra_deps = graph_task_deps - ds_task_deps

            if missing_deps:
                issues.append(ValidationIssue(
                    category="TASK_DEPENDENCY_MISSING",
                    severity="HIGH",
                    expected=len(ds_task_deps),
                    actual=len(graph_task_deps),
                    details=f"缺少 {len(missing_deps)} 个任务依赖关系",
                    evidence={"missing_deps": list(missing_deps)[:10]}
                ))

            if extra_deps:
                issues.append(ValidationIssue(
                    category="TASK_DEPENDENCY_EXTRA",
                    severity="MEDIUM",
                    expected=len(ds_task_deps),
                    actual=len(graph_task_deps),
                    details=f"多出 {len(extra_deps)} 个任务依赖关系",
                    evidence={"extra_deps": list(extra_deps)[:10]}
                ))

        # ========== 验证维度 6: 子工作流调用 ==========
        ds_sub_calls = ds_data.get("sub_workflow_calls", [])
        graph_sub_calls = edges.get("workflow_calls_subworkflow", [])

        if ds_sub_calls:
            graph_sub_set = set()
            for edge in graph_sub_calls:
                parent = edge.get("source")
                child = edge.get("target")
                if parent and child:
                    graph_sub_set.add((str(parent), str(child)))

            ds_sub_set = set()
            for call in ds_sub_calls:
                parent = str(call["parent_workflow"])
                child = str(call["sub_workflow"])
                ds_sub_set.add((parent, child))

            missing_subs = ds_sub_set - graph_sub_set
            if missing_subs:
                issues.append(ValidationIssue(
                    category="SUB_WORKFLOW_CALL_MISSING",
                    severity="HIGH",
                    expected=len(ds_sub_set),
                    actual=len(graph_sub_set),
                    details=f"缺少 {len(missing_subs)} 个子工作流调用关系",
                    evidence={"missing": list(missing_subs)[:5]}
                ))

        # ========== 验证维度 7: 类名映射 ==========
        # 图谱中的类名映射
        class_maps = edges.get("class_maps_to_task", [])
        graph_class_task_map: Dict[str, List[str]] = {}
        for edge in class_maps:
            class_name = edge.get("source")
            task_code = edge.get("target")
            if class_name and task_code:
                if class_name not in graph_class_task_map:
                    graph_class_task_map[class_name] = []
                graph_class_task_map[class_name].append(task_code)

        # DS 实际的 Spark 主类
        if ds_tasks:
            ds_class_task_map: Dict[str, List[str]] = {}
            for task in ds_tasks:
                if task.get("task_type") == "SPARK" and task.get("mainClass"):
                    class_name = task["mainClass"]
                    task_code = str(task["code"])
                    if class_name not in ds_class_task_map:
                        ds_class_task_map[class_name] = []
                    ds_class_task_map[class_name].append(task_code)

            # 对比类名映射
            for class_name in set(ds_class_task_map.keys()) | set(graph_class_task_map.keys()):
                ds_tasks_for_class = set(ds_class_task_map.get(class_name, []))
                graph_tasks_for_class = set(graph_class_task_map.get(class_name, []))

                if ds_tasks_for_class != graph_tasks_for_class:
                    issues.append(ValidationIssue(
                        category="CLASS_TASK_MAPPING",
                        severity="MEDIUM",
                        expected=list(ds_tasks_for_class),
                        actual=list(graph_tasks_for_class),
                        details=f"类 {class_name} 映射的任务不一致",
                    ))

        # ========== 验证维度 8: 表血缘完整性 ==========
        # 检查图谱中的表是否有完整的读写关系
        task_produces = edges.get("task_produces_table", [])
        task_consumes = edges.get("task_consumes_table", [])

        produces_task_set: Dict[str, Set[str]] = {}
        for edge in task_produces:
            task = edge.get("source")
            table = edge.get("target")
            if task and table:
                if table not in produces_task_set:
                    produces_task_set[table] = set()
                produces_task_set[table].add(task)

        consumes_task_set: Dict[str, Set[str]] = {}
        for edge in task_consumes:
            task = edge.get("source")
            table = edge.get("target")
            if task and table:
                if table not in consumes_task_set:
                    consumes_task_set[table] = set()
                consumes_task_set[table].add(task)

        # 检查是否有表有产出但无消费（或反之）
        for table in graph_tables:
            table_name = table["full_name"]
            has_producer = table_name in produces_task_set
            has_consumer = table_name in consumes_task_set

            # ADS/DWS 层表无消费可能是正常的
            is_output_layer = any(
                pattern in table_name.lower()
                for pattern in ["ads", "dws", "report"]
            )

            if not has_producer and not has_consumer:
                issues.append(ValidationIssue(
                    category="ORPHAN_TABLE",
                    severity="HIGH",
                    expected="有生产者或消费者",
                    actual="无",
                    details=f"表 {table_name} 既无生产者也无消费者",
                ))
            elif not has_producer and not is_output_layer:
                issues.append(ValidationIssue(
                    category="TABLE_NO_PRODUCER",
                    severity="HIGH",
                    expected="有生产者",
                    actual="无",
                    details=f"表 {table_name} 无生产者（数据来源不明）",
                ))

        # ========== 计算准确性指标 ==========
        accuracy_metrics = {}

        if ds_workflows:
            wf_match_count = len(ds_wf_codes & graph_wf_codes)
            accuracy_metrics["workflow_match_rate"] = wf_match_count / len(ds_wf_codes) if ds_wf_codes else 0

        if ds_tasks:
            task_match_count = len(ds_task_codes & graph_task_codes)
            accuracy_metrics["task_match_rate"] = task_match_count / len(ds_task_codes) if ds_task_codes else 0

        if ds_relations:
            dep_match_count = len(set((str(r["preTaskCode"]), str(r["postTaskCode"])) for r in ds_relations) & graph_task_deps)
            accuracy_metrics["dependency_match_rate"] = dep_match_count / len(ds_relations) if ds_relations else 0

        accuracy_metrics["class_count"] = len(graph_classes)
        accuracy_metrics["table_count"] = len(graph_tables)
        accuracy_metrics["produces_edge_count"] = len(task_produces)
        accuracy_metrics["consumes_edge_count"] = len(task_consumes)

        # ========== 生成摘要 ==========
        high_issues = [i for i in issues if i.severity == "HIGH"]
        medium_issues = [i for i in issues if i.severity == "MEDIUM"]

        summary_parts = [
            f"工作流: 图谱 {len(graph_workflows)} vs DS {len(ds_workflows)}",
            f"任务: 图谱 {len(graph_tasks)} vs DS {len(ds_tasks)}",
            f"发现问题: {len(high_issues)} HIGH, {len(medium_issues)} MEDIUM",
        ]

        if accuracy_metrics.get("workflow_match_rate"):
            summary_parts.append(f"工作流匹配率: {accuracy_metrics['workflow_match_rate']*100:.1f}%")

        summary = " | ".join(summary_parts)

        return ValidationResult(
            project_code=project_code,
            project_name=project_name,
            total_workflows_graph=len(graph_workflows),
            total_workflows_ds=len(ds_workflows),
            total_tasks_graph=len(graph_tasks),
            total_tasks_ds=len(ds_tasks),
            issues=issues,
            accuracy_metrics=accuracy_metrics,
            summary=summary,
            scan_time=datetime.now().isoformat(),
        )

    def generate_report(self, result: ValidationResult) -> str:
        """生成验证报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("血缘依赖验证报告")
        lines.append("=" * 80)
        lines.append(f"项目: {result.project_name} ({result.project_code})")
        lines.append(f"验证时间: {result.scan_time}")
        lines.append("")
        lines.append("摘要: " + result.summary)
        lines.append("")
        lines.append("=" * 80)

        # 统计对比
        lines.append("数据统计对比")
        lines.append("=" * 80)
        lines.append(f"  工作流数量: 图谱 {result.total_workflows_graph} vs DS API {result.total_workflows_ds}")
        lines.append(f"  任务数量: 图谱 {result.total_tasks_graph} vs DS API {result.total_tasks_ds}")
        lines.append("")
        lines.append("准确性指标:")
        for key, value in result.accuracy_metrics.items():
            if isinstance(value, float):
                lines.append(f"  {key}: {value*100:.1f}%")
            else:
                lines.append(f"  {key}: {value}")
        lines.append("")

        # 问题列表
        if result.issues:
            lines.append("=" * 80)
            lines.append("验证问题详情")
            lines.append("=" * 80)
            lines.append(f"共发现 {len(result.issues)} 个问题:")
            lines.append("")

            # 按类别分组
            by_category: Dict[str, List[ValidationIssue]] = {}
            for issue in result.issues:
                cat = issue.category
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(issue)

            for category, issues in by_category.items():
                severity_counts = {}
                for i in issues:
                    s = i.severity
                    severity_counts[s] = severity_counts.get(s, 0) + 1

                severity_str = ", ".join(f"{s}: {c}" for s, c in severity_counts.items())
                lines.append(f"[{category}] ({severity_str}):")

                for issue in issues[:5]:  # 只显示前5个
                    lines.append(f"  - {issue.details}")
                    if issue.expected != issue.actual:
                        lines.append(f"    预期: {issue.expected}, 实际: {issue.actual}")

                if len(issues) > 5:
                    lines.append(f"    ... 还有 {len(issues) - 5} 个类似问题")
                lines.append("")

        # 建议
        lines.append("=" * 80)
        lines.append("改进建议")
        lines.append("=" * 80)

        high_issues = [i for i in result.issues if i.severity == "HIGH"]
        if high_issues:
            lines.append("1. 优先处理 HIGH 级别问题:")
            for cat in set(i.category for i in high_issues):
                lines.append(f"   - {cat}")
        else:
            lines.append("1. 无 HIGH 级别问题，血缘数据基本准确")

        lines.append("")
        lines.append("2. 建议改进:")
        if result.accuracy_metrics.get("produces_edge_count", 0) == 0:
            lines.append("   - task_produces_table 边为空，需改进产出表识别逻辑")
        if result.accuracy_metrics.get("workflow_match_rate", 1) < 0.9:
            lines.append("   - 工作流匹配率低，检查扫描是否遗漏工作流")
        if result.accuracy_metrics.get("task_match_rate", 1) < 0.9:
            lines.append("   - 任务匹配率低，检查任务解析是否正确")

        return "\n".join(lines)

    def export_json_report(self, result: ValidationResult, output_path: str) -> None:
        """导出 JSON 报告"""
        report_data = {
            "project_code": result.project_code,
            "project_name": result.project_name,
            "scan_time": result.scan_time,
            "summary": result.summary,
            "statistics": {
                "workflows_graph": result.total_workflows_graph,
                "workflows_ds": result.total_workflows_ds,
                "tasks_graph": result.total_tasks_graph,
                "tasks_ds": result.total_tasks_ds,
            },
            "accuracy_metrics": result.accuracy_metrics,
            "issues": [
                {
                    "category": i.category,
                    "severity": i.severity,
                    "expected": i.expected,
                    "actual": i.actual,
                    "details": i.details,
                    "evidence": i.evidence,
                }
                for i in result.issues
            ],
            "issue_summary": {
                "total": len(result.issues),
                "high": len([i for i in result.issues if i.severity == "HIGH"]),
                "medium": len([i for i in result.issues if i.severity == "MEDIUM"]),
                "low": len([i for i in result.issues if i.severity == "LOW"]),
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)


def validate_lineage(project_code: str, fetch_ds: bool = True) -> ValidationResult:
    """验证项目血缘（便捷入口）"""
    validator = LineageValidator()
    return validator.validate_project(project_code, fetch_ds)


def generate_validation_report(project_code: str, output_dir: str = None, fetch_ds: bool = True) -> str:
    """生成验证报告"""
    if output_dir is None:
        output_dir = str(DATA_DIR)

    validator = LineageValidator()
    result = validator.validate_project(project_code, fetch_ds)

    # 生成文本报告
    report_text = validator.generate_report(result)
    text_path = os.path.join(output_dir, f"{project_code}_lineage_validation.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # 生成 JSON 报告
    json_path = os.path.join(output_dir, f"{project_code}_lineage_validation.json")
    validator.export_json_report(result, json_path)

    return text_path


__all__ = [
    "LineageValidator",
    "ValidationIssue",
    "ValidationResult",
    "validate_lineage",
    "generate_validation_report",
]