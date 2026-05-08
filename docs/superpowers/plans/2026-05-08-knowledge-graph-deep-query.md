# 知识图谱深度查询与 Chat Agent 完整集成 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-step.

**Goal:** 实现深度查询功能（NetworkX 路径分析 + Mermaid 可视化）和完整的 Chat Agent 集成（scan_graph + visualize_lineage + LangGraph 流程图）

**Architecture:** Querier 增加 NetworkX 方法，Chat Module 增加 scan_graph_node 和 visualize_node，创建 LangGraph 流程定义

**Tech Stack:** NetworkX, LangGraph, Mermaid, GraphScanner

---

## 文件结构

**新建文件：**
```
src/graph/
├── networkx_analyzer.py    # NetworkX 路径分析
├── mermaid_generator.py    # Mermaid 图生成

src/chat/
├── graph.py                # LangGraph 流程定义
├── nodes/
│   ├── scan_graph.py       # 图谱扫描节点
│   ├── visualize.py        # 可视化节点

tests/test_graph/
├── test_networkx_analyzer.py
├── test_mermaid_generator.py

tests/test_chat/
├── test_scan_graph.py
├── test_visualize.py
├── test_graph_flow.py
```

**修改文件：**
```
src/chat/api/dingtalk_webhook.py  # 完整流程集成
src/chat/nodes/query_lineage.py   # 增加 depth_query 支持
```

---

## Task 1: NetworkX Analyzer - NetworkX 路径分析

**Files:**
- Create: `src/graph/networkx_analyzer.py`
- Create: `tests/test_graph/test_networkx_analyzer.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
NetworkX Analyzer 测试
"""

import pytest
import tempfile
from src.graph.networkx_analyzer import NetworkXAnalyzer
from src.graph.storage import GraphStorage
from src.graph.models import Graph


class TestNetworkXAnalyzer:

    def test_init(self):
        """测试初始化"""
        analyzer = NetworkXAnalyzer()
        assert analyzer is not None

    def test_build_workflow_graph(self):
        """测试构建工作流依赖图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
                {"source": "1", "target": "4"},
            ]
            storage.save_graph("123", graph.to_dict())
            
            analyzer = NetworkXAnalyzer(storage)
            nx_graph = analyzer.build_workflow_graph("123")
            
            assert nx_graph.number_of_nodes() == 4
            assert nx_graph.number_of_edges() == 3

    def test_find_shortest_path(self):
        """测试查找最短路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
                {"source": "1", "target": "4"},
                {"source": "4", "target": "3"},
            ]
            storage.save_graph("123", graph.to_dict())
            
            analyzer = NetworkXAnalyzer(storage)
            analyzer.build_workflow_graph("123")
            
            path = analyzer.find_shortest_path("123", "1", "3")
            
            # 最短路径可能是 1->2->3 或 1->4->3
            assert path[0] == "1"
            assert path[-1] == "3"

    def test_find_all_paths(self):
        """测试查找所有路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
                {"source": "1", "target": "4"},
                {"source": "4", "target": "3"},
            ]
            storage.save_graph("123", graph.to_dict())
            
            analyzer = NetworkXAnalyzer(storage)
            analyzer.build_workflow_graph("123")
            
            paths = analyzer.find_all_paths("123", "1", "3")
            
            assert len(paths) == 2

    def test_find_cycles(self):
        """测试检测环"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
                {"source": "3", "target": "1"},  # 形成环
            ]
            storage.save_graph("123", graph.to_dict())
            
            analyzer = NetworkXAnalyzer(storage)
            analyzer.build_workflow_graph("123")
            
            cycles = analyzer.find_cycles("123")
            
            assert len(cycles) > 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_graph/test_networkx_analyzer.py -v`

- [ ] **Step 3: 实现 networkx_analyzer.py**

