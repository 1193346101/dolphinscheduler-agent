# System Integration 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造告警 Agent 和 LangGraph Workflow，使用本地图谱替代实时 API 调用进行影响分析

**Architecture:** 在 alert_agent.py 和 risk.py 中集成 GraphQuerier，优先查询本地图谱，图谱不存在时降级到原有逻辑

**Tech Stack:** GraphQuerier, AgentState, AlertAgent, LangGraph

---

## 文件结构

**修改文件：**
```
src/agent/alert_agent.py        # 改造 _analyze_impact 方法
src/workflow/nodes/risk.py      # 改造 impact_analysis 节点
src/tools/impact.py             # 保留作为降级备选
```

**新增文件：**
```
src/tools/graph_impact.py       # 图谱影响分析工具
tests/test_tools/test_graph_impact.py
```

---

## Task 1: Graph Impact Tool - 图谱影响分析工具

**Files:**
- Create: `src/tools/graph_impact.py`
- Create: `tests/test_tools/test_graph_impact.py`

- [ ] **Step 1: 创建测试文件 test_graph_impact.py**

```python
"""
Graph Impact Tool 测试
"""

import pytest
import tempfile
from unittest.mock import Mock, patch
from src.tools.graph_impact import GraphImpactTool


class TestGraphImpactTool:

    def test_analyze_workflow_downstream_with_graph(self):
        """测试有图谱时的工作流下游分析"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.graph.storage import GraphStorage
            from src.graph.models import Graph
            
            storage = GraphStorage(data_dir=tmpdir)
            
            # 构建模拟图谱
            graph = Graph(project_code="12345", project_name="test", scanned_at="", version=1)
            graph.nodes.workflows = [
                {"code": "100", "name": "wf1"},
                {"code": "200", "name": "wf2"},
            ]
            graph.edges.workflow_depends_workflow = [{"from": "100", "to": "200"}]
            storage.save_graph("12345", graph.to_dict())
            
            # 生成索引
            from src.graph.indexer import GraphIndexer
            indexer = GraphIndexer(storage=storage)
            indexer.generate_all_indexes("12345")
            
            tool = GraphImpactTool(storage=storage)
            result = tool.analyze_workflow_downstream(project_code="12345", workflow_code="100")
            
            assert result["graph_available"] is True
            assert result["downstream_count"] == 1
            assert "200" in result["downstream_workflows"]

    def test_analyze_workflow_downstream_no_graph(self):
        """测试无图谱时的降级处理"""
        tool = GraphImpactTool()
        
        result = tool.analyze_workflow_downstream(project_code="nonexistent", workflow_code="100")
        
        assert result["graph_available"] is False
        assert "图谱未扫描" in result["message"]

    def test_analyze_task_impact_with_graph(self):
        """测试有图谱时的任务影响分析"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.graph.storage import GraphStorage
            from src.graph.models import Graph
            
            storage = GraphStorage(data_dir=tmpdir)
            
            graph = Graph(project_code="12345", project_name="test", scanned_at="", version=1)
            graph.nodes.tasks = [
                {"code": "t1", "name": "task1", "workflow_code": "100"},
                {"code": "t2", "name": "task2", "workflow_code": "100"},
            ]
            graph.edges.task_depends_task = [{"from": "t1", "to": "t2"}]
            storage.save_graph("12345", graph.to_dict())
            
            from src.graph.indexer import GraphIndexer
            indexer = GraphIndexer(storage=storage)
            indexer.generate_all_indexes("12345")
            
            tool = GraphImpactTool(storage=storage)
            result = tool.analyze_task_downstream(project_code="12345", workflow_code="100", task_code="t1")
            
            assert result["graph_available"] is True
            assert result["downstream_count"] == 1

    def test_build_impact_summary(self):
        """测试构建影响摘要"""
        tool = GraphImpactTool()
        
        summary = tool.build_impact_summary(
            workflow_code="100",
            downstream_workflows=["200", "300"],
            downstream_tasks=["t2", "t3"],
        )
        
        assert "100" in summary
        assert "2" in summary or "下游" in summary
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_graph_impact.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 graph_impact.py**

```python
"""
Graph Impact Tool - 图谱影响分析工具

使用本地图谱分析下游影响，替代实时 API 调用
"""

from typing import Dict, List, Optional
from ..graph.storage import GraphStorage
from ..graph.querier import GraphQuerier


