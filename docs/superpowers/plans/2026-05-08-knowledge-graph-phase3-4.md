# 知识图谱 Phase 3-4 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现知识图谱的核心服务：Scanner（图谱扫描构建）、Indexer（索引生成）、Querier（图谱查询）

**Architecture:** Scanner 调用 DSCLIClient 获取工作流定义，CodeSearcher + SQLParser 解析代码，GraphStorage 存储图谱；Indexer 从图谱生成三个查询索引；Querier 提供基础查询和深度查询（NetworkX）。

**Tech Stack:** DSCLIClient, NetworkX, dataclasses, Glob

---

## 文件结构

**新建文件：**
```
src/graph/
├── scanner.py          # 图谱扫描器（Phase 3）
├── indexer.py          # 索引生成器（Phase 3）
├── querier.py          # 图谱查询器（Phase 4）

tests/test_graph/
├── test_scanner.py
├── test_indexer.py
├── test_querier.py
```

---

## Task 5: Scanner - 图谱扫描器

**Files:**
- Create: `src/graph/scanner.py`
- Create: `tests/test_graph/test_scanner.py`

- [ ] **Step 1: 创建测试文件 test_scanner.py**

```python
"""
Scanner 测试
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from src.graph.scanner import GraphScanner
from src.graph.storage import GraphStorage


class TestGraphScanner:

    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            assert scanner.storage.data_dir == tmpdir

    @patch("src.graph.scanner.DSCLIClient")
    def test_scan_project_empty(self, mock_dsctl):
        """测试扫描空项目"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            mock_instance = Mock()
            mock_instance.list_workflows.return_value = Mock(
                success=True, stdout="[]", stderr=""
            )
            mock_dsctl.return_value = mock_instance
            
            result = scanner.scan_project(
                project_code="123",
                project_name="test_project",
                ds_api_url="http://test:12345",
                ds_api_token="test_token"
            )
            
            assert result["workflows_count"] == 0
            assert result["tasks_count"] == 0

    @patch("src.graph.scanner.DSCLIClient")
    def test_scan_project_with_workflow(self, mock_dsctl):
        """测试扫描有工作流的项目"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            # Mock 工作流定义
            workflows_json = '''[
                {
                    "code": "456",
                    "name": "daily_etl",
                    "scheduleType": "CRON",
                    "scheduleCron": "0 8 * * *"
                }
            ]'''
            
            mock_instance = Mock()
            mock_instance.list_workflows.return_value = Mock(
                success=True, stdout=workflows_json, stderr=""
            )
            mock_instance.get_workflow_detail.return_value = Mock(
                success=True, stdout='{"tasks": [], "dependencies": []}', stderr=""
            )
            mock_dsctl.return_value = mock_instance
            
            result = scanner.scan_project(
                project_code="123",
                project_name="test_project",
                ds_api_url="http://test:12345",
                ds_api_token="test_token"
            )
            
            assert result["workflows_count"] == 1
            assert storage.graph_exists("123")

    def test_extract_spark_main_class(self):
        """测试提取 Spark 主类"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            task_params = {
                "mainArgs": "--class com.example.TransformJob --master yarn"
            }
            
            main_class = scanner._extract_spark_main_class(task_params)
            
            assert main_class == "com.example.TransformJob"

    def test_parse_workflow_dependencies(self):
        """测试解析工作流依赖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            workflow_detail = {
                "processDefinitionCode": "123",
                "dependence": {
                    "dependenceDefinitionCodes": ["456", "789"]
                }
            }
            
            deps = scanner._parse_workflow_dependencies(workflow_detail)
            
            assert "456" in deps
            assert "789" in deps

    def test_parse_task_dependencies(self):
        """测试解析任务依赖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            scanner = GraphScanner(storage=storage, code_root=tmpdir)
            
            task_relations = [
                {"preTaskCode": "789", "postTaskCode": "790"}
            ]
            
            deps = scanner._parse_task_dependencies(task_relations)
            
            assert len(deps) == 1
            assert deps[0]["from"] == "789"
            assert deps[0]["to"] == "790"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_scanner.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 scanner.py**

```python
"""
Scanner - 图谱扫描器

扫描 DS 工作流定义 + 本地代码仓库，构建知识图谱
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import asdict

from .storage import GraphStorage
from .models import Graph, GraphNodes, GraphEdges, WorkflowNode, TaskNode, TableNode, ClassNode
from .code_searcher import CodeSearcher
from .sql_parser import SQLParser
from ..integrations.dsctl_wrapper import DSCLIClient


class GraphScanner:
    """
    图谱扫描器
    
    扫描流程:
    1. 获取项目所有工作流定义
    2. 解析工作流信息、节点信息、依赖关系
    3. 提取 SPARK 节点的 --class 参数
    4. 搜索代码文件并解析 SQL
    5. 构建图谱并存储
    """
    
    def __init__(self, storage: GraphStorage, code_root: str):
        """
        初始化
        
        Args:
            storage: 图谱存储
            code_root: 代码仓库根目录
        """
        self.storage = storage
        self.code_root = code_root
        self.code_searcher = CodeSearcher(code_root)
        self.sql_parser = SQLParser()
    
    def scan_project(
        self,
        project_code: str,
        project_name: str,
        ds_api_url: str,
        ds_api_token: str
    ) -> Dict:
        """
        扫描项目
        
        Args:
            project_code: 项目代码
            project_name: 项目名称
            ds_api_url: DS API URL
            ds_api_token: DS API Token
            
        Returns:
            扫描结果统计
        """
        # 创建 DSCLIClient
        dsctl = DSCLIClient(api_url=ds_api_url, api_token=ds_api_token)
        
        # 初始化图谱
        graph = Graph(
            project_code=project_code,
            project_name=project_name,
            scanned_at=datetime.now().isoformat(),
            version=1
        )
        
        # 1. 获取所有工作流
        workflows = self._fetch_workflows(dsctl, project_code)
        
        # 2. 解析每个工作流
        for wf in workflows:
            self._parse_workflow(wf, dsctl, graph, project_name)
        
        # 3. 保存图谱
        self.storage.save_graph(project_code, graph.to_dict())
        
        # 返回统计
        return {
            "workflows_count": len(graph.nodes.workflows),
            "tasks_count": len(graph.nodes.tasks),
            "tables_count": len(graph.nodes.tables),
            "classes_count": len(graph.nodes.classes),
            "scanned_at": graph.scanned_at
        }
    
    def _fetch_workflows(self, dsctl: DSCLIClient, project_code: str) -> List[Dict]:
        """获取项目所有工作流"""
        try:
            result = dsctl.list_workflows(project_code)
            if result.success:
                return json.loads(result.stdout) if result.stdout else []
        except Exception:
            pass
        return []
    
    def _parse_workflow(
        self,
        workflow: Dict,
        dsctl: DSCLIClient,
        graph: Graph,
        project_name: str
    ) -> None:
        """解析单个工作流"""
        wf_code = str(workflow.get("code", ""))
        wf_name = workflow.get("name", "")
        
        # 创建工作流节点
        wf_node = WorkflowNode(
            code=wf_code,
            name=wf_name,
            schedule_type=workflow.get("scheduleType", "MANUAL"),
            schedule_cron=workflow.get("scheduleCron", ""),
            is_sub_workflow=False,
            parent_workflow=None
        )
        graph.nodes.workflows.append(wf_node)
        
        # 获取工作流详情
        wf_detail = self._fetch_workflow_detail(dsctl, wf_code)
        
        if wf_detail:
            # 解析任务
            tasks = wf_detail.get("tasks", [])
            for task in tasks:
                self._parse_task(task, wf_code, graph, project_name)
            
            # 解析任务依赖
            task_relations = wf_detail.get("taskRelations", [])
            for rel in task_relations:
                edge = {
                    "from": str(rel.get("preTaskCode", "")),
                    "to": str(rel.get("postTaskCode", ""))
                }
                graph.edges.task_depends_task.append(edge)
            
            # 解析工作流依赖
            deps = self._parse_workflow_dependencies(wf_detail)
            for dep_code in deps:
                edge = {"from": wf_code, "to": str(dep_code)}
                graph.edges.workflow_depends_workflow.append(edge)
    
    def _fetch_workflow_detail(self, dsctl: DSCLIClient, wf_code: str) -> Optional[Dict]:
        """获取工作流详情"""
        try:
            result = dsctl.get_workflow_detail(wf_code)
            if result.success:
                return json.loads(result.stdout) if result.stdout else {}
        except Exception:
            pass
        return None
    
    def _parse_task(
        self,
        task: Dict,
        wf_code: str,
        graph: Graph,
        project_name: str
    ) -> None:
        """解析单个任务"""
        task_code = str(task.get("code", ""))
        task_name = task.get("name", "")
        task_type = task.get("type", "UNKNOWN")
        task_params = task.get("params", {})
        
        # 提取 Spark 主类
        spark_main_class = None
        if task_type == "SPARK":
            spark_main_class = self._extract_spark_main_class(task_params)
        
        # 创建任务节点
        task_node = TaskNode(
            code=task_code,
            name=task_name,
            workflow_code=wf_code,
            task_type=task_type,
            spark_main_class=spark_main_class,
            params=task_params
        )
        graph.nodes.tasks.append(task_node)
        
        # 添加工作流包含任务边
        graph.edges.workflow_contains_task.append({"workflow": wf_code, "task": task_code})
        
        # 解析类名到表名映射
        if spark_main_class:
            self._parse_class_tables(spark_main_class, task_code, graph, project_name)
    
    def _extract_spark_main_class(self, params: Dict) -> Optional[str]:
        """提取 Spark 主类名"""
        main_args = params.get("mainArgs", "")
        if not main_args:
            return None
        
        # 匹配 --class 参数
        match = re.search(r'--class\s+(\S+)', main_args)
        if match:
            return match.group(1)
        
        return None
    
    def _parse_workflow_dependencies(self, wf_detail: Dict) -> List[str]:
        """解析工作流依赖"""
        deps = []
        
        # dependence 字段
        dependence = wf_detail.get("dependence", {})
        codes = dependence.get("dependenceDefinitionCodes", [])
        
        for code in codes:
            deps.append(str(code))
        
        return deps
    
    def _parse_class_tables(
        self,
        class_name: str,
        task_code: str,
        graph: Graph,
        project_name: str
    ) -> None:
        """解析类名到表名映射"""
        # 搜索代码文件
        search_result = self.code_searcher.search_class(class_name, project_name)
        
        if not search_result["found"]:
            # 记录未找到的类
            cls_node = ClassNode(
                name=class_name,
                file_path="",
                cross_project=False,
                source_project=None,
                tables_input=[],
                tables_output=[]
            )
            graph.nodes.classes.append(cls_node)
            return
        
        # 读取文件内容
        file_path = search_result["file_path"]
        content = self.code_searcher.read_file_content(file_path)
        
        if not content:
            return
        
        # 解析 SQL
        file_ext = os.path.splitext(file_path)[1]
        tables = self.sql_parser.parse_file_content(content, file_ext)
        
        # 创建类节点
        cls_node = ClassNode(
            name=class_name,
            file_path=file_path,
            cross_project=search_result["cross_project"],
            source_project=search_result["source_project"],
            tables_input=tables["input"],
            tables_output=tables["output"]
        )
        graph.nodes.classes.append(cls_node)
        
        # 添加类到任务映射
        graph.edges.class_maps_to_task.append({"class": class_name, "task": task_code})
        
        # 添加表节点和边
        for table_name in tables["input"]:
            self._add_table_node(table_name, graph)
            graph.edges.task_consumes_table.append({"task": task_code, "table": table_name})
        
        for table_name in tables["output"]:
            self._add_table_node(table_name, graph)
            graph.edges.task_produces_table.append({"task": task_code, "table": table_name})
    
    def _add_table_node(self, table_name: str, graph: Graph) -> None:
        """添加表节点"""
        # 检查是否已存在
        for t in graph.nodes.tables:
            if t.full_name == table_name:
                return
        
        # 创建新表节点
        table_node = TableNode(
            full_name=table_name,
            table_type=self._detect_table_type(table_name)
        )
        graph.nodes.tables.append(table_node)
    
    def _detect_table_type(self, table_name: str) -> str:
        """检测表类型"""
        if table_name.startswith("hive."):
            return "HIVE"
        elif "." in table_name and not table_name.startswith("hive."):
            return "MYSQL"
        return "UNKNOWN"


__all__ = ["GraphScanner"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_scanner.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/scanner.py tests/test_graph/test_scanner.py && git commit -m "feat: 添加 GraphScanner 图谱扫描器"
```

---

## Task 6: Indexer - 索引生成器

**Files:**
- Create: `src/graph/indexer.py`
- Create: `tests/test_graph/test_indexer.py`

- [ ] **Step 1: 创建测试文件 test_indexer.py**

```python
"""
Indexer 测试
"""

import pytest
import tempfile
from src.graph.indexer import GraphIndexer
from src.graph.storage import GraphStorage
from src.graph.models import Graph, GraphNodes, GraphEdges, WorkflowNode


class TestGraphIndexer:

    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            
            assert indexer.storage.data_dir == tmpdir

    def test_generate_downstream_index(self):
        """测试生成下游依赖索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            
            # 构建模拟图谱
            graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2026-05-08T10:00:00",
                version=1
            )
            
            # 添加工作流依赖边
            graph.edges.workflow_depends_workflow = [
                {"from": "1", "to": "2"},
                {"from": "2", "to": "3"},
                {"from": "1", "to": "4"}
            ]
            
            # 生成索引
            index = indexer.generate_downstream_index(graph)
            
            assert "1" in index["workflow_downstream"]
            assert "2" in index["workflow_downstream"]["1"]["direct"]
            assert "4" in index["workflow_downstream"]["1"]["direct"]
            assert index["workflow_downstream"]["1"]["count"] >= 2

    def test_generate_table_consumer_index(self):
        """测试生成表消费索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            
            graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2026-05-08T10:00:00",
                version=1
            )
            
            # 添加表消费边
            graph.edges.task_consumes_table = [
                {"task": "789", "table": "hive.db.source"}
            ]
            graph.edges.task_produces_table = [
                {"task": "789", "table": "hive.db.target"}
            ]
            graph.edges.workflow_contains_task = [
                {"workflow": "123", "task": "789"}
            ]
            
            index = indexer.generate_table_consumer_index(graph)
            
            assert "hive.db.source" in index["table_consumers"]
            assert "hive.db.target" in index["table_producers"]

    def test_generate_workflow_nodes_index(self):
        """测试生成工作流节点索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            
            graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2026-05-08T10:00:00",
                version=1
            )
            
            # 添加工作流和任务节点
            from src.graph.models import TaskNode
            graph.nodes.workflows.append(WorkflowNode(code="123", name="test_wf", schedule_type="CRON", schedule_cron="", is_sub_workflow=False, parent_workflow=None))
            graph.nodes.tasks.append(TaskNode(code="789", name="spark_task", workflow_code="123", task_type="SPARK", spark_main_class="com.example.Job"))
            
            graph.edges.workflow_contains_task = [
                {"workflow": "123", "task": "789"}
            ]
            
            index = indexer.generate_workflow_nodes_index(graph)
            
            assert "123" in index["workflow_tasks"]
            assert "789" in index["workflow_tasks"]["123"]["tasks"]
            assert index["workflow_tasks"]["123"]["task_types"]["789"] == "SPARK"

    def test_generate_all_indexes(self):
        """测试生成所有索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            
            graph = Graph(
                project_code="123",
                project_name="test",
                scanned_at="2026-05-08T10:00:00",
                version=1
            )
            
            # 保存图谱
            storage.save_graph("123", graph.to_dict())
            
            # 生成所有索引
            indexer.generate_all_indexes("123")
            
            # 验证索引文件存在
            assert storage.load_index("123", "downstream") is not None
            assert storage.load_index("123", "table_consumer") is not None
            assert storage.load_index("123", "workflow_nodes") is not None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_indexer.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 indexer.py**

```python
"""
Indexer - 索引生成器

