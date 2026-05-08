"""
GraphImpactTool - 图谱影响分析工具

基于知识图谱进行影响分析，为告警处理提供下游依赖信息
"""

from typing import Dict, List, Optional, Tuple

from ..graph import GraphQuerier, GraphStorage
from ..config import settings


class GraphImpactTool:
    """图谱影响分析工具

    封装 GraphQuerier，提供影响分析功能，支持降级到 DS API
    """

    def __init__(self, storage: Optional[GraphStorage] = None):
        """
        初始化

        Args:
            storage: 可选的图谱存储实例，如果不提供则使用默认配置
        """
        if storage is None:
            graph_path = getattr(settings, 'GRAPH_STORAGE_PATH', 'data/graph')
            storage = GraphStorage(data_dir=graph_path)
        self.storage = storage
        self.querier = GraphQuerier(storage)

    def analyze_workflow_downstream(
        self,
        project_code: str,
        workflow_code: str,
    ) -> Dict:
        """
        分析工作流的下游依赖

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "graph_available": bool,
                "downstream_count": int,
                "downstream_workflows": List[str],
                "workflow_names": Dict[str, str],  # workflow_code -> name
                "impact_level": str  # low/medium/high
            }
        """
        result = self.querier.query_workflow_downstream(project_code, workflow_code)

        if not result.get("found"):
            return {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_workflows": [],
                "workflow_names": {},
                "impact_level": "low",
            }

        downstream_workflows = result.get("all", [])
        downstream_count = result.get("count", len(downstream_workflows))

        # 获取工作流名称
        workflow_names = self._get_workflow_names(project_code, downstream_workflows)

        # 计算影响级别
        impact_level = self._calculate_impact_level(downstream_count)

        return {
            "graph_available": True,
            "downstream_count": downstream_count,
            "downstream_workflows": downstream_workflows,
            "workflow_names": workflow_names,
            "impact_level": impact_level,
        }

    def analyze_task_downstream(
        self,
        project_code: str,
        workflow_code: str,
        task_code: str,
    ) -> Dict:
        """
        分析任务的下游依赖

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            task_code: 任务代码

        Returns:
            {
                "graph_available": bool,
                "downstream_count": int,
                "downstream_tasks": List[str],
                "task_names": Dict[str, str]
            }
        """
        # 先查询工作流节点
        nodes_result = self.querier.query_workflow_nodes(project_code, workflow_code)

        if not nodes_result.get("found"):
            return {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_tasks": [],
                "task_names": {},
            }

        # 检查任务是否在工作流中
        tasks = nodes_result.get("tasks", [])
        if task_code not in tasks:
            return {
                "graph_available": True,
                "downstream_count": 0,
                "downstream_tasks": [],
                "task_names": {},
            }

        # 加载主图谱获取任务依赖边
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return {
                "graph_available": True,
                "downstream_count": 0,
                "downstream_tasks": [],
                "task_names": nodes_result.get("task_names", {}),
            }

        # 构建任务依赖图（只包含当前工作流的任务）
        from ..graph.models import Graph
        graph = Graph.from_dict(graph_data)

        # 筛选当前工作流内的任务依赖
        task_depends = graph.edges.task_depends_task
        workflow_tasks = set(tasks)

        # 构建依赖图
        downstream_tasks = self._find_task_downstream(
            task_code,
            task_depends,
            workflow_tasks
        )

        return {
            "graph_available": True,
            "downstream_count": len(downstream_tasks),
            "downstream_tasks": downstream_tasks,
            "task_names": nodes_result.get("task_names", {}),
        }

    def _find_task_downstream(
        self,
        start_task: str,
        task_depends: List[Dict],
        workflow_tasks: set,
    ) -> List[str]:
        """
        查找任务的下游任务（在工作流范围内）

        Args:
            start_task: 起始任务
            task_depends: 任务依赖边列表
            workflow_tasks: 工作流内的任务集合

        Returns:
            下游任务列表
        """
        # 构建依赖图
        import networkx as nx
        G = nx.DiGraph()

        for edge in task_depends:
            source = edge.get("source", edge.get("from", ""))
            target = edge.get("target", edge.get("to", ""))
            if source and target:
                # 只添加工作流内的依赖
                if source in workflow_tasks and target in workflow_tasks:
                    G.add_edge(source, target)

        # BFS 查找下游
        downstream = []
        if start_task in G:
            for node in nx.descendants(G, start_task):
                downstream.append(node)

        return downstream

    def analyze_workflow_nodes(
        self,
        project_code: str,
        workflow_code: str,
    ) -> Dict:
        """
        分析工作流包含的节点

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            {
                "graph_available": bool,
                "task_count": int,
                "tasks": List[str],
                "task_names": Dict[str, str],
                "task_types": Dict[str, str],
                "spark_classes": Dict[str, str]
            }
        """
        result = self.querier.query_workflow_nodes(project_code, workflow_code)

        if not result.get("found"):
            return {
                "graph_available": False,
                "task_count": 0,
                "tasks": [],
                "task_names": {},
                "task_types": {},
                "spark_classes": {},
            }

        tasks = result.get("tasks", [])
        return {
            "graph_available": True,
            "task_count": len(tasks),
            "tasks": tasks,
            "task_names": result.get("task_names", {}),
            "task_types": result.get("task_types", {}),
            "spark_classes": result.get("spark_classes", {}),
        }

    def build_impact_summary(
        self,
        workflow_code: str,
        downstream_workflows: List[str],
        downstream_tasks: List[str],
        workflow_names: Dict[str, str],
    ) -> str:
        """
        构建影响摘要 Markdown

        Args:
            workflow_code: 工作流代码
            downstream_workflows: 下游工作流列表
            downstream_tasks: 下游任务列表
            workflow_names: 工作流名称映射

        Returns:
            Markdown 格式的影响摘要
        """
        lines = [f"## 工作流 {workflow_code} 影响分析\n"]

        # 下游工作流
        if downstream_workflows:
            lines.append("### 下游工作流\n")
            for wf_code in downstream_workflows[:10]:
                wf_name = workflow_names.get(wf_code, wf_code)
                lines.append(f"- {wf_name} ({wf_code})")

            if len(downstream_workflows) > 10:
                lines.append(f"- ... 以及另外 {len(downstream_workflows) - 10} 个工作流")
            lines.append("")

        # 下游任务
        if downstream_tasks:
            lines.append("### 下游任务\n")
            for task in downstream_tasks[:10]:
                lines.append(f"- {task}")

            if len(downstream_tasks) > 10:
                lines.append(f"- ... 以及另外 {len(downstream_tasks) - 10} 个任务")
            lines.append("")

        if not downstream_workflows and not downstream_tasks:
            lines.append("无下游依赖\n")

        return "\n".join(lines)

    def _get_workflow_names(
        self,
        project_code: str,
        workflow_codes: List[str],
    ) -> Dict[str, str]:
        """
        获取工作流名称映射

        Args:
            project_code: 项目代码
            workflow_codes: 工作流代码列表

        Returns:
            workflow_code -> workflow_name 映射
        """
        names = {}
        for code in workflow_codes:
            info = self.querier.query_workflow_info(project_code, code)
            if info.get("found"):
                names[code] = info.get("name", code)
            else:
                names[code] = code
        return names

    def _calculate_impact_level(self, downstream_count: int) -> str:
        """
        计算影响级别

        Args:
            downstream_count: 下游数量

        Returns:
            low/medium/high
        """
        if downstream_count == 0:
            return "low"
        elif downstream_count <= 5:
            return "medium"
        else:
            return "high"


__all__ = ["GraphImpactTool"]