class GraphImpactTool:
    """
    图谱影响分析工具
    
    分析类型:
    - workflow_downstream: 工作流下游依赖
    - task_downstream: 任务下游依赖
    - workflow_nodes: 工作流节点信息
    
    降级策略:
    - 图谱不存在: 返回 graph_available=False，提示需要扫描
    - 索引不存在: 尝试从主图谱实时计算
    """
    
    def __init__(self, storage: GraphStorage = None):
        """
        初始化
        
        Args:
            storage: 图谱存储实例（可选，默认自动创建）
        """
        self.storage = storage or GraphStorage()
        self.querier = GraphQuerier(self.storage)
    
    def analyze_workflow_downstream(
        self,
        project_code: str,
        workflow_code: str
    ) -> Dict:
        """
        分析工作流下游依赖
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            
        Returns:
            {
                "graph_available": bool,
                "downstream_count": int,
                "downstream_workflows": List[str],
                "downstream_workflow_names": Dict[str, str],
                "impact_level": "low" | "medium" | "high",
                "message": str (if graph not available)
            }
        """
        # 检查图谱是否存在
        graph = self.storage.load_graph(project_code)
        if not graph:
            return {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_workflows": [],
                "downstream_workflow_names": {},
                "impact_level": "unknown",
                "message": "图谱未扫描，无法评估下游影响",
            }
        
        # 查询下游
        result = self.querier.query_workflow_downstream(project_code, workflow_code)
        
        if not result.get("found"):
            return {
                "graph_available": True,
                "downstream_count": 0,
                "downstream_workflows": [],
                "downstream_workflow_names": {},
                "impact_level": "low",
                "message": "工作流无下游依赖",
            }
        
        downstream_codes = result.get("all", [])
        downstream_count = len(downstream_codes)
        
        # 获取工作流名称
        workflow_names = {}
        for wf in graph.get("nodes", {}).get("workflows", []):
            if wf["code"] in downstream_codes:
                workflow_names[wf["code"]] = wf.get("name", wf["code"])
        
        # 计算影响等级
        impact_level = self._calculate_impact_level(downstream_count)
        
        return {
            "graph_available": True,
            "downstream_count": downstream_count,
            "downstream_workflows": downstream_codes,
            "downstream_workflow_names": workflow_names,
            "impact_level": impact_level,
        }
    
    def analyze_task_downstream(
        self,
        project_code: str,
        workflow_code: str,
        task_code: str
    ) -> Dict:
        """
        分析任务下游依赖
        
        Args:
            project_code: 项目代码
            workflow_code: 工作流代码
            task_code: 任务代码
            
        Returns:
            {
                "graph_available": bool,
                "downstream_count": int,
                "downstream_tasks": List[str],
                "impact_level": str,
                "message": str (if not available)
            }
        """
        graph = self.storage.load_graph(project_code)
        if not graph:
            return {
                "graph_available": False,
                "downstream_count": 0,
                "downstream_tasks": [],
                "impact_level": "unknown",
                "message": "图谱未扫描",
            }
        
        # 从 workflow_nodes 索引查询
        nodes_index = self.storage.load_index(project_code, "workflow_nodes")
        if not nodes_index:
            return {
                "graph_available": True,
                "downstream_count": 0,
                "downstream_tasks": [],
                "impact_level": "low",
                "message": "索引未生成",
            }
        
        workflow_data = nodes_index.get("workflow_tasks", {}).get(workflow_code, {})
        tasks = workflow_data.get("tasks", [])
        
        # 查找 task 在 tasks 列表中的位置，后面都是下游
        try:
            task_index = tasks.index(task_code)
            downstream_tasks = tasks[task_index + 1:]
        except ValueError:
            downstream_tasks = []
        
        downstream_count = len(downstream_tasks)
        impact_level = self._calculate_impact_level(downstream_count)
        
        return {
            "graph_available": True,
            "downstream_count": downstream_count,
            "downstream_tasks": downstream_tasks,
            "impact_level": impact_level,
        }
    
    def analyze_workflow_nodes(
        self,
        project_code: str,
        workflow_code: str
    ) -> Dict:
        """
        分析工作流节点信息
        
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
                "spark_classes": Dict[str, str],
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
                "message": result.get("message", "查询失败"),
            }
        
        return {
            "graph_available": True,
            "task_count": len(result.get("tasks", [])),
            "tasks": result.get("tasks", []),
            "task_names": result.get("task_names", {}),
            "task_types": result.get("task_types", {}),
            "spark_classes": result.get("spark_classes", {}),
        }
    
    def build_impact_summary(
        self,
        workflow_code: str,
        downstream_workflows: List[str],
        downstream_tasks: List[str],
        workflow_names: Dict[str, str] = None
    ) -> str:
        """
        构建影响摘要文本
        
        Args:
            workflow_code: 工作流代码
            downstream_workflows: 下游工作流列表
            downstream_tasks: 下游任务列表
            workflow_names: 工作流名称映射
            
        Returns:
            Markdown 格式的影响摘要
        """
        workflow_names = workflow_names or {}
        
        lines = [f"### 工作流 {workflow_code} 影响分析", ""]
        
        # 下游工作流
        wf_count = len(downstream_workflows)
        if wf_count > 0:
            lines.append(f"**下游工作流**: {wf_count} 个")
            for wf_code in downstream_workflows[:5]:
                wf_name = workflow_names.get(wf_code, wf_code)
                lines.append(f"- {wf_code} ({wf_name})")
            if wf_count > 5:
                lines.append(f"... 以及另外 {wf_count - 5} 个")
        else:
            lines.append("**下游工作流**: 无")
        
        # 下游任务
        task_count = len(downstream_tasks)
        if task_count > 0:
            lines.append("")
            lines.append(f"**下游任务**: {task_count} 个")
            for task in downstream_tasks[:5]:
                lines.append(f"- {task}")
        
        return "\n".join(lines)
    
    def _calculate_impact_level(self, downstream_count: int) -> str:
        """
        根据下游数量计算影响等级
        
        Args:
            downstream_count: 下游数量
            
        Returns:
            "low" | "medium" | "high"
        """
        if downstream_count == 0:
            return "low"
        elif downstream_count <= 5:
            return "medium"
        else:
            return "high"


__all__ = ["GraphImpactTool"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_graph_impact.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/graph_impact.py tests/test_tools/test_graph_impact.py && git commit -m "feat: 添加 GraphImpactTool 图谱影响分析工具"
```

---

## Task 2: 改造 Alert Agent 影响分析

**Files:**
- Modify: `src/agent/alert_agent.py:188-209`

- [ ] **Step 1: 添加 GraphImpactTool 导入**

在 `src/agent/alert_agent.py` 文件顶部添加导入：

```python
from ..tools.graph_impact import GraphImpactTool
```

修改位置：在第 21 行后添加

- [ ] **Step 2: 在 __init__ 方法中初始化 GraphImpactTool**

修改 `__init__` 方法：

```python
def __init__(self):
    self.ds_cli = DSCLIClient()
    self.llm = self._create_llm()
    self.notifier = DingTalkNotifier()
    self.approval_workflow = ApprovalWorkflow()
    self.graph_impact = GraphImpactTool()  # 新增
```

- [ ] **Step 3: 改造 _analyze_impact 方法**

替换 `_analyze_impact` 方法（第 188-209 行）：

```python
def _analyze_impact(self, alert_info: AlertInfo) -> dict:
    """分析下游影响 - 使用本地图谱"""
    project_code = str(alert_info.project_code)
    workflow_code = str(alert_info.process_definition_code)
    
    # 优先使用本地图谱
    impact_result = self.graph_impact.analyze_workflow_downstream(
        project_code=project_code,
        workflow_code=workflow_code,
    )
    
    # 如果图谱可用，返回图谱结果
    if impact_result["graph_available"]:
        return {
            "downstream_workflows": impact_result["downstream_count"],
            "downstream_list": impact_result["downstream_workflows"],
            "workflow_names": impact_result.get("downstream_workflow_names", {}),
            "impact_level": impact_result["impact_level"],
            "source": "graph",
        }
    
    # 降级：图谱不存在，尝试获取任务详情
    if alert_info.process_instance_id:
        tasks_result = self.ds_cli.task_instance_list(
            alert_info.process_instance_id,
        )
        if tasks_result.success and tasks_result.data:
            task_list = tasks_result.data.get('items', [])
            for task in task_list:
                if task.get('taskCode') == alert_info.task_code:
                    end_time = task.get('endTime', '')
                    if end_time and alert_info.raw_payload:
                        alert_info.raw_payload['taskEndTime'] = end_time
                    break
    
    # 返回降级结果
    return {
        "downstream_workflows": 0,
        "downstream_list": [],
        "impact_level": "unknown",
        "message": impact_result.get("message", "图谱未扫描，无法评估影响"),
        "source": "fallback",
    }
```

- [ ] **Step 4: 验证修改**

Run: `cd D:/Project/dolphinscheduler-agent && python -c "from src.agent.alert_agent import AlertAgent; agent = AlertAgent(); print('AlertAgent initialized successfully')"`
Expected: 无报错

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/agent/alert_agent.py && git commit -m "feat: 改造 AlertAgent 使用本地图谱进行影响分析"
```

---

## Task 3: 改造 Risk Node 影响分析

**Files:**
- Modify: `src/workflow/nodes/risk.py:28-52`

- [ ] **Step 1: 添加导入**

在 `src/workflow/nodes/risk.py` 文件顶部添加：

```python
from ...tools.graph_impact import GraphImpactTool
```

修改位置：在第 8 行后添加

- [ ] **Step 2: 改造 impact_analysis 函数**

替换 `impact_analysis` 函数（第 28-52 行）：

```python
def impact_analysis(state: AgentState) -> AgentState:
    """分析下游影响 - 使用本地图谱"""
    graph_impact = GraphImpactTool()
    
    project_code = state.get("project_code", "")
    workflow_code = state.get("workflow_code", "")
    task_code = state.get("task_code", "")
    
    # 优先使用本地图谱分析工作流下游
    if project_code and workflow_code:
        impact_result = graph_impact.analyze_workflow_downstream(
            project_code=project_code,
            workflow_code=workflow_code,
        )
        
        if impact_result["graph_available"]:
            return {
                **state,
                "downstream_tasks": impact_result["downstream_count"],
                "downstream_list": impact_result["downstream_workflows"],
                "impact_summary": graph_impact.build_impact_summary(
                    workflow_code=workflow_code,
                    downstream_workflows=impact_result["downstream_workflows"],
                    downstream_tasks=[],
                    workflow_names=impact_result.get("downstream_workflow_names", {}),
                ),
            }
    
    # 降级：使用原有 ImpactTool
    impact_tool = ImpactTool()
    task_relations = state.get("task_relations", None)
    
    if task_relations is None:
        return {
            **state,
            "downstream_tasks": 0,
            "downstream_list": [],
            "impact_summary": "图谱未扫描，无法分析下游影响",
        }
    
    impact = impact_tool.analyze_downstream(task_relations, task_code)
    return {
        **state,
        "downstream_tasks": impact["downstream_tasks"],
        "downstream_list": impact["downstream_list"],
        "impact_summary": impact["impact_summary"],
    }
```

- [ ] **Step 3: 验证修改**

Run: `cd D:/Project/dolphinscheduler-agent && python -c "from src.workflow.nodes.risk import impact_analysis; print('risk node imported successfully')"`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/risk.py && git commit -m "feat: 改造 risk node 使用本地图谱进行影响分析"
```

---

## Task 4: 集成测试 - 告警处理流程

**Files:**
- Create: `tests/test_integration/test_alert_with_graph.py`

- [ ] **Step 1: 创建集成测试文件**

```python
"""
告警处理流程集成测试 - 使用本地图谱
"""

import pytest
import tempfile
from unittest.mock import Mock, patch

from src.agent.alert_agent import AlertAgent
from src.graph.storage import GraphStorage
from src.graph.models import Graph
from src.graph.indexer import GraphIndexer


class TestAlertAgentWithGraph:

    def test_alert_with_graph_available(self):
        """测试图谱可用时的告警处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 准备图谱数据
            storage = GraphStorage(data_dir=tmpdir)
            graph = Graph(
                project_code="12345",
                project_name="test_project",
                scanned_at="2026-05-08T10:00:00",
                version=1
            )
            graph.nodes.workflows = [
                {"code": "100", "name": "daily_etl"},
                {"code": "200", "name": "daily_summary"},
                {"code": "300", "name": "daily_report"},
            ]
            graph.edges.workflow_depends_workflow = [
                {"from": "100", "to": "200"},
                {"from": "200", "to": "300"},
            ]
            storage.save_graph("12345", graph.to_dict())
            
            indexer = GraphIndexer(storage=storage)
            indexer.generate_all_indexes("12345")
            
            # 模拟告警数据
            alert_payload = {
                "projectCode": 12345,
                "processDefinitionCode": 100,
                "taskCode": "t1",
                "taskType": "SPARK",
                "taskState": "FAILURE",
                "processId": 1,
                "taskInstanceId": 1,
                "projectName": "test_project",
                "processName": "daily_etl",
                "taskName": "spark_task",
            }
            
            # Mock DSCLIClient 和 DingTalkNotifier
            with patch("src.agent.alert_agent.DSCLIClient") as mock_cli:
                with patch("src.agent.alert_agent.DingTalkNotifier") as mock_notifier:
                    mock_cli_instance = Mock()
                    mock_cli_instance.task_log.return_value = Mock(success=True, output="Error: OOM")
                    mock_cli_instance.task_instance_list.return_value = Mock(
                        success=True,
                        data={"items": [{"taskCode": "t1", "endTime": "2026-05-08T10:00:00"}]}
                    )
                    mock_cli.return_value = mock_cli_instance
                    
                    mock_notifier_instance = Mock()
                    mock_notifier.return_value = mock_notifier_instance
                    
                    # 创建 AlertAgent 并处理告警
                    agent = AlertAgent()
                    agent.graph_impact = GraphImpactTool(storage=storage)
                    
                    # 直接测试 _analyze_impact
                    from src.models import AlertInfo
                    alert_info = AlertInfo(
                        project_code=12345,
                        process_definition_code=100,
                        task_code="t1",
                        task_instance_id=1,
                        task_type="SPARK",
                        state="FAILURE",
                        raw_payload=alert_payload,
                    )
                    
                    impact_result = agent._analyze_impact(alert_info)
                    
                    assert impact_result["source"] == "graph"
                    assert impact_result["downstream_workflows"] == 2
                    assert "200" in impact_result["downstream_list"]

    def test_alert_without_graph(self):
        """测试图谱不存在时的降级处理"""
        alert_payload = {
            "projectCode": 99999,
            "processDefinitionCode": 100,
            "taskCode": "t1",
            "taskType": "SPARK",
            "taskState": "FAILURE",
            "processId": 1,
            "taskInstanceId": 1,
        }
        
        with patch("src.agent.alert_agent.DSCLIClient") as mock_cli:
            with patch("src.agent.alert_agent.DingTalkNotifier") as mock_notifier:
                mock_cli_instance = Mock()
                mock_cli_instance.task_log.return_value = Mock(success=True, output="Error")
                mock_cli_instance.task_instance_list.return_value = Mock(success=True, data={"items": []})
                mock_cli.return_value = mock_cli_instance
                
                agent = AlertAgent()
                
                from src.models import AlertInfo
                alert_info = AlertInfo(
                    project_code=99999,
                    process_definition_code=100,
                    task_code="t1",
                    task_instance_id=1,
                    task_type="SPARK",
                    state="FAILURE",
                    raw_payload=alert_payload,
                )
                
                impact_result = agent._analyze_impact(alert_info)
                
                assert impact_result["source"] == "fallback"
                assert "图谱未扫描" in impact_result.get("message", "") or impact_result["impact_level"] == "unknown"
