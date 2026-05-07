# DolphinScheduler 告警自动化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 LangGraph 状态机重构告警处理流程，实现自动化错误分析、风险评估、自动修复和审批通知。

**Architecture:** 使用 LangGraph 构建状态机，每个节点处理一个阶段：解析告警 → 验证项目 → 获取日志 → 分析错误 → 查询知识库 → 风险评估 → 审批/自动修复 → 钉钉通知 → 存储结果。Skills 使用预定义规则匹配错误，Tools 封装外部服务调用。

**Tech Stack:** LangGraph, Python 3.11, requests, kubernetes-client, pyyaml, pytest

---

## 文件结构

**新建文件：**
```
src/
├── workflow/
│   ├── __init__.py
│   ├── state.py              # AgentState TypedDict
│   ├── graph.py              # LangGraph 状态机定义
│   └── nodes/
│       ├── __init__.py
│       ├── parse.py          # parse_alert 节点
│       ├── validate.py       # validate_project 节点
│       ├── fetch_logs.py     # fetch_logs 节点
│       ├── analyze.py        # analyze_* 节点（按 Skill 分发）
│       ├── knowledge.py      # query_knowledge 节点
│       ├── risk.py           # assess_risk + impact_analysis 节点
│       ├── approval.py       # request_approval + check_approval 节点
│       ├── execute.py        # execute_action 节点
│       ├── notify.py         # notify_dingtalk 节点
│       └── store.py          # store_results 节点
├── tools/
│   ├── __init__.py
│   ├── spark_hist.py         # SparkHistTool
│   ├── yarn_log.py           # YARNLogTool
│   ├── k8s_log.py            # K8sLogTool
│   ├── dingtalk_enterprise.py # DingTalkEnterpriseTool
│   ├── log_store.py          # LogStoreTool
│   ├── approval.py           # ApprovalTool
│   ├── impact.py             # ImpactTool
│   └── risk_assess.py        # RiskAssessTool
│   └── knowledge.py          # KnowledgeTool
tests/
├── workflow/
│   ├── __init__.py
│   ├── test_state.py
│   ├── test_graph.py
│   └── test_nodes/
│       ├── __init__.py
│       ├── test_parse.py
│       ├── test_validate.py
│       ├── test_analyze.py
│       └── test_risk.py
├── tools/
│   ├── __init__.py
│   ├── test_spark_hist.py
│   ├── test_dingtalk_enterprise.py
│   ├── test_log_store.py
│   ├── test_risk_assess.py
```

**修改文件：**
- `src/skills/spark_skill.py` - 扩展错误模式和自动修复规则
- `src/skills/shell_skill.py` - 扩展错误模式
- `src/skills/python_skill.py` - 扩展错误模式
- `src/skills/datax_skill.py` - 扩展错误模式
- `src/config/projects.py` - 添加钉钉企业机器人配置字段
- `src/api/webhook_api.py` - 使用新的 workflow graph
- `requirements.txt` - 添加 langgraph, kubernetes 依赖

---

## Task 1: AgentState 状态定义

**Files:**
- Create: `src/workflow/__init__.py`
- Create: `src/workflow/state.py`
- Create: `tests/workflow/__init__.py`
- Create: `tests/workflow/test_state.py`

- [ ] **Step 1: 创建 workflow 模块目录**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/src/workflow/nodes
mkdir -p D:/Project/dolphinscheduler-agent/tests/workflow/test_nodes
```

- [ ] **Step 2: 创建 workflow/__init__.py**

```python
"""
LangGraph 状态机模块
"""

from .state import AgentState
from .graph import AlertWorkflowGraph

__all__ = ["AgentState", "AlertWorkflowGraph"]
```

- [ ] **Step 3: 编写 state.py - AgentState TypedDict**

```python
"""
AgentState - LangGraph 状态机状态定义

定义告警处理流程中每个节点的输入和输出字段
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any


class AgentState(TypedDict):
    """
    告警处理状态
    
    所有节点共享此状态，每个节点读取输入字段，写入输出字段
    """
    
    # === 输入阶段 ===
    alert_raw: Dict[str, Any]          # 原始 webhook JSON
    project_code: str                   # 提取的项目编码
    workflow_code: str                  # 提取的工作流编码
    task_code: str                      # 提取的任务编码
    task_type: Literal["SHELL", "SPARK", "PYTHON", "DATAX"]
    error_time: str                     # 告警时间戳
    
    # === 验证阶段 ===
    project_valid: bool                 # 项目 token 已验证
    project_config: Optional[Dict]      # 项目特定配置
    
    # === 日志获取阶段 ===
    driver_logs: Optional[str]          # dsctl CLI 日志
    spark_logs: Optional[str]           # Spark History Server 日志（YARN/K8s 都可用）
    yarn_logs: Optional[str]            # YARN Gateway 日志（Spark on YARN）
    k8s_logs: Optional[Dict[str, str]]  # K8s Pod 日志（Spark on K8s）
    log_fetch_error: Optional[str]      # 日志获取失败时的错误信息
    
    # === 分析阶段 ===
    error_patterns: List[str]           # Skill 匹配的错误模式
    error_category: str                 # 错误分类（RESOURCE, NETWORK, DATA, CONFIG, EXECUTION）
    suggested_actions: List[Dict]       # 建议的修复动作
    knowledge_match: Optional[Dict]     # 匹配的知识库条目
    confidence_score: float             # 分析置信度 (0-1)
    
    # === 风险评估阶段 ===
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    risk_factors: List[str]             # 影响风险的因素
    downstream_tasks: int               # 受影响的下游任务数量
    impact_summary: Optional[str]       # HIGH/CRITICAL 的影响描述
    
    # === 审批阶段 ===
    approval_required: bool             # 是否需要审批
    approval_status: Optional[Literal["pending", "approved", "rejected", "timeout"]]
    approval_message_id: Optional[str]  # 钉钉消息 ID 用于追踪
    
    # === 执行阶段 ===
    executed_actions: List[Dict]        # 已执行的动作
    execution_results: List[Dict]       # 每个动作的结果
    execution_success: bool             # 整体执行是否成功
    
    # === 通知阶段 ===
    notification_sent: bool             # 钉钉通知状态
    notification_content: Optional[str] # 通知消息内容
    
    # === 存储阶段 ===
    log_stored: bool                    # 日志已保存
    result_stored: bool                 # 分析结果已保存
    log_store_path: Optional[str]       # 日志存储路径


# 初始状态模板
INITIAL_STATE: AgentState = {
    "alert_raw": {},
    "project_code": "",
    "workflow_code": "",
    "task_code": "",
    "task_type": "SHELL",
    "error_time": "",
    
    "project_valid": False,
    "project_config": None,
    
    "driver_logs": None,
    "spark_logs": None,
    "yarn_logs": None,
    "k8s_logs": None,
    "log_fetch_error": None,
    
    "error_patterns": [],
    "error_category": "",
    "suggested_actions": [],
    "knowledge_match": None,
    "confidence_score": 0.0,
    
    "risk_level": "LOW",
    "risk_factors": [],
    "downstream_tasks": 0,
    "impact_summary": None,
    
    "approval_required": False,
    "approval_status": None,
    "approval_message_id": None,
    
    "executed_actions": [],
    "execution_results": [],
    "execution_success": False,
    
    "notification_sent": False,
    "notification_content": None,
    
    "log_stored": False,
    "result_stored": False,
    "log_store_path": None,
}


__all__ = ["AgentState", "INITIAL_STATE"]
```

- [ ] **Step 4: 创建 tests/workflow/__init__.py**

```python
"""
Workflow 模块测试
"""
```

- [ ] **Step 5: 编写 test_state.py**

```python
"""
AgentState 测试
"""

import pytest
from src.workflow.state import AgentState, INITIAL_STATE


def test_initial_state_has_all_fields():
    """测试初始状态包含所有必要字段"""
    assert "alert_raw" in INITIAL_STATE
    assert "project_code" in INITIAL_STATE
    assert "workflow_code" in INITIAL_STATE
    assert "task_code" in INITIAL_STATE
    assert "task_type" in INITIAL_STATE
    assert "project_valid" in INITIAL_STATE
    assert "driver_logs" in INITIAL_STATE
    assert "spark_logs" in INITIAL_STATE
    assert "yarn_logs" in INITIAL_STATE
    assert "k8s_logs" in INITIAL_STATE
    assert "error_patterns" in INITIAL_STATE
    assert "risk_level" in INITIAL_STATE
    assert "approval_required" in INITIAL_STATE


def test_initial_state_defaults():
    """测试初始状态默认值"""
    assert INITIAL_STATE["alert_raw"] == {}
    assert INITIAL_STATE["project_valid"] is False
    assert INITIAL_STATE["driver_logs"] is None
    assert INITIAL_STATE["error_patterns"] == []
    assert INITIAL_STATE["risk_level"] == "LOW"
    assert INITIAL_STATE["confidence_score"] == 0.0


def test_state_can_be_updated():
    """测试状态可以更新"""
    state = dict(INITIAL_STATE)
    state["project_code"] = "123456"
    state["workflow_code"] = "789012"
    state["task_type"] = "SPARK"
    state["project_valid"] = True
    
    assert state["project_code"] == "123456"
    assert state["workflow_code"] == "789012"
    assert state["task_type"] == "SPARK"
    assert state["project_valid"] is True


def test_state_task_type_literal():
    """测试 task_type 只接受预定义值"""
    valid_types = ["SHELL", "SPARK", "PYTHON", "DATAX"]
    state = dict(INITIAL_STATE)
    
    for task_type in valid_types:
        state["task_type"] = task_type
        assert state["task_type"] == task_type


def test_state_risk_level_literal():
    """测试 risk_level 只接受预定义值"""
    valid_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    state = dict(INITIAL_STATE)
    
    for level in valid_levels:
        state["risk_level"] = level
        assert state["risk_level"] == level
```

- [ ] **Step 6: 运行测试验证状态定义**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/workflow/test_state.py -v
```

Expected: 5 tests PASS

- [ ] **Step 7: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/__init__.py src/workflow/state.py tests/workflow/__init__.py tests/workflow/test_state.py && git commit -m "feat: 添加 AgentState TypedDict 状态定义"
```

---

## Task 2: parse_alert 节点

**Files:**
- Create: `src/workflow/nodes/__init__.py`
- Create: `src/workflow/nodes/parse.py`
- Create: `tests/workflow/test_nodes/__init__.py`
- Create: `tests/workflow/test_nodes/test_parse.py`

- [ ] **Step 1: 创建 nodes/__init__.py**

```python
"""
LangGraph 状态机节点
"""

from .parse import parse_alert
from .validate import validate_project
from .fetch_logs import fetch_logs
from .analyze import analyze_error
from .knowledge import query_knowledge
from .risk import assess_risk, impact_analysis
from .approval import request_approval, check_approval
from .execute import execute_action
from .notify import notify_dingtalk
from .store import store_results

__all__ = [
    "parse_alert",
    "validate_project",
    "fetch_logs",
    "analyze_error",
    "query_knowledge",
    "assess_risk",
    "impact_analysis",
    "request_approval",
    "check_approval",
    "execute_action",
    "notify_dingtalk",
    "store_results",
]
```

- [ ] **Step 2: 编写 parse.py - parse_alert 节点**

```python
"""
parse_alert 节点

