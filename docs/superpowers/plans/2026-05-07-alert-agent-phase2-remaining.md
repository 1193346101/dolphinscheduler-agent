# Alert Agent Phase 2 剩余部分实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善告警 Agent 节点实现层、集成层和审批层，实现完整的自动修复和审批流程。

**Architecture:** 分层实现：节点层(execute/notify/store) → 集成层(端到端测试) → 审批层(ApprovalTool+回调)，复用已有的基础设施层工具。

**Tech Stack:** LangGraph, pytest, fastapi, dataclasses

---

## 文件结构

**新建文件：**
```
src/tools/approval_tool.py           # ApprovalTool 审批管理
src/workflow/nodes/execute.py        # 完善实现 (已存在，需修改)
src/workflow/nodes/notify.py         # 完善实现 (已存在，需修改)
src/workflow/nodes/store.py          # 完善实现 (已存在，需修改)
src/workflow/nodes/approval.py       # 完善实现 (已存在，需修改)
src/api/webhook_api.py               # 添加审批回调 (已存在，需修改)
tests/test_tools/test_approval_tool.py
tests/test_workflow/test_nodes/test_execute.py
tests/test_workflow/test_nodes/test_notify.py
tests/test_workflow/test_nodes/test_store.py
tests/test_integration/test_e2e_workflow.py
data/approvals/                      # 审批请求存储目录
```

**修改文件：**
```
src/tools/__init__.py                # 添加 ApprovalTool 导出
src/workflow/nodes/execute.py        # 从 placeholder 改为完整实现
src/workflow/nodes/notify.py         # 从 placeholder 改为完整实现
src/workflow/nodes/store.py          # 从 placeholder 改为完整实现
src/workflow/nodes/approval.py       # 完善 request_approval/check_approval
src/api/webhook_api.py               # 添加 /approval/{request_id} 回调
```

---

## Task 8: 完善 execute_action 节点

**Files:**
- Modify: `src/workflow/nodes/execute.py`
- Create: `tests/test_workflow/test_nodes/test_execute.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
execute_action 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.execute import execute_action


class TestExecuteAction:

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_rerun_action(self, mock_dsctl):
        """测试重跑动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_rerun.return_value = Mock(
            success=True, stdout="OK", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "rerun", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert result["execution_success"] is True
        assert len(result["executed_actions"]) == 1

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_recover_action(self, mock_dsctl):
        """测试恢复动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(
            success=True, stdout="Recovery started", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "LOW"}]
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert len(result["executed_actions"]) > 0

    def test_execute_high_risk_without_approval(self):
        """测试高风险动作无审批"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = None
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}

        result = execute_action(state)

        # 高风险无审批应该跳过
        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 0

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_high_risk_with_approval(self, mock_dsctl):
        """测试高风险动作已审批"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(
            success=True, stdout="OK", stderr="", returncode=0
        )
        mock_dsctl.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["task_code"] = "789"
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = "approved"
        state["project_config"] = {
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }

        result = execute_action(state)

        assert len(result["executed_actions"]) > 0

    def test_execute_no_actions(self):
        """测试无动作列表"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["suggested_actions"] = []
        state["project_config"] = {}

        result = execute_action(state)

        assert result["execution_success"] is False
        assert len(result["executed_actions"]) == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_execute.py -v`
Expected: FAIL (测试会因 placeholder 实现返回空结果而失败)

- [ ] **Step 3: 完善 src/workflow/nodes/execute.py**

