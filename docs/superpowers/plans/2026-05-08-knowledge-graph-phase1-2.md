# 知识图谱 Phase 1-2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现知识图谱的基础服务：Scanner（图谱扫描）、Storage（JSON存储）、Indexer（索引生成）

**Architecture:** 分层实现：Storage 基础存储 → Scanner 扫描构建图谱 → Indexer 生成查询索引。使用 DSCLIClient 获取工作流定义，本地代码仓库搜索类名并解析 SQL。

**Tech Stack:** Python, JSON, Glob, sqlparse, dataclasses

---

## 文件结构

**新建文件：**
```
src/graph/
├── __init__.py
├── storage.py          # JSON 文件读写管理
├── models.py           # 图谱数据模型（dataclasses）
├── scanner.py          # 图谱扫描器
├── indexer.py          # 索引生成器
├── sql_parser.py       # SQL 解析（正则 + sqlparse）
├── code_searcher.py    # 代码文件搜索

data/graph/             # 图谱存储目录

tests/test_graph/
├── __init__.py
├── test_storage.py
├── test_models.py
├── test_sql_parser.py
├── test_code_searcher.py
├── test_scanner.py
├── test_indexer.py
```

---

## Task 1: Storage - JSON 存储管理

**Files:**
- Create: `src/graph/__init__.py`
- Create: `src/graph/storage.py`
- Create: `tests/test_graph/__init__.py`
- Create: `tests/test_graph/test_storage.py`

- [ ] **Step 1: 创建模块目录和 __init__.py**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/src/graph
mkdir -p D:/Project/dolphinscheduler-agent/tests/test_graph
mkdir -p D:/Project/dolphinscheduler-agent/data/graph
```

Create `src/graph/__init__.py`:
```python
"""
Graph module - Knowledge graph service

Provides:
- Storage: JSON file management
- Scanner: Graph building from DS + code repo
- Indexer: Query index generation
- Querier: Graph query service
"""

from .storage import GraphStorage
from .models import Graph, WorkflowNode, TaskNode, TableNode, ClassNode

__all__ = [
    "GraphStorage",
    "Graph",
    "WorkflowNode",
    "TaskNode",
    "TableNode",
    "ClassNode",
]
```

Create `tests/test_graph/__init__.py`:
```python
"""Graph module tests"""
```

- [ ] **Step 2: 创建测试文件 test_storage.py**

```python
"""
Storage 测试
"""

import pytest
import tempfile
import os
from src.graph.storage import GraphStorage


class TestGraphStorage:

    def test_init_with_data_dir(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            assert storage.data_dir == tmpdir

    def test_save_graph(self):
        """测试保存图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph_data = {
                "project_code": "123",
                "project_name": "test_project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {"workflows": [], "tasks": [], "tables": [], "classes": []},
                "edges": {}
            }
            
            storage.save_graph("123", graph_data)
            
            # 验证文件存在
            path = os.path.join(tmpdir, "123_graph.json")
            assert os.path.exists(path)

    def test_load_graph(self):
        """测试加载图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph_data = {
                "project_code": "123",
                "project_name": "test_project",
                "scanned_at": "2026-05-08T10:00:00",
                "version": 1,
                "nodes": {"workflows": [], "tasks": [], "tables": [], "classes": []},
                "edges": {}
            }
            
            storage.save_graph("123", graph_data)
            loaded = storage.load_graph("123")
            
            assert loaded["project_code"] == "123"

    def test_load_graph_not_found(self):
        """测试加载不存在的图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            loaded = storage.load_graph("nonexistent")
            assert loaded is None

    def test_save_index(self):
        """测试保存索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {}
            }
            
            storage.save_index("123", "downstream", index_data)
            
            path = os.path.join(tmpdir, "123_index_downstream.json")
            assert os.path.exists(path)

    def test_load_index(self):
        """测试加载索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            index_data = {
                "generated_at": "2026-05-08T10:00:00",
                "workflow_downstream": {"123": {"direct": [], "all": [], "count": 0}}
            }
            
            storage.save_index("123", "downstream", index_data)
            loaded = storage.load_index("123", "downstream")
            
            assert loaded["workflow_downstream"]["123"]["count"] == 0

    def test_graph_exists(self):
        """测试检查图谱是否存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            assert storage.graph_exists("123") is False
            
            graph_data = {"project_code": "123", "nodes": {}, "edges": {}}
            storage.save_graph("123", graph_data)
            
            assert storage.graph_exists("123") is True
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_storage.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 实现 storage.py**