从 webhook JSON 提取关键信息：project_code, workflow_code, task_code, task_type
"""

from typing import Dict, Any
from ..state import AgentState


def parse_alert(state: AgentState) -> AgentState:
    """
    解析告警数据
    
    从 alert_raw 提取:
    - project_code
    - workflow_code (process_definition_code)
    - task_code
    - task_type
    - error_time
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态
    """
    alert_raw = state["alert_raw"]
    
    # 提取项目编码
    project_code = str(alert_raw.get("projectCode", 0))
    
    # 提取工作流编码 (DS 3.2.0 使用 processDefinitionCode)
    workflow_code = str(alert_raw.get("processDefinitionCode", 0))
    
    # 提取任务编码
    task_code = str(alert_raw.get("taskCode", 0))
    
    # 提取任务类型
    task_type = alert_raw.get("taskType", "UNKNOWN").upper()
    # 规范化任务类型
    if task_type not in ["SHELL", "SPARK", "PYTHON", "DATAX"]:
        task_type = "SHELL"  # 默认
    
    # 提取错误时间
    error_time = alert_raw.get("endTime") or alert_raw.get("taskEndTime") or ""
    
    # 更新状态
    return {
        **state,
        "project_code": project_code,
        "workflow_code": workflow_code,
        "task_code": task_code,
        "task_type": task_type,
        "error_time": error_time,
    }


__all__ = ["parse_alert"]
```

- [ ] **Step 3: 创建 tests/workflow/test_nodes/__init__.py**

```python
"""
节点测试
"""
```

- [ ] **Step 4: 编写 test_parse.py**

```python
"""
parse_alert 节点测试
"""

import pytest
from src.workflow.state import INITIAL_STATE
from src.workflow.nodes.parse import parse_alert


def test_parse_alert_extract_project_code():
    """测试提取项目编码"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SPARK",
    }
    
    result = parse_alert(state)
    
    assert result["project_code"] == "11598158952448"


def test_parse_alert_extract_workflow_code():
    """测试提取工作流编码"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SPARK",
    }
    
    result = parse_alert(state)
    
    assert result["workflow_code"] == "21451302002208"


def test_parse_alert_extract_task_code():
    """测试提取任务编码"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SPARK",
    }
    
    result = parse_alert(state)
    
    assert result["task_code"] == "123456789"


def test_parse_alert_extract_task_type():
    """测试提取任务类型"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SPARK",
    }
    
    result = parse_alert(state)
    
    assert result["task_type"] == "SPARK"


def test_parse_alert_normalize_task_type():
    """测试任务类型规范化"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "spark",  # 小写
    }
    
    result = parse_alert(state)
    
    assert result["task_type"] == "SPARK"


def test_parse_alert_default_unknown_task_type():
    """测试未知任务类型默认为 SHELL"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SQL",  # 不在预定义类型中
    }
    
    result = parse_alert(state)
    
    assert result["task_type"] == "SHELL"


def test_parse_alert_extract_error_time():
    """测试提取错误时间"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {
        "projectCode": 11598158952448,
        "processDefinitionCode": 21451302002208,
        "taskCode": 123456789,
        "taskType": "SPARK",
        "endTime": "2025-05-07 14:30:00",
    }
    
    result = parse_alert(state)
    
    assert result["error_time"] == "2025-05-07 14:30:00"


def test_parse_alert_missing_fields():
    """测试缺失字段使用默认值"""
    state = dict(INITIAL_STATE)
    state["alert_raw"] = {}  # 空数据
    
    result = parse_alert(state)
    
    assert result["project_code"] == "0"
    assert result["workflow_code"] == "0"
    assert result["task_code"] == "0"
    assert result["task_type"] == "SHELL"
    assert result["error_time"] == ""
```

- [ ] **Step 5: 运行测试验证 parse 节点**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/workflow/test_nodes/test_parse.py -v
```

Expected: 8 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/__init__.py src/workflow/nodes/parse.py tests/workflow/test_nodes/__init__.py tests/workflow/test_nodes/test_parse.py && git commit -m "feat: 添加 parse_alert 节点解析告警数据"
```

---

## Task 3: validate_project 节点

**Files:**
- Create: `src/workflow/nodes/validate.py`
- Modify: `src/config/projects.py`
- Create: `tests/workflow/test_nodes/test_validate.py`

- [ ] **Step 1: 修改 projects.py 添加钉钉企业机器人配置**

查看现有 `src/config/projects.py`，添加新字段：

```python
"""
多项目配置管理

每个 DolphinScheduler 项目可以有独立的:
- API 地址和 Token
- Spark History Server 地址
- YARN ResourceManager 地址 / K8s 配置
- 钉钉企业机器人配置
"""

from dataclasses import dataclass, field
from typing import Optional, List
import yaml
import os

from ..config.settings import settings


@dataclass
class DingTalkConfig:
    """钉钉企业机器人配置"""
    
    robot_code: str                       # 机器人编码
    client_id: str                        # Client ID
    client_secret: str                    # Client Secret
    notify_users: List[str] = field(default_factory=list)  # 通知接收人（钉钉用户 ID）


@dataclass
class SparkLogConfig:
    """Spark 日志配置"""
    
    mode: str = "yarn"                    # yarn 或 k8s
    history_url: Optional[str] = None     # Spark History Server URL
    
    # YARN 配置
    yarn_gateway_url: Optional[str] = None
    yarn_auth_type: str = "basic"
    yarn_username: Optional[str] = None
    yarn_password: Optional[str] = None
    
    # K8s 配置
    k8s_api_server: Optional[str] = None
    k8s_namespace: str = "spark-apps"
    k8s_kubeconfig_path: Optional[str] = None


@dataclass
class ProjectConfig:
    """单个项目配置"""

    # 基本信息
    name: str                          # 项目名称
    code: int                          # 项目编码
    ds_api_url: str                    # DolphinScheduler API 地址
    ds_api_token: str                  # 项目 Token
    ds_version: str = "3.2.0"          # DS 版本

    # 权限配置
    allowed_users: List[str] = field(default_factory=list)    # 允许操作的用户
    admin_users: List[str] = field(default_factory=list)      # 管理员（可审批高风险操作）

    # 集成配置
    spark_log: Optional[SparkLogConfig] = None
    dingtalk: Optional[DingTalkConfig] = None

    @property
    def effective_spark_history_url(self) -> str:
        """获取有效的 Spark History URL"""
        if self.spark_log and self.spark_log.history_url:
            return self.spark_log.history_url
        return settings.SPARK_HISTORY_URL

    @property
    def effective_spark_mode(self) -> str:
        """获取 Spark 日志模式"""
        if self.spark_log:
            return self.spark_log.mode
        return "yarn"

    @property
    def effective_yarn_gateway_url(self) -> Optional[str]:
        """获取有效的 YARN Gateway URL"""
        if self.spark_log and self.spark_log.yarn_gateway_url:
            return self.spark_log.yarn_gateway_url
        return getattr(settings, "YARN_GATEWAY_URL", None)

    @property
    def effective_dingtalk_config(self) -> Optional[DingTalkConfig]:
        """获取有效的钉钉配置"""
        return self.dingtalk