```python
"""
NetworkX Analyzer - NetworkX 路径分析

使用 NetworkX 进行图算法分析
"""

import networkx as nx
from typing import Dict, List, Optional
from .storage import GraphStorage
from .models import Graph


class NetworkXAnalyzer:
    """
    NetworkX 路径分析器
    
    功能:
    - 构建工作流/任务依赖图
    - 最短路径分析
    - 所有路径查找
    - 环检测
    """
    
    def __init__(self, storage: GraphStorage = None):
        """
        初始化
        
        Args:
            storage: 图谱存储
        """
        self.storage = storage or GraphStorage()
        self._workflow_graph: Optional[nx.DiGraph] = None
        self._task_graph: Optional[nx.DiGraph] = None
        self._project_code: str = ""
    
    def build_workflow_graph(self, project_code: str) -> nx.DiGraph:
        """
        构建工作流依赖图
        
        Args:
            project_code: 项目代码
            
        Returns:
            NetworkX DiGraph
        """
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return nx.DiGraph()
        
        graph = Graph.from_dict(graph_data)
        
        G = nx.DiGraph()
        for edge in graph.edges.workflow_depends_workflow:
            source = edge.get("source", edge.get("from", ""))
            target = edge.get("target", edge.get("to", ""))
            if source and target:
                G.add_edge(source, target)
        
        self._workflow_graph = G
        self._project_code = project_code
        return G
    
    def build_task_graph(self, project_code: str, workflow_code: str) -> nx.DiGraph:
        """
        构建任务依赖图
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            NetworkX DiGraph
        """
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return nx.DiGraph()
        
        graph = Graph.from_dict(graph_data)
        
        G = nx.DiGraph()
        for edge in graph.edges.task_depends_task:
            source = edge.get("source", edge.get("from", ""))
            target = edge.get("target", edge.get("to", ""))
            if source and target:
                G.add_edge(source, target)
        
        self._task_graph = G
        return G
    
    def find_shortest_path(self, project_code: str, source: str, target: str) -> List[str]:
        """
        查找最短路径
        
        Args:
            project_code: 项目代码
            source: 起点
            target: 终点
            
        Returns:
            路径节点列表
        """
        if self._workflow_graph is None or self._project_code != project_code:
            self.build_workflow_graph(project_code)
        
        try:
            return nx.shortest_path(self._workflow_graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def find_all_paths(self, project_code: str, source: str, target: str) -> List[List[str]]:
        """
        查找所有路径
        
        Args:
            project_code: 项目代码
            source: 起点
            target: 终点
            
        Returns:
            所有路径列表
        """
        if self._workflow_graph is None or self._project_code != project_code:
            self.build_workflow_graph(project_code)
        
        try:
            return list(nx.all_simple_paths(self._workflow_graph, source, target))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def find_cycles(self, project_code: str) -> List[List[str]]:
        """
        检测图中的环
        
        Args:
            project_code: 项目代码
            
        Returns:
            环列表
        """
        if self._workflow_graph is None or self._project_code != project_code:
            self.build_workflow_graph(project_code)
        
        return list(nx.simple_cycles(self._workflow_graph))
    
    def calculate_degree(self, project_code: str, node: str) -> Dict:
        """
        计算节点度数
        
        Args:
            project_code: 项目代码
            node: 节点
            
        Returns:
            {"in_degree": N, "out_degree": N}
        """
        if self._workflow_graph is None or self._project_code != project_code:
            self.build_workflow_graph(project_code)
        
        if node not in self._workflow_graph:
            return {"in_degree": 0, "out_degree": 0}
        
        return {
            "in_degree": self._workflow_graph.in_degree(node),
            "out_degree": self._workflow_graph.out_degree(node)
        }


__all__ = ["NetworkXAnalyzer"]
```

- [ ] **Step 4: 运行测试验证通过**

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/networkx_analyzer.py tests/test_graph/test_networkx_analyzer.py && git commit -m "feat: 添加 NetworkXAnalyzer 路径分析器"
```

---

## Task 2: Mermaid Generator - Mermaid 图生成

**Files:**
- Create: `src/graph/mermaid_generator.py`
- Create: `tests/test_graph/test_mermaid_generator.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
Mermaid Generator 测试
"""

import pytest
import tempfile
from src.graph.mermaid_generator import MermaidGenerator
from src.graph.storage import GraphStorage
from src.graph.models import Graph


class TestMermaidGenerator:

    def test_init(self):
        """测试初始化"""
        generator = MermaidGenerator()
        assert generator is not None

    def test_generate_downstream_graph(self):
        """测试生成下游依赖图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.nodes.workflows = [
                {"code": "1", "name": "daily_etl"},
                {"code": "2", "name": "daily_summary"},
                {"code": "3", "name": "daily_report"},
            ]
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
                {"source": "2", "target": "3"},
            ]
            storage.save_graph("123", graph.to_dict())
            
            generator = MermaidGenerator(storage)
            mermaid = generator.generate_downstream_graph("123", "1")
            
            assert "graph TD" in mermaid
            assert "1" in mermaid
            assert "2" in mermaid

    def test_generate_path_graph(self):
        """测试生成路径图"""
        generator = MermaidGenerator()
        
        path = ["1", "2", "3", "4"]
        mermaid = generator.generate_path_graph(path)
        
        assert "graph LR" in mermaid
        assert "1 --> 2" in mermaid
        assert "3 --> 4" in mermaid

    def test_generate_full_graph(self):
        """测试生成完整图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.nodes.workflows = [
                {"code": "1", "name": "wf1"},
                {"code": "2", "name": "wf2"},
            ]
            graph.edges.workflow_depends_workflow = [
                {"source": "1", "target": "2"},
            ]
            storage.save_graph("123", graph.to_dict())
            
            generator = MermaidGenerator(storage)
            mermaid = generator.generate_full_graph("123")
            
            assert "graph TD" in mermaid
```

- [ ] **Step 2: 运行测试验证失败**

- [ ] **Step 3: 实现 mermaid_generator.py**

```python
"""
Mermaid Generator - Mermaid 图生成