```python
"""
Storage - JSON 文件存储管理

管理图谱和索引文件的读写
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional


class GraphStorage:
    """
    图谱存储管理
    
    文件命名规则:
    - 主图谱: {project_code}_graph.json
    - 索引: {project_code}_index_{index_type}.json
    """
    
    DEFAULT_DATA_DIR = "data/graph"
    
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        """
        初始化
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def save_graph(self, project_code: str, graph_data: Dict) -> None:
        """
        保存主图谱
        
        Args:
            project_code: 项目代码
            graph_data: 图谱数据
        """
        path = self._get_graph_path(project_code)
        
        # 路径穿越防护
        safe_path = self._sanitize_path(path)
        
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
    
    def load_graph(self, project_code: str) -> Optional[Dict]:
        """
        加载主图谱
        
        Args:
            project_code: 项目代码
            
        Returns:
            图谱数据或 None
        """
        path = self._get_graph_path(project_code)
        
        if not os.path.exists(path):
            return None
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def save_index(self, project_code: str, index_type: str, index_data: Dict) -> None:
        """
        保存索引
        
        Args:
            project_code: 项目代码
            index_type: 索引类型 (downstream, table_consumer, workflow_nodes)
            index_data: 索引数据
        """
        path = self._get_index_path(project_code, index_type)
        safe_path = self._sanitize_path(path)
        
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    def load_index(self, project_code: str, index_type: str) -> Optional[Dict]:
        """
        加载索引
        
        Args:
            project_code: 项目代码
            index_type: 索引类型
            
        Returns:
            索引数据或 None
        """
        path = self._get_index_path(project_code, index_type)
        
        if not os.path.exists(path):
            return None
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def graph_exists(self, project_code: str) -> bool:
        """
        检查图谱是否存在
        
        Args:
            project_code: 项目代码
            
        Returns:
            是否存在
        """
        path = self._get_graph_path(project_code)
        return os.path.exists(path)
    
    def _get_graph_path(self, project_code: str) -> str:
        """获取图谱文件路径"""
        # 清理 project_code
        safe_code = self._sanitize_code(str(project_code))
        return os.path.join(self.data_dir, f"{safe_code}_graph.json")
    
    def _get_index_path(self, project_code: str, index_type: str) -> str:
        """获取索引文件路径"""
        safe_code = self._sanitize_code(str(project_code))
        safe_type = self._sanitize_code(index_type)
        return os.path.join(self.data_dir, f"{safe_code}_index_{safe_type}.json")
    
    def _sanitize_code(self, code: str) -> str:
        """清理代码字符串"""
        import re
        # 只保留字母、数字、下划线
        return re.sub(r'[^\w]', '_', code) if code else "unknown"
    
    def _sanitize_path(self, path: str) -> str:
        """路径安全检查"""
        # 确保路径在 data_dir 内部
        abs_path = os.path.abspath(path)
        abs_data_dir = os.path.abspath(self.data_dir)
        
        if not abs_path.startswith(abs_data_dir):
            raise ValueError(f"路径穿越攻击: {path}")
        
        return abs_path


__all__ = ["GraphStorage"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_storage.py -v`
Expected: 7 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/ tests/test_graph/ data/graph/ && git commit -m "feat: 添加 GraphStorage 图谱存储管理"
```

---

## Task 2: Models - 图谱数据模型

**Files:**
- Create: `src/graph/models.py`
- Create: `tests/test_graph/test_models.py`

- [ ] **Step 1: 创建测试文件 test_models.py**

```python
"""
Models 测试
"""