class ProjectsRegistry:
    """多项目注册表"""

    def __init__(self):
        self._projects: dict[int, ProjectConfig] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        """从配置文件加载项目配置"""
        config_path = os.getenv("PROJECTS_CONFIG_PATH", "config/projects.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "projects" in data:
                    for proj_data in data["projects"]:
                        # 解析钉钉配置
                        dingtalk_data = proj_data.get("dingtalk")
                        dingtalk = None
                        if dingtalk_data:
                            dingtalk = DingTalkConfig(
                                robot_code=dingtalk_data.get("robot_code", ""),
                                client_id=dingtalk_data.get("client_id", ""),
                                client_secret=dingtalk_data.get("client_secret", ""),
                                notify_users=dingtalk_data.get("notify_users", []),
                            )
                        
                        # 解析 Spark 日志配置
                        spark_data = proj_data.get("spark_log")
                        spark_log = None
                        if spark_data:
                            spark_log = SparkLogConfig(
                                mode=spark_data.get("mode", "yarn"),
                                history_url=spark_data.get("history_url"),
                                yarn_gateway_url=spark_data.get("yarn_gateway_url"),
                                yarn_auth_type=spark_data.get("yarn_auth_type", "basic"),
                                yarn_username=spark_data.get("yarn_username"),
                                yarn_password=spark_data.get("yarn_password"),
                                k8s_api_server=spark_data.get("k8s_api_server"),
                                k8s_namespace=spark_data.get("k8s_namespace", "spark-apps"),
                                k8s_kubeconfig_path=spark_data.get("k8s_kubeconfig_path"),
                            )
                        
                        config = ProjectConfig(
                            name=proj_data.get("name", ""),
                            code=proj_data.get("code", 0),
                            ds_api_url=proj_data.get("ds_api_url", ""),
                            ds_api_token=proj_data.get("ds_api_token", ""),
                            ds_version=proj_data.get("ds_version", "3.2.0"),
                            allowed_users=proj_data.get("allowed_users", []),
                            admin_users=proj_data.get("admin_users", []),
                            spark_log=spark_log,
                            dingtalk=dingtalk,
                        )
                        self._projects[config.code] = config

    def get_by_code(self, code: int) -> Optional[ProjectConfig]:
        """根据项目编码获取配置"""
        return self._projects.get(code)

    def get_by_name(self, name: str) -> Optional[ProjectConfig]:
        """根据项目名称获取配置"""
        for config in self._projects.values():
            if config.name == name:
                return config
        return None

    def all_projects(self) -> List[ProjectConfig]:
        """获取所有项目配置"""
        return list(self._projects.values())

    def register(self, config: ProjectConfig) -> None:
        """注册新项目"""
        self._projects[config.code] = config

    def validate_token(self, project_code: int, token: str) -> bool:
        """验证项目 token"""
        config = self.get_by_code(project_code)
        if not config:
            return False
        return config.ds_api_token == token


# 全局项目注册表
projects_registry = ProjectsRegistry()


__all__ = ["ProjectConfig", "DingTalkConfig", "SparkLogConfig", "ProjectsRegistry", "projects_registry"]
```

- [ ] **Step 2: 编写 validate.py - validate_project 节点**

```python
"""
validate_project 节点

验证项目是否存在且 token 有效
"""

from typing import Dict, Any
from ..state import AgentState
from ...config.projects import projects_registry


def validate_project(state: AgentState) -> AgentState:
    """
    验证项目配置
    
    检查:
    - 项目编码是否存在
    - 返回项目配置
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (project_valid, project_config)
    """
    project_code = state["project_code"]
    
    # 尝试转换为 int
    try:
        code_int = int(project_code)
    except ValueError:
        return {
            **state,
            "project_valid": False,
            "project_config": None,
        }
    
    # 查找项目配置
    config = projects_registry.get_by_code(code_int)
    
    if config:
        # 转换为字典格式
        config_dict = {
            "name": config.name,
            "code": config.code,
            "ds_api_url": config.ds_api_url,
            "ds_api_token": config.ds_api_token,
            "ds_version": config.ds_version,
            "spark_mode": config.effective_spark_mode,
            "spark_history_url": config.effective_spark_history_url,
            "yarn_gateway_url": config.effective_yarn_gateway_url,
            "dingtalk": None,
        }
        
        if config.dingtalk:
            config_dict["dingtalk"] = {
                "robot_code": config.dingtalk.robot_code,
                "client_id": config.dingtalk.client_id,
                "client_secret": config.dingtalk.client_secret,
                "notify_users": config.dingtalk.notify_users,
            }
        
        return {
            **state,
            "project_valid": True,
            "project_config": config_dict,
        }
    
    return {
        **state,
        "project_valid": False,
        "project_config": None,
    }


__all__ = ["validate_project"]
```

- [ ] **Step 3: 编写 test_validate.py**

```python
"""
validate_project 节点测试
"""

import pytest
from src.workflow.state import INITIAL_STATE
from src.workflow.nodes.validate import validate_project
from src.config.projects import projects_registry, ProjectConfig, DingTalkConfig


def test_validate_project_valid():
    """测试有效项目"""
    # 先注册一个测试项目
    test_config = ProjectConfig(
        name="test_project",
        code=123456,
        ds_api_url="http://test:12345/dolphinscheduler",
        ds_api_token="test_token",
    )
    projects_registry.register(test_config)
    
    state = dict(INITIAL_STATE)
    state["project_code"] = "123456"
    
    result = validate_project(state)
    
    assert result["project_valid"] is True
    assert result["project_config"] is not None
    assert result["project_config"]["name"] == "test_project"


def test_validate_project_invalid_code():
    """测试无效项目编码"""
    state = dict(INITIAL_STATE)
    state["project_code"] = "999999"  # 不存在的编码
    
    result = validate_project(state)
    
    assert result["project_valid"] is False
    assert result["project_config"] is None


def test_validate_project_non_numeric_code():
    """测试非数字项目编码"""
    state = dict(INITIAL_STATE)
    state["project_code"] = "invalid"
    
    result = validate_project(state)
    
    assert result["project_valid"] is False
    assert result["project_config"] is None


def test_validate_project_with_dingtalk_config():
    """测试项目包含钉钉配置"""
    dingtalk = DingTalkConfig(
        robot_code="test_robot",
        client_id="test_client_id",
        client_secret="test_secret",
        notify_users=["user1", "user2"],
    )
    
    test_config = ProjectConfig(
        name="test_project_dingtalk",
        code=789012,
        ds_api_url="http://test:12345/dolphinscheduler",
        ds_api_token="test_token",
        dingtalk=dingtalk,
    )
    projects_registry.register(test_config)
    
    state = dict(INITIAL_STATE)
    state["project_code"] = "789012"
    
    result = validate_project(state)
    
    assert result["project_valid"] is True
    assert result["project_config"]["dingtalk"] is not None
    assert result["project_config"]["dingtalk"]["robot_code"] == "test_robot"
    assert result["project_config"]["dingtalk"]["notify_users"] == ["user1", "user2"]
```

- [ ] **Step 4: 运行测试验证 validate 节点**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/workflow/test_nodes/test_validate.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/config/projects.py src/workflow/nodes/validate.py tests/workflow/test_nodes/test_validate.py && git commit -m "feat: 添加 validate_project 节点和钉钉企业机器人配置"
```

---

## Task 4: RiskAssessTool 风险评估工具

**Files:**
- Create: `src/tools/__init__.py`
- Create: `src/tools/risk_assess.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_risk_assess.py`

- [ ] **Step 1: 创建 tools/__init__.py**

```python
"""
工具模块
"""

from .risk_assess import RiskAssessTool
from .impact import ImpactTool
from .spark_hist import SparkHistTool
from .yarn_log import YARNLogTool
from .k8s_log import K8sLogTool
from .dingtalk_enterprise import DingTalkEnterpriseTool
from .log_store import LogStoreTool
from .approval import ApprovalTool
from .knowledge import KnowledgeTool

__all__ = [
    "RiskAssessTool",
    "ImpactTool",
    "SparkHistTool",
    "YARNLogTool",
    "K8sLogTool",
    "DingTalkEnterpriseTool",
    "LogStoreTool",
    "ApprovalTool",
    "KnowledgeTool",
]
```

- [ ] **Step 2: 编写 risk_assess.py**

```python
"""
RiskAssessTool - 风险评估工具

根据操作类型和下游影响评估风险等级
"""

from typing import Dict, List


class RiskAssessTool:
    """
    风险评估工具
    
    规则:
    - LOW: 单配置变更、临时重试、无下游影响
    - MEDIUM: 多配置变更、多次重试、下游 <5
    - HIGH: 结构性变更、下游 >5、调度修改
    - CRITICAL: 删除操作、跨项目影响
    """
    
    def assess(self, suggested_actions: List[Dict], downstream_count: int) -> Dict:
        """
        评估风险等级
        
        Args:
            suggested_actions: 建议的动作列表
            downstream_count: 下游任务数量
        
        Returns:
            {
                "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
                "risk_factors": ["factor1", "factor2"],
                "approval_required": bool
            }
        """
        max_risk = "LOW"
        risk_factors = []
        
        for action in suggested_actions:
            action_risk = self._assess_action(action, downstream_count)
            risk_factors.append(f"{action.get('action_type', 'unknown')}: {action_risk}")
            
            if self._risk_level_value(action_risk) > self._risk_level_value(max_risk):
                max_risk = action_risk
        
        return {
            "risk_level": max_risk,
            "risk_factors": risk_factors,
            "approval_required": max_risk in ["HIGH", "CRITICAL"],
        }
    
    def _assess_action(self, action: Dict, downstream_count: int) -> str:
        """评估单个动作的风险"""
        action_type = action.get("action_type", "")
        
        # CRITICAL 条件
        if action_type in ["delete", "cross_project"]:
            return "CRITICAL"
        
        # HIGH 条件
        if action_type == "recover-failed" and downstream_count > 5:
            return "HIGH"
        if action_type == "config-change" and action.get("structural"):
            return "HIGH"
        
        # MEDIUM 条件
        if action_type == "config-change" and action.get("multi_param"):
            return "MEDIUM"
        if action_type == "rerun" and action.get("retry_count", 0) > 3:
            return "MEDIUM"
        if action_type == "recover-failed" and downstream_count >= 1:
            return "MEDIUM"
        
        # 默认 LOW
        return "LOW"
    
    def _risk_level_value(self, level: str) -> int:
        """将风险等级转换为数值"""
        mapping = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        return mapping.get(level, 0)


__all__ = ["RiskAssessTool"]
```

- [ ] **Step 3: 创建 tests/tools/__init__.py**

```python
"""
工具测试
"""
```

- [ ] **Step 4: 编写 test_risk_assess.py**

```python
"""
RiskAssessTool 测试
"""

import pytest
from src.tools.risk_assess import RiskAssessTool


def test_assess_low_risk_single_config():
    """测试 LOW 风险 - 单配置变更"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "config_key": "spark.executor.memory"}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False


def test_assess_low_risk_rerun_transient():
    """测试 LOW 风险 - 临时重试"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "rerun", "transient": True, "retry_count": 1}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False


def test_assess_medium_risk_multiple_config():
    """测试 MEDIUM 风险 - 多配置变更"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "multi_param": True}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "MEDIUM"
    assert result["approval_required"] is False


def test_assess_medium_risk_recover_small_downstream():
    """测试 MEDIUM 风险 - 下游少于 5 的恢复"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=3,
    )
    
    assert result["risk_level"] == "MEDIUM"
    assert result["approval_required"] is False


def test_assess_high_risk_recover_many_downstream():
    """测试 HIGH 风险 - 下游超过 5 的恢复"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "recover-failed"}],
        downstream_count=12,
    )
    
    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_high_risk_structural_change():
    """测试 HIGH 风险 - 结构性变更"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "config-change", "structural": True}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_critical_risk_delete():
    """测试 CRITICAL 风险 - 删除操作"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "delete"}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "CRITICAL"
    assert result["approval_required"] is True


def test_assess_critical_risk_cross_project():
    """测试 CRITICAL 风险 - 跨项目操作"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[{"action_type": "cross_project"}],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "CRITICAL"
    assert result["approval_required"] is True


def test_assess_multiple_actions_max_risk():
    """测试多个动作取最大风险"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[
            {"action_type": "config-change", "config_key": "spark.executor.memory"},
            {"action_type": "recover-failed"},
        ],
        downstream_count=10,
    )
    
    assert result["risk_level"] == "HIGH"
    assert result["approval_required"] is True


def test_assess_empty_actions():
    """测试空动作列表"""
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=[],
        downstream_count=0,
    )
    
    assert result["risk_level"] == "LOW"
    assert result["approval_required"] is False
```

- [ ] **Step 5: 运行测试验证 RiskAssessTool**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/tools/test_risk_assess.py -v
```

Expected: 10 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/__init__.py src/tools/risk_assess.py tests/tools/__init__.py tests/tools/test_risk_assess.py && git commit -m "feat: 添加 RiskAssessTool 风险评估工具"
```

---

## Task 5: DingTalkEnterpriseTool 钉钉企业机器人

**Files:**
- Create: `src/tools/dingtalk_enterprise.py`
- Create: `tests/tools/test_dingtalk_enterprise.py`

- [ ] **Step 1: 编写 dingtalk_enterprise.py**

```python
"""
DingTalkEnterpriseTool - 钉钉企业机器人工具

使用 Client ID + Client Secret 获取 access_token，发送消息
"""

import time
import json
import requests
from typing import Dict, List, Optional


class DingTalkError(Exception):
    """钉钉 API 错误"""
    pass


class DingTalkEnterpriseTool:
    """
    钉钉企业机器人
    
    认证流程:
    1. 使用 Client ID + Client Secret 获取 access_token
    2. 使用 access_token 调用消息发送 API
    """
    
    TOKEN_API = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    MESSAGE_API = "https://api.dingtalk.com/v1.0/robot/oToMessages"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
        self.token_expire_time: float = 0
    
    def _get_access_token(self) -> str:
        """获取企业机器人 access_token"""
        # 检查 token 是否过期，提前 5 分钟刷新
        if self.access_token and time.time() < self.token_expire_time - 300:
            return self.access_token
        
        response = requests.post(
            self.TOKEN_API,
            headers={"Content-Type": "application/json"},
            json={
                "clientId": self.client_id,
                "clientSecret": self.client_secret,
            },
            timeout=10,
        )
        
        if response.status_code != 200:
            raise DingTalkError(f"获取 access_token 失败: {response.text}")
        
        data = response.json()
        self.access_token = data.get("accessToken", "")
        expire_in = data.get("expireIn", 7200)
        self.token_expire_time = time.time() + expire_in
        
        return self.access_token
    
    def send_notification(
        self,
        robot_code: str,
        user_ids: List[str],
        title: str,
        content: str,
        buttons: Optional[List[Dict]] = None,
    ) -> str:
        """
        发送通知
        
        Args:
            robot_code: 机器人编码
            user_ids: 接收用户 ID 列表
            title: 标题
            content: Markdown 内容
            buttons: 可选按钮列表
        
        Returns:
            消息 ID
        """
        access_token = self._get_access_token()
        
        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        }
        
        # 构建消息参数
        msg_param = {
            "title": title,
            "text": content,
        }
        
        if buttons:
            msg_param["btns"] = buttons
        
        payload = {
            "robotCode": robot_code,
            "userIds": user_ids,
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(msg_param),
        }
        
        response = requests.post(
            self.MESSAGE_API,
            headers=headers,
            json=payload,
            timeout=10,
        )
        
        if response.status_code != 200:
            raise DingTalkError(f"发送消息失败: {response.text}")
        
        data = response.json()
        return data.get("processQueryKeys", "")
    
    def build_error_notification(
        self,
        task_type: str,
        workflow_code: str,
        task_code: str,
        risk_level: str,
        error_category: str,
        error_patterns: List[str],
        suggested_actions: List[Dict],
        ds_url: str,
    ) -> Dict:
        """构建错误通知内容"""
        title = f"告警分析: {task_type}"
        
        content = f"""## 错误分析结果

**工作流:** {workflow_code}
**任务:** {task_code}
**类型:** {task_type}
**风险等级:** {risk_level}

### 错误分类
{error_category}

### 匹配的错误模式
{chr(10).join(f'- {p}' for p in error_patterns[:5])}

### 建议的动作
{chr(10).join(f'- {a.get("description", a.get("action_type", "unknown"))}' for a in suggested_actions[:3])}
"""
        
        return {
            "title": title,
            "content": content,
            "single_url": f"{ds_url}/#/workflow/{workflow_code}",
        }
    
    def build_approval_request(
        self,
        task_type: str,
        workflow_code: str,
        task_code: str,
        risk_level: str,
        impact_summary: str,
        suggested_actions: List[Dict],
        risk_factors: List[str],
        approve_url: str,
        reject_url: str,
    ) -> Dict:
        """构建审批请求内容"""
        title = f"需要审批: {risk_level} 风险"
        
        content = f"""## 动作审批请求

**工作流:** {workflow_code}
**任务:** {task_code}
**类型:** {task_type}
**风险等级:** {risk_level}

### 影响摘要
{impact_summary}

### 提议的动作
{chr(10).join(f'- {a.get("description", a.get("action_type", "unknown"))}' for a in suggested_actions)}

### 风险因素
{chr(10).join(f'- {f}' for f in risk_factors)}

请批准或拒绝这些动作。
"""
        
        buttons = [
            {"title": "批准", "actionUrl": approve_url},
            {"title": "拒绝", "actionUrl": reject_url},
        ]
        
        return {
            "title": title,
            "content": content,
            "buttons": buttons,
        }


__all__ = ["DingTalkEnterpriseTool", "DingTalkError"]
```

- [ ] **Step 2: 编写 test_dingtalk_enterprise.py**

```python
"""
DingTalkEnterpriseTool 测试

注意: access_token 和消息发送需要 Mock
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.dingtalk_enterprise import DingTalkEnterpriseTool, DingTalkError


class TestDingTalkEnterpriseTool:
    
    def test_init_with_credentials(self):
        """测试初始化"""
        tool = DingTalkEnterpriseTool(
            client_id="test_client_id",
            client_secret="test_secret",
        )
        
        assert tool.client_id == "test_client_id"
        assert tool.client_secret == "test_secret"
        assert tool.access_token is None
    
    @patch("requests.post")
    def test_get_access_token_success(self, mock_post):
        """测试获取 access_token 成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessToken": "test_token_123",
            "expireIn": 7200,
        }
        mock_post.return_value = mock_response
        
        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        token = tool._get_access_token()
        
        assert token == "test_token_123"
        assert tool.access_token == "test_token_123"
    
    @patch("requests.post")
    def test_get_access_token_failure(self, mock_post):
        """测试获取 access_token 失败"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        
        with pytest.raises(DingTalkError):
            tool._get_access_token()
    
    @patch("requests.post")
    def test_send_notification_success(self, mock_post):
        """测试发送通知成功"""
        # Mock token response
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {"accessToken": "test_token", "expireIn": 7200}
        
        # Mock message response
        message_response = Mock()
        message_response.status_code = 200
        message_response.json.return_value = {"processQueryKeys": "msg_123"}
        
        mock_post.side_effect = [token_response, message_response]
        
        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        result = tool.send_notification(
            robot_code="test_robot",
            user_ids=["user1", "user2"],
            title="Test Alert",
            content="Test content",
        )
        
        assert result == "msg_123"
    
    def test_build_error_notification(self):
        """测试构建错误通知"""
        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        
        result = tool.build_error_notification(
            task_type="SPARK",
            workflow_code="123456",
            task_code="789012",
            risk_level="LOW",
            error_category="RESOURCE",
            error_patterns=["OutOfMemoryError", "Container killed"],
            suggested_actions=[{"description": "增加内存配置"}],
            ds_url="http://test:12345/dolphinscheduler",
        )
        
        assert result["title"] == "告警分析: SPARK"
        assert "OutOfMemoryError" in result["content"]
        assert "增加内存配置" in result["content"]
    
    def test_build_approval_request(self):
        """测试构建审批请求"""
        tool = DingTalkEnterpriseTool("test_id", "test_secret")
        
        result = tool.build_approval_request(
            task_type="SPARK",
            workflow_code="123456",
            task_code="789012",
            risk_level="HIGH",
            impact_summary="影响 10 个下游任务",
            suggested_actions=[{"description": "从失败恢复"}],
            risk_factors=["recover-failed: HIGH"],
            approve_url="/approval/approve",
            reject_url="/approval/reject",
        )
        
        assert result["title"] == "需要审批: HIGH 风险"
        assert "影响 10 个下游任务" in result["content"]
        assert len(result["buttons"]) == 2
        assert result["buttons"][0]["title"] == "批准"
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/tools/test_dingtalk_enterprise.py -v
```

Expected: 6 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/dingtalk_enterprise.py tests/tools/test_dingtalk_enterprise.py && git commit -m "feat: 添加 DingTalkEnterpriseTool 钉钉企业机器人工具"
```

---

## Task 6: LogStoreTool 日志存储工具

**Files:**
- Create: `src/tools/log_store.py`
- Create: `tests/tools/test_log_store.py`

- [ ] **Step 1: 编写 log_store.py**

```python
"""
LogStoreTool - 日志存储工具

存储日志到本地目录，保留 7 天，自动清理
"""

import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, Optional
import yaml


class LogStoreTool:
    """
    日志存储工具
    
    目录结构:
    logs/alerts/
    ├── 2026-05-07/
    │   ├── workflow_code/
    │   │   ├── task_code/
    │   │   │   ├── driver.log
    │   │   │   ├── spark.log
    │   │   │   ├── yarn.log (或 k8s/)
    │   │   │   └── metadata.yaml
    """
    
    DEFAULT_BASE_PATH = "logs/alerts"
    DEFAULT_RETENTION_DAYS = 7
    
    def __init__(self, base_path: str = DEFAULT_BASE_PATH, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.base_path = base_path
        self.retention_days = retention_days
    
    def store_logs(
        self,
        workflow_code: str,
        task_code: str,
        driver_logs: str,
        spark_logs: str,
        yarn_logs: Optional[str] = None,
        k8s_logs: Optional[Dict[str, str]] = None,
        spark_mode: str = "yarn",
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        存储日志
        
        Args:
            workflow_code: 工作流编码
            task_code: 任务编码
            driver_logs: Driver 日志
            spark_logs: Spark History 日志
            yarn_logs: YARN 日志 (Spark on YARN)
            k8s_logs: K8s Pod 日志 (Spark on K8s)
            spark_mode: yarn 或 k8s
            metadata: 元数据
        
        Returns:
            存储路径
        """
        date_path = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        
        store_path = os.path.join(self.base_path, date_path, workflow_code, task_code)
        os.makedirs(store_path, exist_ok=True)
        
        # 存储基础日志
        files = {
            "driver.log": driver_logs,
            "spark.log": spark_logs,
        }
        
        # 根据 Spark 模式存储不同来源日志
        if spark_mode == "yarn" and yarn_logs:
            files["yarn.log"] = yarn_logs
        elif spark_mode == "k8s" and k8s_logs:
            k8s_dir = os.path.join(store_path, "k8s")
            os.makedirs(k8s_dir, exist_ok=True)
            for pod_name, logs in k8s_logs.items():
                files[f"k8s/{pod_name}.log"] = logs
        
        # 写入文件
        for filename, content in files.items():
            file_path = os.path.join(store_path, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content if content else "")
        
        # 存储元数据
        sources = ["dsctl", "spark-history"]
        if spark_mode == "yarn":
            sources.append("yarn-gateway")
        else:
            sources.append("k8s-api")
        
        meta = metadata or {}
        meta.update({
            "workflow_code": workflow_code,
            "task_code": task_code,
            "timestamp": timestamp,
            "spark_mode": spark_mode,
            "sources": sources,
        })
        
        with open(os.path.join(store_path, "metadata.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(meta, f)
        
        return store_path
    
    def cleanup_old_logs(self) -> int:
        """
        删除超过保留期的日志
        
        Returns:
            删除的目录数量
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_path = cutoff_date.strftime("%Y-%m-%d")
        deleted_count = 0
        
        if not os.path.exists(self.base_path):
            return 0
        
        for date_dir in os.listdir(self.base_path):
            if date_dir < cutoff_path:
                dir_path = os.path.join(self.base_path, date_dir)
                if os.path.isdir(dir_path):
                    shutil.rmtree(dir_path)
                    deleted_count += 1
        
        return deleted_count
    
    def get_log_path(self, workflow_code: str, task_code: str) -> Optional[str]:
        """
        查找最新日志路径
        
        Args:
            workflow_code: 工作流编码
            task_code: 任务编码
        
        Returns:
            日志路径或 None
        """
        if not os.path.exists(self.base_path):
            return None
        
        for date_dir in sorted(os.listdir(self.base_path), reverse=True):
            potential_path = os.path.join(self.base_path, date_dir, workflow_code, task_code)
            if os.path.exists(potential_path):
                return potential_path
        
        return None
    
    def log_cleanup_result(self, deleted_count: int) -> None:
        """记录清理结果"""
        cleanup_log_path = os.path.join(self.base_path, "..", "cleanup.log")
        with open(cleanup_log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}: 删除了 {deleted_count} 个日期目录\n")


__all__ = ["LogStoreTool"]
```

- [ ] **Step 2: 编写 test_log_store.py**

```python
"""
LogStoreTool 测试
"""

import os
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from src.tools.log_store import LogStoreTool


class TestLogStoreTool:
    
    def test_store_logs_yarn_mode(self):
        """测试存储日志 - YARN 模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)
            
            result = tool.store_logs(
                workflow_code="123456",
                task_code="789012",
                driver_logs="driver log content",
                spark_logs="spark log content",
                yarn_logs="yarn log content",
                spark_mode="yarn",
            )
            
            assert os.path.exists(result)
            assert os.path.exists(os.path.join(result, "driver.log"))
            assert os.path.exists(os.path.join(result, "spark.log"))
            assert os.path.exists(os.path.join(result, "yarn.log"))
            assert os.path.exists(os.path.join(result, "metadata.yaml"))
    
    def test_store_logs_k8s_mode(self):
        """测试存储日志 - K8s 模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)
            
            result = tool.store_logs(
                workflow_code="123456",
                task_code="789012",
                driver_logs="driver log content",
                spark_logs="spark log content",
                k8s_logs={"driver_pod": "pod log", "executor_1": "executor log"},
                spark_mode="k8s",
            )
            
            assert os.path.exists(result)
            assert os.path.exists(os.path.join(result, "k8s", "driver_pod.log"))
            assert os.path.exists(os.path.join(result, "k8s", "executor_1.log"))
            assert not os.path.exists(os.path.join(result, "yarn.log"))
    
    def test_store_logs_creates_directory_structure(self):
        """测试创建目录结构"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)
            
            result = tool.store_logs(
                workflow_code="wf1",
                task_code="task1",
                driver_logs="log",
                spark_logs="log",
            )
            
            # 验证日期目录存在
            date_path = datetime.now().strftime("%Y-%m-%d")
            assert os.path.exists(os.path.join(tmpdir, date_path))
            assert os.path.exists(os.path.join(tmpdir, date_path, "wf1"))
            assert os.path.exists(os.path.join(tmpdir, date_path, "wf1", "task1"))
    
    def test_cleanup_old_logs(self):
        """测试清理过期日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir, retention_days=7)
            
            # 创建过期目录
            old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            old_path = os.path.join(tmpdir, old_date, "wf1", "task1")
            os.makedirs(old_path)
            with open(os.path.join(old_path, "driver.log"), "w") as f:
                f.write("old log")
            
            # 创建新目录
            new_date = datetime.now().strftime("%Y-%m-%d")
            new_path = os.path.join(tmpdir, new_date, "wf2", "task2")
            os.makedirs(new_path)
            with open(os.path.join(new_path, "driver.log"), "w") as f:
                f.write("new log")
            
            deleted = tool.cleanup_old_logs()
            
            assert deleted == 1
            assert not os.path.exists(os.path.join(tmpdir, old_date))
            assert os.path.exists(os.path.join(tmpdir, new_date))
    
    def test_get_log_path_returns_latest(self):
        """测试获取最新日志路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)
            
            # 创建多个日期目录
            for i in range(3):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                path = os.path.join(tmpdir, date, "wf1", "task1")
                os.makedirs(path)
                with open(os.path.join(path, "driver.log"), "w") as f:
                    f.write(f"day {i}")
            
            result = tool.get_log_path("wf1", "task1")
            
            # 返回今天的路径（最新的）
            today = datetime.now().strftime("%Y-%m-%d")
            assert result == os.path.join(tmpdir, today, "wf1", "task1")
    
    def test_get_log_path_not_found(self):
        """测试未找到日志路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = LogStoreTool(base_path=tmpdir)
            
            result = tool.get_log_path("nonexistent", "task")
            
            assert result is None
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/tools/test_log_store.py -v
```

Expected: 6 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/log_store.py tests/tools/test_log_store.py && git commit -m "feat: 添加 LogStoreTool 日志存储和清理工具"
```

---

## Task 7: assess_risk 和 impact_analysis 节点

**Files:**
- Create: `src/workflow/nodes/risk.py`
- Create: `src/tools/impact.py`
- Create: `tests/workflow/test_nodes/test_risk.py`

- [ ] **Step 1: 编写 impact.py**

```python
"""
ImpactTool - 下游影响分析工具

计算失败任务的下游依赖数量
"""

from typing import Dict, List, Set


class ImpactTool:
    """
    下游影响分析工具
    
    通过 DAG 边关系计算下游任务数量
    """
    
    def analyze_downstream(
        self,
        task_relations: List[Dict],
        task_code: str,
    ) -> Dict:
        """
        分析下游任务
        
        Args:
            task_relations: 任务关系列表 [{"preTaskCode": x, "postTaskCode": y}]
            task_code: 失败任务编码
        
        Returns:
            {
                "downstream_tasks": int,
                "downstream_list": [str],
                "impact_summary": str
            }
        """
        downstream = self._find_downstream_tasks(task_relations, task_code)
        downstream_count = len(downstream)
        
        impact_summary = self._build_impact_summary(task_code, downstream, downstream_count)
        
        return {
            "downstream_tasks": downstream_count,
            "downstream_list": downstream,
            "impact_summary": impact_summary,
        }
    
    def _find_downstream_tasks(self, task_relations: List[Dict], task_code: str) -> List[str]:
        """查找所有下游依赖任务"""
        downstream: Set[str] = set()
        to_process = [task_code]
        
        while to_process:
            current = to_process.pop()
            for rel in task_relations:
                # preTaskCode 是上游，postTaskCode 是下游
                pre_code = str(rel.get("preTaskCode", 0))
                post_code = str(rel.get("postTaskCode", 0))
                
                if pre_code == current and post_code not in downstream:
                    downstream.add(post_code)
                    to_process.append(post_code)
        
        return list(downstream)
    
    def _build_impact_summary(self, task_code: str, downstream: List[str], count: int) -> str:
        """构建影响摘要"""
        if count == 0:
            return f"任务 {task_code} 没有下游依赖"
        
        lines = [f"任务 {task_code} 影响 {count} 个下游任务:"]
        for task in downstream[:10]:
            lines.append(f"- {task}")
        
        if count > 10:
            lines.append(f"... 以及另外 {count - 10} 个")
        
        return "\n".join(lines)


__all__ = ["ImpactTool"]
```

- [ ] **Step 2: 编写 risk.py - assess_risk 和 impact_analysis 节点**

```python
"""
risk.py - 风险评估节点

包含 assess_risk 和 impact_analysis 两个节点
"""

from typing import Dict
from ..state import AgentState
from ...tools.risk_assess import RiskAssessTool
from ...tools.impact import ImpactTool
from ...integrations.ds_cli import DSCLIClient


def assess_risk(state: AgentState) -> AgentState:
    """
    评估风险等级
    
    根据 suggested_actions 和 downstream_tasks 评估风险
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (risk_level, risk_factors, approval_required)
    """
    tool = RiskAssessTool()
    
    result = tool.assess(
        suggested_actions=state.get("suggested_actions", []),
        downstream_count=state.get("downstream_tasks", 0),
    )
    
    return {
        **state,
        "risk_level": result["risk_level"],
        "risk_factors": result["risk_factors"],
        "approval_required": result["approval_required"],
    }


def impact_analysis(state: AgentState) -> AgentState:
    """
    分析下游影响
    
    获取工作流 DAG 并计算下游任务数量
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (downstream_tasks, impact_summary)
    """
    # 只对 HIGH/CRITICAL 需要详细影响分析
    # 但这里先计算，后续节点会根据 risk_level 决定是否使用
    
    impact_tool = ImpactTool()
    ds_cli = DSCLIClient()
    
    # 获取工作流定义以提取任务关系
    try:
        project_code = int(state["project_code"])
        workflow_code = int(state["workflow_code"])
        task_code = state["task_code"]
        
        dag_result = ds_cli.workflow_get(project_code, workflow_code)
        
        if dag_result.success and dag_result.data:
            task_relations = dag_result.data.get("processTaskRelationList", [])
            
            impact = impact_tool.analyze_downstream(task_relations, task_code)
            
            return {
                **state,
                "downstream_tasks": impact["downstream_tasks"],
                "impact_summary": impact["impact_summary"],
            }
    except Exception:
        pass
    
    # 默认值
    return {
        **state,
        "downstream_tasks": 0,
        "impact_summary": "无法分析下游影响",
    }


__all__ = ["assess_risk", "impact_analysis"]
```

- [ ] **Step 3: 编写 test_risk.py**

```python
"""
risk 节点测试
"""

import pytest
from src.workflow.state import INITIAL_STATE
from src.workflow.nodes.risk import assess_risk, impact_analysis
from src.tools.impact import ImpactTool


class TestAssessRisk:
    
    def test_assess_risk_low(self):
        """测试 LOW 风险评估"""
        state = dict(INITIAL_STATE)
        state["suggested_actions"] = [{"action_type": "config-change", "config_key": "memory"}]
        state["downstream_tasks"] = 0
        
        result = assess_risk(state)
        
        assert result["risk_level"] == "LOW"
        assert result["approval_required"] is False
    
    def test_assess_risk_high_with_downstream(self):
        """测试 HIGH 风险 - 下游超过 5"""
        state = dict(INITIAL_STATE)
        state["suggested_actions"] = [{"action_type": "recover-failed"}]
        state["downstream_tasks"] = 10
        
        result = assess_risk(state)
        
        assert result["risk_level"] == "HIGH"
        assert result["approval_required"] is True
    
    def test_assess_risk_critical(self):
        """测试 CRITICAL 风险"""
        state = dict(INITIAL_STATE)
        state["suggested_actions"] = [{"action_type": "delete"}]
        state["downstream_tasks"] = 0
        
        result = assess_risk(state)
        
        assert result["risk_level"] == "CRITICAL"
        assert result["approval_required"] is True


class TestImpactTool:
    
    def test_find_downstream_tasks_no_downstream(self):
        """测试无下游任务"""
        tool = ImpactTool()
        
        relations = [
            {"preTaskCode": 100, "postTaskCode": 200},
            {"preTaskCode": 200, "postTaskCode": 300},
        ]
        
        result = tool.analyze_downstream(relations, "300")
        
        assert result["downstream_tasks"] == 0
        assert result["downstream_list"] == []
    
    def test_find_downstream_tasks_single_level(self):
        """测试单层下游"""
        tool = ImpactTool()
        
        relations = [
            {"preTaskCode": 100, "postTaskCode": 200},
            {"preTaskCode": 100, "postTaskCode": 201},
        ]
        
        result = tool.analyze_downstream(relations, "100")
        
        assert result["downstream_tasks"] == 2
        assert "200" in result["downstream_list"]
        assert "201" in result["downstream_list"]
    
    def test_find_downstream_tasks_multi_level(self):
        """测试多层下游"""
        tool = ImpactTool()
        
        relations = [
            {"preTaskCode": 100, "postTaskCode": 200},
            {"preTaskCode": 200, "postTaskCode": 300},
            {"preTaskCode": 300, "postTaskCode": 400},
        ]
        
        result = tool.analyze_downstream(relations, "100")
        
        assert result["downstream_tasks"] == 3
        assert "200" in result["downstream_list"]
        assert "300" in result["downstream_list"]
        assert "400" in result["downstream_list"]
    
    def test_build_impact_summary_empty(self):
        """测试无下游影响摘要"""
        tool = ImpactTool()
        
        summary = tool._build_impact_summary("100", [], 0)
        
        assert "没有下游依赖" in summary
    
    def test_build_impact_summary_with_downstream(self):
        """测试有下游影响摘要"""
        tool = ImpactTool()
        
        summary = tool._build_impact_summary("100", ["200", "300"], 2)
        
        assert "影响 2 个下游任务" in summary
        assert "200" in summary
```

- [ ] **Step 4: 运行测试**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/workflow/test_nodes/test_risk.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/risk.py src/tools/impact.py tests/workflow/test_nodes/test_risk.py && git commit -m "feat: 添加 assess_risk 和 impact_analysis 节点"
```

---

## Task 8: LangGraph 状态机定义

**Files:**
- Create: `src/workflow/graph.py`
- Modify: `requirements.txt`
- Create: `tests/workflow/test_graph.py`

- [ ] **Step 1: 更新 requirements.txt 添加 langgraph**

```text
langgraph>=0.2.0
langchain-core>=0.3.0
requests>=2.28.0
pyyaml>=6.0
kubernetes>=28.0.0
pytest>=7.0.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: 编写 graph.py**

```python
"""
graph.py - LangGraph 状态机定义

定义告警处理的状态流转
"""

from langgraph.graph import StateGraph, END
from .state import AgentState, INITIAL_STATE
from .nodes import (
    parse_alert,
    validate_project,
    fetch_logs,
    analyze_error,
    query_knowledge,
    impact_analysis,
    assess_risk,
    request_approval,
    check_approval,
    execute_action,
    notify_dingtalk,
    store_results,
)


def should_continue(state: AgentState) -> str:
    """判断是否继续处理"""
    if not state.get("project_valid"):
        return "end"
    return "continue"


def route_by_risk(state: AgentState) -> str:
    """根据风险等级路由"""
    if state.get("approval_required"):
        return "approval"
    return "auto_execute"


def check_approval_status(state: AgentState) -> str:
    """检查审批状态"""
    status = state.get("approval_status")
    if status == "approved":
        return "execute"
    elif status == "rejected":
        return "notify_reject"
    elif status == "timeout":
        return "notify_timeout"
    return "wait"


def build_alert_graph() -> StateGraph:
    """
    构建告警处理状态机
    
    流程:
    parse_alert -> validate_project -> fetch_logs -> analyze_error
    -> query_knowledge -> impact_analysis -> assess_risk
    -> [approval分支] request_approval -> check_approval -> [execute/end]
    -> [auto_execute分支] execute_action
    -> notify_dingtalk -> store_results -> END
    """
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("parse_alert", parse_alert)
    graph.add_node("validate_project", validate_project)
    graph.add_node("fetch_logs", fetch_logs)
    graph.add_node("analyze_error", analyze_error)
    graph.add_node("query_knowledge", query_knowledge)
    graph.add_node("impact_analysis", impact_analysis)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("request_approval", request_approval)
    graph.add_node("check_approval", check_approval)
    graph.add_node("execute_action", execute_action)
    graph.add_node("notify_dingtalk", notify_dingtalk)
    graph.add_node("store_results", store_results)
    
    # 设置入口
    graph.set_entry_point("parse_alert")
    
    # 添加边
    graph.add_edge("parse_alert", "validate_project")
    
    # 验证失败直接结束
    graph.add_conditional_edges(
        "validate_project",
        should_continue,
        {
            "continue": "fetch_logs",
            "end": END,
        },
    )
    
    graph.add_edge("fetch_logs", "analyze_error")
    graph.add_edge("analyze_error", "query_knowledge")
    graph.add_edge("query_knowledge", "impact_analysis")
    graph.add_edge("impact_analysis", "assess_risk")
    
    # 根据风险等级路由
    graph.add_conditional_edges(
        "assess_risk",
        route_by_risk,
        {
            "approval": "request_approval",
            "auto_execute": "execute_action",
        },
    )
    
    # 审批分支
    graph.add_edge("request_approval", "check_approval")
    graph.add_conditional_edges(
        "check_approval",
        check_approval_status,
        {
            "execute": "execute_action",
            "notify_reject": "notify_dingtalk",
            "notify_timeout": "notify_dingtalk",
            "wait": END,  # 等待审批回调
        },
    )
    
    # 执行后通知
    graph.add_edge("execute_action", "notify_dingtalk")
    graph.add_edge("notify_dingtalk", "store_results")
    graph.add_edge("store_results", END)
    
    return graph


class AlertWorkflowGraph:
    """
    告警处理工作流
    
    封装 LangGraph 状态机，提供简单的执行接口
    """
    
    def __init__(self):
        self.graph = build_alert_graph()
        self.app = self.graph.compile()
    
    def run(self, alert_raw: dict) -> AgentState:
        """
        执行工作流
        
        Args:
            alert_raw: 原始告警数据
        
        Returns:
            最终状态
        """
        initial_state = dict(INITIAL_STATE)
        initial_state["alert_raw"] = alert_raw
        
        return self.app.invoke(initial_state)
    
    def continue_from_approval(self, state: AgentState, approval_status: str) -> AgentState:
        """
        从审批状态继续
        
        Args:
            state: 当前状态
            approval_status: approved / rejected / timeout
        
        Returns:
            更新后的状态
        """
        state["approval_status"] = approval_status
        return self.app.invoke(state)


__all__ = ["AlertWorkflowGraph", "build_alert_graph"]
```

- [ ] **Step 3: 编写 test_graph.py**

```python
"""
LangGraph 状态机测试
"""

import pytest
from src.workflow.graph import build_alert_graph, AlertWorkflowGraph
from src.workflow.state import INITIAL_STATE


class TestAlertGraph:
    
    def test_graph_structure(self):
        """测试状态机结构"""
        graph = build_alert_graph()
        
        # 检查节点存在
        assert "parse_alert" in graph.nodes
        assert "validate_project" in graph.nodes
        assert "fetch_logs" in graph.nodes
        assert "analyze_error" in graph.nodes
        assert "assess_risk" in graph.nodes
        assert "execute_action" in graph.nodes
        assert "notify_dingtalk" in graph.nodes
    
    def test_graph_entry_point(self):
        """测试入口节点"""
        graph = build_alert_graph()
        
        assert graph.entry_point == "parse_alert"
    
    def test_workflow_class_init(self):
        """测试工作流类初始化"""
        workflow = AlertWorkflowGraph()
        
        assert workflow.graph is not None
        assert workflow.app is not None
```

- [ ] **Step 4: 运行测试**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/workflow/test_graph.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add requirements.txt src/workflow/graph.py tests/workflow/test_graph.py && git commit -m "feat: 添加 LangGraph 状态机定义"
```

---

## Task 9: 扩展 SparkSkill 错误模式

**Files:**
- Modify: `src/skills/spark_skill.py`
- Create: `tests/skills/test_spark_skill_extended.py`

- [ ] **Step 1: 扩展 spark_skill.py**

在现有 `src/skills/spark_skill.py` 中添加更多错误模式：

```python
"""
Spark Skill - Spark 任务错误分析

扩展错误模式覆盖更多场景
"""

import re
from typing import Optional, List, Dict
from ..models.analysis import ErrorAnalysis
from ..models.risk import RiskLevel, AutoFixAction
from ..models.alert import AlertContext
from .base import BaseSkill


class SparkSkill(BaseSkill):
    """
    Spark 任务分析 Skill
    
    扩展错误模式:
    - OOM (Executor/Driver/Direct Memory)
    - ClassNotFound / NoClassDefFoundError
    - Shuffle 失败
    - Container killed
    - Network 连接失败
    - Data 文件不存在 / Schema 不匹配
    - Performance Broadcast timeout / Data skew
    - Driver disconnected
    """

    skill_name = "spark"
    task_types = ["SPARK", "SPARK_STREAMING"]

    # 扩展的错误模式
    error_patterns = {
        # Resource errors
        "oom_executor": "java.lang.OutOfMemoryError: Java heap space",
        "oom_driver": "OutOfMemoryError: unable to create new native thread",
        "oom_driver_direct": "OutOfMemoryError: Container memory exceeded",
        "container_killed": "Container killed by YARN",
        "executor_lost": "Executor lost",
        
        # Config errors
        "class_not_found": "ClassNotFoundException",
        "no_class_def": "NoClassDefFoundError",
        "spark_config_invalid": "Spark config.*invalid",
        
        # Network errors
        "shuffle_failed": "FetchFailedException",
        "connection_refused": "Connection refused|ConnectException",
        "driver_disconnected": "Driver disconnected",
        
        # Data errors
        "hdfs_not_found": "HDFS.*does not exist|FileNotFound",
        "schema_mismatch": "Schema mismatch|cannot resolve",
        "partition_not_found": "Partition not found",
        
        # Execution errors
        "spark_sql_error": "SparkSQLException",
        "job_aborted": "SparkException: Job aborted",
        "stage_failed": "Stage \\d+ failed",
        "app_submission_failed": "Application submission failed",
        
        # Performance errors
        "broadcast_timeout": "BroadcastHashJoin.*timeout",
        "skewed_partition": "Skewed partition",
        
        # User action
        "killed_by_user": "Killed by user",
    }

    # 扩展的建议模板
    suggestion_templates = {
        "oom_executor": "增加 Executor 内存: spark.executor.memory=4g, spark.executor.memoryOverhead=1g",
        "oom_driver": "增加 Driver 内存: spark.driver.memory=2g",
        "oom_driver_direct": "增加 Driver 直接内存: spark.driver.maxResultSize=2g",
        "container_killed": "检查 YARN 资源配额或减少 Executor 数量",
        "executor_lost": "检查 Executor 状态或增加 spark.executor.heartbeatInterval",
        "class_not_found": "检查依赖包是否已上传到资源中心",
        "no_class_def": "检查依赖包是否正确加载",
        "spark_config_invalid": "检查 Spark 配置参数是否正确",
        "shuffle_failed": "检查网络连接或增加 shuffle service",
        "connection_refused": "检查目标服务是否运行",
        "driver_disconnected": "检查 Driver 状态和网络连接",
        "hdfs_not_found": "检查输入文件路径是否存在",
        "schema_mismatch": "检查数据 Schema 是否匹配",
        "partition_not_found": "检查分区是否存在",
        "spark_sql_error": "检查 SQL 语法错误",
        "job_aborted": "检查具体失败原因，可能是 OOM 或依赖问题",
        "stage_failed": "检查 Stage 失败日志",
        "app_submission_failed": "检查应用提交配置",
        "broadcast_timeout": "禁用 BroadcastJoin: spark.sql.autoBroadcastJoinThreshold=-1",
        "skewed_partition": "处理数据倾斜: spark.sql.adaptive.skewedPartitionFactor",
        "killed_by_user": "任务被手动终止，无需自动修复",
    }

    # 可自动修复的错误类型
    auto_fixable_errors = [
        "oom_executor",
        "oom_driver",
        "oom_driver_direct",
        "broadcast_timeout",
        "connection_refused",  # 临时网络错误可重试
    ]

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """使用预定义规则分析日志"""
        # 遍历错误模式，找到匹配
        for error_type, pattern in self.error_patterns.items():
            if re.search(pattern, log_content, re.IGNORECASE):
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=self._extract_error_message(log_content, pattern),
                    matched_pattern=pattern,
                    spark_app_id=self._extract_app_id(log_content),
                    can_auto_fix=error_type in self.auto_fixable_errors,
                    confidence=0.9,
                )

        # 未匹配到预定义模式
        return ErrorAnalysis(
            error_type="unknown",
            error_message=log_content[:500],
            can_auto_fix=False,
            confidence=0.5,
        )

    def suggest(self, analysis: ErrorAnalysis) -> List[str]:
        """
        给出修复建议（扩展版）
        
        返回多个建议选项
        """
        suggestions = []
        
        if analysis.error_type in self.suggestion_templates:
            suggestions.append(self.suggestion_templates[analysis.error_type])
        
        # 补充通用建议
        if analysis.can_auto_fix:
            suggestions.append("可尝试自动修复")
        else:
            suggestions.append("请联系运维人员查看")
        
        return suggestions

    def _extract_error_message(self, log_content: str, pattern: str) -> str:
        """提取错误消息"""
        lines = log_content.split("\n")
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                return "\n".join(lines[start:end])
        return pattern

    def _extract_app_id(self, log_content: str) -> Optional[str]:
        """提取 Spark ApplicationId"""
        patterns = [
            r"application_\d+_\d+",
            r"app-\d+-\d+",
            r"application_\d+",
        ]
        
        for p in patterns:
            match = re.search(p, log_content)
            if match:
                return match.group(0)
        
        return None

    def _build_auto_fix_action(self, analysis: ErrorAnalysis) -> Optional[AutoFixAction]:
        """构建自动修复动作"""
        if analysis.error_type == "oom_executor":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.executor.memory": "4g",
                    "spark.executor.memoryOverhead": "1g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "oom_driver":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.driver.memory": "2g",
                    "spark.driver.maxResultSize": "2g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "oom_driver_direct":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.driver.maxResultSize": "2g",
                },
                need_recover=True,
            )
        elif analysis.error_type == "broadcast_timeout":
            return AutoFixAction(
                action_type="modify_config",
                config_changes={
                    "spark.sql.autoBroadcastJoinThreshold": "-1",
                },
                need_recover=True,
            )
        elif analysis.error_type == "connection_refused":
            # 网络错误建议重试，不修改配置
            return AutoFixAction(
                action_type="rerun",
                config_changes={},
                need_recover=True,
            )
        
        return None
    
    def get_auto_fix_rules(self) -> List[Dict]:
        """获取自动修复规则列表"""
        return [
            {
                "action_type": "config-change",
                "conditions": {"error": "OutOfMemoryError", "component": "executor"},
                "description": "增加 Executor 内存 50%",
                "risk_level": "LOW",
            },
            {
                "action_type": "config-change",
                "conditions": {"error": "OutOfMemoryError", "component": "driver"},
                "description": "增加 Driver 内存 50%",
                "risk_level": "LOW",
            },
            {
                "action_type": "config-change",
                "conditions": {"error": "BroadcastHashJoin timeout"},
                "description": "禁用 Broadcast Join",
                "risk_level": "LOW",
            },
            {
                "action_type": "rerun",
                "conditions": {"error": "Connection refused", "retry_count": "<3"},
                "description": "重试工作流（临时网络错误）",
                "risk_level": "MEDIUM",
            },
            {
                "action_type": "recover-failed",
                "conditions": {"error": "Stage failed", "upstream_success": True},
                "description": "从失败任务恢复",
                "risk_level": "MEDIUM",
            },
        ]


