"""
图谱数据模型

使用 dataclasses 定义节点和边的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class WorkflowNode:
    """工作流节点"""
    code: str
    name: str
    schedule_type: str  # CRON, MANUAL, etc.
    schedule_cron: str
    is_sub_workflow: bool
    parent_workflow: Optional[str]  # 父工作流 code
    schedule_start_time: str = ""  # 调度开始时间
    schedule_end_time: str = ""  # 调度结束时间
    schedule_timezone: str = ""  # 时区


@dataclass
class TaskNode:
    """任务节点"""
    code: str
    name: str
    workflow_code: str
    task_type: str  # SPARK, SHELL, PYTHON, DATAX, etc.
    spark_main_class: Optional[str]
    params: Dict[str, Any]


@dataclass
class TableNode:
    """表节点"""
    full_name: str  # e.g., hive.db.table
    table_type: str  # HIVE, MYSQL, etc.


@dataclass
class ClassNode:
    """类节点 (Java/Scala class)"""
    name: str  # fully qualified class name
    file_path: str
    cross_project: bool
    source_project: Optional[str]
    tables_input: List[str]  # 输入表 full_name 列表
    tables_output: List[str]  # 输出表 full_name 列表


@dataclass
class GraphNodes:
    """图谱节点集合"""
    workflows: List[WorkflowNode] = field(default_factory=list)
    tasks: List[TaskNode] = field(default_factory=list)
    tables: List[TableNode] = field(default_factory=list)
    classes: List[ClassNode] = field(default_factory=list)


@dataclass
class GraphEdges:
    """图谱边集合"""
    workflow_depends_workflow: List[Dict[str, Any]] = field(default_factory=list)
    workflow_calls_subworkflow: List[Dict[str, Any]] = field(default_factory=list)
    workflow_contains_task: List[Dict[str, Any]] = field(default_factory=list)
    task_depends_task: List[Dict[str, Any]] = field(default_factory=list)
    task_produces_table: List[Dict[str, Any]] = field(default_factory=list)
    task_consumes_table: List[Dict[str, Any]] = field(default_factory=list)
    class_maps_to_task: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Graph:
    """知识图谱"""
    project_code: str
    project_name: str
    scanned_at: str
    version: int
    nodes: GraphNodes = field(default_factory=GraphNodes)
    edges: GraphEdges = field(default_factory=GraphEdges)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "project_code": self.project_code,
            "project_name": self.project_name,
            "scanned_at": self.scanned_at,
            "version": self.version,
            "nodes": {
                "workflows": [asdict(w) for w in self.nodes.workflows],
                "tasks": [asdict(t) for t in self.nodes.tasks],
                "tables": [asdict(t) for t in self.nodes.tables],
                "classes": [asdict(c) for c in self.nodes.classes],
            },
            "edges": {
                "workflow_depends_workflow": self.edges.workflow_depends_workflow,
                "workflow_calls_subworkflow": self.edges.workflow_calls_subworkflow,
                "workflow_contains_task": self.edges.workflow_contains_task,
                "task_depends_task": self.edges.task_depends_task,
                "task_produces_table": self.edges.task_produces_table,
                "task_consumes_table": self.edges.task_consumes_table,
                "class_maps_to_task": self.edges.class_maps_to_task,
            }
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Graph":
        """从字典创建图谱"""
        nodes_data = data.get("nodes", {})
        edges_data = data.get("edges", {})

        # 解析节点
        workflows = [
            WorkflowNode(**w) for w in nodes_data.get("workflows", [])
        ]
        tasks = [
            TaskNode(**t) for t in nodes_data.get("tasks", [])
        ]
        tables = [
            TableNode(**t) for t in nodes_data.get("tables", [])
        ]
        classes = [
            ClassNode(**c) for c in nodes_data.get("classes", [])
        ]

        # 解析边
        edges = GraphEdges(
            workflow_depends_workflow=edges_data.get("workflow_depends_workflow", []),
            workflow_calls_subworkflow=edges_data.get("workflow_calls_subworkflow", []),
            workflow_contains_task=edges_data.get("workflow_contains_task", []),
            task_depends_task=edges_data.get("task_depends_task", []),
            task_produces_table=edges_data.get("task_produces_table", []),
            task_consumes_table=edges_data.get("task_consumes_table", []),
            class_maps_to_task=edges_data.get("class_maps_to_task", []),
        )

        return Graph(
            project_code=data["project_code"],
            project_name=data["project_name"],
            scanned_at=data["scanned_at"],
            version=data["version"],
            nodes=GraphNodes(
                workflows=workflows,
                tasks=tasks,
                tables=tables,
                classes=classes,
            ),
            edges=edges,
        )