生成 Mermaid 格式的可视化图
"""

from typing import Dict, List, Optional
from .storage import GraphStorage
from .models import Graph


class MermaidGenerator:
    """
    Mermaid 图生成器
    
    生成格式:
    - 下游依赖图 (graph TD)
    - 路径图 (graph LR)
    - 完整图
    """
    
    def __init__(self, storage: GraphStorage = None):
        """
        初始化
        
        Args:
            storage: 图谱存储
        """
        self.storage = storage or GraphStorage()
    
    def generate_downstream_graph(self, project_code: str, workflow_code: str) -> str:
        """
        生成下游依赖图
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            Mermaid 图代码
        """
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return "graph TD\n  NoGraph[图谱未扫描]"
        
        graph = Graph.from_dict(graph_data)
        
        # 获取下游索引
        downstream_index = self.storage.load_index(project_code, "downstream")
        if not downstream_index:
            return "graph TD\n  NoIndex[索引未生成]"
        
        workflow_downstream = downstream_index.get("workflow_downstream", {})
        downstream_codes = workflow_downstream.get(workflow_code, {}).get("all", [])
        
        # 构建工作流名称映射
        workflow_names = {}
        for wf in graph.nodes.workflows:
            workflow_names[wf.code] = wf.name
        
        # 构建边
        lines = ["graph TD"]
        
        # 添加起点
        start_name = workflow_names.get(workflow_code, workflow_code)
        lines.append(f"  {workflow_code}[{start_name}]")
        
        # 添加下游节点和边
        for edge in graph.edges.workflow_depends_workflow:
            source = edge.get("source", edge.get("from", ""))
            target = edge.get("target", edge.get("to", ""))
            
            if source == workflow_code or target in downstream_codes:
                source_name = workflow_names.get(source, source)
                target_name = workflow_names.get(target, target)
                lines.append(f"  {source}[{source_name}] --> {target}[{target_name}]")
        
        return "\n".join(lines)
    
    def generate_path_graph(self, path: List[str], names: Dict[str, str] = None) -> str:
        """
        生成路径图
        
        Args:
            path: 路径节点列表
            names: 节点名称映射
            
        Returns:
            Mermaid 图代码
        """
        names = names or {}
        
        if len(path) < 2:
            return "graph LR\n  Empty[路径为空]"
        
        lines = ["graph LR"]
        
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i + 1]
            source_name = names.get(source, source)
            target_name = names.get(target, target)
            lines.append(f"  {source}[{source_name}] --> {target}[{target_name}]")
        
        return "\n".join(lines)
    
    def generate_full_graph(self, project_code: str) -> str:
        """
        生成完整图
        
        Args:
            project_code: 项目代码
            
        Returns:
            Mermaid 图代码
        """
        graph_data = self.storage.load_graph(project_code)
        if not graph_data:
            return "graph TD\n  NoGraph[图谱未扫描]"
        
        graph = Graph.from_dict(graph_data)
        
        # 构建工作流名称映射
        workflow_names = {}
        for wf in graph.nodes.workflows:
            workflow_names[wf.code] = wf.name
        
        lines = ["graph TD"]
        
        # 添加所有节点
        for wf in graph.nodes.workflows:
            lines.append(f"  {wf.code}[{wf.name}]")
        
        # 添加边
        for edge in graph.edges.workflow_depends_workflow:
            source = edge.get("source", edge.get("from", ""))
            target = edge.get("target", edge.get("to", ""))
            lines.append(f"  {source} --> {target}")
        
        return "\n".join(lines)


__all__ = ["MermaidGenerator"]
```

- [ ] **Step 4: 运行测试验证通过**

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/graph/mermaid_generator.py tests/test_graph/test_mermaid_generator.py && git commit -m "feat: 添加 MermaidGenerator 可视化生成器"
```

---

## Task 3: Scan Graph Node - 图谱扫描节点

**Files:**
- Create: `src/chat/nodes/scan_graph.py`
- Create: `tests/test_chat/test_scan_graph.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
Scan Graph Node 测试
"""