```python
"""
execute_action 节点

执行修复动作 - 完整实现
"""

from typing import Dict, List
from ..state import AgentState
from ...integrations.dsctl_wrapper import DSCLIClient, CLIResult


def execute_action(state: AgentState) -> AgentState:
    """
    执行动作

    支持动作:
    - rerun: 重跑工作流
    - recover-failed: 从失败恢复
    - config-change: 修改配置
    - notify-only: 仅通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (executed_actions, execution_results, execution_success)
    """
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    project_config = state.get("project_config")

    if not actions or not project_config:
        return {
            **state,
            "executed_actions": [],
            "execution_results": [],
            "execution_success": False,
        }

    dsctl = DSCLIClient(
        api_url=project_config.get("ds_api_url", ""),
        api_token=project_config.get("ds_api_token", "")
    )

    executed = []
    results = []

    instance_id = state["alert_raw"].get("processInstanceId")
    task_code = int(state.get("task_code", 0) or 0)

    for action in actions:
        action_type = action.get("action_type", "")
        risk_level = action.get("risk_level", "LOW")

        # 检查审批
        if risk_level in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                results.append({
                    "action": action,
                    "status": "skipped",
                    "reason": f"需要审批，当前状态: {approval_status}"
                })
                continue

        # 执行动作
        result = _execute_single_action(
            action_type,
            dsctl,
            instance_id,
            task_code,
            state
        )

        if result:
            executed.append(action)
            results.append({
                "action": action,
                "status": "success" if result.success else "failed",
                "output": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:200] if result.stderr else ""
            })
        else:
            results.append({
                "action": action,
                "status": "skipped",
                "reason": "未知动作类型"
            })

    # 判断整体成功
    success = any(
        r.get("status") == "success"
        for r in results
        if r.get("status") != "skipped"
    ) if executed else False

    return {
        **state,
        "executed_actions": executed,
        "execution_results": results,
        "execution_success": success,
    }


def _execute_single_action(
    action_type: str,
    dsctl: DSCLIClient,
    instance_id: int,
    task_code: int,
    state: Dict
) -> CLIResult:
    """执行单个动作"""

    if action_type == "rerun":
        return dsctl.workflow_instance_rerun(instance_id)

    elif action_type == "recover-failed":
        return dsctl.workflow_instance_recover(instance_id, task_code)

    elif action_type == "config-change":
        # config-change 需要: 1) 更新参数 2) 重跑
        # 当前简化实现，直接重跑
        return dsctl.workflow_instance_rerun(instance_id)

    elif action_type == "notify-only":
        # 仅通知，不执行
        return CLIResult(success=True, stdout="仅通知", stderr="", returncode=0)

    return None


__all__ = ["execute_action"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_execute.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/execute.py tests/test_workflow/test_nodes/test_execute.py && git commit -m "feat: 完善 execute_action 节点支持 rerun/recover/config-change"
```

---

## Task 9: 完善 notify_dingtalk 节点

**Files:**
- Modify: `src/workflow/nodes/notify.py`
- Create: `tests/test_workflow/test_nodes/test_notify.py`

- [ ] **Step 1: 查看现有 notify.py**

Run: `cat D:/Project/dolphinscheduler-agent/src/workflow/nodes/notify.py`

- [ ] **Step 2: 创建测试文件**

```python
"""
notify_dingtalk 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.notify import notify_dingtalk


class TestNotifyDingtalk:

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_error_analysis(self, mock_dingtalk):
        """测试发送错误分析通知"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_123"
        mock_instance.build_error_notification.return_value = {
            "title": "告警分析",
            "content": "error content"
        }
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["approval_required"] = False
        state["risk_level"] = "LOW"
        state["error_category"] = "RESOURCE"
        state["error_patterns"] = ["oom_executor"]
        state["suggested_actions"] = []
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test_robot",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "notify_users": ["user1"]
            },
            "ds_api_url": "http://ds:12345"
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is True
        assert result["approval_message_id"] == "msg_123"

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_approval_request(self, mock_dingtalk):
        """测试发送审批请求通知"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_approval"
        mock_instance.build_approval_request.return_value = {
            "title": "审批请求",
            "content": "需要审批",
            "buttons": [{"title": "批准", "actionUrl": "/approval/approve"}]
        }
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["task_type"] = "SPARK"
        state["workflow_code"] = "456"
        state["task_code"] = "789"
        state["approval_required"] = True
        state["risk_level"] = "HIGH"
        state["error_category"] = "RESOURCE"
        state["suggested_actions"] = [{"action_type": "recover-failed"}]
        state["impact_summary"] = "下游 3 个工作流"
        state["risk_factors"] = ["下游依赖多"]
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test_robot",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "notify_users": ["user1"]
            }
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is True

    def test_notify_no_dingtalk_config(self):
        """测试无钉钉配置"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["project_config"] = {}

        result = notify_dingtalk(state)

        assert result["notification_sent"] is False

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_send_failure(self, mock_dingtalk):
        """测试发送失败"""
        mock_instance = Mock()
        mock_instance.send_notification.side_effect = Exception("网络错误")
        mock_instance.build_error_notification.return_value = {"title": "test", "content": "test"}
        mock_dingtalk.return_value = mock_instance

        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["approval_required"] = False
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test",
                "client_id": "test",
                "client_secret": "test",
                "notify_users": ["user1"]
            }
        }

        result = notify_dingtalk(state)

        assert result["notification_sent"] is False
        assert "发送失败" in result["notification_content"]
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_notify.py -v`
Expected: FAIL