__all__ = ["SparkSkill"]
```

- [ ] **Step 2: 编写 test_spark_skill_extended.py**

```python
"""
扩展 SparkSkill 测试
"""

import pytest
from src.skills.spark_skill import SparkSkill
from src.models.alert import AlertContext, AlertInfo


class TestSparkSkillExtended:
    
    def setup_method(self):
        self.skill = SparkSkill()
        self.context = AlertContext(
            alert_info=AlertInfo(
                project_code=123,
                process_definition_code=456,
                process_instance_id=789,
                task_code=111,
                task_instance_id=222,
                task_type="SPARK",
                state="FAILURE",
            )
        )
    
    def test_analyze_oom_executor(self):
        """测试 OOM Executor 分析"""
        log = """Exception in thread "executor-1" java.lang.OutOfMemoryError: Java heap space
        at org.apache.spark.executor.Executor"""
        
        result = self.skill.analyze(log, self.context)
        
        assert result.error_type == "oom_executor"
        assert result.can_auto_fix is True
    
    def test_analyze_class_not_found(self):
        """测试 ClassNotFoundException 分析"""
        log = """java.lang.ClassNotFoundException: com.example.MyClass
        at org.apache.spark"""
        
        result = self.skill.analyze(log, self.context)
        
        assert result.error_type == "class_not_found"
        assert result.can_auto_fix is False
    
    def test_analyze_shuffle_failed(self):
        """测试 Shuffle 失败分析"""
        log = """org.apache.spark.shuffle.FetchFailedException: Failed to fetch shuffle blocks"""
        
        result = self.skill.analyze(log, self.context)
        
        assert result.error_type == "shuffle_failed"
    
    def test_analyze_broadcast_timeout(self):
        """测试 Broadcast timeout 分析"""
        log = """org.apache.spark.sql.execution.joins.BroadcastHashJoin timeout"""
        
        result = self.skill.analyze(log, self.context)
        
        assert result.error_type == "broadcast_timeout"
        assert result.can_auto_fix is True
    
    def test_analyze_hdfs_not_found(self):
        """测试 HDFS 文件不存在分析"""
        log = """org.apache.hadoop.mapred.InvalidInputException: Input path does not exist: hdfs://path/file"""
        
        result = self.skill.analyze(log, self.context)
        
        assert result.error_type == "hdfs_not_found"
    
    def test_suggest_returns_list(self):
        """测试建议返回列表"""
        from src.models.analysis import ErrorAnalysis
        
        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            can_auto_fix=True,
        )
        
        suggestions = self.skill.suggest(analysis)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        assert "spark.executor.memory" in suggestions[0]
    
    def test_get_auto_fix_rules(self):
        """测试获取自动修复规则"""
        rules = self.skill.get_auto_fix_rules()
        
        assert isinstance(rules, list)
        assert len(rules) >= 4
        assert any(r["action_type"] == "config-change" for r in rules)
    
    def test_build_auto_fix_action_oom_executor(self):
        """测试构建 OOM Executor 修复动作"""
        from src.models.analysis import ErrorAnalysis
        
        analysis = ErrorAnalysis(
            error_type="oom_executor",
            error_message="OOM",
            can_auto_fix=True,
        )
        
        action = self.skill._build_auto_fix_action(analysis)
        
        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.executor.memory" in action.config_changes
    
    def test_build_auto_fix_action_broadcast_timeout(self):
        """测试构建 Broadcast timeout 修复动作"""
        from src.models.analysis import ErrorAnalysis
        
        analysis = ErrorAnalysis(
            error_type="broadcast_timeout",
            error_message="Broadcast timeout",
            can_auto_fix=True,
        )
        
        action = self.skill._build_auto_fix_action(analysis)
        
        assert action is not None
        assert action.action_type == "modify_config"
        assert "spark.sql.autoBroadcastJoinThreshold" in action.config_changes
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_spark_skill_extended.py -v
```

Expected: 8 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/skills/spark_skill.py tests/skills/test_spark_skill_extended.py && git commit -m "feat: 扩展 SparkSkill 错误模式和自动修复规则"
```