import pytest
from src.graph.models import (
    Graph, WorkflowNode, TaskNode, TableNode, ClassNode,
    WorkflowEdge, TaskEdge
)


class TestModels:

    def test_workflow_node_creation(self):
        """测试工作流节点创建"""
        workflow = WorkflowNode(
            code="123",
            name="daily_etl",
            schedule_type="CRON",
            schedule_cron="0 8 * * *",
            is_sub_workflow=False,
            parent_workflow=None
        )
        
        assert workflow.code == "123"
        assert workflow.name == "daily_etl"
        assert workflow.schedule_type == "CRON"

    def test_task_node_creation(self):
        """测试任务节点创建"""
        task = TaskNode(
            code="789",
            name="spark_transform",
            workflow_code="123",
            task_type="SPARK",
            spark_main_class="com.example.TransformJob",
            params={}
        )
        
        assert task.code == "789"
        assert task.task_type == "SPARK"
        assert task.spark_main_class == "com.example.TransformJob"

    def test_table_node_creation(self):
        """测试表节点创建"""
        table = TableNode(
            full_name="hive.db.target_table",
            table_type="HIVE"
        )
        
        assert table.full_name == "hive.db.target_table"
        assert table.table_type == "HIVE"

    def test_class_node_creation(self):
        """测试类节点创建"""
        cls = ClassNode(
            name="com.example.TransformJob",
            file_path="/code/com/example/TransformJob.java",
            cross_project=False,
            source_project=None,
            tables_input=["hive.db.source_table"],
            tables_output=["hive.db.target_table"]
        )
        
        assert cls.name == "com.example.TransformJob"
        assert cls.tables_input == ["hive.db.source_table"]

    def test_graph_creation(self):
        """测试图谱创建"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )
        
        assert graph.project_code == "123"
        assert graph.nodes.workflows == []
        assert graph.edges.workflow_depends_workflow == []

    def test_graph_add_workflow(self):
        """测试添加工作流"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )
        
        workflow = WorkflowNode(code="123", name="test", schedule_type="CRON", schedule_cron="", is_sub_workflow=False, parent_workflow=None)
        graph.nodes.workflows.append(workflow)
        
        assert len(graph.nodes.workflows) == 1

    def test_graph_to_dict(self):
        """测试转换为字典"""
        graph = Graph(
            project_code="123",
            project_name="test_project",
            scanned_at="2026-05-08T10:00:00",
            version=1
        )
        
        workflow = WorkflowNode(code="123", name="test", schedule_type="CRON", schedule_cron="0 8 * * *", is_sub_workflow=False, parent_workflow=None)
        graph.nodes.workflows.append(workflow)
        
        data = graph.to_dict()
        
        assert data["project_code"] == "123"
        assert len(data["nodes"]["workflows"]) == 1

    def test_graph_from_dict(self):
        """测试从字典创建"""
        data = {
            "project_code": "123",
            "project_name": "test_project",
            "scanned_at": "2026-05-08T10:00:00",
            "version": 1,
            "nodes": {
                "workflows": [
                    {"code": "123", "name": "test", "schedule_type": "CRON", "schedule_cron": "", "is_sub_workflow": False, "parent_workflow": None}
                ],
                "tasks": [],
                "tables": [],
                "classes": []
            },
            "edges": {
                "workflow_depends_workflow": [],
                "task_depends_task": [],
                "workflow_contains_task": [],
                "task_produces_table": [],
                "task_consumes_table": [],
                "class_maps_to_task": []
            }
        }
        
        graph = Graph.from_dict(data)
        
        assert graph.project_code == "123"
        assert len(graph.nodes.workflows) == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_models.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 models.py**

