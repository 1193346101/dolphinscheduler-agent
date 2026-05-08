"""
GraphScanner - 图谱扫描器

扫描 DolphinScheduler 工作流和代码仓库构建知识图谱
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

from .storage import GraphStorage
from .models import (
    Graph,
    GraphNodes,
    GraphEdges,
    WorkflowNode,
    TaskNode,
    TableNode,
    ClassNode,
)
from .code_searcher import CodeSearcher
from .sql_parser import SQLParser
from ..integrations.dsctl_wrapper import DSCLIClient, CLIResult


class GraphScanner:
    """
    图谱扫描器

    扫描 DolphinScheduler 项目的工作流定义，
    结合代码仓库分析，构建知识图谱。
    """

    def __init__(self, storage: GraphStorage, code_root: str):
        """
        初始化扫描器

        Args:
            storage: 图谱存储管理器
            code_root: 代码仓库根目录
        """
        self.storage = storage
        self.code_searcher = CodeSearcher(code_root)
        self.sql_parser = SQLParser()

    def scan_project(
        self,
        project_code: str,
        project_name: str,
        ds_api_url: str,
        ds_api_token: str,
    ) -> Dict:
        """
        扫描项目构建知识图谱

        Args:
            project_code: 项目编码
            project_name: 项目名称
            ds_api_url: DolphinScheduler API URL
            ds_api_token: API Token

        Returns:
            统计信息 {"workflows_count": N, "tasks_count": N, "tables_count": N}
        """
        # 创建 DSCLI 客户端
        dsctl = DSCLIClient(api_url=ds_api_url, api_token=ds_api_token)

        # 创建图谱对象
        graph = Graph(
            project_code=project_code,
            project_name=project_name,
            scanned_at=datetime.now().isoformat(),
            version=1,
            nodes=GraphNodes(),
            edges=GraphEdges(),
        )

        # 收集所有表名用于统计
        all_tables: set = set()

        # 获取所有工作流
        workflows = self._fetch_workflows(dsctl, project_code)

        # 解析每个工作流
        for workflow in workflows:
            self._parse_workflow(workflow, dsctl, graph, project_name, all_tables)

        # 保存图谱
        self.storage.save_graph(project_code, graph.to_dict())

        return {
            "workflows_count": len(graph.nodes.workflows),
            "tasks_count": len(graph.nodes.tasks),
            "tables_count": len(all_tables),
        }

    def _fetch_workflows(self, dsctl: DSCLIClient, project_code: str) -> List[Dict]:
        """
        获取项目中的所有工作流

        Args:
            dsctl: DSCLI 客户端
            project_code: 项目编码

        Returns:
            工作流列表
        """
        result = dsctl.list_workflows(int(project_code))

        if not result.success:
            return []

        try:
            workflows = json.loads(result.stdout)
            if isinstance(workflows, list):
                return workflows
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def _parse_workflow(
        self,
        workflow: Dict,
        dsctl: DSCLIClient,
        graph: Graph,
        project_name: str,
        all_tables: set,
    ) -> None:
        """
        解析工作流定义

        Args:
            workflow: 工作流基本信息 (code, name, version)
            dsctl: DSCLI 客户端
            graph: 图谱对象
            project_name: 项目名称
            all_tables: 收集的所有表名集合
        """
        workflow_code = str(workflow.get("code", ""))
        workflow_name = workflow.get("name", "")

        if not workflow_code:
            return

        # 获取工作流详细信息
        detail_result = dsctl.describe_workflow(
            int(graph.project_code),
            int(workflow_code)
        )

        if not detail_result.success:
            # 创建基本的 WorkflowNode
            workflow_node = WorkflowNode(
                code=workflow_code,
                name=workflow_name or "",
                schedule_type="UNKNOWN",
                schedule_cron="",
                is_sub_workflow=False,
                parent_workflow=None,
            )
            graph.nodes.workflows.append(workflow_node)
            return

        try:
            detail = json.loads(detail_result.stdout)
        except (json.JSONDecodeError, TypeError):
            detail = {}

        workflow_data = detail.get("workflow", {})
        tasks_data = detail.get("tasks", [])
        relations_data = detail.get("relations", [])

        # 创建 WorkflowNode
        schedule = workflow_data.get("schedule", {})
        schedule_cron = schedule.get("crontab", "") if schedule else ""
        schedule_type = "CRON" if schedule_cron else "MANUAL"

        workflow_node = WorkflowNode(
            code=workflow_code,
            name=workflow_data.get("name", workflow_name or ""),
            schedule_type=schedule_type,
            schedule_cron=schedule_cron,
            is_sub_workflow=False,
            parent_workflow=None,
        )
        graph.nodes.workflows.append(workflow_node)

        # 创建 workflow_contains_task 边
        for task in tasks_data:
            task_code = str(task.get("code", ""))
            if task_code:
                graph.edges.workflow_contains_task.append({
                    "source": workflow_code,
                    "target": task_code,
                })

        # 解析任务
        for task in tasks_data:
            self._parse_task(
                task,
                workflow_code,
                graph,
                project_name,
                all_tables
            )

        # 解析任务依赖关系
        self._parse_task_dependencies(relations_data, workflow_code, graph)

        # 解析工作流依赖 (dependence 字段)
        self._parse_workflow_dependencies(workflow_data, workflow_code, graph)

    def _parse_task(
        self,
        task: Dict,
        workflow_code: str,
        graph: Graph,
        project_name: str,
        all_tables: set,
    ) -> None:
        """
        解析单个任务

        Args:
            task: 任务定义
            workflow_code: 所属工作流编码
            graph: 图谱对象
            project_name: 项目名称
            all_tables: 所有表名集合
        """
        task_code = str(task.get("code", ""))
        task_name = task.get("name", "")
        task_type = task.get("taskType", "UNKNOWN")
        task_params = task.get("taskParams", {})

        if not task_code:
            return

        # 提取 Spark main class
        spark_main_class = None
        if task_type == "SPARK":
            spark_main_class = self._extract_spark_main_class(task_params)

        # 创建 TaskNode
        task_node = TaskNode(
            code=task_code,
            name=task_name or "",
            workflow_code=workflow_code,
            task_type=task_type,
            spark_main_class=spark_main_class,
            params=task_params,
        )
        graph.nodes.tasks.append(task_node)

        # 如果有 Spark main class，解析类文件中的表
        if spark_main_class:
            self._parse_class_tables(
                spark_main_class,
                task_code,
                graph,
                project_name,
                all_tables
            )

    def _extract_spark_main_class(self, params: Dict) -> Optional[str]:
        """
        从 Spark 任务参数中提取主类名

        Args:
            params: 任务参数

        Returns:
            主类名或 None
        """
        # 从 mainArgs 中提取 --class 参数
        main_args = params.get("mainArgs", "")
        if not main_args:
            return None

        # 正则匹配 --class xxx
        pattern = r'--class\s+(\S+)'
        match = re.search(pattern, main_args)
        if match:
            return match.group(1)

        return None

    def _parse_class_tables(
        self,
        class_name: str,
        task_code: str,
        graph: Graph,
        project_name: str,
        all_tables: set,
    ) -> None:
        """
        解析类文件中的表信息

        Args:
            class_name: 类名
            task_code: 任务编码
            graph: 图谱对象
            project_name: 项目名称
            all_tables: 所有表名集合
        """
        # 搜索类文件
        search_result = self.code_searcher.search_class(class_name, project_name)

        if not search_result.get("found"):
            return

        file_path = search_result.get("file_path", "")
        cross_project = search_result.get("cross_project", False)
        source_project = search_result.get("source_project")

        # 读取文件内容
        content = self.code_searcher.read_file_content(file_path)
        if not content:
            return

        # 获取文件扩展名
        import os
        file_ext = os.path.splitext(file_path)[1].lower()

        # 解析 SQL 提取表名
        tables = self.sql_parser.parse_file_content(content, file_ext)

        tables_input = tables.get("input", [])
        tables_output = tables.get("output", [])

        # 添加表名到集合
        for table in tables_input + tables_output:
            all_tables.add(table)

        # 创建 TableNode 并添加边
        for table_name in tables_input:
            # 检查是否已存在
            existing = None
            for t in graph.nodes.tables:
                if t.full_name == table_name:
                    existing = t
                    break

            if not existing:
                table_node = TableNode(
                    full_name=table_name,
                    table_type="HIVE",  # 默认 HIVE
                )
                graph.nodes.tables.append(table_node)

            # 添加 task_consumes_table 边
            graph.edges.task_consumes_table.append({
                "source": task_code,
                "target": table_name,
            })

        for table_name in tables_output:
            # 检查是否已存在
            existing = None
            for t in graph.nodes.tables:
                if t.full_name == table_name:
                    existing = t
                    break

            if not existing:
                table_node = TableNode(
                    full_name=table_name,
                    table_type="HIVE",
                )
                graph.nodes.tables.append(table_node)

            # 添加 task_produces_table 边
            graph.edges.task_produces_table.append({
                "source": task_code,
                "target": table_name,
            })

        # 创建 ClassNode
        class_node = ClassNode(
            name=class_name,
            file_path=file_path,
            cross_project=cross_project,
            source_project=source_project,
            tables_input=tables_input,
            tables_output=tables_output,
        )
        graph.nodes.classes.append(class_node)

        # 添加 class_maps_to_task 边
        graph.edges.class_maps_to_task.append({
            "source": class_name,
            "target": task_code,
        })

    def _parse_task_dependencies(
        self,
        relations: List[Dict],
        workflow_code: str,
        graph: Graph,
    ) -> None:
        """
        解析任务依赖关系

        Args:
            relations: 任务关系列表
            workflow_code: 工作流编码
            graph: 图谱对象
        """
        for relation in relations:
            pre_task_code = relation.get("preTaskCode")
            post_task_code = relation.get("postTaskCode")

            # preTaskCode 为 0 表示起始任务，无前置依赖
            if pre_task_code and post_task_code and pre_task_code != 0:
                graph.edges.task_depends_task.append({
                    "source": str(pre_task_code),
                    "target": str(post_task_code),
                })

    def _parse_workflow_dependencies(
        self,
        workflow_data: Dict,
        workflow_code: str,
        graph: Graph,
    ) -> None:
        """
        解析工作流依赖关系

        Args:
            workflow_data: 工作流详细信息
            workflow_code: 当前工作流编码
            graph: 图谱对象
        """
        # 从任务参数中的 dependence 字段提取工作流依赖
        # 这通常在 DEPENDENT 类型任务中
        tasks = workflow_data.get("tasks", [])
        if not tasks:
            # 从 graph.nodes.tasks 中查找属于此工作流的 DEPENDENT 任务
            for task in graph.nodes.tasks:
                if task.workflow_code == workflow_code and task.task_type == "DEPENDENT":
                    dep_config = task.params.get("dependence", {})
                    self._extract_workflow_dependency_edges(
                        dep_config,
                        workflow_code,
                        graph
                    )
        else:
            for task in tasks:
                if task.get("taskType") == "DEPENDENT":
                    task_params = task.get("taskParams", {})
                    dep_config = task_params.get("dependence", {})
                    self._extract_workflow_dependency_edges(
                        dep_config,
                        workflow_code,
                        graph
                    )

    def _extract_workflow_dependency_edges(
        self,
        dep_config: Dict,
        workflow_code: str,
        graph: Graph,
    ) -> None:
        """
        从依赖配置中提取工作流依赖边

        Args:
            dep_config: 依赖配置
            workflow_code: 当前工作流编码
            graph: 图谱对象
        """
        # DolphinScheduler DEPENDENT 任务的 dependence 结构:
        # {"projectCode": xxx, "processDefinitionCode": xxx, ...}
        dep_project_code = dep_config.get("projectCode")
        dep_workflow_code = dep_config.get("processDefinitionCode")

        if dep_workflow_code:
            graph.edges.workflow_depends_workflow.append({
                "source": workflow_code,
                "target": str(dep_workflow_code),
            })


__all__ = ["GraphScanner"]