从主图谱生成查询索引文件
"""

from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict

from .storage import GraphStorage
from .models import Graph


class GraphIndexer:
    """
    索引生成器
    
    生成三个索引:
    - downstream: 下游依赖索引
    - table_consumer: 表消费索引
    - workflow_nodes: 工作流节点索引
    """
    
    def __init__(self, storage: GraphStorage):
        """
        初始化
        
        Args:
            storage: 图谱存储
        """
        self.storage = storage
    
    def generate_all_indexes(self, project_code: str) -> None:
        """
        生成所有索引
        
        Args:
            project_code: 项目代码
        """
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return
        
        graph = Graph.from_dict(graph_data)
        
        # 生成三个索引
        downstream_index = self.generate_downstream_index(graph)
        table_index = self.generate_table_consumer_index(graph)
        nodes_index = self.generate_workflow_nodes_index(graph)
        
        # 保存索引
        self.storage.save_index(project_code, "downstream", downstream_index)
        self.storage.save_index(project_code, "table_consumer", table_index)
        self.storage.save_index(project_code, "workflow_nodes", nodes_index)
    
    def generate_downstream_index(self, graph: Graph) -> Dict:
        """
        生成下游依赖索引
        
        Args:
            graph: 图谱
            
        Returns:
            下游依赖索引数据
        """
        workflow_downstream = {}
        task_downstream = {}
        
        # 构建工作流依赖图
        wf_edges = graph.edges.workflow_depends_workflow
        
        # 计算每个工作流的下游
        for edge in wf_edges:
            from_wf = edge["from"]
            if from_wf not in workflow_downstream:
                workflow_downstream[from_wf] = {"direct": [], "all": [], "count": 0}
            workflow_downstream[from_wf]["direct"].append(edge["to"])
        
        # 计算全量下游（递归）
        for wf_code in workflow_downstream:
            all_downstream = self._find_all_downstream(wf_code, wf_edges)
            workflow_downstream[wf_code]["all"] = list(set(all_downstream))
            workflow_downstream[wf_code]["count"] = len(all_downstream)
        
        # 构建任务依赖图
        task_edges = graph.edges.task_depends_task
        
        for edge in task_edges:
            from_task = edge["from"]
            if from_task not in task_downstream:
                task_downstream[from_task] = {"direct": [], "all": [], "count": 0}
            task_downstream[from_task]["direct"].append(edge["to"])
        
        for task_code in task_downstream:
            all_downstream = self._find_all_downstream(task_code, task_edges)
            task_downstream[task_code]["all"] = list(set(all_downstream))
            task_downstream[task_code]["count"] = len(all_downstream)
        
        return {
            "generated_at": datetime.now().isoformat(),
            "workflow_downstream": workflow_downstream,
            "task_downstream": task_downstream
        }
    
    def generate_table_consumer_index(self, graph: Graph) -> Dict:
        """
        生成表消费索引
        
        Args:
            graph: 图谱
            
        Returns:
            表消费索引数据
        """
        table_consumers = defaultdict(lambda: {"workflows": [], "tasks": [], "classes": []})
        table_producers = defaultdict(lambda: {"workflows": [], "tasks": [], "classes": []})
        
        # 构建 task → workflow 映射
        task_to_workflow = {}
        for edge in graph.edges.workflow_contains_task:
            task_to_workflow[edge["task"]] = edge["workflow"]
        
        # 构建 class → task 映射
        class_to_task = {}
        for edge in graph.edges.class_maps_to_task:
            class_to_task[edge["class"]] = edge["task"]
        
        # 处理消费关系
        for edge in graph.edges.task_consumes_table:
            table = edge["table"]
            task = edge["task"]
            
            table_consumers[table]["tasks"].append(task)
            
            if task in task_to_workflow:
                table_consumers[table]["workflows"].append(task_to_workflow[task])
        
        # 处理产出关系
        for edge in graph.edges.task_produces_table:
            table = edge["table"]
            task = edge["task"]
            
            table_producers[table]["tasks"].append(task)
            
            if task in task_to_workflow:
                table_producers[table]["workflows"].append(task_to_workflow[task])
        
        # 添加类信息
        for cls_node in graph.nodes.classes:
            for table in cls_node.tables_input:
                table_consumers[table]["classes"].append(cls_node.name)
            for table in cls_node.tables_output:
                table_producers[table]["classes"].append(cls_node.name)
        
        # 去重
        for table in table_consumers:
            table_consumers[table]["workflows"] = list(set(table_consumers[table]["workflows"]))
            table_consumers[table]["tasks"] = list(set(table_consumers[table]["tasks"]))
            table_consumers[table]["classes"] = list(set(table_consumers[table]["classes"]))
        
        for table in table_producers:
            table_producers[table]["workflows"] = list(set(table_producers[table]["workflows"]))
            table_producers[table]["tasks"] = list(set(table_producers[table]["tasks"]))
            table_producers[table]["classes"] = list(set(table_producers[table]["classes"]))
        
        return {
            "generated_at": datetime.now().isoformat(),
            "table_consumers": dict(table_consumers),
            "table_producers": dict(table_producers)
        }
    
    def generate_workflow_nodes_index(self, graph: Graph) -> Dict:
        """
        生成工作流节点索引
        
        Args:
            graph: 图谱
            
        Returns:
            工作流节点索引数据
        """
        workflow_tasks = defaultdict(lambda: {
            "tasks": [],
            "task_names": {},
            "task_types": {},
            "spark_classes": {}
        })
        
        # 构建 task → workflow 映射
        for edge in graph.edges.workflow_contains_task:
            wf = edge["workflow"]
            task = edge["task"]
            workflow_tasks[wf]["tasks"].append(task)
        
        # 填充任务信息
        for task_node in graph.nodes.tasks:
            wf = task_node.workflow_code
            task = task_node.code
            
            workflow_tasks[wf]["task_names"][task] = task_node.name
            workflow_tasks[wf]["task_types"][task] = task_node.task_type
            
            if task_node.spark_main_class:
                workflow_tasks[wf]["spark_classes"][task] = task_node.spark_main_class
        
        return {
            "generated_at": datetime.now().isoformat(),
            "workflow_tasks": dict(workflow_tasks)
        }
    
    def _find_all_downstream(self, start_code: str, edges: List[Dict]) -> List[str]:
        """递归查找所有下游"""
        all_downstream = set()
        to_process = [start_code]
        
        while to_process:
            current = to_process.pop()
            for edge in edges:
                if edge["from"] == current:
                    downstream = edge["to"]
                    if downstream not in all_downstream:
                        all_downstream.add(downstream)
                        to_process.append(downstream)
        
        return list(all_downstream)


__all__ = ["GraphIndexer"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_indexer.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/indexer.py tests/test_graph/test_indexer.py && git commit -m "feat: 添加 GraphIndexer 索引生成器"
```

---

## Task 7: Querier - 图谱查询器

**Files:**
- Create: `src/graph/querier.py`
- Create: `tests/test_graph/test_querier.py`

- [ ] **Step 1: 创建测试文件 test_querier.py**

```python
"""
Querier 测试
"""

import pytest
import tempfile
from src.graph.querier import GraphQuerier
from src.graph.storage import GraphStorage
from src.graph.models import Graph, WorkflowNode, TaskNode
from src.graph.indexer import GraphIndexer


class TestGraphQuerier:

    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            querier = GraphQuerier(storage=storage)
            
            assert querier.storage.data_dir == tmpdir

    def test_query_workflow_downstream(self):
        """测试查询工作流下游"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            querier = GraphQuerier(storage=storage)
            
            # 构建图谱
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [{"from": "1", "to": "2"}]
            
            storage.save_graph("123", graph.to_dict())
            indexer.generate_all_indexes("123")
            
            result = querier.query_workflow_downstream("123", "1")
            
            assert result["found"] is True
            assert "2" in result["direct"]

    def test_query_workflow_downstream_not_found(self):
        """测试查询不存在的工作流"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            querier = GraphQuerier(storage=storage)
            
            result = querier.query_workflow_downstream("123", "nonexistent")
            
            assert result["found"] is False

    def test_query_table_consumers(self):
        """测试查询表消费者"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            querier = GraphQuerier(storage=storage)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.task_consumes_table = [{"task": "789", "table": "hive.db.source"}]
            graph.edges.workflow_contains_task = [{"workflow": "123", "task": "789"}]
            
            storage.save_graph("123", graph.to_dict())
            indexer.generate_all_indexes("123")
            
            result = querier.query_table_consumers("123", "hive.db.source")
            
            assert result["found"] is True
            assert "789" in result["tasks"]

    def test_query_workflow_nodes(self):
        """测试查询工作流节点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            indexer = GraphIndexer(storage=storage)
            querier = GraphQuerier(storage=storage)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.nodes.workflows.append(WorkflowNode(code="123", name="wf", schedule_type="CRON", schedule_cron="", is_sub_workflow=False, parent_workflow=None))
            graph.nodes.tasks.append(TaskNode(code="789", name="task", workflow_code="123", task_type="SPARK"))
            graph.edges.workflow_contains_task = [{"workflow": "123", "task": "789"}]
            
            storage.save_graph("123", graph.to_dict())
            indexer.generate_all_indexes("123")
            
            result = querier.query_workflow_nodes("123", "123")
            
            assert result["found"] is True
            assert "789" in result["tasks"]

    def test_query_no_graph(self):
        """测试无图谱时的查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            querier = GraphQuerier(storage=storage)
            
            result = querier.query_workflow_downstream("nonexistent", "1")
            
            assert result["found"] is False
            assert "图谱未扫描" in result["message"]

    def test_query_workflow_info(self):
        """测试查询工作流详情"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            querier = GraphQuerier(storage=storage)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.nodes.workflows.append(WorkflowNode(code="123", name="daily_etl", schedule_type="CRON", schedule_cron="0 8 * * *", is_sub_workflow=False, parent_workflow=None))
            
            storage.save_graph("123", graph.to_dict())
            
            result = querier.query_workflow_info("123", "123")
            
            assert result["found"] is True
            assert result["name"] == "daily_etl"
            assert result["schedule_cron"] == "0 8 * * *"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_querier.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 querier.py**

```python
"""
Querier - 图谱查询器