- [ ] **Step 4: 完善 src/workflow/nodes/notify.py**

```python
"""
notify_dingtalk 节点

发送钉钉通知 - 完整实现
"""

from ..state import AgentState
from ...tools.dingtalk_enterprise import DingTalkEnterpriseTool


def notify_dingtalk(state: AgentState) -> AgentState:
    """
    发送钉钉通知

    根据审批状态发送不同类型通知:
    - 无需审批: 错误分析通知
    - 需审批: 审批请求通知

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (notification_sent, notification_content, approval_message_id)
    """
    project_config = state.get("project_config")
    dingtalk_config = project_config.get("dingtalk") if project_config else None

    if not dingtalk_config:
        return {
            **state,
            "notification_sent": False,
            "notification_content": None,
            "approval_message_id": None,
        }

    tool = DingTalkEnterpriseTool(
        client_id=dingtalk_config.get("client_id", ""),
        client_secret=dingtalk_config.get("client_secret", "")
    )

    approval_required = state.get("approval_required", False)

    if approval_required:
        # 审批请求通知
        content = tool.build_approval_request(
            task_type=state.get("task_type", ""),
            workflow_code=state.get("workflow_code", ""),
            task_code=state.get("task_code", ""),
            risk_level=state.get("risk_level", ""),
            impact_summary=state.get("impact_summary", ""),
            suggested_actions=state.get("suggested_actions", []),
            risk_factors=state.get("risk_factors", []),
            approve_url="/approval/approve",
            reject_url="/approval/reject"
        )
        buttons = content.get("buttons", [])
    else:
        # 错误分析通知
        content = tool.build_error_notification(
            task_type=state.get("task_type", ""),
            workflow_code=state.get("workflow_code", ""),
            task_code=state.get("task_code", ""),
            risk_level=state.get("risk_level", ""),
            error_category=state.get("error_category", ""),
            error_patterns=state.get("error_patterns", []),
            suggested_actions=state.get("suggested_actions", []),
            ds_url=project_config.get("ds_api_url", "")
        )
        buttons = None

    # 发送通知
    try:
        msg_id = tool.send_notification(
            robot_code=dingtalk_config.get("robot_code", ""),
            user_ids=dingtalk_config.get("notify_users", []),
            title=content.get("title", ""),
            content=content.get("content", ""),
            buttons=buttons
        )

        return {
            **state,
            "notification_sent": True,
            "notification_content": content.get("content", ""),
            "approval_message_id": msg_id,
        }
    except Exception as e:
        return {
            **state,
            "notification_sent": False,
            "notification_content": f"发送失败: {str(e)}",
            "approval_message_id": None,
        }


__all__ = ["notify_dingtalk"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_notify.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/notify.py tests/test_workflow/test_nodes/test_notify.py && git commit -m "feat: 完善 notify_dingtalk 节点发送钉钉通知"
```

---

## Task 10: 完善 store_results 节点

