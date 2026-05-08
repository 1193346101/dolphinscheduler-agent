# Chat Module Phase 1-2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现对话模块：意图解析、钉钉交互、图谱查询集成、响应格式化

**Architecture:** LangGraph 流程：用户消息 → parse_intent → route → execute(query_lineage/scan_graph) → format_response → 钉钉回复。复用 GraphQuerier 进行图谱查询。

**Tech Stack:** LangGraph, LangChain, FastAPI, DingTalk API

---

## 文件结构

**新建文件：**
```
src/chat/
├── __init__.py
├── state.py               # 对话状态定义
├── graph.py               # LangGraph 流程定义
├── nodes/
│   ├── __init__.py
│   ├── parse_intent.py    # 意图解析节点
│   ├── scan_graph.py      # 图谱扫描节点
│   ├── query_lineage.py   # 图谱查询节点
│   ├── format_response.py # 响应格式化节点
├── tools/
│   ├── __init__.py
│   ├── intent_parser.py   # 意图解析工具
│   ├── dingtalk_notifier.py # 钉钉通知发送
├── api/
│   ├── __init__.py
│   └── dingtalk_webhook.py # 钉钉消息接收 API

tests/test_chat/
├── __init__.py
├── test_intent_parser.py
├── test_parse_intent.py
├── test_query_lineage.py
├── test_format_response.py
├── test_dingtalk_webhook.py
```

---

## Task 1: Intent Parser - 意图解析工具

**Files:**
- Create: `src/chat/__init__.py`
- Create: `src/chat/tools/__init__.py`
- Create: `src/chat/tools/intent_parser.py`
- Create: `tests/test_chat/__init__.py`
- Create: `tests/test_chat/test_intent_parser.py`

- [ ] **Step 1: 创建模块目录**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/src/chat/nodes
mkdir -p D:/Project/dolphinscheduler-agent/src/chat/tools
mkdir -p D:/Project/dolphinscheduler-agent/src/chat/api
mkdir -p D:/Project/dolphinscheduler-agent/tests/test_chat
```

- [ ] **Step 2: 创建 __init__.py 文件**

`src/chat/__init__.py`:
```python
"""
Chat Module - 对话交互服务

提供:
- 意图解析
- 图谱查询
- 钉钉交互
"""

__all__ = []
```

`src/chat/tools/__init__.py`:
```python
"""Chat tools"""
from .intent_parser import IntentParser

__all__ = ["IntentParser"]
```

`tests/test_chat/__init__.py`:
```python
"""Chat module tests"""
```

- [ ] **Step 3: 创建测试文件 test_intent_parser.py**

```python
"""
Intent Parser 测试
"""

import pytest
from src.chat.tools.intent_parser import IntentParser


class TestIntentParser:

    def test_parse_scan_graph_intent(self):
        """测试解析扫描图谱意图"""
        parser = IntentParser()
        
        result = parser.parse("扫描项目 data_platform 图谱")
        
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "data_platform"

    def test_parse_lineage_query_intent(self):
        """测试解析血缘查询意图"""
        parser = IntentParser()
        
        result = parser.parse("工作流 123 的下游有哪些")
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "123"

    def test_parse_table_consumer_intent(self):
        """测试解析表消费查询意图"""
        parser = IntentParser()
        
        result = parser.parse("表 hive.db.target_table 被谁消费")
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_consumer"
        assert result["table_name"] == "hive.db.target_table"

    def test_parse_workflow_nodes_intent(self):
        """测试解析工作流节点查询意图"""
        parser = IntentParser()
        
        result = parser.parse("工作流 456 有哪些节点")
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "workflow_nodes"
        assert result["workflow_code"] == "456"

    def test_parse_upstream_intent(self):
        """测试解析上游查询意图"""
        parser = IntentParser()
        
        result = parser.parse("工作流 789 的上游依赖")
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "upstream"
        assert result["workflow_code"] == "789"

    def test_parse_unknown_intent(self):
        """测试未知意图"""
        parser = IntentParser()
        
        result = parser.parse("今天天气怎么样")
        
        assert result["intent_type"] == "unknown"
