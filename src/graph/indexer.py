"""
GraphIndexer - 索引生成器

从主图谱生成查询索引,加速查询性能
"""

from datetime import datetime
from typing import Dict, List, Set, Any
from collections import deque

from .storage import GraphStorage
from .models import Graph


class GraphIndexer:
    """
    图谱索引生成器

    生成三种索引:
    - downstream: 下游依赖索引
    - table_consumer: 表消费/生产索引
    - workflow_nodes: 工作流节点索引
    """

    INDEX_TYPES = ["downstream", "table_consumer", "workflow_nodes"]

    def __init__(self, storage: GraphStorage):
        """
        初始化索引生成器

        Args:
            storage: 图谱存储实例
        """
        self.storage = storage

    def generate_all_indexes(self, project_code: str) -> Dict[str, Dict]:
        """
        生成所有索引

        Args:
            project_code: 项目代码

        Returns:
            生成的索引数据字典 {index_type: index_data}

        Raises:
            ValueError: 如果图谱不存在
        """
        # 加载图谱
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            raise ValueError(f"Graph not found for project: {project_code}")

        graph = Graph.from_dict(graph_data)

        # 生成三种索引
        indexes = {}

        indexes["downstream"] = self.generate_downstream_index(graph)
        indexes["table_consumer"] = self.generate_table_consumer_index(graph)
        indexes["workflow_nodes"] = self.generate_workflow_nodes_index(graph)

        # 保存所有索引
        for index_type, index_data in indexes.items():
            self.storage.save_index(project_code, index_type, index_data)

        return indexes

    def generate_downstream_index(self, graph: Graph) -> Dict:
        """
        生成下游依赖索引

        索引结构:
        {
            "generated_at": "ISO timestamp",
            "workflow_downstream": {
                "workflow_code": {
                    "direct": ["下游工作流code列表"],
                    "all": ["所有下游工作流code列表(传递闭包)"],
                    "count": 总数
                }
            },
            "task_downstream": {
                "task_code": {
                    "direct": ["下游任务code列表"],
                    "all": ["所有下游任务code列表(传递闭包)"],
                    "count": 总数
                }
            }
        }

        Args:
            graph: 图谱对象

        Returns:
            下游索引数据
        """
        generated_at = datetime.now().isoformat()

        # 工作流下游索引
        workflow_downstream = {}
        workflow_edges = graph.edges.workflow_depends_workflow + graph.edges.workflow_calls_subworkflow

        for workflow in graph.nodes.workflows:
            # 直接下游
            direct = [
                edge["target"] for edge in workflow_edges
                if edge["source"] == workflow.code
            ]
            # 所有下游(传递闭包)
            all_downstream = self._find_all_downstream(workflow.code, workflow_edges)

            workflow_downstream[workflow.code] = {
                "direct": direct,
                "all": all_downstream,
                "count": len(all_downstream)
            }

        # 任务下游索引
        task_downstream = {}
        task_edges = graph.edges.task_depends_task

        for task in graph.nodes.tasks:
            # 直接下游
            direct = [
                edge["target"] for edge in task_edges
                if edge["source"] == task.code
            ]
            # 所有下游(传递闭包)
            all_downstream = self._find_all_downstream(task.code, task_edges)

            task_downstream[task.code] = {
                "direct": direct,
                "all": all_downstream,
                "count": len(all_downstream)
            }

        return {
            "generated_at": generated_at,
            "workflow_downstream": workflow_downstream,
            "task_downstream": task_downstream
        }

    def generate_table_consumer_index(self, graph: Graph) -> Dict:
        """
        生成表消费/生产索引

        索引结构:
        {
            "generated_at": "ISO timestamp",
            "table_consumers": {
                "table_name": {
                    "workflows": ["使用此表的工作流code列表"],
                    "tasks": ["使用此表的任务code列表"],
                    "classes": ["使用此表的类列表"]
                }
            },
            "table_producers": {
                "table_name": {
                    "workflows": ["生产此表的工作流code列表"],
                    "tasks": ["生产此表的任务code列表"],
                    "classes": ["生产此表的类列表"]
                }
            }
        }

        Args:
            graph: 图谱对象

        Returns:
            表消费/生产索引数据
        """
        generated_at = datetime.now().isoformat()

        # 建立 task -> workflow 映射
        task_to_workflow: Dict[str, str] = {}
        for edge in graph.edges.workflow_contains_task:
            task_to_workflow[edge["target"]] = edge["source"]

        # 建立 class -> task 映射
        class_to_task: Dict[str, str] = {}
        for edge in graph.edges.class_maps_to_task:
            class_to_task[edge["source"]] = edge["target"]

        # 表消费索引
        table_consumers: Dict[str, Dict[str, List[str]]] = {}
        for edge in graph.edges.task_consumes_table:
            table_name = edge["target"]
            task_code = edge["source"]

            if table_name not in table_consumers:
                table_consumers[table_name] = {
                    "workflows": [],
                    "tasks": [],
                    "classes": []
                }

            # 添加任务
            if task_code not in table_consumers[table_name]["tasks"]:
                table_consumers[table_name]["tasks"].append(task_code)

            # 添加工作流
            workflow_code = task_to_workflow.get(task_code)
            if workflow_code and workflow_code not in table_consumers[table_name]["workflows"]:
                table_consumers[table_name]["workflows"].append(workflow_code)

            # 添加类(查找映射到此任务的类)
            for class_name, mapped_task in class_to_task.items():
                if mapped_task == task_code and class_name not in table_consumers[table_name]["classes"]:
                    table_consumers[table_name]["classes"].append(class_name)

        # 表生产索引
        table_producers: Dict[str, Dict[str, List[str]]] = {}
        for edge in graph.edges.task_produces_table:
            table_name = edge["target"]
            task_code = edge["source"]

            if table_name not in table_producers:
                table_producers[table_name] = {
                    "workflows": [],
                    "tasks": [],
                    "classes": []
                }

            # 添加任务
            if task_code not in table_producers[table_name]["tasks"]:
                table_producers[table_name]["tasks"].append(task_code)

            # 添加工作流
            workflow_code = task_to_workflow.get(task_code)
            if workflow_code and workflow_code not in table_producers[table_name]["workflows"]:
                table_producers[table_name]["workflows"].append(workflow_code)

            # 添加类(查找映射到此任务的类)
            for class_name, mapped_task in class_to_task.items():
                if mapped_task == task_code and class_name not in table_producers[table_name]["classes"]:
                    table_producers[table_name]["classes"].append(class_name)

        return {
            "generated_at": generated_at,
            "table_consumers": table_consumers,
            "table_producers": table_producers
        }

    def generate_workflow_nodes_index(self, graph: Graph) -> Dict:
        """
        生成工作流节点索引

        索引结构:
        {
            "generated_at": "ISO timestamp",
            "workflow_tasks": {
                "workflow_code": {
                    "tasks": ["任务code列表"],
                    "task_names": {"task_code": "task_name"},
                    "task_types": {"task_code": "task_type"},
                    "spark_classes": {"task_code": "spark_main_class"}
                }
            }
        }

        Args:
            graph: 图谱对象

        Returns:
            工作流节点索引数据
        """
        generated_at = datetime.now().isoformat()

        # 建立工作流到任务的映射
        workflow_tasks: Dict[str, Dict[str, Any]] = {}

        # 初始化所有工作流
        for workflow in graph.nodes.workflows:
            workflow_tasks[workflow.code] = {
                "tasks": [],
                "task_names": {},
                "task_types": {},
                "spark_classes": {}
            }

        # 根据 workflow_contains_task 边填充数据
        for edge in graph.edges.workflow_contains_task:
            workflow_code = edge["source"]
            task_code = edge["target"]

            # 查找任务节点
            task_node = None
            for task in graph.nodes.tasks:
                if task.code == task_code:
                    task_node = task
                    break

            if workflow_code not in workflow_tasks:
                workflow_tasks[workflow_code] = {
                    "tasks": [],
                    "task_names": {},
                    "task_types": {},
                    "spark_classes": {}
                }

            workflow_tasks[workflow_code]["tasks"].append(task_code)

            if task_node:
                workflow_tasks[workflow_code]["task_names"][task_code] = task_node.name
                workflow_tasks[workflow_code]["task_types"][task_code] = task_node.task_type
                if task_node.spark_main_class:
                    workflow_tasks[workflow_code]["spark_classes"][task_code] = task_node.spark_main_class

        return {
            "generated_at": generated_at,
            "workflow_tasks": workflow_tasks
        }

    def _find_all_downstream(self, start_code: str, edges: List[Dict]) -> List[str]:
        """
        使用 BFS 查找所有下游节点(传递闭包)

        Args:
            start_code: 起始节点代码
            edges: 边列表,每条边包含 source 和 target 字段

        Returns:
            所有下游节点代码列表(不包含起始节点)
        """
        # 构建邻接表
        adjacency: Dict[str, List[str]] = {}
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source not in adjacency:
                adjacency[source] = []
            adjacency[source].append(target)

        # BFS 遍历
        visited: Set[str] = set()
        queue = deque()
        result: List[str] = []

        # 将起始节点标记为已访问(但不加入结果),防止环路时重复添加
        visited.add(start_code)

        # 从起始节点的直接邻居开始
        if start_code in adjacency:
            for neighbor in adjacency[start_code]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    result.append(neighbor)

        # BFS
        while queue:
            current = queue.popleft()
            if current in adjacency:
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        result.append(neighbor)

        return result


__all__ = ["GraphIndexer"]