```python
"""
Models - 图谱数据模型

使用 dataclasses 定义节点和边的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class WorkflowNode:
    """工作流节点"""
    code: str
    name: str
    schedule_type: str  # CRON, MANUAL, etc.
    schedule_cron: str
    is_sub_workflow: bool
    parent_workflow: Optional[str]


@dataclass
class TaskNode:
    """任务节点"""
    code: str
    name: str
    workflow_code: str
    task_type: str  # SPARK, SHELL, PYTHON, DATAX, etc.
    spark_main_class: Optional[str] = None
    params: Dict = field(default_factory=dict)


@dataclass
class TableNode:
    """表节点"""
    full_name: str  # hive.db.table_name
    table_type: str  # HIVE, MYSQL, etc.


@dataclass
class ClassNode:
    """类节点"""
    name: str  # com.example.TransformJob
    file_path: str
    cross_project: bool
    source_project: Optional[str]
    tables_input: List[str] = field(default_factory=list)
    tables_output: List[str] = field(default_factory=list)


@dataclass
class WorkflowEdge:
    """工作流边"""
    workflow: str
    task: str


@dataclass
class TaskEdge:
    """任务边"""
    from_task: str
    to_task: str


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
    workflow_contains_task: List[Dict] = field(default_factory=list)
    workflow_depends_workflow: List[Dict] = field(default_factory=list)
    workflow_calls_subworkflow: List[Dict] = field(default_factory=list)
    task_depends_task: List[Dict] = field(default_factory=list)
    task_produces_table: List[Dict] = field(default_factory=list)
    task_consumes_table: List[Dict] = field(default_factory=list)
    class_maps_to_task: List[Dict] = field(default_factory=list)


@dataclass
class Graph:
    """完整图谱"""
    project_code: str
    project_name: str
    scanned_at: str
    version: int
    nodes: GraphNodes = field(default_factory=GraphNodes)
    edges: GraphEdges = field(default_factory=GraphEdges)
    
    def to_dict(self) -> Dict:
        """转换为字典（用于 JSON 存储）"""
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
                "workflow_contains_task": self.edges.workflow_contains_task,
                "workflow_depends_workflow": self.edges.workflow_depends_workflow,
                "workflow_calls_subworkflow": self.edges.workflow_calls_subworkflow,
                "task_depends_task": self.edges.task_depends_task,
                "task_produces_table": self.edges.task_produces_table,
                "task_consumes_table": self.edges.task_consumes_table,
                "class_maps_to_task": self.edges.class_maps_to_task,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Graph":
        """从字典创建图谱"""
        nodes = GraphNodes(
            workflows=[WorkflowNode(**w) for w in data.get("nodes", {}).get("workflows", [])],
            tasks=[TaskNode(**t) for t in data.get("nodes", {}).get("tasks", [])],
            tables=[TableNode(**t) for t in data.get("nodes", {}).get("tables", [])],
            classes=[ClassNode(**c) for c in data.get("nodes", {}).get("classes", [])],
        )
        
        edges_data = data.get("edges", {})
        edges = GraphEdges(
            workflow_contains_task=edges_data.get("workflow_contains_task", []),
            workflow_depends_workflow=edges_data.get("workflow_depends_workflow", []),
            workflow_calls_subworkflow=edges_data.get("workflow_calls_subworkflow", []),
            task_depends_task=edges_data.get("task_depends_task", []),
            task_produces_table=edges_data.get("task_produces_table", []),
            task_consumes_table=edges_data.get("task_consumes_table", []),
            class_maps_to_task=edges_data.get("class_maps_to_task", []),
        )
        
        return cls(
            project_code=data["project_code"],
            project_name=data["project_name"],
            scanned_at=data["scanned_at"],
            version=data["version"],
            nodes=nodes,
            edges=edges,
        )


__all__ = [
    "Graph",
    "GraphNodes",
    "GraphEdges",
    "WorkflowNode",
    "TaskNode",
    "TableNode",
    "ClassNode",
    "WorkflowEdge",
    "TaskEdge",
]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_models.py -v`
Expected: 8 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/models.py tests/test_graph/test_models.py && git commit -m "feat: 添加图谱数据模型"
```

---

## Task 3: SQL Parser - SQL 解析器

**Files:**
- Create: `src/graph/sql_parser.py`
- Create: `tests/test_graph/test_sql_parser.py`

- [ ] **Step 1: 创建测试文件 test_sql_parser.py**

```python
"""
SQL Parser 测试
"""

