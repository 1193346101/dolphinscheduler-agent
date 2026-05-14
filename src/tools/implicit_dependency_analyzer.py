"""
隐式依赖分析脚本

扫描 DolphinScheduler 项目的工作流，分析隐式依赖关系：
1. SUB_PROCESS 任务 - 子工作流调用
2. DEPENDENT 任务 - 外部依赖等待

输出依赖图和未关联依赖的工作流报告。

Usage:
    python -m src.tools.implicit_dependency_analyzer <project_name>
    python scripts/analyze_implicit_dependency.py <project_name>
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录
try:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
except:
    PROJECT_ROOT = Path(os.getcwd())


@dataclass
class WorkflowInfo:
    """工作流信息"""
    code: int
    name: str
    version: int
    release_state: str
    description: str = ""


@dataclass
class SubProcessCall:
    """SUB_PROCESS 调用关系"""
    parent_workflow_code: int
    parent_workflow_name: str
    task_code: int
    task_name: str
    sub_workflow_code: int
    sub_workflow_name: str = ""  # 后续填充


@dataclass
class DependentRelation:
    """DEPENDENT 依赖关系"""
    workflow_code: int
    workflow_name: str
    task_code: int
    task_name: str
    depend_task_list: List[Dict]  # 依赖配置
    is_empty: bool  # 是否配置为空


@dataclass
class TableLineageDependency:
    """表血缘驱动的隐式依赖"""
    consumer_workflow_code: int
    consumer_workflow_name: str
    producer_workflow_code: int
    producer_workflow_name: str
    shared_tables: List[str]  # 共享的表（producer 输出，consumer 输入）
    has_dependent_task: bool  # consumer 是否有 DEPENDENT 任务等待 producer


@dataclass
class ImplicitDependencyResult:
    """隐式依赖分析结果"""
    project_code: int
    project_name: str
    scan_time: str
    total_workflows: int
    main_workflows: List[WorkflowInfo]  # 主调度工作流
    sub_process_calls: List[SubProcessCall]  # SUB_PROCESS 调用
    dependent_relations: List[DependentRelation]  # DEPENDENT 依赖
    child_workflows: Set[int]  # 被调用的子工作流 code
    independent_workflows: List[WorkflowInfo]  # 真正独立的工作流
    test_workflows: List[WorkflowInfo]  # 测试/复制工作流
    table_lineage_dependencies: List[TableLineageDependency]  # 表血缘驱动的依赖
    missing_dependencies: List[TableLineageDependency]  # 缺失的依赖（需告警）
    dependency_graph_dot: str  # DOT 格式依赖图
    summary: str
    dependency_graph_ascii: str = ""  # ASCII 文本依赖图
    html_report: str = ""  # HTML 报告


class ImplicitDependencyAnalyzer:
    """隐式依赖分析器"""

    def __init__(self):
        """初始化"""
        # 尝试导入 dsctl_wrapper
        sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from src.integrations.dsctl_wrapper import DSCLIClient
            self.client_class = DSCLIClient
        except ImportError:
            self.client_class = None

        # 项目配置
        self.projects_config = self._load_projects_config()

    def _load_projects_config(self) -> Dict:
        """加载项目配置"""
        config_path = PROJECT_ROOT / "config" / "projects.yaml"
        if not config_path.exists():
            return {}

        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            # 如果没有 yaml 模块，手动解析
            return {}

    def _get_project_config(self, project_name: str) -> Optional[Dict]:
        """获取项目配置"""
        projects = self.projects_config.get("projects", [])
        for p in projects:
            if p.get("name") == project_name:
                return p
        return None

    def _load_table_lineage(self, project_code: int) -> Optional[Dict]:
        """
        加载表血缘数据（从 graph.json 文件）

        Args:
            project_code: 项目代码

        Returns:
            {
                workflow_produces: {workflow_code: set(table_names)},
                workflow_consumes: {workflow_code: set(table_names)},
                workflow_name_map: {workflow_code: workflow_name}
            }
        """
        graph_file = PROJECT_ROOT / "data" / "graph" / f"{project_code}_graph.json"
        if not graph_file.exists():
            print(f"[WARN] 血缘数据文件不存在: {graph_file}")
            return None

        try:
            with open(graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取血缘数据失败: {e}")
            return None

        # 构建映射
        workflow_produces: Dict[int, Set[str]] = {}
        workflow_consumes: Dict[int, Set[str]] = {}
        workflow_name_map: Dict[int, str] = {}
        task_to_workflow: Dict[int, int] = {}

        # workflow_name_map
        workflows = data.get("nodes", {}).get("workflows", [])
        for wf in workflows:
            wf_code = int(wf.get("code"))
            workflow_name_map[wf_code] = wf.get("name")
            workflow_produces[wf_code] = set()
            workflow_consumes[wf_code] = set()

        # task_to_workflow
        edges = data.get("edges", {})
        workflow_contains_task = edges.get("workflow_contains_task", [])
        for edge in workflow_contains_task:
            wf_code = int(edge.get("source"))
            task_code = int(edge.get("target"))
            task_to_workflow[task_code] = wf_code

        # task_produces_table -> workflow_produces
        task_produces_table = edges.get("task_produces_table", [])
        for edge in task_produces_table:
            task_code = int(edge.get("source"))
            table_name = edge.get("target")
            wf_code = task_to_workflow.get(task_code)
            if wf_code and table_name:
                workflow_produces[wf_code].add(table_name)

        # task_consumes_table -> workflow_consumes
        task_consumes_table = edges.get("task_consumes_table", [])
        for edge in task_consumes_table:
            task_code = int(edge.get("source"))
            table_name = edge.get("target")
            wf_code = task_to_workflow.get(task_code)
            if wf_code and table_name:
                workflow_consumes[wf_code].add(table_name)

        return {
            "workflow_produces": workflow_produces,
            "workflow_consumes": workflow_consumes,
            "workflow_name_map": workflow_name_map,
        }

    def _analyze_table_lineage_dependencies(
        self,
        workflow_produces: Dict[int, Set[str]],
        workflow_consumes: Dict[int, Set[str]],
        workflow_name_map: Dict[int, str],
        dependent_relations: List[DependentRelation],
        test_workflow_codes: Set[int] = None,
        child_workflow_codes: Set[int] = None,
        independent_workflow_codes: Set[int] = None,
    ) -> Tuple[List[TableLineageDependency], List[TableLineageDependency]]:
        """
        分析表血缘驱动的跨工作流依赖

        只关注：独立工作流使用其他工作流的输出表
        子工作流之间的依赖在父工作流 DAG 中已体现

        Args:
            workflow_produces: 每个工作流输出的表
            workflow_consumes: 每个工作流输入的表
            workflow_name_map: 工作流 code -> name 映射
            dependent_relations: DEPENDENT 任务列表
            test_workflow_codes: 测试/复制工作流 code（需过滤）
            child_workflow_codes: SUB_PROCESS 子工作流 code（已有显式依赖）
            independent_workflow_codes: 独立工作流 code（需检查）

        Returns:
            (table_lineage_dependencies, missing_dependencies)
        """
        test_workflow_codes = test_workflow_codes or set()
        child_workflow_codes = child_workflow_codes or set()
        independent_workflow_codes = independent_workflow_codes or set()

        # 构建 DEPENDENT 关系映射：workflow -> 它等待的 workflow 列表
        dependent_waiting: Dict[int, Set[int]] = {}
        for dep in dependent_relations:
            if dep.is_empty:
                continue
            for task_dep in dep.depend_task_list:
                # dependTaskList 结构: [{projectCode, processDefinitionCode, ...}]
                depend_wf_code = task_dep.get("processDefinitionCode")
                if depend_wf_code:
                    if dep.workflow_code not in dependent_waiting:
                        dependent_waiting[dep.workflow_code] = set()
                    dependent_waiting[dep.workflow_code].add(int(depend_wf_code))

        table_lineage_deps: List[TableLineageDependency] = []
        missing_deps: List[TableLineageDependency] = []

        # 遍历所有工作流，找出表血缘依赖
        # 只关注：独立工作流使用其他工作流（子工作流或独立工作流）的输出表

        for consumer_wf_code, consumer_tables in workflow_consumes.items():
            # 只检查独立工作流作为 consumer（子工作流在父 DAG 中已有调度）
            if consumer_wf_code not in independent_workflow_codes:
                continue

            for producer_wf_code, producer_tables in workflow_produces.items():
                # 排除自身
                if consumer_wf_code == producer_wf_code:
                    continue

                # 过滤测试工作流作为 producer
                if producer_wf_code in test_workflow_codes:
                    continue

                # 找交集：consumer 输入的表 = producer 输出的表
                shared_tables = consumer_tables & producer_tables
                if not shared_tables:
                    continue

                # 过滤临时视图/CTE 名称（view_*, temp_*, *_view, *_temp）
                real_shared_tables = {
                    t for t in shared_tables
                    if not t.startswith("view_") and not t.startswith("temp_")
                    and not t.endswith("_view") and not t.endswith("_temp")
                    and "view" not in t.lower() and "temp" not in t.lower()
                    and not t.startswith("hdfs:")  # 过滤 HDFS 路径
                }

                if not real_shared_tables:
                    continue

                # 检查是否有 DEPENDENT 任务等待 producer
                has_dependent = producer_wf_code in dependent_waiting.get(consumer_wf_code, set())

                dep = TableLineageDependency(
                    consumer_workflow_code=consumer_wf_code,
                    consumer_workflow_name=workflow_name_map.get(consumer_wf_code, str(consumer_wf_code)),
                    producer_workflow_code=producer_wf_code,
                    producer_workflow_name=workflow_name_map.get(producer_wf_code, str(producer_wf_code)),
                    shared_tables=list(real_shared_tables),
                    has_dependent_task=has_dependent,
                )

                table_lineage_deps.append(dep)

                # 如果没有 DEPENDENT 任务，记录为缺失依赖
                if not has_dependent:
                    missing_deps.append(dep)

        return table_lineage_deps, missing_deps

    def analyze_project(self, project_name: str) -> ImplicitDependencyResult:
        """
        分析项目的隐式依赖关系

        Args:
            project_name: 项目名称

        Returns:
            ImplicitDependencyResult
        """
        print(f"\n{'='*60}")
        print(f"[INFO] 分析项目: {project_name}")
        print(f"{'='*60}\n")

        # 获取项目配置
        project_config = self._get_project_config(project_name)
        if not project_config:
            print(f"[ERROR] 项目 '{project_name}' 未在配置中找到")
            print(f"[INFO] 可用项目: {[p.get('name') for p in self.projects_config.get('projects', [])]}")
            return self._empty_result(project_name)

        project_code = project_config.get("code")
        print(f"[INFO] 项目代码: {project_code}")

        # 创建 DSCLIClient
        if not self.client_class:
            print(f"[ERROR] 无法导入 DSCLIClient")
            return self._empty_result(project_name, project_code)

        client = self.client_class(
            api_url=project_config.get("ds_api_url"),
            api_token=project_config.get("ds_api_token"),
            version=project_config.get("ds_version", "3.2.0")
        )

        # 1. 获取工作流列表
        print(f"[INFO] 获取工作流列表...")
        workflows_result = client.list_workflows(project_code)

        if not workflows_result.success:
            print(f"[ERROR] 获取工作流列表失败: {workflows_result.stderr}")
            return self._empty_result(project_name, project_code)

        workflows_data = self._parse_json_response(workflows_result.stdout)
        if not workflows_data:
            print(f"[ERROR] 解析工作流列表失败")
            return self._empty_result(project_name, project_code)

        workflows: List[WorkflowInfo] = []
        for wf in workflows_data:
            workflows.append(WorkflowInfo(
                code=wf.get("code"),
                name=wf.get("name"),
                version=wf.get("version"),
                release_state=wf.get("releaseState", ""),
                description=wf.get("description", ""),
            ))

        print(f"[INFO] 共 {len(workflows)} 个工作流")

        # 创建工作流 name -> code 映射
        workflow_name_map: Dict[int, str] = {wf.code: wf.name for wf in workflows}

        # 2. 分析每个工作流，识别 SUB_PROCESS 和 DEPENDENT 任务
        print(f"[INFO] 分析工作流任务...")
        sub_process_calls: List[SubProcessCall] = []
        dependent_relations: List[DependentRelation] = []
        child_workflow_codes: Set[int] = set()

        for wf in workflows:
            print(f"  >> 分析: {wf.name}")

            detail_result = client.describe_workflow(project_code, wf.code)
            if not detail_result.success:
                print(f"     [WARN] 获取详情失败: {detail_result.stderr[:50]}")
                continue

            detail_data = self._parse_json_response(detail_result.stdout)
            if not detail_data:
                continue

            tasks = detail_data.get("tasks", [])
            for task in tasks:
                task_type = task.get("taskType")
                task_code = task.get("code")
                task_name = task.get("name")
                task_params = task.get("taskParams", {})

                if isinstance(task_params, str):
                    try:
                        task_params = json.loads(task_params)
                    except:
                        task_params = {}

                # SUB_PROCESS 任务
                if task_type == "SUB_PROCESS":
                    sub_wf_code = task_params.get("processDefinitionCode")
                    if sub_wf_code:
                        sub_process_calls.append(SubProcessCall(
                            parent_workflow_code=wf.code,
                            parent_workflow_name=wf.name,
                            task_code=task_code,
                            task_name=task_name,
                            sub_workflow_code=sub_wf_code,
                            sub_workflow_name=workflow_name_map.get(sub_wf_code, ""),
                        ))
                        child_workflow_codes.add(sub_wf_code)
                        print(f"     [SUB_PROCESS] {task_name} -> {workflow_name_map.get(sub_wf_code, sub_wf_code)}")

                # DEPENDENT 任务
                elif task_type == "DEPENDENT":
                    depend_task_list = task_params.get("dependence", {}).get("dependTaskList", [])
                    is_empty = not depend_task_list or len(depend_task_list) == 0

                    dependent_relations.append(DependentRelation(
                        workflow_code=wf.code,
                        workflow_name=wf.name,
                        task_code=task_code,
                        task_name=task_name,
                        depend_task_list=depend_task_list,
                        is_empty=is_empty,
                    ))

                    if is_empty:
                        print(f"     [DEPENDENT] {task_name} -> (空配置)")
                    else:
                        print(f"     [DEPENDENT] {task_name} -> {len(depend_task_list)} 个依赖")

        # 3. 分类工作流
        print(f"\n[INFO] 分类工作流...")

        # 主调度工作流（有 SUB_PROCESS 任务）
        main_workflow_codes = set(call.parent_workflow_code for call in sub_process_calls)
        main_workflows = [wf for wf in workflows if wf.code in main_workflow_codes]

        # 测试/复制工作流（名称包含测试、copy 等）
        test_keywords = ["测试", "test", "copy", "_copy_", "agent-test"]
        test_workflows = [
            wf for wf in workflows
            if any(kw in wf.name.lower() for kw in test_keywords)
        ]

        # 真正独立的工作流（无父工作流调用，非测试）
        independent_workflows = [
            wf for wf in workflows
            if wf.code not in child_workflow_codes
            and wf.code not in main_workflow_codes
            and wf not in test_workflows
        ]

        print(f"  >> 主调度工作流: {len(main_workflows)}")
        print(f"  >> SUB_PROCESS 子工作流: {len(child_workflow_codes)}")
        print(f"  >> 真正独立工作流: {len(independent_workflows)}")
        print(f"  >> 测试/复制工作流: {len(test_workflows)}")

        # 4. 分析表血缘驱动的依赖
        print(f"\n[INFO] 分析表血缘依赖...")
        table_lineage_deps: List[TableLineageDependency] = []
        missing_deps: List[TableLineageDependency] = []

        # 构建测试工作流和子工作流 code 集合（用于过滤）
        test_wf_codes = set(wf.code for wf in test_workflows)
        independent_wf_codes = set(wf.code for wf in independent_workflows)

        lineage_data = self._load_table_lineage(project_code)
        if lineage_data:
            table_lineage_deps, missing_deps = self._analyze_table_lineage_dependencies(
                lineage_data["workflow_produces"],
                lineage_data["workflow_consumes"],
                lineage_data["workflow_name_map"],
                dependent_relations,
                test_workflow_codes=test_wf_codes,
                child_workflow_codes=child_workflow_codes,
                independent_workflow_codes=independent_wf_codes,
            )
            print(f"  >> 表血缘依赖: {len(table_lineage_deps)} 条")
            print(f"  >> 缺失 DEPENDENT: {len(missing_deps)} 条（需告警）")

            # 打印缺失依赖详情
            if missing_deps:
                print(f"\n[WARN] 缺失 DEPENDENT 任务的工作流依赖:")
                for dep in missing_deps[:10]:  # 只显示前10条
                    print(f"  - {dep.consumer_workflow_name} 应等待 {dep.producer_workflow_name}")
                    print(f"    共享表: {', '.join(dep.shared_tables[:3])}{'...' if len(dep.shared_tables) > 3 else ''}")

        # 5. 生成依赖图（多种格式）
        ascii_graph = self._generate_ascii_graph(
            workflows, main_workflows, sub_process_calls,
            child_workflow_codes, independent_workflows, test_workflows
        )

        dot_graph = self._generate_dot_graph(
            workflows, main_workflows, sub_process_calls,
            child_workflow_codes, independent_workflows, test_workflows
        )

        html_report = self._generate_html_report(
            ImplicitDependencyResult(
                project_code=project_code,
                project_name=project_name,
                scan_time=datetime.now().isoformat(),
                total_workflows=len(workflows),
                main_workflows=main_workflows,
                sub_process_calls=sub_process_calls,
                dependent_relations=dependent_relations,
                child_workflows=child_workflow_codes,
                independent_workflows=independent_workflows,
                test_workflows=test_workflows,
                table_lineage_dependencies=table_lineage_deps,
                missing_dependencies=missing_deps,
                dependency_graph_dot=dot_graph,
                summary="",
            )
        )

        # 6. 生成摘要
        summary = self._generate_summary(
            project_name, project_code, workflows, main_workflows,
            sub_process_calls, dependent_relations, child_workflow_codes,
            independent_workflows, test_workflows
        )

        return ImplicitDependencyResult(
            project_code=project_code,
            project_name=project_name,
            scan_time=datetime.now().isoformat(),
            total_workflows=len(workflows),
            main_workflows=main_workflows,
            sub_process_calls=sub_process_calls,
            dependent_relations=dependent_relations,
            child_workflows=child_workflow_codes,
            independent_workflows=independent_workflows,
            test_workflows=test_workflows,
            table_lineage_dependencies=table_lineage_deps,
            missing_dependencies=missing_deps,
            dependency_graph_dot=dot_graph,
            dependency_graph_ascii=ascii_graph,
            html_report=html_report,
            summary=summary,
        )

    def _parse_json_response(self, stdout: str) -> Optional[List]:
        """解析 dsctl JSON 输出"""
        try:
            data = json.loads(stdout)
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            return None
        except json.JSONDecodeError:
            return None

    def _empty_result(self, project_name: str, project_code: int = 0) -> ImplicitDependencyResult:
        """返回空结果"""
        return ImplicitDependencyResult(
            project_code=project_code,
            project_name=project_name,
            scan_time=datetime.now().isoformat(),
            total_workflows=0,
            main_workflows=[],
            sub_process_calls=[],
            dependent_relations=[],
            child_workflows=set(),
            independent_workflows=[],
            test_workflows=[],
            table_lineage_dependencies=[],
            missing_dependencies=[],
            dependency_graph_dot="",
            dependency_graph_ascii="",
            html_report="",
            summary="分析失败",
        )

    def _generate_ascii_graph(
        self,
        workflows: List[WorkflowInfo],
        main_workflows: List[WorkflowInfo],
        sub_process_calls: List[SubProcessCall],
        child_workflow_codes: Set[int],
        independent_workflows: List[WorkflowInfo],
        test_workflows: List[WorkflowInfo],
    ) -> str:
        """生成 ASCII 文本格式依赖图"""
        lines = []
        lines.append("+" + "-"*78 + "+")
        lines.append("|" + " "*30 + "依赖关系图" + " "*36 + "|")
        lines.append("+" + "-"*78 + "+")

        # 主调度工作流
        lines.append("")
        lines.append("[主调度工作流]")
        lines.append("-"*40)
        for wf in main_workflows:
            lines.append(f"    * {wf.name} ({wf.code})")

        # SUB_PROCESS 调用关系
        lines.append("")
        lines.append("[SUB_PROCESS 调用关系]")
        lines.append("-"*40)

        by_parent: Dict[int, List[SubProcessCall]] = {}
        for call in sub_process_calls:
            if call.parent_workflow_code not in by_parent:
                by_parent[call.parent_workflow_code] = []
            by_parent[call.parent_workflow_code].append(call)

        for parent_code, calls in sorted(by_parent.items()):
            parent_name = calls[0].parent_workflow_name
            lines.append(f"    {parent_name}")
            for call in sorted(calls, key=lambda x: x.task_name):
                lines.append(f"        |-- [{call.task_name}] -> {call.sub_workflow_name}")

        # 独立工作流
        lines.append("")
        lines.append("[独立工作流 - 需关注]")
        lines.append("-"*40)
        for wf in independent_workflows:
            lines.append(f"    ! {wf.name} ({wf.code})")

        # 测试工作流
        if test_workflows:
            lines.append("")
            lines.append("[测试/复制工作流 - 可忽略]")
            lines.append("-"*40)
            for wf in test_workflows:
                lines.append(f"    o {wf.name} ({wf.code})")

        lines.append("")
        lines.append("+" + "-"*78 + "+")
        lines.append("| * 主调度  |-- SUB_PROCESS调用  ! 需关注  o 测试/复制 |")
        lines.append("+" + "-"*78 + "+")

        return "\n".join(lines)

    def _generate_dot_graph(
        self,
        workflows: List[WorkflowInfo],
        main_workflows: List[WorkflowInfo],
        sub_process_calls: List[SubProcessCall],
        child_workflow_codes: Set[int],
        independent_workflows: List[WorkflowInfo],
        test_workflows: List[WorkflowInfo],
    ) -> str:
        """生成 DOT 格式依赖图"""
        lines = [
            "digraph implicit_dependencies {",
            "    rankdir=TB;",
            "    node [shape=box, style=filled];",
            "",
        ]

        # 主调度工作流
        lines.append("    // 主调度工作流")
        lines.append("    subgraph cluster_main {")
        lines.append("        label = \"主调度工作流\";")
        lines.append("        style = filled;")
        lines.append("        fillcolor = lightyellow;")
        for wf in main_workflows:
            lines.append(f'        "{wf.name}" [fillcolor=gold, label="{wf.name}\\n{wf.code}"];')
        lines.append("    }")
        lines.append("")

        # SUB_PROCESS 子工作流
        if child_workflow_codes:
            lines.append("    // SUB_PROCESS 子工作流")
            lines.append("    subgraph cluster_sub {")
            lines.append("        label = \"SUB_PROCESS 子工作流\";")
            lines.append("        style = filled;")
            lines.append("        fillcolor = lightgreen;")
            for wf in workflows:
                if wf.code in child_workflow_codes and wf not in test_workflows:
                    lines.append(f'        "{wf.name}" [label="{wf.name}\\n{wf.code}"];')
            lines.append("    }")
            lines.append("")

        # SUB_PROCESS 调用边
        lines.append("    // SUB_PROCESS 调用关系")
        for call in sub_process_calls:
            if call.sub_workflow_name:
                lines.append(f'    "{call.parent_workflow_name}" -> "{call.sub_workflow_name}" [label="{call.task_name}", color=blue];')

        # 独立工作流
        if independent_workflows:
            lines.append("")
            lines.append("    // 真正独立的工作流")
            lines.append("    subgraph cluster_independent {")
            lines.append("        label = \"独立工作流（需关注）\";")
            lines.append("        style = filled;")
            lines.append("        fillcolor = lightcoral;")
            for wf in independent_workflows:
                lines.append(f'        "{wf.name}" [fillcolor=coral, label="{wf.name}\\n{wf.code}"];')
            lines.append("    }")

        # 测试工作流
        if test_workflows:
            lines.append("")
            lines.append("    // 测试/复制工作流（忽略）")
            lines.append("    subgraph cluster_test {")
            lines.append("        label = \"测试/复制工作流\";")
            lines.append("        style = filled;")
            lines.append("        fillcolor = gray;")
            for wf in test_workflows:
                lines.append(f'        "{wf.name}" [fillcolor=gray, label="{wf.name}\\n{wf.code}"];')
            lines.append("    }")

        lines.append("}")
        return "\n".join(lines)

    def _generate_html_report(self, result: ImplicitDependencyResult) -> str:
        """生成 HTML 报告（包含可交互的依赖图）"""
        lines = []
        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='zh-CN'>")
        lines.append("<head>")
        lines.append("    <meta charset='UTF-8'>")
        lines.append("    <title>隐式依赖分析报告 - " + result.project_name + "</title>")
        lines.append("    <style>")
        lines.append("        body { font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 20px; background: #f5f5f5; }")
        lines.append("        .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 8px; }")
        lines.append("        h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }")
        lines.append("        h2 { color: #555; margin-top: 30px; }")
        lines.append("        table { width: 100%; border-collapse: collapse; margin: 15px 0; }")
        lines.append("        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }")
        lines.append("        th { background: #007bff; color: white; }")
        lines.append("        tr:nth-child(even) { background: #f9f9f9; }")
        lines.append("        .main { background: #fff3cd; }")
        lines.append("        .child { background: #d4edda; }")
        lines.append("        .independent { background: #f8d7da; }")
        lines.append("        .test { background: #e2e3e5; color: #666; }")
        lines.append("        .stats { display: flex; gap: 20px; margin: 20px 0; }")
        lines.append("        .stat-box { background: #e9ecef; padding: 15px; border-radius: 5px; flex: 1; text-align: center; }")
        lines.append("        .stat-box h3 { margin: 0; color: #007bff; }")
        lines.append("        .stat-box p { margin: 5px 0; font-size: 24px; font-weight: bold; }")
        lines.append("        .warning { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0; }")
        lines.append("        .dot-link { background: #007bff; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; display: inline-block; }")
        lines.append("    </style>")
        lines.append("</head>")
        lines.append("<body>")
        lines.append("    <div class='container'>")
        lines.append("        <h1>隐式依赖分析报告</h1>")
        lines.append("        <p><strong>项目:</strong> " + result.project_name + " (" + str(result.project_code) + ")</p>")
        lines.append("        <p><strong>分析时间:</strong> " + result.scan_time + "</p>")
        lines.append("")
        lines.append("        <div class='stats'>")
        lines.append("            <div class='stat-box'><h3>总工作流</h3><p>" + str(result.total_workflows) + "</p></div>")
        lines.append("            <div class='stat-box'><h3>主调度</h3><p>" + str(len(result.main_workflows)) + "</p></div>")
        lines.append("            <div class='stat-box'><h3>子工作流</h3><p>" + str(len(result.child_workflows)) + "</p></div>")
        lines.append("            <div class='stat-box'><h3>独立工作流</h3><p>" + str(len(result.independent_workflows)) + "</p></div>")
        lines.append("        </div>")
        lines.append("")
        lines.append("        <h2>主调度工作流</h2>")
        lines.append("        <table>")
        lines.append("            <tr><th>名称</th><th>Code</th><th>子工作流数</th></tr>")
        for wf in result.main_workflows:
            child_count = len([c for c in result.sub_process_calls if c.parent_workflow_code == wf.code])
            lines.append(f"            <tr class='main'><td>{wf.name}</td><td>{wf.code}</td><td>{child_count}</td></tr>")
        lines.append("        </table>")
        lines.append("")
        lines.append("        <h2>SUB_PROCESS 调用详情</h2>")
        lines.append("        <table>")
        lines.append("            <tr><th>父工作流</th><th>任务名</th><th>子工作流</th><th>子工作流Code</th></tr>")
        for call in result.sub_process_calls:
            lines.append(f"            <tr class='child'><td>{call.parent_workflow_name}</td><td>{call.task_name}</td><td>{call.sub_workflow_name}</td><td>{call.sub_workflow_code}</td></tr>")
        lines.append("        </table>")
        lines.append("")
        lines.append("        <h2>独立工作流（需关注）</h2>")
        if result.independent_workflows:
            lines.append("        <div class='warning'>")
            lines.append("            <strong>⚠ 以下工作流无隐式依赖，请检查是否应有前置依赖：</strong>")
            lines.append("        </div>")
            lines.append("        <table>")
            lines.append("            <tr><th>名称</th><th>Code</th><th>版本</th></tr>")
            for wf in result.independent_workflows:
                lines.append(f"            <tr class='independent'><td>{wf.name}</td><td>{wf.code}</td><td>{wf.version}</td></tr>")
            lines.append("        </table>")
        else:
            lines.append("        <p>✓ 所有工作流都有隐式依赖关系</p>")
        lines.append("")
        lines.append("        <h2>DEPENDENT 任务</h2>")
        lines.append("        <table>")
        lines.append("            <tr><th>工作流</th><th>任务名</th><th>状态</th></tr>")
        for dep in result.dependent_relations:
            status = "空配置（需检查）" if dep.is_empty else f"{len(dep.depend_task_list)} 个依赖"
            css_class = "independent" if dep.is_empty else ""
            lines.append(f"            <tr class='{css_class}'><td>{dep.workflow_name}</td><td>{dep.task_name}</td><td>{status}</td></tr>")
        lines.append("        </table>")
        lines.append("")
        lines.append("        <h2>在线渲染 DOT 图</h2>")
        lines.append("        <p>点击下方链接，在线查看依赖关系图：</p>")
        lines.append("        <a class='dot-link' href='https://dreampuf.github.io/GraphvizOnline/?dot=")
        # 编码 DOT 内容为 URL 参数
        import urllib.parse
        dot_encoded = urllib.parse.quote(result.dependency_graph_dot)
        lines.append(dot_encoded + "' target='_blank'>在线查看 DOT 图</a>")
        lines.append("")
        lines.append("        <h2>ASCII 文本依赖图</h2>")
        lines.append("        <pre style='background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;'>")
        lines.append(self._generate_ascii_graph(
            [], result.main_workflows, result.sub_process_calls,
            result.child_workflows, result.independent_workflows, result.test_workflows
        ))
        lines.append("        </pre>")
        lines.append("    </div>")
        lines.append("</body>")
        lines.append("</html>")
        return "\n".join(lines)

    def _generate_summary(
        self,
        project_name: str,
        project_code: int,
        workflows: List[WorkflowInfo],
        main_workflows: List[WorkflowInfo],
        sub_process_calls: List[SubProcessCall],
        dependent_relations: List[DependentRelation],
        child_workflow_codes: Set[int],
        independent_workflows: List[WorkflowInfo],
        test_workflows: List[WorkflowInfo],
    ) -> str:
        """生成摘要"""
        parts = [
            f"项目 {project_name} ({project_code}) 隐式依赖分析",
            f"总工作流: {len(workflows)}",
            f"主调度: {len(main_workflows)}, 子工作流: {len(child_workflow_codes)}",
            f"独立工作流: {len(independent_workflows)}, 测试工作流: {len(test_workflows)}",
        ]
        return " | ".join(parts)

    def generate_report(self, result: ImplicitDependencyResult) -> str:
        """生成分析报告"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"DolphinScheduler 隐式依赖分析报告")
        lines.append("=" * 80)
        lines.append(f"项目: {result.project_name} ({result.project_code})")
        lines.append(f"分析时间: {result.scan_time}")
        lines.append("")
        lines.append(f"摘要: {result.summary}")
        lines.append("")

        # 工作流分类
        lines.append("=" * 80)
        lines.append("工作流分类")
        lines.append("=" * 80)
        lines.append(f"总工作流数: {result.total_workflows}")
        lines.append("")
        lines.append(f"1. 主调度工作流 ({len(result.main_workflows)} 个)")
        for wf in result.main_workflows:
            lines.append(f"   - {wf.name} ({wf.code})")
        lines.append("")

        lines.append(f"2. SUB_PROCESS 子工作流 ({len(result.child_workflows)} 个)")
        child_names = sorted(set(
            call.sub_workflow_name
            for call in result.sub_process_calls
            if call.sub_workflow_name
        ))
        for name in child_names:
            lines.append(f"   - {name}")
        lines.append("")

        lines.append(f"3. 真正独立工作流 ({len(result.independent_workflows)} 个) - 需关注")
        for wf in result.independent_workflows:
            lines.append(f"   - {wf.name} ({wf.code})")
        lines.append("")

        lines.append(f"4. 测试/复制工作流 ({len(result.test_workflows)} 个) - 可忽略")
        for wf in result.test_workflows:
            lines.append(f"   - {wf.name} ({wf.code})")
        lines.append("")

        # SUB_PROCESS 调用详情
        lines.append("=" * 80)
        lines.append("SUB_PROCESS 调用详情")
        lines.append("=" * 80)

        # 按父工作流分组
        by_parent: Dict[int, List[SubProcessCall]] = {}
        for call in result.sub_process_calls:
            if call.parent_workflow_code not in by_parent:
                by_parent[call.parent_workflow_code] = []
            by_parent[call.parent_workflow_code].append(call)

        for parent_code, calls in sorted(by_parent.items()):
            parent_name = calls[0].parent_workflow_name
            lines.append(f"\n{parent_name} ({parent_code}) -> {len(calls)} 个子工作流:")
            for call in sorted(calls, key=lambda x: x.task_name):
                lines.append(f"   - [{call.task_name}] -> {call.sub_workflow_name} ({call.sub_workflow_code})")

        lines.append("")

        # DEPENDENT 任务详情
        lines.append("=" * 80)
        lines.append("DEPENDENT 任务详情")
        lines.append("=" * 80)

        if result.dependent_relations:
            for dep in result.dependent_relations:
                status = "空配置（需检查）" if dep.is_empty else f"{len(dep.depend_task_list)} 个依赖"
                lines.append(f"   - {dep.workflow_name}/{dep.task_name}: {status}")
        else:
            lines.append("   无 DEPENDENT 任务")

        lines.append("")

        # 依赖图 ASCII（无 Graphviz 也可查看）
        lines.append("=" * 80)
        lines.append("依赖关系图（ASCII 文本格式）")
        lines.append("=" * 80)
        lines.append(result.dependency_graph_ascii)
        lines.append("")

        # 依赖图 DOT
        lines.append("=" * 80)
        lines.append("依赖关系图 (DOT 格式)")
        lines.append("=" * 80)
        lines.append("提示: 可使用在线渲染器 https://dreampuf.github.io/GraphvizOnline 查看")
        lines.append("")
        lines.append(result.dependency_graph_dot)
        lines.append("")

        # 结论和建议
        lines.append("=" * 80)
        lines.append("结论和建议")
        lines.append("=" * 80)

        if len(result.independent_workflows) > 0:
            lines.append(f"\n[需关注] {len(result.independent_workflows)} 个工作流无隐式依赖:")
            for wf in result.independent_workflows:
                lines.append(f"   - {wf.name}")
            lines.append("")
            lines.append("建议检查:")
            lines.append("   1. 这些工作流是否应有前置依赖（如数据源工作流）")
            lines.append("   2. 是否需要添加 DEPENDENT 任务等待其他工作流完成")
            lines.append("   3. 是否为独立调度的工作流（正常情况）")
        else:
            lines.append("\n[OK] 所有工作流都有隐式依赖关系或为测试工作流")

        # DEPENDENT 空配置警告
        empty_deps = [d for d in result.dependent_relations if d.is_empty]
        if empty_deps:
            lines.append(f"\n[WARN] {len(empty_deps)} 个 DEPENDENT 任务配置为空:")
            for dep in empty_deps:
                lines.append(f"   - {dep.workflow_name}/{dep.task_name}")
            lines.append("建议检查 DEPENDENT 任务配置是否正确")

        return "\n".join(lines)

    def export_json_report(self, result: ImplicitDependencyResult, output_path: str) -> None:
        """导出 JSON 报告"""
        report_data = {
            "project_code": result.project_code,
            "project_name": result.project_name,
            "scan_time": result.scan_time,
            "summary": result.summary,
            "statistics": {
                "total_workflows": result.total_workflows,
                "main_workflows": len(result.main_workflows),
                "child_workflows": len(result.child_workflows),
                "independent_workflows": len(result.independent_workflows),
                "test_workflows": len(result.test_workflows),
                "sub_process_calls": len(result.sub_process_calls),
                "dependent_tasks": len(result.dependent_relations),
                "table_lineage_dependencies": len(result.table_lineage_dependencies),
                "missing_dependencies": len(result.missing_dependencies),
            },
            "main_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.main_workflows
            ],
            "sub_process_calls": [
                {
                    "parent_workflow_code": call.parent_workflow_code,
                    "parent_workflow_name": call.parent_workflow_name,
                    "task_name": call.task_name,
                    "sub_workflow_code": call.sub_workflow_code,
                    "sub_workflow_name": call.sub_workflow_name,
                }
                for call in result.sub_process_calls
            ],
            "dependent_relations": [
                {
                    "workflow_code": dep.workflow_code,
                    "workflow_name": dep.workflow_name,
                    "task_name": dep.task_name,
                    "is_empty": dep.is_empty,
                    "depend_task_count": len(dep.depend_task_list),
                }
                for dep in result.dependent_relations
            ],
            "table_lineage_dependencies": [
                {
                    "consumer_workflow_code": dep.consumer_workflow_code,
                    "consumer_workflow_name": dep.consumer_workflow_name,
                    "producer_workflow_code": dep.producer_workflow_code,
                    "producer_workflow_name": dep.producer_workflow_name,
                    "shared_tables": dep.shared_tables,
                    "has_dependent_task": dep.has_dependent_task,
                }
                for dep in result.table_lineage_dependencies
            ],
            "missing_dependencies": [
                {
                    "consumer_workflow_code": dep.consumer_workflow_code,
                    "consumer_workflow_name": dep.consumer_workflow_name,
                    "producer_workflow_code": dep.producer_workflow_code,
                    "producer_workflow_name": dep.producer_workflow_name,
                    "shared_tables": dep.shared_tables,
                    "has_dependent_task": dep.has_dependent_task,
                }
                for dep in result.missing_dependencies
            ],
            "independent_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.independent_workflows
            ],
            "test_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.test_workflows
            ],
            "dependency_graph_dot": result.dependency_graph_dot,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)