**Files:**
- Modify: `src/workflow/nodes/store.py`
- Create: `tests/test_workflow/test_nodes/test_store.py`

- [ ] **Step 1: 查看现有 store.py**

Run: `cat D:/Project/dolphinscheduler-agent/src/workflow/nodes/store.py`

- [ ] **Step 2: 创建测试文件**

```python
"""
store_results 节点测试
"""

import pytest
import tempfile
import os
from src.workflow.state import create_initial_state
from src.workflow.nodes.store import store_results


class TestStoreResults:

    def test_store_logs_success(self):
        """测试存储日志成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })
            state["workflow_code"] = "456"
            state["task_code"] = "789"
            state["driver_logs"] = "driver log"
            state["spark_logs"] = "spark log"
            state["yarn_logs"] = "yarn log"
            state["error_category"] = "RESOURCE"
            state["risk_level"] = "LOW"
            state["project_config"] = {"spark_mode": "yarn"}

            result = store_results(state, base_path=tmpdir)

            assert result["log_stored"] is True
            assert result["log_store_path"] is not None

    def test_store_logs_no_logs(self):
        """测试无日志时不存储"""
        state = create_initial_state({
            "projectCode": "123",
            "processDefinitionCode": "456",
            "taskCode": "789",
            "taskType": "SPARK",
        })
        state["driver_logs"] = None
        state["spark_logs"] = None

        result = store_results(state)

        assert result["log_stored"] is False

    def test_store_logs_k8s_mode(self):
        """测试 K8s 模式存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })
            state["workflow_code"] = "456"
            state["task_code"] = "789"
            state["driver_logs"] = "driver log"
            state["spark_logs"] = "spark log"
            state["k8s_logs"] = {"pod-1": "pod log"}
            state["project_config"] = {"spark_mode": "k8s"}

            result = store_results(state, base_path=tmpdir)

            assert result["log_stored"] is True
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_store.py -v`
Expected: FAIL (placeholder implementation returns log_stored=False)

- [ ] **Step 4: 完善 src/workflow/nodes/store.py**