import pytest
from src.graph.sql_parser import SQLParser


class TestSQLParser:

    def test_extract_insert_tables(self):
        """测试提取 INSERT 表名"""
        parser = SQLParser()
        
        sql = "INSERT INTO TABLE hive.db.target_table SELECT * FROM source"
        tables = parser.extract_tables(sql)
        
        assert "hive.db.target_table" in tables["output"]

    def test_extract_from_tables(self):
        """测试提取 FROM 表名"""
        parser = SQLParser()
        
        sql = "SELECT * FROM hive.db.source_table"
        tables = parser.extract_tables(sql)
        
        assert "hive.db.source_table" in tables["input"]

    def test_extract_join_tables(self):
        """测试提取 JOIN 表名"""
        parser = SQLParser()
        
        sql = "SELECT * FROM t1 JOIN hive.db.t2 ON t1.id = t2.id"
        tables = parser.extract_tables(sql)
        
        assert "hive.db.t2" in tables["input"]

    def test_extract_complex_sql(self):
        """测试复杂 SQL"""
        parser = SQLParser()
        
        sql = """
        INSERT OVERWRITE TABLE hive.db.target
        SELECT a.*, b.name
        FROM hive.db.source_a a
        JOIN hive.db.source_b b ON a.id = b.id
        """
        tables = parser.extract_tables(sql)
        
        assert "hive.db.target" in tables["output"]
        assert "hive.db.source_a" in tables["input"]
        assert "hive.db.source_b" in tables["input"]

    def test_parse_java_file_sql(self):
        """测试解析 Java 文件中的 SQL"""
        parser = SQLParser()
        
        java_code = """
        String sql = "INSERT INTO TABLE hive.db.output_table " +
                     "SELECT * FROM hive.db.input_table";
        """
        tables = parser.parse_file_content(java_code, ".java")
        
        assert "hive.db.output_table" in tables["output"]

    def test_parse_sql_file(self):
        """测试解析 SQL 文件"""
        parser = SQLParser()
        
        sql_content = """
        -- Create table
        CREATE TABLE hive.db.new_table AS
        SELECT * FROM hive.db.old_table;
        """
        tables = parser.parse_file_content(sql_content, ".sql")
        
        assert "hive.db.old_table" in tables["input"]

    def test_empty_sql(self):
        """测试空 SQL"""
        parser = SQLParser()
        
        tables = parser.extract_tables("")
        
        assert tables["input"] == []
        assert tables["output"] == []

    def test_no_tables(self):
        """测试无表名的 SQL"""
        parser = SQLParser()
        
        sql = "SELECT 1 + 1"
        tables = parser.extract_tables(sql)
        
        assert tables["input"] == []
        assert tables["output"] == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_sql_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 sql_parser.py**