def analyze_implicit_dependency(project_name: str, output_dir: str = None) -> ImplicitDependencyResult:
    """
    分析项目隐式依赖（便捷入口）

    Args:
        project_name: 项目名称
        output_dir: 输出目录（可选，默认 data/graph）

    Returns:
        ImplicitDependencyResult
    """
    # 默认输出到 data/graph 目录（与血缘查询同一目录）
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / "data" / "graph")

    analyzer = ImplicitDependencyAnalyzer()
    result = analyzer.analyze_project(project_name)

    if result.total_workflows > 0:
        # 按项目名称创建子目录（与血缘查询一致）
        project_dir = Path(output_dir) / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # 生成 JS 数据文件（供 HTML 页面使用）
        js_data = {
            "project_code": result.project_code,
            "project_name": result.project_name,
            "scan_time": result.scan_time,
            "total_workflows": result.total_workflows,
            "statistics": {
                "main_workflows": len(result.main_workflows),
                "child_workflows": len(result.child_workflows),
                "independent_workflows": len(result.independent_workflows),
                "test_workflows": len(result.test_workflows),
                "sub_process_calls": len(result.sub_process_calls),
                "dependent_tasks": len(result.dependent_relations),
                "table_lineage_dependencies": len(result.table_lineage_dependencies),
                "missing_dependencies": len(result.missing_dependencies),
            },
            "main_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.main_workflows
            ],
            "sub_process_calls": [
                {
                    "parent_workflow_code": call.parent_workflow_code,
                    "parent_workflow_name": call.parent_workflow_name,
                    "task_name": call.task_name,
                    "sub_workflow_code": call.sub_workflow_code,
                    "sub_workflow_name": call.sub_workflow_name,
                }
                for call in result.sub_process_calls
            ],
            "dependent_relations": [
                {
                    "workflow_code": dep.workflow_code,
                    "workflow_name": dep.workflow_name,
                    "task_name": dep.task_name,
                    "is_empty": dep.is_empty,
                    "depend_task_count": len(dep.depend_task_list),
                }
                for dep in result.dependent_relations
            ],
            "table_lineage_dependencies": [
                {
                    "consumer_workflow_code": dep.consumer_workflow_code,
                    "consumer_workflow_name": dep.consumer_workflow_name,
                    "producer_workflow_code": dep.producer_workflow_code,
                    "producer_workflow_name": dep.producer_workflow_name,
                    "shared_tables": dep.shared_tables,
                    "has_dependent_task": dep.has_dependent_task,
                }
                for dep in result.table_lineage_dependencies
            ],
            "missing_dependencies": [
                {
                    "consumer_workflow_code": dep.consumer_workflow_code,
                    "consumer_workflow_name": dep.consumer_workflow_name,
                    "producer_workflow_code": dep.producer_workflow_code,
                    "producer_workflow_name": dep.producer_workflow_name,
                    "shared_tables": dep.shared_tables,
                    "has_dependent_task": dep.has_dependent_task,
                }
                for dep in result.missing_dependencies
            ],
            "child_workflows": list(result.child_workflows),
            "independent_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.independent_workflows
            ],
            "test_workflows": [
                {"code": wf.code, "name": wf.name, "version": wf.version}
                for wf in result.test_workflows
            ],
            "dependency_graph_dot": result.dependency_graph_dot,
        }

        js_content = f"const implicitDependencyData = {json.dumps(js_data, ensure_ascii=False)};"
        js_file = project_dir / "implicit_dependency_data.js"
        with open(js_file, "w", encoding="utf-8") as f:
            f.write(js_content)
        print(f"\n[INFO] JS 数据已保存: {js_file}")

        # 生成 HTML 报告（可直接用浏览器查看）
        html_path = project_dir / "implicit_dependency.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(result.html_report)
        print(f"[INFO] HTML 报告已保存: {html_path}")

        # 生成 DOT 文件
        dot_path = project_dir / "dependency_graph.dot"
        with open(dot_path, "w", encoding="utf-8") as f:
            f.write(result.dependency_graph_dot)
        print(f"[INFO] DOT 图已保存: {dot_path}")

        # 更新项目列表索引（用于下拉框）
        update_implicit_project_list(output_dir)

    return result