```

- [ ] **Step 4: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_intent_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 5: 实现 intent_parser.py**

```python
"""
Intent Parser - 意图解析工具

解析用户消息，提取意图类型和参数
"""

import re
from typing import Dict, Optional


class IntentParser:
    """
    意图解析器
    
    支持意图:
    - scan_graph: 扫描项目图谱
    - lineage_query: 血缘查询 (downstream/upstream/table_consumer/workflow_nodes)
    - visualize_lineage: 影响链路可视化
    - help: 使用帮助
    - unknown: 无法识别
    """
    
    # 正则表达式模式
    SCAN_GRAPH_PATTERN = r'扫描项目\s+(\S+)\s*图谱|更新\s+(\S+)\s*图谱'
    
    WORKFLOW_DOWNSTREAM_PATTERN = r'工作流\s+(\S+)\s*的下游|工作流\s+(\S+)\s+下游'
    WORKFLOW_UPSTREAM_PATTERN = r'工作流\s+(\S+)\s*的上游|工作流\s+(\S+)\s+上游依赖'
    WORKFLOW_NODES_PATTERN = r'工作流\s+(\S+)\s*有哪些节点|工作流\s+(\S+)\s*的节点'
    
    TABLE_CONSUMER_PATTERN = r'表\s+(\S+)\s*被谁消费|表\s+(\S+)\s+的消费'
    TABLE_PRODUCER_PATTERN = r'表\s+(\S+)\s*被谁产出|表\s+(\S+)\s+的生产'
    
    VISUALIZE_PATTERN = r'展示\s+(\S+)\s*的影响链路|可视化\s+(\S+)\s+的下游'
    
    def parse(self, message: str) -> Dict:
        """
        解析用户消息
        
        Args:
            message: 用户消息
            
        Returns:
            {
                "intent_type": str,
                "query_type": str (optional),
                "project_name": str (optional),
                "workflow_code": str (optional),
                "table_name": str (optional)
            }
        """
        message = message.strip()
        
        # 1. 扫描图谱意图
        result = self._parse_scan_graph(message)
        if result:
            return result
        
        # 2. 可视化意图
        result = self._parse_visualize(message)
        if result:
            return result
        
        # 3. 血缘查询意图
        result = self._parse_lineage_query(message)
        if result:
            return result
        
        # 4. 帮助意图
        if "帮助" in message or "help" in message.lower():
            return {"intent_type": "help"}
        
        # 5. 未知意图
        return {"intent_type": "unknown"}
    
    def _parse_scan_graph(self, message: str) -> Optional[Dict]:
        """解析扫描图谱意图"""
        match = re.search(self.SCAN_GRAPH_PATTERN, message)
        if match:
            project_name = match.group(1) or match.group(2)
            return {
                "intent_type": "scan_graph",
                "project_name": project_name
            }
        return None
    
    def _parse_visualize(self, message: str) -> Optional[Dict]:
        """解析可视化意图"""
        match = re.search(self.VISUALIZE_PATTERN, message)
        if match:
            workflow_code = match.group(1)
            return {
                "intent_type": "visualize_lineage",
                "workflow_code": workflow_code
            }
        return None
    
    def _parse_lineage_query(self, message: str) -> Optional[Dict]:
        """解析血缘查询意图"""
        # 工作流下游
        match = re.search(self.WORKFLOW_DOWNSTREAM_PATTERN, message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "downstream",
                "workflow_code": workflow_code
            }
        
        # 工作流上游
        match = re.search(self.WORKFLOW_UPSTREAM_PATTERN, message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "upstream",
                "workflow_code": workflow_code
            }
        
        # 工作流节点
        match = re.search(self.WORKFLOW_NODES_PATTERN, message)
        if match:
            workflow_code = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "workflow_nodes",
                "workflow_code": workflow_code
            }
        
        # 表消费
        match = re.search(self.TABLE_CONSUMER_PATTERN, message)
        if match:
            table_name = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "table_consumer",
                "table_name": table_name
            }
        
        # 表产出
        match = re.search(self.TABLE_PRODUCER_PATTERN, message)
        if match:
            table_name = match.group(1) or match.group(2)
            return {
                "intent_type": "lineage_query",
                "query_type": "table_producer",
                "table_name": table_name
            }
        
        return None