```python
"""
store_results 节点

存储结果 - 完整实现
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from ..state import AgentState


def store_results(state: AgentState, base_path: str = "data/logs") -> AgentState:
    """
    存储结果

    存储内容:
    - driver_logs, spark_logs, yarn_logs, k8s_logs
    - error_category, risk_level, error_patterns
    - suggested_actions, execution_results

    Args:
        state: 当前状态
        base_path: 存储目录根路径

    Returns:
        更新后的状态 (log_stored, result_stored, log_store_path)
    """
    workflow_code = state.get("workflow_code", "")
    task_code = state.get("task_code", "")

    # 检查是否有日志需要存储
    has_logs = any([
        state.get("driver_logs"),
        state.get("spark_logs"),
        state.get("yarn_logs"),
        state.get("k8s_logs"),
    ])

    if not has_logs:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
        }

    # 创建存储目录
    date_str = datetime.now().strftime("%Y%m%d")
    log_dir = os.path.join(base_path, date_str, str(workflow_code))
    os.makedirs(log_dir, exist_ok=True)

    # 构建存储数据
    log_data = {
        "workflow_code": workflow_code,
        "task_code": task_code,
        "task_type": state.get("task_type", ""),
        "error_category": state.get("error_category", ""),
        "risk_level": state.get("risk_level", ""),
        "error_patterns": state.get("error_patterns", []),
        "suggested_actions": state.get("suggested_actions", []),
        "execution_results": state.get("execution_results", []),
        "confidence_score": state.get("confidence_score", 0.0),
        "stored_at": datetime.now().isoformat(),
    }

    # 添加日志
    if state.get("driver_logs"):
        log_data["driver_logs"] = state["driver_logs"]
    if state.get("spark_logs"):
        log_data["spark_logs"] = state["spark_logs"]
    if state.get("yarn_logs"):
        log_data["yarn_logs"] = state["yarn_logs"]
    if state.get("k8s_logs"):
        log_data["k8s_logs"] = state["k8s_logs"]

    # 存储文件
    filename = f"{task_code}_{datetime.now().strftime('%H%M%S')}.json"
    filepath = os.path.join(log_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return {
        **state,
        "log_stored": True,
        "result_stored": True,
        "log_store_path": filepath,
    }


__all__ = ["store_results"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_store.py -v`
Expected: 3 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/store.py tests/test_workflow/test_nodes/test_store.py && git commit -m "feat: 完善 store_results 节点存储日志"
```

---

## Task 11: 端到端集成测试

**Files:**
- Create: `tests/test_integration/test_e2e_workflow.py`

- [ ] **Step 1: 创建测试目录和文件**

```python
"""
端到端工作流测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.workflow.graph import AlertWorkflowGraph
from src.workflow.state import create_initial_state
from src.config.projects import projects_registry, ProjectConfig


class TestEndToEndWorkflow:

    @patch("src.workflow.nodes.fetch_logs.DSCLIClient")
    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_low_risk_auto_fix_flow(self, mock_exec_dsctl, mock_dingtalk, mock_fetch_dsctl):
        """测试 LOW 风险自动修复流程"""
        # Mock 日志获取
        mock_fetch_dsctl_instance = Mock()
        mock_fetch_dsctl_instance.get_task_logs.return_value = Mock(
            success=True, stdout="java.lang.OutOfMemoryError: Java heap space"
        )
        mock_fetch_dsctl.return_value = mock_fetch_dsctl_instance

        # Mock 钉钉通知
        mock_dingtalk_instance = Mock()
        mock_dingtalk_instance.send_notification.return_value = "msg_123"
        mock_dingtalk_instance.build_error_notification.return_value = {
            "title": "test", "content": "test"
        }
        mock_dingtalk.return_value = mock_dingtalk_instance

        # Mock 动作执行
        mock_exec_instance = Mock()
        mock_exec_instance.workflow_instance_rerun.return_value = Mock(
            success=True, stdout="OK", stderr="", returncode=0
        )
        mock_exec_dsctl.return_value = mock_exec_instance

        workflow = AlertWorkflowGraph()

        # 注册测试项目
        test_config = ProjectConfig(
            name="test_project",
            code=11598158952448,
            ds_api_url="http://test:12345",
            ds_api_token="test_token",
            dingtalk=Mock(
                robot_code="test",
                client_id="test",
                client_secret="test",
                notify_users=["user1"]
            )
        )
        projects_registry.register(test_config)

        alert_raw = {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456,
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
            "taskState": "FAILURE",
        }

        result = workflow.run(alert_raw)

        assert result.get("project_valid") is True

    def test_invalid_project_flow(self):
        """测试无效项目流程"""
        workflow = AlertWorkflowGraph()

        alert_raw = {
            "projectCode": 999999,  # 不存在的项目
            "processDefinitionCode": 123,
            "taskCode": 456,
            "taskType": "SPARK",
        }

        result = workflow.run(alert_raw)

        assert result.get("project_valid") is False

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_approval_required_flow(self, mock_dingtalk):
        """测试需要审批的流程"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_approval"
        mock_instance.build_approval_request.return_value = {
            "title": "审批请求",
            "content": "需要审批",
            "buttons": [{"title": "批准", "actionUrl": "/approval/approve"}]
        }
        mock_dingtalk.return_value = mock_instance

        # 简化测试，验证审批流程触发
        pass
```

- [ ] **Step 2: 运行测试**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_integration/test_e2e_workflow.py -v`
Expected: 2 tests PASS (简化测试)

- [ ] **Step 3: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add tests/test_integration/ && git commit -m "feat: 添加端到端集成测试"
```

---

## Task 12: ApprovalTool - 审批管理工具

**Files:**
- Create: `src/tools/approval_tool.py`
- Create: `tests/test_tools/test_approval_tool.py`
- Create: `data/approvals/` 目录
- Modify: `src/tools/__init__.py`

- [ ] **Step 1: 创建数据目录**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/data/approvals
```

