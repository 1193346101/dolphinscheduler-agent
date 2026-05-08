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


__all__ = ["GraphQuerier"]