__all__ = ["IntentParser"]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_intent_parser.py -v`
Expected: 6 tests PASS

- [ ] **Step 7: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/ tests/test_chat/ && git commit -m "feat: 添加 IntentParser 意图解析工具"
```

---

## Task 2: Chat State - 对话状态定义

**Files:**
- Create: `src/chat/state.py`
- Create: `tests/test_chat/test_state.py`

- [ ] **Step 1: 创建测试文件 test_state.py**

```python
"""
Chat State 测试
"""

import pytest
from src.chat.state import ChatState, create_chat_state


class TestChatState:

    def test_create_chat_state(self):
        """测试创建对话状态"""
        state = create_chat_state(
            message="工作流 123 的下游",
            user_id="user_001",
            conversation_id="conv_001"
        )
        
        assert state["message"] == "工作流 123 的下游"
        assert state["user_id"] == "user_001"
        assert state["intent_type"] == ""

    def test_chat_state_fields(self):
        """测试对话状态字段"""
        state = ChatState(
            message="test",
            user_id="u1",
            conversation_id="c1",
            intent_type="lineage_query",
            query_type="downstream",
            workflow_code="123",
            project_code="456",
            project_name="test",
            result_data={},
            response_content="",
            error_message=None
        )
        
        assert state["intent_type"] == "lineage_query"
        assert state["query_type"] == "downstream"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 state.py**

```python
"""
Chat State - 对话状态定义

使用 TypedDict 定义对话流程状态
"""

from typing import TypedDict, Optional, Dict, Any, List


class ChatState(TypedDict, total=False):
    """
    对话状态
    
    字段说明:
    - message: 用户原始消息
    - user_id: 用户 ID
    - conversation_id: 会话 ID
    - intent_type: 意图类型 (scan_graph, lineage_query, visualize_lineage, help, unknown)
    - query_type: 查询类型 (downstream, upstream, table_consumer, workflow_nodes)
    - workflow_code: 工作流代码
    - task_code: 任务代码
    - table_name: 表名
    - project_code: 项目代码
    - project_name: 项目名称
    - result_data: 查询结果数据
    - response_content: 格式化后的响应内容
    - error_message: 错误信息
    """
    message: str
    user_id: str
    conversation_id: str
    intent_type: str
    query_type: str
    workflow_code: str
    task_code: str
    table_name: str
    project_code: str
    project_name: str
    result_data: Dict[str, Any]
    response_content: str
    error_message: Optional[str]


def create_chat_state(
    message: str,
    user_id: str = "",
    conversation_id: str = ""
) -> ChatState:
    """
    创建初始对话状态
    
    Args:
        message: 用户消息
        user_id: 用户 ID
        conversation_id: 会话 ID
        
    Returns:
        初始对话状态
    """
    return ChatState(
        message=message,
        user_id=user_id,
        conversation_id=conversation_id,
        intent_type="",
        query_type="",
        workflow_code="",
        task_code="",
        table_name="",
        project_code="",
        project_name="",
        result_data={},
        response_content="",
        error_message=None
    )