def update_implicit_project_list(graph_dir: str):
    """更新隐式依赖项目列表索引"""
    graph_path = Path(graph_dir)

    # 扫描所有项目的隐式依赖数据
    projects = []
    for project_dir in graph_path.iterdir():
        if project_dir.is_dir():
            js_file = project_dir / "implicit_dependency_data.js"
            if js_file.exists():
                # 从目录名获取项目名称
                project_name = project_dir.name
                projects.append({
                    "name": project_name,
                    "dir": project_name,
                })

    # 生成索引 JS 文件
    index_content = f"const implicitProjectList = {json.dumps(projects, ensure_ascii=False)};"
    index_file = graph_path / "implicit_project_list.js"
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(index_content)
    print(f"[INFO] 项目列表索引已更新: {index_file}")


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: python -m src.tools.implicit_dependency_analyzer <project_name>")
        print("Example: python -m src.tools.implicit_dependency_analyzer ad_monitor")
        sys.exit(1)

    project_name = sys.argv[1]

    # 默认输出目录
    output_dir = PROJECT_ROOT / "data" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = analyze_implicit_dependency(project_name, str(output_dir))

    # 打印报告
    print("\n" + "=" * 80)
    print("分析报告")
    print("=" * 80)
    analyzer = ImplicitDependencyAnalyzer()
    print(analyzer.generate_report(result))


__all__ = [
    "ImplicitDependencyAnalyzer",
    "ImplicitDependencyResult",
    "TableLineageDependency",
    "analyze_implicit_dependency",
]