import pytest
import tempfile
from unittest.mock import Mock, patch
from src.chat.state import create_chat_state
from src.chat.nodes.scan_graph import scan_graph_node


class TestScanGraphNode:

    def test_scan_graph_success(self):
        """测试成功扫描"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_chat_state(message="扫描项目 test_project 图谱")
            state["intent_type"] = "scan_graph"
            state["project_name"] = "test_project"
            state["project_code"] = "12345"
            
            with patch("src.chat.nodes.scan_graph.GraphScanner") as mock_scanner:
                mock_instance = Mock()
                mock_instance.scan_project.return_value = {
                    "workflows_count": 10,
                    "tasks_count": 50,
                    "tables_count": 20,
                    "classes_count": 15
                }
                mock_scanner.return_value = mock_instance
                
                result = scan_graph_node(state)
                
                assert result["intent_type"] == "scan_graph"
                assert result["result_data"]["workflows_count"] == 10

    def test_scan_graph_no_project(self):
        """测试无项目代码"""
        state = create_chat_state(message="扫描图谱")
        state["intent_type"] = "scan_graph"
        
        result = scan_graph_node(state)
        
        assert result["error_message"] is not None
```

- [ ] **Step 2: 实现 scan_graph.py**

```python
"""
Scan Graph Node - 图谱扫描节点

调用 GraphScanner 执行图谱扫描
"""

from ..state import ChatState
from ...graph.storage import GraphStorage
from ...graph.scanner import GraphScanner
from ...config import settings


def scan_graph_node(state: ChatState) -> ChatState:
    """
    图谱扫描节点
    
    Args:
        state: 当前对话状态
        
    Returns:
        更新后的状态
    """
    project_name = state.get("project_name", "")
    project_code = state.get("project_code", "")
    
    if not project_name and not project_code:
        return {
            **state,
            "error_message": "缺少项目名称或项目代码"
        }
    
    # 初始化 Scanner
    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    scanner = GraphScanner(storage=storage, code_root=settings.CODE_ROOT_PATH)
    
    try:
        # 执行扫描
        result = scanner.scan_project(
            project_code=project_code or project_name,
            project_name=project_name,
            ds_api_url=settings.DS_API_URL,
            ds_api_token=settings.DS_API_TOKEN
        )
        
        # 生成索引
        from ...graph.indexer import GraphIndexer
        indexer = GraphIndexer(storage=storage)
        indexer.generate_all_indexes(project_code or project_name)
        
        return {
            **state,
            "result_data": result
        }
    
    except Exception as e:
        return {
            **state,
            "error_message": f"扫描失败: {str(e)}"
        }


__all__ = ["scan_graph_node"]
```

- [ ] **Step 3: 运行测试验证**

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/nodes/scan_graph.py tests/test_chat/test_scan_graph.py && git commit -m "feat: 添加 scan_graph_node 图谱扫描节点"
```

---

## Task 4: Visualize Node - 可视化节点

**Files:**
- Create: `src/chat/nodes/visualize.py`
- Create: `tests/test_chat/test_visualize.py`

- [ ] **Step 5: 提交**

---

## Task 5: LangGraph 流程定义

**Files:**
- Create: `src/chat/graph.py`
- Create: `tests/test_chat/test_graph_flow.py`

---

## Task 6: 完整 DingTalk 集成

**Files:**
- Modify: `src/chat/api/dingtalk_webhook.py`

---

## 实现说明

完成后 Chat Agent 将支持完整功能:
- 扫描图谱
- 血缘查询（基础 + 深度）
- 影响链路可视化