__all__ = ["ChatState", "create_chat_state"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_state.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/state.py tests/test_chat/test_state.py && git commit -m "feat: 添加 ChatState 对话状态定义"
```

---

## Task 3: Parse Intent Node - 意图解析节点

**Files:**
- Create: `src/chat/nodes/__init__.py`
- Create: `src/chat/nodes/parse_intent.py`
- Create: `tests/test_chat/test_parse_intent.py`

- [ ] **Step 1: 创建 __init__.py**

`src/chat/nodes/__init__.py`:
```python
"""Chat nodes"""
from .parse_intent import parse_intent_node

__all__ = ["parse_intent_node"]
```

- [ ] **Step 2: 创建测试文件 test_parse_intent.py**

```python
"""
Parse Intent Node 测试
"""

import pytest
from src.chat.state import create_chat_state
from src.chat.nodes.parse_intent import parse_intent_node


class TestParseIntentNode:

    def test_parse_scan_graph(self):
        """测试解析扫描图谱"""
        state = create_chat_state(message="扫描项目 data_platform 图谱")
        
        result = parse_intent_node(state)
        
        assert result["intent_type"] == "scan_graph"
        assert result["project_name"] == "data_platform"

    def test_parse_lineage_query_downstream(self):
        """测试解析下游查询"""
        state = create_chat_state(message="工作流 123 的下游有哪些")
        
        result = parse_intent_node(state)
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "downstream"
        assert result["workflow_code"] == "123"

    def test_parse_table_consumer(self):
        """测试解析表消费查询"""
        state = create_chat_state(message="表 hive.db.target 被谁消费")
        
        result = parse_intent_node(state)
        
        assert result["intent_type"] == "lineage_query"
        assert result["query_type"] == "table_consumer"
        assert result["table_name"] == "hive.db.target"

    def test_parse_unknown(self):
        """测试未知意图"""
        state = create_chat_state(message="随便说点什么")
        
        result = parse_intent_node(state)
        
        assert result["intent_type"] == "unknown"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_parse_intent.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 parse_intent.py**

```python
"""
Parse Intent Node - 意图解析节点

解析用户消息，提取意图和参数
"""

from ..state import ChatState
from ..tools.intent_parser import IntentParser


def parse_intent_node(state: ChatState) -> ChatState:
    """
    意图解析节点
    
    Args:
        state: 当前对话状态
        
    Returns:
        更新后的状态 (intent_type, query_type, workflow_code, table_name, project_name)
    """
    message = state.get("message", "")
    
    parser = IntentParser()
    parsed = parser.parse(message)
    
    return {
        **state,
        "intent_type": parsed.get("intent_type", "unknown"),
        "query_type": parsed.get("query_type", ""),
        "workflow_code": parsed.get("workflow_code", ""),
        "table_name": parsed.get("table_name", ""),
        "project_name": parsed.get("project_name", ""),
    }


__all__ = ["parse_intent_node"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_parse_intent.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/nodes/ tests/test_chat/test_parse_intent.py && git commit -m "feat: 添加 parse_intent_node 意图解析节点"
```

---

## Task 4: Query Lineage Node - 图谱查询节点

**Files:**
- Create: `src/chat/nodes/query_lineage.py`
- Create: `tests/test_chat/test_query_lineage.py`

- [ ] **Step 1: 创建测试文件 test_query_lineage.py**

```python
"""
Query Lineage Node 测试
"""

import pytest
import tempfile
from unittest.mock import Mock, patch
from src.chat.state import create_chat_state
from src.chat.nodes.query_lineage import query_lineage_node


class TestQueryLineageNode:

    def test_query_downstream(self):
        """测试查询下游"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.graph.storage import GraphStorage
            from src.graph.models import Graph, WorkflowNode
            from src.graph.indexer import GraphIndexer
            
            storage = GraphStorage(data_dir=tmpdir)
            
            # 构建模拟图谱
            graph = Graph(project_code="123", project_name="test", scanned_at="", version=1)
            graph.edges.workflow_depends_workflow = [{"from": "456", "to": "789"}]
            storage.save_graph("123", graph.to_dict())
            
            indexer = GraphIndexer(storage=storage)
            indexer.generate_all_indexes("123")
            
            state = create_chat_state(message="工作流 456 的下游")
            state["intent_type"] = "lineage_query"
            state["query_type"] = "downstream"
            state["workflow_code"] = "456"
            state["project_code"] = "123"
            
            with patch("src.chat.nodes.query_lineage.GraphStorage", return_value=storage):
                with patch("src.chat.nodes.query_lineage.GraphQuerier") as mock_querier:
                    mock_querier_instance = Mock()
                    mock_querier_instance.query_workflow_downstream.return_value = {
                        "found": True,
                        "direct": ["789"],
                        "all": ["789"],
                        "count": 1
                    }
                    mock_querier.return_value = mock_querier_instance
                    
                    result = query_lineage_node(state)
                    
                    assert result["intent_type"] == "lineage_query"
                    assert result["result_data"]["found"] is True

    def test_query_table_consumer(self):
        """测试查询表消费"""
        state = create_chat_state(message="表 hive.db.source 被谁消费")
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_consumer"
        state["table_name"] = "hive.db.source"
        state["project_code"] = "123"
        
        with patch("src.chat.nodes.query_lineage.GraphQuerier") as mock_querier:
            mock_instance = Mock()
            mock_instance.query_table_consumers.return_value = {
                "found": True,
                "workflows": ["456"],
                "tasks": ["789"],
                "classes": []
            }
            mock_querier.return_value = mock_instance
            
            result = query_lineage_node(state)
            
            assert result["result_data"]["found"] is True

    def test_query_no_graph(self):
        """测试图谱不存在"""
        state = create_chat_state(message="工作流 456 的下游")
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "456"
        state["project_code"] = "nonexistent"
        
        with patch("src.chat.nodes.query_lineage.GraphQuerier") as mock_querier:
            mock_instance = Mock()
            mock_instance.query_workflow_downstream.return_value = {
                "found": False,
                "message": "图谱未扫描"
            }
            mock_querier.return_value = mock_instance
            
            result = query_lineage_node(state)
            
            assert result["error_message"] == "图谱未扫描"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_query_lineage.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 query_lineage.py**

```python
"""
Query Lineage Node - 图谱查询节点

调用 GraphQuerier 执行图谱查询
"""

from ..state import ChatState
from ...graph.storage import GraphStorage
from ...graph.querier import GraphQuerier


def query_lineage_node(state: ChatState) -> ChatState:
    """
    图谱查询节点
    
    根据 query_type 调用不同的查询方法:
    - downstream: query_workflow_downstream
    - upstream: query_workflow_upstream
    - workflow_nodes: query_workflow_nodes
    - table_consumer: query_table_consumers
    - table_producer: query_table_producers
    
    Args:
        state: 当前对话状态
        
    Returns:
        更新后的状态 (result_data, error_message)
    """
    query_type = state.get("query_type", "")
    project_code = state.get("project_code", "")
    
    if not project_code:
        return {
            **state,
            "error_message": "缺少项目代码"
        }
    
    # 初始化 Querier
    storage = GraphStorage()
    querier = GraphQuerier(storage)
    
    result_data = {}
    error_message = None
    
    try:
        if query_type == "downstream":
            workflow_code = state.get("workflow_code", "")
            result_data = querier.query_workflow_downstream(project_code, workflow_code)
        
        elif query_type == "upstream":
            workflow_code = state.get("workflow_code", "")
            result_data = querier.query_workflow_upstream(project_code, workflow_code)
        
        elif query_type == "workflow_nodes":
            workflow_code = state.get("workflow_code", "")
            result_data = querier.query_workflow_nodes(project_code, workflow_code)
        
        elif query_type == "table_consumer":
            table_name = state.get("table_name", "")
            result_data = querier.query_table_consumers(project_code, table_name)
        
        elif query_type == "table_producer":
            table_name = state.get("table_name", "")
            result_data = querier.query_table_producers(project_code, table_name)
        
        else:
            error_message = f"未知的查询类型: {query_type}"
        
        if not result_data.get("found"):
            error_message = result_data.get("message", "查询失败")
    
    except Exception as e:
        error_message = str(e)
    
    return {
        **state,
        "result_data": result_data,
        "error_message": error_message
    }


__all__ = ["query_lineage_node"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_query_lineage.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/nodes/query_lineage.py tests/test_chat/test_query_lineage.py && git commit -m "feat: 添加 query_lineage_node 图谱查询节点"
```

---

## Task 5: Format Response Node - 响应格式化节点

**Files:**
- Create: `src/chat/nodes/format_response.py`
- Create: `tests/test_chat/test_format_response.py`

- [ ] **Step 1: 创建测试文件 test_format_response.py**

```python
"""
Format Response Node 测试
"""

import pytest
from src.chat.state import create_chat_state
from src.chat.nodes.format_response import format_response_node


class TestFormatResponseNode:

    def test_format_downstream_response(self):
        """测试格式化下游响应"""
        state = create_chat_state(message="工作流 123 的下游")
        state["intent_type"] = "lineage_query"
        state["query_type"] = "downstream"
        state["workflow_code"] = "123"
        state["result_data"] = {
            "found": True,
            "direct": ["456", "789"],
            "all": ["456", "789", "111"],
            "count": 3
        }
        
        result = format_response_node(state)
        
        assert "下游依赖" in result["response_content"]
        assert "456" in result["response_content"]

    def test_format_table_consumer_response(self):
        """测试格式化表消费响应"""
        state = create_chat_state(message="表 hive.db.source 被谁消费")
        state["intent_type"] = "lineage_query"
        state["query_type"] = "table_consumer"
        state["table_name"] = "hive.db.source"
        state["result_data"] = {
            "found": True,
            "workflows": ["123"],
            "tasks": ["789", "790"],
            "classes": []
        }
        
        result = format_response_node(state)
        
        assert "hive.db.source" in result["response_content"]
        assert "789" in result["response_content"]

    def test_format_error_response(self):
        """测试格式化错误响应"""
        state = create_chat_state(message="工作流 123 的下游")
        state["intent_type"] = "lineage_query"
        state["error_message"] = "图谱未扫描"
        
        result = format_response_node(state)
        
        assert "图谱未扫描" in result["response_content"]

    def test_format_unknown_intent_response(self):
        """测试格式化未知意图响应"""
        state = create_chat_state(message="随便说说")
        state["intent_type"] = "unknown"
        
        result = format_response_node(state)
        
        assert "无法理解" in result["response_content"]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_format_response.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 format_response.py**

```python
"""
Format Response Node - 响应格式化节点

将查询结果格式化为钉钉 Markdown 消息
"""

from ..state import ChatState


def format_response_node(state: ChatState) -> ChatState:
    """
    响应格式化节点
    
    根据意图类型和查询结果生成钉钉 Markdown 响应
    
    Args:
        state: 当前对话状态
        
    Returns:
        更新后的状态 (response_content)
    """
    intent_type = state.get("intent_type", "unknown")
    error_message = state.get("error_message")
    
    # 错误响应
    if error_message:
        return {
            **state,
            "response_content": f"❌ {error_message}"
        }
    
    # 根据意图类型格式化
    if intent_type == "lineage_query":
        return format_lineage_response(state)
    
    elif intent_type == "scan_graph":
        return format_scan_response(state)
    
    elif intent_type == "help":
        return format_help_response(state)
    
    else:
        return {
            **state,
            "response_content": "❌ 无法理解您的意图，请说\"帮助\"查看可用命令"
        }


def format_lineage_response(state: ChatState) -> ChatState:
    """格式化血缘查询响应"""
    query_type = state.get("query_type", "")
    result_data = state.get("result_data", {})
    
    if query_type == "downstream":
        workflow_code = state.get("workflow_code", "")
        direct = result_data.get("direct", [])
        all_downstream = result_data.get("all", [])
        count = result_data.get("count", 0)
        
        lines = [
            f"### 工作流 {workflow_code} 下游依赖",
            "",
            f"**直接下游**: {len(direct)} 个",
        ]
        for wf in direct[:5]:
            lines.append(f"- {wf}")
        if len(direct) > 5:
            lines.append(f"... 以及另外 {len(direct) - 5} 个")
        
        lines.append("")
        lines.append(f"**全部下游**: {count} 个工作流")
        
        return {**state, "response_content": "\n".join(lines)}
    
    elif query_type == "upstream":
        workflow_code = state.get("workflow_code", "")
        upstream = result_data.get("upstream", [])
        
        lines = [
            f"### 工作流 {workflow_code} 上游依赖",
            "",
            f"**上游工作流**: {len(upstream)} 个",
        ]
        for wf in upstream[:5]:
            lines.append(f"- {wf}")
        
        return {**state, "response_content": "\n".join(lines)}
    
    elif query_type == "workflow_nodes":
        workflow_code = state.get("workflow_code", "")
        tasks = result_data.get("tasks", [])
        task_names = result_data.get("task_names", {})
        task_types = result_data.get("task_types", {})
        spark_classes = result_data.get("spark_classes", {})
        
        lines = [
            f"### 工作流 {workflow_code} 节点列表",
            "",
            f"**节点数量**: {len(tasks)} 个",
        ]
        for task in tasks[:10]:
            name = task_names.get(task, task)
            type_ = task_types.get(task, "UNKNOWN")
            spark_class = spark_classes.get(task, "")
            
            if spark_class:
                lines.append(f"- {name} ({type_}) → {spark_class}")
            else:
                lines.append(f"- {name} ({type_})")
        
        return {**state, "response_content": "\n".join(lines)}
    
    elif query_type == "table_consumer":
        table_name = state.get("table_name", "")
        workflows = result_data.get("workflows", [])
        tasks = result_data.get("tasks", [])
        
        lines = [
            f"### 表 {table_name} 消费者",
            "",
            f"**消费工作流**: {len(workflows)} 个",
        ]
        for wf in workflows[:5]:
            lines.append(f"- {wf}")
        
        lines.append("")
        lines.append(f"**消费任务**: {len(tasks)} 个")
        for task in tasks[:5]:
            lines.append(f"- {task}")
        
        return {**state, "response_content": "\n".join(lines)}
    
    elif query_type == "table_producer":
        table_name = state.get("table_name", "")
        workflows = result_data.get("workflows", [])
        tasks = result_data.get("tasks", [])
        
        lines = [
            f"### 表 {table_name} 生产者",
            "",
            f"**产出工作流**: {len(workflows)} 个",
        ]
        for wf in workflows[:5]:
            lines.append(f"- {wf}")
        
        return {**state, "response_content": "\n".join(lines)}
    
    return {
        **state,
        "response_content": "❌ 未知的查询类型"
    }


def format_scan_response(state: ChatState) -> ChatState:
    """格式化扫描响应"""
    result_data = state.get("result_data", {})
    
    workflows_count = result_data.get("workflows_count", 0)
    tasks_count = result_data.get("tasks_count", 0)
    tables_count = result_data.get("tables_count", 0)
    
    lines = [
        "### 图谱扫描完成",
        "",
        f"**工作流**: {workflows_count} 个",
        f"**任务节点**: {tasks_count} 个",
        f"**数据表**: {tables_count} 个",
    ]
    
    return {**state, "response_content": "\n".join(lines)}


def format_help_response(state: ChatState) -> ChatState:
    """格式化帮助响应"""
    lines = [
        "### 🤖 DolphinScheduler Agent 使用帮助",
        "",
        "**图谱操作**:",
        "- `扫描项目 X 图谱` - 扫描项目并构建图谱",
        "- `更新 X 图谱` - 重新扫描更新图谱",
        "",
        "**血缘查询**:",
        "- `工作流 Y 的下游` - 查询下游依赖",
        "- `工作流 Y 的上游` - 查询上游依赖",
        "- `工作流 Y 有哪些节点` - 查询节点列表",
        "- `表 T 被谁消费` - 查询表消费者",
        "- `表 T 被谁产出` - 查询表生产者",
    ]
    
    return {**state, "response_content": "\n".join(lines)}


__all__ = ["format_response_node"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_format_response.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/nodes/format_response.py tests/test_chat/test_format_response.py && git commit -m "feat: 添加 format_response_node 响应格式化节点"
```

---

## Task 6: DingTalk Webhook API - 钉钉消息接收

**Files:**
- Create: `src/chat/api/__init__.py`
- Create: `src/chat/api/dingtalk_webhook.py`
- Create: `tests/test_chat/test_dingtalk_webhook.py`

- [ ] **Step 1: 创建 __init__.py**

`src/chat/api/__init__.py`:
```python
"""Chat API"""
from .dingtalk_webhook import router

__all__ = ["router"]
```

- [ ] **Step 2: 创建测试文件 test_dingtalk_webhook.py**

```python
"""
DingTalk Webhook API 测试
"""

import pytest
from fastapi.testclient import TestClient
from src.api.webhook_api import app


class TestDingTalkWebhook:

    def test_chat_endpoint_exists(self):
        """测试 chat 端点存在"""
        client = TestClient(app)
        
        # 发送测试消息
        response = client.post("/chat", json={
            "message": "帮助",
            "user_id": "test_user"
        })
        
        # 端点应该存在（可能返回错误因为没有 LLM，但不应 404）
        assert response.status_code != 404

    def test_chat_help_message(self):
        """测试帮助消息"""
        client = TestClient(app)
        
        response = client.post("/chat", json={
            "message": "帮助",
            "user_id": "test_user"
        })
        
        # 帮助消息应该返回成功
        assert response.status_code == 200
```

- [ ] **Step 3: 运行测试**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_dingtalk_webhook.py -v`
Expected: 测试可能 FAIL 或 PASS（取决于现有 chat 端点）

- [ ] **Step 4: 实现 dingtalk_webhook.py**

```python
"""
DingTalk Webhook API - 钉钉消息接收

处理钉钉机器人发送的消息
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel

from ..state import create_chat_state
from ..nodes.parse_intent import parse_intent_node
from ..nodes.query_lineage import query_lineage_node
from ..nodes.format_response import format_response_node


router = APIRouter(prefix="/dingtalk", tags=["dingtalk"])


class DingTalkMessage(BaseModel):
    """钉钉消息模型"""
    msgtype: str
    text: Optional[dict] = None
    senderId: Optional[str] = None
    conversationId: Optional[str] = None


@router.post("/message")
async def receive_message(request: Request):
    """
    接收钉钉消息
    
    处理流程:
    1. 解析消息内容
    2. 意图识别
    3. 执行对应节点
    4. 格式化响应
    """
    try:
        payload = await request.json()
        
        # 解析钉钉消息格式
        message = DingTalkMessage(**payload)
        
        # 提取文本内容
        text_content = ""
        if message.text:
            text_content = message.text.get("content", "")
        
        if not text_content:
            return JSONResponse(content={
                "status": "error",
                "message": "消息内容为空"
            })
        
        # 创建对话状态
        state = create_chat_state(
            message=text_content,
            user_id=message.senderId or "",
            conversation_id=message.conversationId or ""
        )
        
        # 意图解析
        state = parse_intent_node(state)
        
        # 根据意图路由
        intent_type = state.get("intent_type", "unknown")
        
        if intent_type == "lineage_query":
            # 需要项目代码，从会话上下文获取或配置默认
            # 这里暂时使用空值，实际需要会话管理
            state["project_code"] = ""  # TODO: 从会话获取
            state = query_lineage_node(state)
        
        elif intent_type == "scan_graph":
            # TODO: 实现 scan_graph_node
            pass
        
        # 格式化响应
        state = format_response_node(state)
        
        # 返回钉钉格式响应
        return JSONResponse(content={
            "msgtype": "text",
            "text": {
                "content": state.get("response_content", "")
            }
        })
    
    except Exception as e:
        return JSONResponse(content={
            "status": "error",
            "message": str(e)
        })


__all__ = ["router"]
```

- [ ] **Step 5: 运行测试验证**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/test_dingtalk_webhook.py -v`

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/chat/api/ tests/test_chat/test_dingtalk_webhook.py && git commit -m "feat: 添加 DingTalk Webhook API"
```

---

## 实现说明

### 测试策略
- IntentParser 使用真实解析逻辑测试
- Query Lineage Node 使用 Mock GraphQuerier
- Format Response Node 使用真实格式化逻辑

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_chat/ -v
```

### 下一步

Chat Module Phase 1-2 完成后继续:
- 系统集成改造（告警 Agent 改用图谱查询）
- Scan Graph Node 实现
- 会话状态管理（记住用户当前项目）
- 权限控制