---

## Task 10: 更新 webhook API 使用新工作流

**Files:**
- Modify: `src/api/webhook_api.py`
- Modify: `src/main.py`

- [ ] **Step 1: 修改 webhook_api.py**

```python
"""
Webhook API - 接收 DolphinScheduler 告警
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..workflow.graph import AlertWorkflowGraph
from ..config.projects import projects_registry

router = APIRouter()

# 创建工作流实例
workflow = AlertWorkflowGraph()


@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    处理 DolphinScheduler 告警 webhook
    
    接收 JSON 格式告警，执行完整处理流程
    """
    try:
        payload = await request.json()
        
        # 执行工作流
        result = workflow.run(payload)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "processed",
                "project_valid": result.get("project_valid"),
                "risk_level": result.get("risk_level"),
                "approval_required": result.get("approval_required"),
                "execution_success": result.get("execution_success"),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approval")
async def handle_approval(request: Request):
    """
    处理审批回调
    
    参数:
    - request_id: 审批请求 ID
    - action: approve / reject
    """
    request_id = request.query_params.get("request_id")
    action = request.query_params.get("action")
    
    if not request_id or not action:
        raise HTTPException(status_code=400, detail="Missing request_id or action")
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    # TODO: 从 ApprovalTool 获取 pending state 并继续工作流
    # approval_status = "approved" if action == "approve" else "rejected"
    # result = workflow.continue_from_approval(state, approval_status)
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "acknowledged",
            "request_id": request_id,
            "action": action,
        },
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


__all__ = ["router"]
```