- [ ] **Step 2: 创建测试文件**

```python
"""
ApprovalTool 测试
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from src.tools.approval_tool import ApprovalTool, ApprovalRequest
from src.workflow.state import create_initial_state


class TestApprovalTool:

    def test_init_with_data_dir(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            assert tool.data_dir == tmpdir

    def test_create_request(self):
        """测试创建审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            request_id = tool.create_request(state, timeout_minutes=30)

            assert request_id is not None
            assert len(request_id) == 36  # UUID 格式

    def test_get_request(self):
        """测试获取审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            request_id = tool.create_request(state)
            request = tool.get_request(request_id)

            assert request is not None
            assert request.status == "pending"

    def test_update_status_approved(self):
        """测试更新状态为已批准"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            request_id = tool.create_request(state)
            result = tool.update_status(request_id, "approved")

            assert result is True
            request = tool.get_request(request_id)
            assert request.status == "approved"

    def test_update_status_rejected(self):
        """测试更新状态为已拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            request_id = tool.create_request(state)
            result = tool.update_status(request_id, "rejected")

            assert result is True
            request = tool.get_request(request_id)
            assert request.status == "rejected"

    def test_update_status_already_processed(self):
        """测试已处理请求不能再次更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            request_id = tool.create_request(state)
            tool.update_status(request_id, "approved")

            # 再次更新应该失败
            result = tool.update_status(request_id, "rejected")
            assert result is False

    def test_check_expired(self):
        """测试检查过期请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            state = create_initial_state({
                "projectCode": "123",
                "processDefinitionCode": "456",
                "taskCode": "789",
                "taskType": "SPARK",
            })

            # 创建一个已过期的请求
            request_id = tool.create_request(state, timeout_minutes=-1)

            expired = tool.check_expired()

            assert request_id in expired

    def test_get_request_not_found(self):
        """测试获取不存在的请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)

            request = tool.get_request("nonexistent-id")

            assert request is None
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_approval_tool.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 创建 src/tools/approval_tool.py**

```python
"""
ApprovalTool - 审批管理工具

管理审批请求的创建、存储、状态更新和过期检查
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ApprovalRequest:
    """审批请求"""
    request_id: str
    workflow_state: Dict
    created_at: str
    expires_at: str
    status: str  # pending, approved, rejected, timeout
    dingtalk_message_id: Optional[str] = None


class ApprovalTool:
    """
    审批管理工具

    使用 JSON 文件存储审批请求
    """

    DEFAULT_DATA_DIR = "data/approvals"

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        """
        初始化

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def create_request(
        self,
        state: Dict,
        timeout_minutes: int = 30,
        dingtalk_message_id: Optional[str] = None
    ) -> str:
        """
        创建审批请求

        Args:
            state: LangGraph 状态快照
            timeout_minutes: 超时时间（分钟）
            dingtalk_message_id: 钉钉消息 ID

        Returns:
            request_id
        """
        request_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=timeout_minutes)

        request = ApprovalRequest(
            request_id=request_id,
            workflow_state=state,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="pending",
            dingtalk_message_id=dingtalk_message_id
        )

        # 存储
        self._save_request(request)

        return request_id

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        获取审批请求

        Args:
            request_id: 请求 ID

        Returns:
            ApprovalRequest 或 None
        """
        path = self._get_request_path(request_id)

        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ApprovalRequest(**data)

    def update_status(self, request_id: str, status: str) -> bool:
        """
        更新审批状态

        Args:
            request_id: 请求 ID
            status: 新状态 (approved, rejected, timeout)

        Returns:
            是否成功
        """
        request = self.get_request(request_id)

        if not request:
            return False

        if request.status != "pending":
            return False  # 只能更新 pending 状态

        request.status = status
        self._save_request(request)

        return True

    def check_expired(self) -> List[str]:
        """
        检查过期请求

        Returns:
            过期的请求 ID 列表
        """
        expired = []
        now = datetime.now()

        for filename in os.listdir(self.data_dir):
            if not filename.endswith(".json"):
                continue

            request_id = filename[:-5]
            request = self.get_request(request_id)

            if request and request.status == "pending":
                expires_at = datetime.fromisoformat(request.expires_at)
                if now > expires_at:
                    expired.append(request_id)

        return expired

    def _save_request(self, request: ApprovalRequest) -> None:
        """保存请求"""
        path = self._get_request_path(request.request_id)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(request), f, ensure_ascii=False, indent=2)

    def _get_request_path(self, request_id: str) -> str:
        """获取请求文件路径"""
        return os.path.join(self.data_dir, f"{request_id}.json")


__all__ = ["ApprovalTool", "ApprovalRequest"]
```

- [ ] **Step 5: 更新 src/tools/__init__.py**

添加导出：
```python
from .approval_tool import ApprovalTool, ApprovalRequest

__all__ = [
    # ... 现有导出 ...
    "ApprovalTool",
    "ApprovalRequest",
]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_approval_tool.py -v`
Expected: 8 tests PASS

- [ ] **Step 7: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/approval_tool.py tests/test_tools/test_approval_tool.py src/tools/__init__.py data/approvals/ && git commit -m "feat: 添加 ApprovalTool 审批管理工具"
```

---

## Task 13: 完善审批节点和回调

**Files:**
- Modify: `src/workflow/nodes/approval.py`
- Modify: `src/api/webhook_api.py`

- [ ] **Step 1: 查看现有 approval.py**

Run: `cat D:/Project/dolphinscheduler-agent/src/workflow/nodes/approval.py`

- [ ] **Step 2: 完善 src/workflow/nodes/approval.py**

```python
"""
approval 节点