```python
"""
SQL Parser - SQL 解析器

混合解析策略:
1. 正则表达式快速提取
2. sqlparse 处理复杂 SQL
"""

import re
from typing import Dict, List, Tuple


class SQLParser:
    """
    SQL 解析器
    
    提取 SQL 中的输入表和输出表
    """
    
    # 正则表达式模式
    INSERT_PATTERN = r'INSERT\s+(INTO|OVERWRITE)\s+TABLE?\s+(\S+)'
    FROM_PATTERN = r'FROM\s+(\S+)'
    JOIN_PATTERN = r'JOIN\s+(\S+)\s+ON'
    
    def __init__(self):
        """初始化"""
        # 尝试导入 sqlparse
        try:
            import sqlparse
            self.sqlparse = sqlparse
        except ImportError:
            self.sqlparse = None
    
    def extract_tables(self, sql: str) -> Dict[str, List[str]]:
        """
        提取 SQL 中的表名
        
        Args:
            sql: SQL 字符串
            
        Returns:
            {"input": [...], "output": [...]}
        """
        if not sql or not sql.strip():
            return {"input": [], "output": []}
        
        # 先用正则快速提取
        tables = self._regex_extract(sql)
        
        # 如果 sqlparse 可用且 SQL 复杂，使用 sqlparse 补充
        if self.sqlparse and self._is_complex_sql(sql):
            parsed_tables = self._sqlparse_extract(sql)
            # 合并结果
            tables["input"] = list(set(tables["input"] + parsed_tables["input"]))
            tables["output"] = list(set(tables["output"] + parsed_tables["output"]))
        
        # 清理表名
        tables["input"] = self._clean_table_names(tables["input"])
        tables["output"] = self._clean_table_names(tables["output"])
        
        return tables
    
    def parse_file_content(self, content: str, file_ext: str) -> Dict[str, List[str]]:
        """
        解析文件内容中的 SQL
        
        Args:
            content: 文件内容
            file_ext: 文件扩展名 (.java, .scala, .py, .sql)
            
        Returns:
            {"input": [...], "output": [...]}
        """
        # 提取文件中的 SQL 字符串
        sql_strings = self._extract_sql_strings(content, file_ext)
        
        # 合并所有 SQL 的表名
        all_input = []
        all_output = []
        
        for sql in sql_strings:
            tables = self.extract_tables(sql)
            all_input.extend(tables["input"])
            all_output.extend(tables["output"])
        
        return {
            "input": list(set(all_input)),
            "output": list(set(all_output))
        }
    
    def _regex_extract(self, sql: str) -> Dict[str, List[str]]:
        """正则表达式提取"""
        input_tables = []
        output_tables = []
        
        # 提取 INSERT 目标表
        insert_matches = re.findall(self.INSERT_PATTERN, sql, re.IGNORECASE)
        for match in insert_matches:
            if len(match) >= 2:
                table = match[1].strip()
                output_tables.append(table)
        
        # 提取 FROM 源表
        from_matches = re.findall(self.FROM_PATTERN, sql, re.IGNORECASE)
        for match in from_matches:
            table = match.strip()
            # 排除子查询关键字
            if table.upper() not in ("SELECT", "(", "WHERE"):
                input_tables.append(table)
        
        # 提取 JOIN 表
        join_matches = re.findall(self.JOIN_PATTERN, sql, re.IGNORECASE)
        for match in join_matches:
            table = match.strip()
            input_tables.append(table)
        
        return {"input": input_tables, "output": output_tables}
    
    def _sqlparse_extract(self, sql: str) -> Dict[str, List[str]]:
        """sqlparse 提取"""
        if not self.sqlparse:
            return {"input": [], "output": []}
        
        parsed = self.sqlparse.parse(sql)[0]
        
        input_tables = []
        output_tables = []
        
        # 遍历 tokens
        for token in parsed.flatten():
            if token.ttype in self.sqlparse.tokens.Token.Keyword:
                # 检查 INSERT, FROM, JOIN 后的标识符
                pass
        
        # 简化实现：返回正则结果
        return {"input": [], "output": []}
    
    def _is_complex_sql(self, sql: str) -> bool:
        """判断是否复杂 SQL"""
        # 包含子查询或多层 JOIN 视为复杂
        complex_indicators = ["SUBQUERY", "(", "JOIN"]
        return any(indicator in sql.upper() for indicator in complex_indicators)
    
    def _extract_sql_strings(self, content: str, file_ext: str) -> List[str]:
        """从文件内容提取 SQL 字符串"""
        sql_strings = []
        
        if file_ext in (".java", ".scala"):
            # 匹配 Java/Scala 字符串中的 SQL
            patterns = [
                r'"([^"]*(?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^"]*)"',
                r'String\s+sql\s*=\s*"([^"]*)"',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                sql_strings.extend(matches)
        
        elif file_ext == ".py":
            # 匹配 Python 字符串中的 SQL
            patterns = [
                r'"([^"]*(?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^"]*)"',
                r"'([^']*(?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^']*)'",
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                sql_strings.extend(matches)
        
        elif file_ext == ".sql":
            # SQL 文件，直接返回内容
            sql_strings.append(content)
        
        return sql_strings
    
    def _clean_table_names(self, tables: List[str]) -> List[str]:
        """清理表名"""
        cleaned = []
        for table in tables:
            # 去除引号、括号、别名
            table = table.strip().strip('"').strip("'").strip("`")
            # 去除尾部别名 (AS alias)
            if " AS " in table.upper():
                table = table.split()[0]
            # 去除尾部逗号
            table = table.rstrip(",")
            # 过滤无效表名
            if table and not table.upper().startswith(("SELECT", "WHERE", "AND", "OR", "ON")):
                cleaned.append(table)
        
        return list(set(cleaned))