- [ ] **Step 2: 修改 main.py**

```python
"""
DolphinScheduler Agent - Entry Point

启动 API 服务接收告警和对话请求
"""

import os
from dotenv import load_dotenv

load_dotenv()

from src.api import run_server
from src.config import settings


def main():
    """Main entry point - 启动 API 服务"""
    print("=" * 60)
    print("DolphinScheduler Agent Ready (LangGraph Edition)")
    print("=" * 60)
    print()
    print("API Endpoints:")
    print("  POST /webhook    - 接收 DS 告警（LangGraph 状态机处理）")
    print("  POST /chat       - 对话交互")
    print("  POST /feedback   - 知识库反馈")
    print("  GET  /approval   - 审批处理")
    print("  GET  /health     - 健康检查")
    print()
    print(f"Server: http://{settings.API_HOST}:{settings.API_PORT}")
    print("-" * 60)

    run_server()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/api/webhook_api.py src/main.py && git commit -m "feat: 更新 webhook API 使用 LangGraph 状态机"
```

---

## Task 11: 更新项目配置文件

**Files:**
- Modify: `config/projects.yaml`

- [ ] **Step 1: 更新 projects.yaml 使用钉钉企业机器人配置**

```yaml
# 多项目配置
projects:
  - name: ad_monitor
    code: 11598158952448
    ds_api_url: http://ali-dolphin-test-01:12345/dolphinscheduler
    ds_api_token: 771c3c883c17618846a5deae40f89d86
    ds_version: "3.2.0"
    
    # 钉钉企业机器人配置
    dingtalk:
      robot_code: dingyyink7zqipbyrnf1
      client_id: dingyyink7zqipbyrnf1
      client_secret: uBn_9NI7eK1Bm3aGIIcnv5cac4g-Imtg_gMV6MJl8rSQ9-I4xIUXt7SQ68vPfN3E
      notify_users:
        - user_id_placeholder  # 替换为实际钉钉用户 ID
    
    # Spark 日志配置
    spark_log:
      mode: yarn
      history_url: ali-odp-test-02.huan.tv:18082
      yarn_gateway_url: https://ali-odp-test-01.huan.tv:8443/gateway/default/yarn/cluster
      yarn_auth_type: basic
      yarn_username: yarn_user_placeholder
      yarn_password: yarn_password_placeholder
    
    # 权限配置
    allowed_users:
      - admin_placeholder
    admin_users:
      - admin_placeholder
```

- [ ] **Step 2: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add config/projects.yaml && git commit -m "feat: 更新项目配置使用钉钉企业机器人"
```

---

## 实现说明

### 剩余任务（后续实现）

1. **fetch_logs 节点** - 集成 SparkHistTool, YARNLogTool
2. **analyze_error 芊点** - 根据 task_type 路由到不同 Skill
3. **query_knowledge 节点** - 集成 KnowledgeTool
4. **request_approval 节点** - 集成 ApprovalTool
5. **execute_action 节点** - 集成 DSCLIClient 执行动作
6. **notify_dingtalk 节点** - 集成 DingTalkEnterpriseTool
7. **store_results 节点** - 集成 LogStoreTool
8. **SparkHistTool** - Spark History Server API
9. **YARNLogTool** - YARN Gateway API
10. **K8sLogTool** - Kubernetes API
11. **扩展 ShellSkill, PythonSkill, DataXSkill**

### 测试策略

- 每个 Tool 单独测试
- 每个节点单独测试
- 工作流集成测试使用 Mock

### 运行完整测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/ -v --cov=src
```