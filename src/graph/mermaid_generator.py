"""
MermaidGenerator - Mermaid 图生成器

生成 Mermaid 格式的图谱可视化代码
"""

from typing import Dict, List, Optional

from .storage import GraphStorage
from .models import Graph


class MermaidGenerator:
    """
    Mermaid 图生成器

    生成 Mermaid 格式的图谱可视化代码,用于在 Markdown 或支持 Mermaid 的环境中展示
    """

    def __init__(self, storage: GraphStorage = None):
        """
        初始化

        Args:
            storage: 图谱存储实例 (可选)
        """
        self.storage = storage

    def generate_downstream_graph(self, project_code: str, workflow_code: str) -> str:
        """
        生成下游依赖图谱 (graph TD)

        显示工作流及其所有下游工作流

        Args:
            project_code: 项目代码
            workflow_code: 工作流代码

        Returns:
            Mermaid 图谱代码
        """
        if self.storage is None:
            return self._empty_graph("TD", "Storage not initialized")

        # 加载图谱
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return self._empty_graph("TD", f"Graph not found for project: {project_code}")

        graph = Graph.from_dict(graph_data)

        # 加载下游索引
        index = self.storage.load_index(project_code, "downstream")
        if index is None:
            return self._empty_graph("TD", "Downstream index not found")

        # 获取下游工作流
        workflow_downstream = index.get("workflow_downstream", {})
        if workflow_code not in workflow_downstream:
            return self._empty_graph("TD", f"Workflow not found: {workflow_code}")

        # 获取下游列表
        downstream_data = workflow_downstream[workflow_code]
        all_downstream = downstream_data.get("all", [])

        # 构建工作流名称映射
        workflow_names = {w.code: w.name for w in graph.nodes.workflows}

        # 获取工作流依赖边
        workflow_edges = graph.edges.workflow_depends_workflow + graph.edges.workflow_calls_subworkflow

        # 收集相关节点
        related_nodes = {workflow_code}
        for code in all_downstream:
            related_nodes.add(code)

        # 生成边
        lines = ["graph TD"]

        # 添加起始节点
        start_name = workflow_names.get(workflow_code, workflow_code)
        lines.append(f"  {workflow_code}[{start_name}]")

        # 添加下游节点和边
        added_edges = set()
        for edge in workflow_edges:
            source = edge["source"]
            target = edge["target"]
            if source in related_nodes and target in related_nodes:
                edge_key = f"{source}->{target}"
                if edge_key not in added_edges:
                    source_name = workflow_names.get(source, source)
                    target_name = workflow_names.get(target, target)
                    lines.append(f"  {source}[{source_name}] --> {target}[{target_name}]")
                    added_edges.add(edge_key)

        return "\n".join(lines)

    def generate_path_graph(self, path: List[str], names: Dict[str, str] = None) -> str:
        """
        生成路径图谱 (graph LR)

        显示从起点到终点的路径

        Args:
            path: 节点代码列表 (按顺序)
            names: 节点名称映射 {code: name}

        Returns:
            Mermaid 图谱代码
        """
        if not path:
            return self._empty_graph("LR", "Empty path")

        if names is None:
            names = {}

        lines = ["graph LR"]

        # 添加节点和边
        for i, code in enumerate(path):
            name = names.get(code, code)
            # 添加节点
            lines.append(f"  {code}[{name}]")

            # 添加边 (除了最后一个节点)
            if i < len(path) - 1:
                next_code = path[i + 1]
                lines.append(f"  {code} --> {next_code}")

        return "\n".join(lines)

    def generate_full_graph(self, project_code: str) -> str:
        """
        生成完整图谱 (graph TD)

        显示项目中所有工作流及其依赖关系

        Args:
            project_code: 项目代码

        Returns:
            Mermaid 图谱代码
        """
        if self.storage is None:
            return self._empty_graph("TD", "Storage not initialized")

        # 加载图谱
        graph_data = self.storage.load_graph(project_code)
        if graph_data is None:
            return self._empty_graph("TD", f"Graph not found for project: {project_code}")

        graph = Graph.from_dict(graph_data)

        # 构建工作流名称映射
        workflow_names = {w.code: w.name for w in graph.nodes.workflows}

        lines = ["graph TD"]

        # 添加所有工作流节点
        for workflow in graph.nodes.workflows:
            lines.append(f"  {workflow.code}[{workflow.name}]")

        # 添加工作流依赖边
        workflow_edges = graph.edges.workflow_depends_workflow + graph.edges.workflow_calls_subworkflow
        for edge in workflow_edges:
            source = edge["source"]
            target = edge["target"]
            source_name = workflow_names.get(source, source)
            target_name = workflow_names.get(target, target)
            lines.append(f"  {source}[{source_name}] --> {target}[{target_name}]")

        # 如果没有任何节点,返回空图谱消息
        if len(graph.nodes.workflows) == 0:
            return self._empty_graph("TD", "No workflows found")

        return "\n".join(lines)

    def generate_table_lineage_graph(self, project_code: str, table_name: str) -> str:
        """
        生成表血缘图谱 (graph LR)

        显示表的生产者和消费者

        Args:
            project_code: 项目代码
            table_name: 表名 (full_name)

        Returns:
            Mermaid 图谱代码
        """
        if self.storage is None:
            return self._empty_graph("LR", "Storage not initialized")

        # 加载表消费索引
        index = self.storage.load_index(project_code, "table_consumer")
        if index is None:
            return self._empty_graph("LR", "Table consumer index not found")

        # 获取生产者和消费者
        table_producers = index.get("table_producers", {})
        table_consumers = index.get("table_consumers", {})

        producers = table_producers.get(table_name, {})
        consumers = table_consumers.get(table_name, {})

        if not producers and not consumers:
            return self._empty_graph("LR", f"Table not found: {table_name}")

        # 加载图谱获取名称
        graph_data = self.storage.load_graph(project_code)
        workflow_names = {}
        if graph_data:
            graph = Graph.from_dict(graph_data)
            workflow_names = {w.code: w.name for w in graph.nodes.workflows}

        lines = ["graph LR"]

        # 使用简化的表名作为节点 ID
        table_id = "table"
        short_table_name = self._short_table_name(table_name)
        lines.append(f"  {table_id}[[{short_table_name}]]")

        # 添加生产者 (左侧)
        producer_workflows = producers.get("workflows", [])
        producer_tasks = producers.get("tasks", [])

        for wf_code in producer_workflows:
            wf_name = workflow_names.get(wf_code, wf_code)
            lines.append(f"  {wf_code}[{wf_name}]")
            lines.append(f"  {wf_code} --> {table_id}")

        for task_code in producer_tasks:
            lines.append(f"  {task_code}[{task_code}]")
            lines.append(f"  {task_code} --> {table_id}")

        # 添加消费者 (右侧)
        consumer_workflows = consumers.get("workflows", [])
        consumer_tasks = consumers.get("tasks", [])

        for wf_code in consumer_workflows:
            wf_name = workflow_names.get(wf_code, wf_code)
            lines.append(f"  {wf_code}_c[{wf_name}]")
            lines.append(f"  {table_id} --> {wf_code}_c")

        for task_code in consumer_tasks:
            lines.append(f"  {task_code}_c[{task_code}]")
            lines.append(f"  {table_id} --> {task_code}_c")

        return "\n".join(lines)

    def _empty_graph(self, direction: str, message: str) -> str:
        """
        生成空图谱消息

        Args:
            direction: 图谱方向 (TD, LR)
            message: 消息内容

        Returns:
            Mermaid 图谱代码
        """
        return f"graph {direction}\n  empty[{message}]"

    def _short_table_name(self, table_name: str) -> str:
        """
        获取简短的表名显示

        Args:
            table_name: 完整表名

        Returns:
            简短表名
        """
        # 如果包含点号,取最后两部分
        parts = table_name.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return table_name


__all__ = ["MermaidGenerator"]