提供基础查询和深度查询能力
"""

from typing import Dict, Optional, List
from datetime import datetime

from .storage import GraphStorage
from .models import Graph


class GraphQuerier:
    """
    图谱查询器
    
    查询类型:
    - 基础查询: 读索引文件
    - 深度查询: NetworkX 图算法
    """
    
    def __init__(self, storage: GraphStorage):
        """
        初始化
        
        Args:
            storage: 图谱存储
        """
        self.storage = storage
    
    def query_workflow_downstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流下游依赖
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            {
                "found": bool,
                "direct": [...],
                "all": [...],
                "count": int,
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
                "message": "图谱未扫描，无法查询下游依赖"
            }
        
        # 加载下游索引
        downstream_index = self.storage.load_index(project_code, "downstream")
        if not downstream_index:
            return {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": "索引未生成"
            }
        
        workflow_downstream = downstream_index.get("workflow_downstream", {})
        
        if workflow_code not in workflow_downstream:
            return {
                "found": False,
                "direct": [],
                "all": [],
                "count": 0,
                "message": "工作流不存在"
            }
        
        data = workflow_downstream[workflow_code]
        return {
            "found": True,
            "direct": data.get("direct", []),
            "all": data.get("all", []),
            "count": data.get("count", 0),
            "message": ""
        }
    
    def query_workflow_upstream(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流上游依赖
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            上游依赖信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "upstream": [],
                "message": "图谱未扫描"
            }
        
        # 加载图谱
        graph_data = self.storage.load_graph(project_code)
        graph = Graph.from_dict(graph_data)
        
        # 从下游索引反向查找
        downstream_index = self.storage.load_index(project_code, "downstream")
        if not downstream_index:
            return {"found": False, "upstream": [], "message": "索引未生成"}
        
        workflow_downstream = downstream_index.get("workflow_downstream", {})
        
        upstream = []
        for wf_code, data in workflow_downstream.items():
            if workflow_code in data.get("all", []):
                upstream.append(wf_code)
        
        return {
            "found": True,
            "upstream": list(set(upstream)),
            "message": ""
        }
    
    def query_table_consumers(self, project_code: str, table_name: str) -> Dict:
        """
        查询表消费者
        
        Args:
            project_code: 项目代码
            table_name: 表名
            
        Returns:
            消费者信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "图谱未扫描"
            }
        
        table_index = self.storage.load_index(project_code, "table_consumer")
        if not table_index:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "索引未生成"
            }
        
        table_consumers = table_index.get("table_consumers", {})
        
        if table_name not in table_consumers:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "表不存在"
            }
        
        data = table_consumers[table_name]
        return {
            "found": True,
            "workflows": data.get("workflows", []),
            "tasks": data.get("tasks", []),
            "classes": data.get("classes", []),
            "message": ""
        }
    
    def query_table_producers(self, project_code: str, table_name: str) -> Dict:
        """
        查询表生产者
        
        Args:
            project_code: 项目代码
            table_name: 表名
            
        Returns:
            生产者信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "图谱未扫描"
            }
        
        table_index = self.storage.load_index(project_code, "table_consumer")
        if not table_index:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "索引未生成"
            }
        
        table_producers = table_index.get("table_producers", {})
        
        if table_name not in table_producers:
            return {
                "found": False,
                "workflows": [],
                "tasks": [],
                "classes": [],
                "message": "表不存在"
            }
        
        data = table_producers[table_name]
        return {
            "found": True,
            "workflows": data.get("workflows", []),
            "tasks": data.get("tasks", []),
            "classes": data.get("classes", []),
            "message": ""
        }
    
    def query_workflow_nodes(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流节点
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            节点信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "tasks": [],
                "message": "图谱未扫描"
            }
        
        nodes_index = self.storage.load_index(project_code, "workflow_nodes")
        if not nodes_index:
            return {
                "found": False,
                "tasks": [],
                "message": "索引未生成"
            }
        
        workflow_tasks = nodes_index.get("workflow_tasks", {})
        
        if workflow_code not in workflow_tasks:
            return {
                "found": False,
                "tasks": [],
                "message": "工作流不存在"
            }
        
        data = workflow_tasks[workflow_code]
        return {
            "found": True,
            "tasks": data.get("tasks", []),
            "task_names": data.get("task_names", {}),
            "task_types": data.get("task_types", {}),
            "spark_classes": data.get("spark_classes", {}),
            "message": ""
        }
    
    def query_workflow_info(self, project_code: str, workflow_code: str) -> Dict:
        """
        查询工作流详情
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            工作流信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "message": "图谱未扫描"
            }
        
        graph_data = self.storage.load_graph(project_code)
        graph = Graph.from_dict(graph_data)
        
        for wf in graph.nodes.workflows:
            if wf.code == workflow_code:
                return {
                    "found": True,
                    "code": wf.code,
                    "name": wf.name,
                    "schedule_type": wf.schedule_type,
                    "schedule_cron": wf.schedule_cron,
                    "is_sub_workflow": wf.is_sub_workflow,
                    "parent_workflow": wf.parent_workflow,
                    "message": ""
                }
        
        return {
            "found": False,
            "message": "工作流不存在"
        }
    
    def query_task_info(self, project_code: str, task_code: str) -> Dict:
        """
        查询任务详情
        
        Args:
            project_code: 项目代码
            task_code: 任务代码
            
        Returns:
            任务信息
        """
        if not self.storage.graph_exists(project_code):
            return {
                "found": False,
                "message": "图谱未扫描"
            }
        
        graph_data = self.storage.load_graph(project_code)
        graph = Graph.from_dict(graph_data)
        
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
                    "message": ""
                }
        
        return {
            "found": False,
            "message": "任务不存在"
        }


__all__ = ["GraphQuerier"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_querier.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/querier.py tests/test_graph/test_querier.py && git commit -m "feat: 添加 GraphQuerier 图谱查询器"
```

---

## 实现说明

### 测试策略
- Scanner 测试使用 Mock DSCLIClient
- Indexer 和 Querier 测试构建模拟图谱数据

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/ -v
```

### 配置更新

在 `src/config/settings.py` 添加:
```python
CODE_ROOT_PATH: str = field(default_factory=lambda: os.getenv("CODE_ROOT_PATH", ""))
GRAPH_STORAGE_PATH: str = field(default_factory=lambda: os.getenv("GRAPH_STORAGE_PATH", "data/graph"))
```

### 下一阶段

Phase 3-4 完成后继续:
- Chat Module Phase 1-2（意图解析 + 钉钉交互 + 图谱查询集成）
- 系统集成改造（告警 Agent 改用图谱查询）