```

- [ ] **Step 2: 运行集成测试**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_integration/test_alert_with_graph.py -v`
Expected: 2 tests PASS

- [ ] **Step 3: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add tests/test_integration/test_alert_with_graph.py && git commit -m "test: 添加告警处理流程集成测试"
```

---

## Task 5: 更新配置文件

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: 添加图谱相关配置**

在 `config/settings.py` 中添加：

```python
# 图谱配置
CODE_ROOT_PATH: str = ""  # 代码仓库根路径
GRAPH_STORAGE_PATH: str = "data/graph"  # 图谱存储路径
```

- [ ] **Step 2: 验证配置**

Run: `cd D:/Project/dolphinscheduler-agent && python -c "from config.settings import settings; print(settings.GRAPH_STORAGE_PATH)"`

- [ ] **Step 3: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add config/settings.py && git commit -m "feat: 添加图谱相关配置项"
```

---

## 实现说明

### 改造策略

1. **优先图谱查询**: `impact_analysis` 和 `_analyze_impact` 优先查询本地图谱
2. **降级处理**: 图谱不存在时返回提示信息，不阻断告警流程
3. **保留原有逻辑**: ImpactTool 保留作为降级备选

### 影响分析结果字段

| 字段 | 说明 |
|------|------|
| graph_available | 图谱是否可用 |
| downstream_workflows | 下游工作流数量 |
| downstream_list | 下游工作流代码列表 |
| workflow_names | 工作流代码→名称映射 |
| impact_level | low/medium/high/unknown |
| source | graph/fallback |

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_graph_impact.py tests/test_integration/test_alert_with_graph.py -v
```

### 完成标志

系统集成完成后:
- 告警触发时不再实时调用 DS API 获取依赖关系
- 优先查询本地图谱，响应更快
- 图谱不存在时降级处理，返回提示信息
- 用户可通过 Chat Module 扫描图谱

### 下一步

系统集成完成后:
1. 执行所有实现计划（Knowledge Graph + Chat Module + System Integration）
2. 部署测试
3. 文档更新