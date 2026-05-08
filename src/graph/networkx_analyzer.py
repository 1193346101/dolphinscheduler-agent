"""
NetworkXAnalyzer - NetworkX 路径分析器

使用 NetworkX 库进行图算法分析
"""

from typing import Dict, List, Optional
import networkx as nx

from src.graph.storage import GraphStorage
from src.graph.models import Graph


class NetworkXAnalyzer:
    """
    NetworkX 图分析器

    使用 NetworkX 库对工作流和任务依赖关系进行路径分析
    """

    def __init__(self, storage: GraphStorage = None):
        """
        初始化分析器

        Args:
            storage: 图谱存储实例，可选
        """
        self.storage = storage
        self._workflow_graph_cache: Dict[str, nx.DiGraph] = {}
        self._task_graph_cache: Dict[str, nx.DiGraph] = {}

    def build_workflow_graph(self, project_code: str) -> nx.DiGraph:
        """
        构建工作流依赖图

        从存储加载图谱数据，构建 NetworkX DiGraph

        Args:
            project_code: 项目代码

        Returns:
            NetworkX DiGraph 工作流依赖图
        """
        if project_code in self._workflow_graph_cache:
            return self._workflow_graph_cache[project_code]

        graph = nx.DiGraph()

        if self.storage is None:
            return graph

        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return graph

        # 解析 Graph 对象
        if isinstance(graph_data, dict):
            graph_obj = Graph.from_dict(graph_data)
        else:
            graph_obj = graph_data

        # 添加节点
        for workflow in graph_obj.nodes.workflows:
            graph.add_node(workflow.code, name=workflow.name)

        # 添加边 - 从 workflow_depends_workflow
        for edge in graph_obj.edges.workflow_depends_workflow:
            source, target = self._parse_edge(edge)
            if source and target:
                graph.add_edge(source, target)

        self._workflow_graph_cache[project_code] = graph
        return graph

    def build_task_graph(self, project_code: str, workflow_code: str) -> nx.DiGraph:
        """
        构建任务依赖图

        从存储加载图谱数据，构建指定工作流的任务依赖图

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            NetworkX DiGraph 任务依赖图
        """
        cache_key = f"{project_code}:{workflow_code}"
        if cache_key in self._task_graph_cache:
            return self._task_graph_cache[cache_key]

        graph = nx.DiGraph()

        if self.storage is None:
            return graph

        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return graph

        # 解析 Graph 对象
        if isinstance(graph_data, dict):
            graph_obj = Graph.from_dict(graph_data)
        else:
            graph_obj = graph_data

        # 获取该工作流下的任务节点
        workflow_tasks = [
            task for task in graph_obj.nodes.tasks
            if task.workflow_code == workflow_code
        ]

        # 添加任务节点
        for task in workflow_tasks:
            graph.add_node(task.code, name=task.name, task_type=task.task_type)

        # 添加边 - 从 task_depends_task
        for edge in graph_obj.edges.task_depends_task:
            source, target = self._parse_edge(edge)
            if source and target:
                # 只添加属于该工作流的任务边
                if source in graph.nodes and target in graph.nodes:
                    graph.add_edge(source, target)

        self._task_graph_cache[cache_key] = graph
        return graph

    def find_shortest_path(
        self, project_code: str, source: str, target: str
    ) -> List[str]:
        """
        查找两个工作流之间的最短路径

        Args:
            project_code: 项目代码
            source: 起始节点
            target: 目标节点

        Returns:
            节点路径列表，如果不存在路径则返回空列表
        """
        graph = self.build_workflow_graph(project_code)

        try:
            path = nx.shortest_path(graph, source=source, target=target)
            return list(path)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_all_paths(
        self, project_code: str, source: str, target: str
    ) -> List[List[str]]:
        """
        查找两个工作流之间的所有简单路径

        Args:
            project_code: 项目代码
            source: 起始节点
            target: 目标节点

        Returns:
            所有路径列表，每条路径是节点列表
        """
        graph = self.build_workflow_graph(project_code)

        try:
            paths = nx.all_simple_paths(graph, source=source, target=target)
            return [list(path) for path in paths]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_cycles(self, project_code: str) -> List[List[str]]:
        """
        查找工作流依赖图中的所有环

        Args:
            project_code: 项目代码

        Returns:
            环列表，每个环是节点列表
        """
        graph = self.build_workflow_graph(project_code)

        try:
            cycles = list(nx.simple_cycles(graph))
            return cycles
        except Exception:
            return []

    def calculate_degree(self, project_code: str, node: str) -> Dict:
        """
        计算节点的入度和出度

        Args:
            project_code: 项目代码
            node: 节点代码

        Returns:
            包含入度和出度的字典 {"in_degree": N, "out_degree": N}
        """
        graph = self.build_workflow_graph(project_code)

        if node not in graph.nodes:
            return {"in_degree": 0, "out_degree": 0}

        in_degree = graph.in_degree(node)
        out_degree = graph.out_degree(node)

        return {
            "in_degree": in_degree if in_degree is not None else 0,
            "out_degree": out_degree if out_degree is not None else 0
        }

    def _parse_edge(self, edge: Dict) -> tuple:
        """
        解析边数据，支持两种键格式

        Args:
            edge: 边数据字典

        Returns:
            (source, target) 元组
        """
        # 支持 {"source": "...", "target": "..."} 格式
        if "source" in edge and "target" in edge:
            return (edge["source"], edge["target"])

        # 支持 {"from": "...", "to": "..."} 格式
        if "from" in edge and "to" in edge:
            return (edge["from"], edge["to"])

        return (None, None)

    def clear_cache(self):
        """清除缓存的图数据"""
        self._workflow_graph_cache.clear()
        self._task_graph_cache.clear()


__all__ = ["NetworkXAnalyzer"]