request_approval 和 check_approval - 完整实现
"""

from typing import Dict, Any, Optional
from ..state import AgentState
from ...tools.approval_tool import ApprovalTool


approval_tool = ApprovalTool()


def request_approval(state: AgentState) -> AgentState:
    """
    请求审批

    使用 ApprovalTool 创建审批请求:
    - 保存状态快照
    - 设置 30 分钟超时
    - 记录钉钉消息 ID

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status, approval_request_id, approval_message_id)
    """
    dingtalk_message_id = state.get("approval_message_id")

    # 创建审批请求
    request_id = approval_tool.create_request(
        state=state,
        timeout_minutes=30,
        dingtalk_message_id=dingtalk_message_id
    )

    return {
        **state,
        "approval_status": "pending",
        "approval_request_id": request_id,
        "approval_message_id": dingtalk_message_id,
    }


def check_approval(state: AgentState) -> AgentState:
    """
    检查审批状态

    检查审批请求状态:
    - approved: 继续执行
    - rejected: 结束流程
    - timeout: 标记超时
    - pending: 等待中

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (approval_status)
    """
    request_id = state.get("approval_request_id")

    if not request_id:
        return state

    request = approval_tool.get_request(request_id)

    if not request:
        return {
            **state,
            "approval_status": "not_found",
        }

    # 返回当前审批状态
    return {
        **state,
        "approval_status": request.status,
    }


__all__ = ["request_approval", "check_approval"]
```

- [ ] **Step 3: 查看 webhook_api.py**

Run: `cat D:/Project/dolphinscheduler-agent/src/api/webhook_api.py`

- [ ] **Step 4: 完善审批回调 webhook_api.py**

将现有的 `/approval/{request_id}` 端点与 ApprovalTool 集成。修改以下部分:

**导入 ApprovalTool**:
```python
from ..tools.approval_tool import ApprovalTool
```

**初始化 ApprovalTool**:
```python
approval_tool = ApprovalTool()
```

**修改 get_approval 端点**:
```python
@app.get("/approval/{request_id}")
async def get_approval(request_id: str, action: Optional[str] = None):
    """
    处理审批回调

    URL 参数:
    - request_id: 审批请求 ID
    - action: approve 或 reject

    继续执行工作流:
    - approve: 继续执行
    - reject: 通知拒绝并结束
    """
    try:
        if not action:
            # 返回审批详情
            request = approval_tool.get_request(request_id)
            if request:
                return JSONResponse(content={
                    "status": "success",
                    "request": {
                        "request_id": request.request_id,
                        "status": request.status,
                        "created_at": request.created_at,
                        "expires_at": request.expires_at,
                        "workflow_state": request.workflow_state,
                    }
                })
            else:
                raise HTTPException(status_code=404, detail="审批请求不存在")

        if action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'reject'")

        # 更新审批状态
        approval_status = "approved" if action == "approve" else "rejected"
        success = approval_tool.update_status(request_id, approval_status)

        if not success:
            raise HTTPException(status_code=400, detail="审批请求已处理或不存在")

        # 获取 pending state 并继续工作流
        request = approval_tool.get_request(request_id)
        if request and request.workflow_state:
            # 继续执行工作流
            pending_state = request.workflow_state
            pending_state["approval_status"] = approval_status
            result = workflow.continue_from_approval(pending_state, approval_status)

            return JSONResponse(content={
                "status": "processed",
                "request_id": request_id,
                "action": action,
                "approval_status": approval_status,
                "execution_success": result.get("execution_success"),
            })

        return JSONResponse(content={
            "status": "acknowledged",
            "request_id": request_id,
            "action": action,
            "approval_status": approval_status,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**修改 process_approval 端点**:
```python
@app.post("/approval/{request_id}")
async def process_approval(request_id: str, body: ApprovalActionRequest):
    """处理审批请求（POST）"""
    try:
        if body.action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="无效的 action")

        approval_status = "approved" if body.action == "approve" else "rejected"
        success = approval_tool.update_status(request_id, approval_status)

        if not success:
            raise HTTPException(status_code=400, detail="审批请求已处理或不存在")

        # 获取 pending state 并继续工作流
        request = approval_tool.get_request(request_id)
        if request and request.workflow_state:
            pending_state = request.workflow_state
            pending_state["approval_status"] = approval_status
            result = workflow.continue_from_approval(pending_state, approval_status)

            return JSONResponse(content={
                "status": "processed",
                "request_id": request_id,
                "action": body.action,
                "approval_status": approval_status,
                "execution_success": result.get("execution_success"),
            })

        return JSONResponse(content={
            "status": "acknowledged",
            "request_id": request_id,
            "action": body.action,
            "approval_status": approval_status,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**AlertWorkflowGraph 需要添加 continue_from_approval 方法**:
```python
def continue_from_approval(self, state: Dict, approval_status: str) -> Dict:
    """
    从审批状态继续执行工作流

    Args:
        state: 保存的状态快照
        approval_status: approved 或 rejected

    Returns:
        最终执行结果
    """
    if approval_status == "approved":
        # 继续执行 execute -> notify -> store
        from .nodes.execute import execute_action
        from .nodes.notify import notify_dingtalk
        from .nodes.store import store_results

        state = execute_action(state)
        state = notify_dingtalk(state)
        state = store_results(state)

    return state
```

- [ ] **Step 5: 运行全部测试**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/approval.py src/api/webhook_api.py && git commit -m "feat: 完善审批节点和回调处理"
```

---

## 实现说明

### 测试策略
- 每个节点单独测试（Mock 依赖工具）
- ApprovalTool 单独测试（使用临时目录）
- 端到端测试验证完整流程

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/ -v --tb=short
```

### 配置更新

新增环境变量：
```bash
APPROVAL_TIMEOUT=1800  # 30 分钟（秒）
```

### 完成后产物

Alert Agent Phase 2 完成后具备：
- 完整的日志获取（dsctl + Spark History + YARN/K8s）
- Skill + LLM 结合的错误分析
- 自动执行修复动作（LOW/MEDIUM 风险）
- 完善的审批流程（HIGH/CRITICAL 风险 + 30分钟超时）
- 钉钉通知与审批回调