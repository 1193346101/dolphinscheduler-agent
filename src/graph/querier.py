"""
GraphQuerier - 图谱查询器

查询知识图谱和预计算索引,提供快速响应
"""

from typing import Dict, List, Optional

from .storage import GraphStorage
from .models import Graph


class GraphQuerier:
    """
    图谱查询器

    用于查询知识图谱和预计算索引,为 Chat Module 和 Alert Agent 提供快速血缘查询
    """

    def __init__(self, storage: GraphStorage):
        """
        初始化查询器

        Args:
            storage: 图谱存储实例
        """
        self.storage = storage

    def query_workflow_downstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流的下游依赖

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "direct": ["直接下游工作流列表"],
                "all": ["所有下游工作流列表(传递闭包)"],
                "count": 总数,
                "message": str
            }
        """
        # 检查图谱是否存在
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": f"Graph not found for project: {project_code}"
            }

        # 加载下游索引
        index = self.storage.load_index(project_code, "downstream")
        if index is None:
            return {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": "Downstream index not found, please generate index first"
            }

        # 查找工作流下游
        workflow_downstream = index.get("workflow_downstream", {})
        if workflow_code not in workflow_downstream:
            return {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": f"Workflow not found: {workflow_code}"
            }

        data = workflow_downstream[workflow_code]
        return {
            "found": True,
            "direct": data.get("direct", []),
            "all": data.get("all", []),
            "count": data.get("count", 0),
            "message": f"Found {data.get('count', 0)} downstream workflows"
        }

    def query_workflow_upstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流的上游依赖(反向查询)

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "upstream": ["上游工作流列表"],
                "message": str
            }
        """
        # 检查图谱是否存在
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "upstream": [],
                "message": f"Graph not found for project: {project_code}"
            }

        # 加载下游索引
        index = self.storage.load_index(project_code, "downstream")
        if index is None:
            return {
                "found": False,
                "upstream": [],
                "message": "Downstream index not found, please generate index first"
            }

        # 反向查找上游: 遍历所有工作流的下游,找出依赖当前工作流的工作流
        workflow_downstream = index.get("workflow_downstream", {})
        upstream: List[str] = []

        for wf_code, data in workflow_downstream.items():
            if workflow_code in data.get("all", []):
                upstream.append(wf_code)

        if not upstream and workflow_code not in workflow_downstream:
            return {
                "found": False,
                "upstream": [],
                "message": f"Workflow not found: {workflow_code}"
            }

        return {
            "found": True,
            "upstream": upstream,
            "message": f"Found {len(upstream)} upstream workflows"
        }

    def query_table_consumers(self, project_code: str, table_name: str) -> Dict:
        """
        查询表的消费者

        Args:
            project_code: 项目代码
            table_name: 表名(full_name)

        Returns:
            {
                "found": bool,
                "workflows": ["消费此表的工作流列表"],
                "tasks": ["消费此表的任务列表"],
                "classes": ["消费此表的类列表"],
                "message": str
            }
        """
        # 检查图谱是否存在
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": f"Graph not found for project: {project_code}"
            }

        # 加载表消费索引
        index = self.storage.load_index(project_code, "table_consumer")
        if index is None:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "Table consumer index not found, please generate index first"
            }

        # 查找表消费者
        table_consumers = index.get("table_consumers", {})
        if table_name not in table_consumers:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": f"Table not found in consumers: {table_name}"
            }

        data = table_consumers[table_name]
        return {
            "found": True,
            "workflows": data.get("workflows", []),
            "tasks": data.get("tasks", []),
            "classes": data.get("classes", []),
            "message": f"Found {len(data.get('tasks', []))} tasks consuming this table"
        }

    def query_table_producers(self, project_code: str, table_name: str) -> Dict:
        """
        查询表的生产者

        Args:
            project_code: 项目代码
            table_name: 表名(full_name)

        Returns:
            {
                "found": bool,
                "workflows": ["生产此表的工作流列表"],
                "tasks": ["生产此表的任务列表"],
                "classes": ["生产此表的类列表"],
                "message": str
            }
        """
        # 检查图谱是否存在
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": f"Graph not found for project: {project_code}"
            }

        # 加载表消费索引
        index = self.storage.load_index(project_code, "table_consumer")
        if index is None:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "Table consumer index not found, please generate index first"
            }

        # 查找表生产者
        table_producers = index.get("table_producers", {})
        if table_name not in table_producers:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": f"Table not found in producers: {table_name}"
            }

        data = table_producers[table_name]
        return {
            "found": True,
            "workflows": data.get("workflows", []),
            "tasks": data.get("tasks", []),
            "classes": data.get("classes", []),
            "message": f"Found {len(data.get('tasks', []))} tasks producing this table"
        }

    def query_workflow_nodes(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流包含的节点(任务)

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "tasks": ["任务code列表"],
                "task_names": {"task_code": "task_name"},
                "task_types": {"task_code": "task_type"},
                "spark_classes": {"task_code": "spark_main_class"},
                "message": str
            }
        """
        # 检查图谱是否存在
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "tasks": [],
                "task_names": {},
                "task_types": {},
                "spark_classes": {},
                "message": f"Graph not found for project: {project_code}"
            }

        # 加载工作流节点索引
        index = self.storage.load_index(project_code, "workflow_nodes")
        if index is None:
            return {
                "found": False,
                "tasks": [],
                "task_names": {},
                "task_types": {},
                "spark_classes": {},
                "message": "Workflow nodes index not found, please generate index first"
            }

        # 查找工作流任务
        workflow_tasks = index.get("workflow_tasks", {})
        if workflow_code not in workflow_tasks:
            return {
                "found": False,
                "tasks": [],
                "task_names": {},
                "task_types": {},
                "spark_classes": {},
                "message": f"Workflow not found: {workflow_code}"
            }

        data = workflow_tasks[workflow_code]
        return {
            "found": True,
            "tasks": data.get("tasks", []),
            "task_names": data.get("task_names", {}),
            "task_types": data.get("task_types", {}),
            "spark_classes": data.get("spark_classes", {}),
            "message": f"Found {len(data.get('tasks', []))} tasks in workflow"
        }

    def query_workflow_info(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流详细信息

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "code": str,
                "name": str,
                "schedule_type": str,
                "schedule_cron": str,
                "is_sub_workflow": bool,
                "parent_workflow": str or None,
                "message": str
            }
        """
        # 加载主图谱
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return {
                "found": False,
                "message": f"Graph not found for project: {project_code}"
            }

        graph = Graph.from_dict(graph_data)

        # 查找工作流节点
        for workflow in graph.nodes.workflows:
            if workflow.code == workflow_code:
                return {
                    "found": True,
                    "code": workflow.code,
                    "name": workflow.name,
                    "schedule_type": workflow.schedule_type,
                    "schedule_cron": workflow.schedule_cron,
                    "is_sub_workflow": workflow.is_sub_workflow,
                    "parent_workflow": workflow.parent_workflow,
                    "message": f"Found workflow: {workflow.name}"
                }

        return {
            "found": False,
            "message": f"Workflow not found: {workflow_code}"
        }

    def query_task_info(self, project_code: str, task_code: str) -> Dict:
        """
        查询任务详细信息

        Args:
            project_code: 项目代码
            task_code: 任务代码

        Returns:
            {
                "found": bool,
                "code": str,
                "name": str,
                "workflow_code": str,
                "task_type": str,
                "spark_main_class": str or None,
                "params": dict,
                "message": str
            }
        """
        # 加载主图谱
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return {
                "found": False,
                "message": f"Graph not found for project: {project_code}"
            }

        graph = Graph.from_dict(graph_data)

        # 查找任务节点
        for task in graph.nodes.tasks:
            if task.code == task_code:
                return {
                    "found": True,
                    "code": task.code,
                    "name": task.name,
                    "workflow_code": task.workflow_code,
                    "task_type": task.task_type,
                    "spark_main_class": task.spark_main_class,
                    "params": task.params,
                    "message": f"Found task: {task.name}"
                }

        return {
            "found": False,
            "message": f"Task not found: {task_code}"
        }

    def query_cross_project_table_lineage(self, table_name: str, project_codes: List[str] = None) -> Dict:
        """
        查询表跨项目的完整血缘链路

        Args:
            table_name: 表名(full_name)
            project_codes: 项目代码列表(可选，不提供则搜索所有已扫描图谱)

        Returns:
            {
                "found": bool,
                "producers": [{"project_code": str, "workflow": str, "task": str}],
                "consumers": [{"project_code": str, "workflow": str, "task": str}],
                "cross_project_references": [{"class": str, "source_project": str, "target_project": str}],
                "message": str
            }
        """
        result = {
            "found": False,
            "producers": [],
            "consumers": [],
            "cross_project_references": [],
            "message": ""
        }

        # 获取所有项目代码
        if project_codes is None:
            project_codes = self._list_all_projects()

        if not project_codes:
            result["message"] = "No scanned graphs found"
            return result

        # 遍历每个项目查询
        for project_code in project_codes:
            # 查询生产者
            producer_result = self.query_table_producers(project_code, table_name)
            if producer_result["found"]:
                for workflow in producer_result["workflows"]:
                    result["producers"].append({
                        "project_code": project_code,
                        "workflow": workflow,
                    })
                for task in producer_result["tasks"]:
                    result["producers"].append({
                        "project_code": project_code,
                        "workflow": "",  # 需要从图谱查找
                        "task": task,
                    })

            # 查询消费者
            consumer_result = self.query_table_consumers(project_code, table_name)
            if consumer_result["found"]:
                for workflow in consumer_result["workflows"]:
                    result["consumers"].append({
                        "project_code": project_code,
                        "workflow": workflow,
                    })
                for task in consumer_result["tasks"]:
                    result["consumers"].append({
                        "project_code": project_code,
                        "workflow": "",
                        "task": task,
                    })

            # 查询跨项目类引用
            graph_data = self.storage.load_graph(project_code)
            if graph_data:
                graph = Graph.from_dict(graph_data)
                for cls in graph.nodes.classes:
                    if cls.cross_project and table_name in (cls.tables_input or []):
                        result["cross_project_references"].append({
                            "class": cls.name,
                            "source_project": cls.source_project or "unknown",
                            "target_project": project_code,
                        })

        # 设置结果
        if result["producers"] or result["consumers"]:
            result["found"] = True
            result["message"] = f"Found lineage for table {table_name} across {len(project_codes)} projects"

        return result

    def query_cross_project_workflow_downstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流跨项目的下游依赖

        通过识别跨项目类引用，追溯下游工作流

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "local_downstream": ["本项目下游工作流"],
                "cross_project_downstream": [{"project_code": str, "workflow": str, "via_class": str}],
                "message": str
            }
        """
        result = {
            "found": False,
            "local_downstream": [],
            "cross_project_downstream": [],
            "message": ""
        }

        # 查询本项目下游
        local_result = self.query_workflow_downstream(project_code, workflow_code)
        if local_result["found"]:
            result["local_downstream"] = local_result["all"]

        # 加载主图谱查找跨项目引用
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            result["message"] = f"Graph not found for project: {project_code}"
            return result

        graph = Graph.from_dict(graph_data)

        # 查找工作流产出的表
        workflow_outputs = []
        for task in graph.nodes.tasks:
            if task.workflow_code == workflow_code:
                # 查找任务产出的表
                for edge in graph.edges.task_produces_table:
                    if edge.get("source") == task.code or edge.get("task") == task.code:
                        table_name = edge.get("target") or edge.get("table")
                        workflow_outputs.append(table_name)

        # 在其他项目中查找消费这些表的工作流
        other_projects = self._list_all_projects()
        other_projects = [p for p in other_projects if p != project_code]

        for other_project in other_projects:
            for table_name in workflow_outputs:
                consumer_result = self.query_table_consumers(other_project, table_name)
                if consumer_result["found"]:
                    for workflow in consumer_result["workflows"]:
                        result["cross_project_downstream"].append({
                            "project_code": other_project,
                            "workflow": workflow,
                            "via_table": table_name,
                        })

        # 设置结果
        if result["local_downstream"] or result["cross_project_downstream"]:
            result["found"] = True
            result["message"] = f"Found downstream for workflow {workflow_code}"

        return result

    def _list_all_projects(self) -> List[str]:
        """
        列出所有已扫描的项目

        Returns:
            项目代码列表
        """
        import os

        graph_dir = self.storage.data_dir
        if not os.path.exists(graph_dir):
            return []

        project_codes = []
        for filename in os.listdir(graph_dir):
            if filename.endswith("_graph.json"):
                project_code = filename.replace("_graph.json", "")
                project_codes.append(project_code)

        return project_codes

    def query_workflow_info_with_subworkflow(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流信息，包含子工作流相关信息

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "found": bool,
                "code": str,
                "name": str,
                "is_sub_workflow": bool,
                "parent_workflow": str or None,
                "sub_workflows": ["子工作流列表"],
                "message": str
            }
        """
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return {
                "found": False,
                "message": f"Graph not found for project: {project_code}"
            }

        graph = Graph.from_dict(graph_data)

        # 查找工作流节点
        workflow_info = None
        for workflow in graph.nodes.workflows:
            if workflow.code == workflow_code:
                workflow_info = workflow
                break

        if workflow_info is None:
            return {
                "found": False,
                "message": f"Workflow not found: {workflow_code}"
            }

        # 查找子工作流
        sub_workflows = []
        for edge in graph.edges.workflow_calls_subworkflow:
            source = edge.get("source") or edge.get("parent")
            if source == workflow_code:
                child = edge.get("target") or edge.get("child")
                if child:
                    sub_workflows.append(child)

        return {
            "found": True,
            "code": workflow_info.code,
            "name": workflow_info.name,
            "is_sub_workflow": workflow_info.is_sub_workflow,
            "parent_workflow": workflow_info.parent_workflow,
            "sub_workflows": sub_workflows,
            "message": f"Found workflow: {workflow_info.name}"
        }

    def query_parent_workflow_downstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询父工作流的下游（用于子工作流失败时的影响分析）

        如果当前工作流是子工作流，返回父工作流中该子工作流之后的下游任务

        Args:
            project_code: 项目代码
            workflow_code: 子工作流代码

        Returns:
            {
                "found": bool,
                "parent_workflow_code": str,
                "parent_workflow_name": str,
                "downstream_in_parent": ["父工作流中的下游任务"],
                "parent_downstream_workflows": ["父工作流的下游工作流"],
                "message": str
            }
        """
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return {
                "found": False,
                "parent_workflow_code": None,
                "parent_workflow_name": "",
                "downstream_in_parent": [],
                "parent_downstream_workflows": [],
                "message": f"Graph not found for project: {project_code}"
            }

        graph = Graph.from_dict(graph_data)

        # 查找工作流信息
        workflow_info = None
        for workflow in graph.nodes.workflows:
            if workflow.code == workflow_code:
                workflow_info = workflow
                break

        if workflow_info is None:
            return {
                "found": False,
                "parent_workflow_code": None,
                "parent_workflow_name": "",
                "downstream_in_parent": [],
                "parent_downstream_workflows": [],
                "message": f"Workflow not found: {workflow_code}"
            }

        # 如果不是子工作流，返回空
        if not workflow_info.is_sub_workflow and not workflow_info.parent_workflow:
            return {
                "found": True,
                "parent_workflow_code": None,
                "parent_workflow_name": "",
                "downstream_in_parent": [],
                "parent_downstream_workflows": [],
                "message": "Not a sub-workflow"
            }

        parent_workflow_code = workflow_info.parent_workflow

        # 查找父工作流信息
        parent_workflow_info = None
        for workflow in graph.nodes.workflows:
            if workflow.code == parent_workflow_code:
                parent_workflow_info = workflow
                break

        if parent_workflow_info is None:
            return {
                "found": True,
                "parent_workflow_code": parent_workflow_code,
                "parent_workflow_name": "",
                "downstream_in_parent": [],
                "parent_downstream_workflows": [],
                "message": f"Parent workflow not found: {parent_workflow_code}"
            }

        # 查找父工作流中子工作流之后的下游任务
        # 子工作流在父工作流中作为一个任务节点存在
        downstream_in_parent = []
        for edge in graph.edges.task_depends_task:
            source = edge.get("source") or edge.get("from")
            # 子工作流的 task_code 通常与 workflow_code 相同或有关联
            if source == workflow_code or source == parent_workflow_code:
                target = edge.get("target") or edge.get("to")
                downstream_in_parent.append(target)

        # 查找父工作流的下游工作流
        parent_downstream_workflows = []
        downstream_index = self.storage.load_index(project_code, "downstream")
        if downstream_index:
            workflow_downstream = downstream_index.get("workflow_downstream", {})
            parent_downstream = workflow_downstream.get(parent_workflow_code, {})
            parent_downstream_workflows = parent_downstream.get("all", [])

        return {
            "found": True,
            "parent_workflow_code": parent_workflow_code,
            "parent_workflow_name": parent_workflow_info.name,
            "downstream_in_parent": downstream_in_parent,
            "parent_downstream_workflows": parent_downstream_workflows,
            "message": f"Found parent workflow: {parent_workflow_info.name}"
        }

    def query_subworkflow_impact(
        self,
        project_code: str,
        sub_workflow_code: str,
        failed_task_code: str
    ) -> Dict:
        """
        查询子工作流失败的完整影响范围

        分析三个维度的影响：
        1. 子工作流内失败任务的下游任务
        2. 父工作流中子工作流之后的下游任务
        3. 父工作流的下游工作流

        Args:
            project_code: 项目代码
            sub_workflow_code: 子工作流代码
            failed_task_code: 失败任务代码

        Returns:
            {
                "found": bool,
                "sub_workflow": {...},
                "task_downstream_in_subworkflow": ["子工作流内的下游任务"],
                "parent_workflow": {...},
                "downstream_in_parent": ["父工作流中的下游"],
                "parent_downstream_workflows": ["父工作流的下游工作流"],
                "total_impact_count": int,
                "impact_summary": str,
                "message": str
            }
        """
        result = {
            "found": False,
            "sub_workflow": {},
            "task_downstream_in_subworkflow": [],
            "parent_workflow": {},
            "downstream_in_parent": [],
            "parent_downstream_workflows": [],
            "total_impact_count": 0,
            "impact_summary": "",
            "message": ""
        }

        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            result["message"] = f"Graph not found for project: {project_code}"
            return result

        graph = Graph.from_dict(graph_data)

        # 1. 查询子工作流信息
        sub_workflow_info = self.query_workflow_info_with_subworkflow(project_code, sub_workflow_code)
        if sub_workflow_info["found"]:
            result["sub_workflow"] = {
                "code": sub_workflow_info["code"],
                "name": sub_workflow_info["name"],
                "is_sub_workflow": sub_workflow_info["is_sub_workflow"],
                "parent_workflow": sub_workflow_info["parent_workflow"],
            }

        # 2. 查询子工作流内失败任务的下游
        task_downstream = self._find_task_downstream_in_workflow(
            graph, sub_workflow_code, failed_task_code
        )
        result["task_downstream_in_subworkflow"] = task_downstream

        # 3. 查询父工作流的影响
        parent_result = self.query_parent_workflow_downstream(project_code, sub_workflow_code)
        if parent_result["found"] and parent_result["parent_workflow_code"]:
            result["parent_workflow"] = {
                "code": parent_result["parent_workflow_code"],
                "name": parent_result["parent_workflow_name"],
            }
            result["downstream_in_parent"] = parent_result["downstream_in_parent"]
            result["parent_downstream_workflows"] = parent_result["parent_downstream_workflows"]

        # 4. 计算总影响
        total = (
            len(task_downstream) +
            len(result["downstream_in_parent"]) +
            len(result["parent_downstream_workflows"])
        )
        result["total_impact_count"] = total

        # 5. 构建影响摘要
        summary_parts = []
        if task_downstream:
            summary_parts.append(f"子工作流内 {len(task_downstream)} 个下游任务受影响")
        if result["downstream_in_parent"]:
            summary_parts.append(f"父工作流内 {len(result['downstream_in_parent'])} 个下游任务受影响")
        if result["parent_downstream_workflows"]:
            summary_parts.append(f"{len(result['parent_downstream_workflows'])} 个下游工作流可能受影响")

        result["impact_summary"] = "; ".join(summary_parts) if summary_parts else "无下游影响"
        result["found"] = True
        result["message"] = f"Total impact: {total}"

        return result

    def _find_task_downstream_in_workflow(
        self,
        graph: Graph,
        workflow_code: str,
        task_code: str
    ) -> List[str]:
        """
        查找工作流内任务的下游任务

        Args:
            graph: 图谱对象
            workflow_code: 工作流代码
            task_code: 任务代码

        Returns:
            下游任务代码列表
        """
        # 获取工作流内的任务
        workflow_tasks = set()
        for edge in graph.edges.workflow_contains_task:
            source = edge.get("source") or edge.get("workflow")
            if source == workflow_code:
                target = edge.get("target") or edge.get("task")
                if target:
                    workflow_tasks.add(target)

        # 使用 NetworkX 查找下游
        import networkx as nx
        G = nx.DiGraph()

        for edge in graph.edges.task_depends_task:
            source = edge.get("source") or edge.get("from")
            target = edge.get("target") or edge.get("to")
            if source in workflow_tasks and target in workflow_tasks:
                G.add_edge(source, target)

        downstream = []
        if task_code in G:
            downstream = list(nx.descendants(G, task_code))

        return downstream


__all__ = ["GraphQuerier"]