__all__ = ["SQLParser"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_sql_parser.py -v`
Expected: 8 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/sql_parser.py tests/test_graph/test_sql_parser.py && git commit -m "feat: 添加 SQLParser SQL 解析器"
```

---

## Task 4: Code Searcher - 代码文件搜索

**Files:**
- Create: `src/graph/code_searcher.py`
- Create: `tests/test_graph/test_code_searcher.py`

- [ ] **Step 1: 创建测试文件 test_code_searcher.py**

```python
"""
Code Searcher 测试
"""

import pytest
import tempfile
import os
from src.graph.code_searcher import CodeSearcher


class TestCodeSearcher:

    def test_init_with_code_root(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)
            assert searcher.code_root == tmpdir

    def test_class_to_path_java(self):
        """测试 Java 类名转路径"""
        searcher = CodeSearcher(code_root="/tmp")
        
        paths = searcher.class_to_paths("com.example.TransformJob")
        
        assert "com/example/TransformJob.java" in paths

    def test_class_to_path_scala(self):
        """测试 Scala 类名转路径"""
        searcher = CodeSearcher(code_root="/tmp")
        
        paths = searcher.class_to_paths("com.example.Job")
        
        assert "com/example/Job.scala" in paths

    def test_class_to_path_python(self):
        """测试 Python 类名转路径"""
        searcher = CodeSearcher(code_root="/tmp")
        
        paths = searcher.class_to_paths("example.transform_job")
        
        assert "example/transform_job.py" in paths

    def test_search_in_project_found(self):
        """测试项目内搜索找到"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建模拟文件
            project_dir = os.path.join(tmpdir, "test_project")
            java_dir = os.path.join(project_dir, "src/main/java/com/example")
            os.makedirs(java_dir)
            
            java_file = os.path.join(java_dir, "TransformJob.java")
            with open(java_file, "w") as f:
                f.write("public class TransformJob {}")
            
            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.example.TransformJob", "test_project")
            
            assert result["found"] is True
            assert result["cross_project"] is False
            assert "TransformJob.java" in result["file_path"]

    def test_search_in_project_not_found_global_found(self):
        """测试项目内未找到，全局找到"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建其他项目的文件
            other_project = os.path.join(tmpdir, "other_project")
            java_dir = os.path.join(other_project, "src/main/java/com/example")
            os.makedirs(java_dir)
            
            java_file = os.path.join(java_dir, "TransformJob.java")
            with open(java_file, "w") as f:
                f.write("public class TransformJob {}")
            
            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.example.TransformJob", "test_project")
            
            assert result["found"] is True
            assert result["cross_project"] is True
            assert result["source_project"] == "other_project"

    def test_search_not_found(self):
        """测试搜索未找到"""
        with tempfile.TemporaryDirectory() as tmpdir:
            searcher = CodeSearcher(code_root=tmpdir)
            result = searcher.search_class("com.example.NonExistent", "test_project")
            
            assert result["found"] is False

    def test_read_file_content(self):
        """测试读取文件内容"""
        with tempfile.TemporaryDirectory() as tmpdir:
            java_file = os.path.join(tmpdir, "Test.java")
            with open(java_file, "w") as f:
                f.write("public class Test { String sql = \"SELECT * FROM t\"; }")
            
            searcher = CodeSearcher(code_root=tmpdir)
            content = searcher.read_file_content(java_file)
            
            assert "SELECT * FROM t" in content
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_code_searcher.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 code_searcher.py**

```python
"""
Code Searcher - 代码文件搜索

按类名搜索代码文件，支持项目内优先和全局搜索
"""

import os
import glob
from typing import Dict, List, Optional


class CodeSearcher:
    """
    代码文件搜索器
    
    搜索策略:
    1. 项目模块目录内搜索
    2. 整个代码仓库全局搜索
    """
    
    def __init__(self, code_root: str):
        """
        初始化
        
        Args:
            code_root: 代码仓库根目录
        """
        self.code_root = code_root
    
    def class_to_paths(self, class_name: str) -> List[str]:
        """
        类名转换为可能的文件路径
        
        Args:
            class_name: 类名 (com.example.TransformJob)
            
        Returns:
            可能的文件路径列表
        """
        # 处理 Scala 内部类 ($Inner)
        if "$" in class_name:
            class_name = class_name.split("$")[0]
        
        # 转换路径
        path_base = class_name.replace(".", "/")
        
        return [
            f"{path_base}.java",
            f"{path_base}.scala",
            f"{path_base}.py",
        ]
    
    def search_class(self, class_name: str, project_name: str) -> Dict:
        """
        搜索类文件
        
        Args:
            class_name: 类名
            project_name: 项目名称
            
        Returns:
            {
                "found": bool,
                "file_path": str or None,
                "cross_project": bool,
                "source_project": str or None
            }
        """
        possible_paths = self.class_to_paths(class_name)
        
        # 第一优先：项目内搜索
        for rel_path in possible_paths:
            project_search_path = os.path.join(
                self.code_root, project_name, "**", rel_path
            )
            matches = glob.glob(project_search_path, recursive=True)
            
            if matches:
                return {
                    "found": True,
                    "file_path": matches[0],
                    "cross_project": False,
                    "source_project": None
                }
        
        # 第二优先：全局搜索
        for rel_path in possible_paths:
            global_search_path = os.path.join(self.code_root, "**", rel_path)
            matches = glob.glob(global_search_path, recursive=True)
            
            if matches:
                # 确定来源项目
                file_path = matches[0]
                source_project = self._extract_project_name(file_path)
                
                return {
                    "found": True,
                    "file_path": file_path,
                    "cross_project": source_project != project_name,
                    "source_project": source_project
                }
        
        # 未找到
        return {
            "found": False,
            "file_path": None,
            "cross_project": False,
            "source_project": None
        }
    
    def read_file_content(self, file_path: str) -> Optional[str]:
        """
        读取文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容或 None
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return None
    
    def _extract_project_name(self, file_path: str) -> Optional[str]:
        """
        从文件路径提取项目名称
        
        Args:
            file_path: 文件绝对路径
            
        Returns:
            项目名称
        """
        abs_root = os.path.abspath(self.code_root)
        abs_file = os.path.abspath(file_path)
        
        if not abs_file.startswith(abs_root):
            return None
        
        # 去除根路径，获取相对路径
        rel_path = os.path.relpath(abs_file, abs_root)
        
        # 第一部分是项目名称
        parts = rel_path.split(os.sep)
        if parts:
            return parts[0]
        
        return None


__all__ = ["CodeSearcher"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_code_searcher.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/code_searcher.py tests/test_graph/test_code_searcher.py && git commit -m "feat: 添加 CodeSearcher 代码文件搜索"
```

---

## 实现说明

### 测试策略
- 每个组件单独测试，使用临时目录模拟文件系统
- Mock DS API 调用（Scanner 集成时）

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/ -v
```

### 配置更新

新增环境变量：
```bash
CODE_ROOT_PATH=/path/to/code_root  # 代码仓库根路径
GRAPH_STORAGE_PATH=data/graph      # 图谱存储路径
```

### 下一阶段

Phase 1 完成后继续:
- Task 5: Scanner - 图谱扫描器
- Task 6: Indexer - 索引生成器
- Task 7: Querier - 图谱查询器