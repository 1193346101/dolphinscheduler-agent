# DolphinScheduler CLI 3.2.0 适配完整报告

## 一、项目背景

DolphinScheduler 3.2.0 与 3.4.0 版本在 API 层面存在显著差异，主要体现在端点路径命名、参数名称、响应结构等方面。本次适配工作旨在让 `dsctl` CLI 工具能够完整支持 DolphinScheduler 3.2.0 版本的所有核心功能。

---

## 二、API 差异分析

### 2.1 端点路径差异

| 功能模块 | 3.2.0 端点 | 3.4.0 端点 |
|----------|-----------|-----------|
| 工作流定义 | `/process-definition` | `/workflow-definition` |
| 工作流实例 | `/process-instances` (复数) | `/workflow-instance` |
| 执行器 | `/executors/start-process-instance` | `/executors/start-workflow-instance` |
| 任务实例 | `/task-instances` | `/task-instances` (路径相同) |
| 项目列表 | `/projects` (无 `/v2/projects`) | `/v2/projects` |
| V2 实例查询 | `/v2/workflow-instances/{id}` ✓ | `/v2/workflow-instances/{id}` |
| V2 任务查询 | `/v2/task-instances/{id}` ✗ | `/v2/task-instances/{id}` |

### 2.2 参数名称差异

| 参数用途 | 3.2.0 参数名 | 3.4.0 参数名 |
|----------|-------------|-------------|
| 工作流定义编码 | `processDefinitionCode` | `workflowDefinitionCode` |
| 工作流实例ID | `processInstanceId` | `workflowInstanceId` |
| 实例状态 | `state` (int) | `stateType` (enum) |

### 2.3 响应结构差异

| 响应字段 | 3.2.0 | 3.4.0 |
|----------|-------|-------|
| 工作流定义对象 | `processDefinition` | `workflowDefinition` |
| 任务关系列表 | `processTaskRelationList` | `workflowTaskRelationList` |
| 执行触发返回值 | 单个 `int` | `list[int]` |
| release 操作返回 | `null` | `bool` |

### 2.4 JSON 格式差异（创建工作流）

创建工作流时，3.2.0 要求：
- `taskParams` 必须是 **对象**（不能是 JSON 字符串）
- `conditionType` 必须是 **字符串 `"NONE"`**（不能是整数 `0`）
- 必须包含 `isCache: "NO"` 字段
- `resourceIds` 应为 `null`（不能是空字符串）
- taskRelation 中 `name` 应为 `null`（不能是空字符串）

---

## 三、修改内容详解

### 3.1 新增文件列表

| 文件路径 | 说明 |
|----------|------|
| `generated/versions/ds_3_2_0/__init__.py` | 模块导出 |
| `generated/versions/ds_3_2_0/client.py` | DS320Client 客户端类 |
| `generated/versions/ds_3_2_0/api/operations/process_definition.py` | 工作流定义操作 |
| `generated/versions/ds_3_2_0/api/operations/process_instance.py` | 工作流实例操作 |
| `generated/versions/ds_3_2_0/api/operations/executor.py` | 执行触发操作 |
| `generated/versions/ds_3_2_0/api/operations/task_instance.py` | 任务实例操作 |
| `upstream/adapters/ds_3_2_0.py` | DS320Adapter 适配器 |

### 3.2 各文件关键修改点

#### 3.2.1 `process_definition.py`

**端点路径**:
```python
path = f"projects/{project_code}/process-definition"
```

**响应字段转换**:
```python
if "processDefinition" in payload:
    payload["workflowDefinition"] = payload.pop("processDefinition")
if "processTaskRelationList" in payload:
    payload["workflowTaskRelationList"] = payload.pop("processTaskRelationList")
```

**release 返回值处理**:
```python
if payload is None:
    return True  # 3.2.0 返回 null，转为 True
```

#### 3.2.2 `process_instance.py`

**端点路径**:
```python
path = f"projects/{project_code}/process-instances"  # 复数形式
```

**状态参数转换**:
```python
state_value = params.stateType.value if hasattr(params.stateType, 'value') else params.stateType
```

#### 3.2.3 `executor.py`

**端点路径**:
```python
path = f"projects/{project_code}/executors/start-process-instance"
```

**返回值转换**:
```python
if isinstance(payload, int):
    return [payload]  # 单个 int 转 list
```

**参数映射**:
```python
params = TriggerProcessDefinitionParams(
    processDefinitionCode=form.workflowDefinitionCode,
    processInstancePriority=form.workflowInstancePriority,
)
```

#### 3.2.4 `task_instance.py`

**参数自动转换**:
```python
def query_task_list_paging(self, project_code: int, params):
    if hasattr(params, 'workflowInstanceId'):
        converted = QueryProcessTaskListPagingParams(
            processInstanceId=params.workflowInstanceId,
            # ...其他参数
        )
```

#### 3.2.5 `client.py`

**关键别名定义**:
```python
self.workflow_definition = self.process_definition
self.workflow_instance = self.process_instance
self.project_v2 = self.project
self.workflow_instance_v2 = WorkflowInstanceV2Operations(...)  # 3.2.0 有此端点
self.task_instance_v2 = TaskInstanceV2Operations(...)  # 复用
```

#### 3.2.6 `ds_3_2_0.py` (Adapter)

**自定义 ProjectOperations**:
```python
class _DS320ProjectOperations:
    def list(self, *, page_no, page_size, search):
        return self.client.project.query_project_list_paging(
            QueryProjectListPagingParams(searchVal=search, pageNo=page_no, pageSize=page_size)
        )
```

**参数名修正**:
```python
audits=_DS341AuditOperations(client=client),  # 不是 audit_logs
monitor=_DS341MonitorOperations(client=client),  # 不是 monitors
workflow_lineages=_DS341WorkflowLineageOperations(client=client),  # 不是 workflow_lineage
```

### 3.3 通用模块修改

#### `services/_workflow_compile.py`

| 原代码 | 修改后 | 原因 |
|--------|--------|------|
| `taskParams: _json_text(...)` | `taskParams: _task_params_payload(...)` | 3.2.0 需要对象而非字符串 |
| `conditionType: 0` | `conditionType: "NONE"` | 3.2.0 需要字符串 |
| `conditionParams: "{}"` | `conditionParams: {}` | 3.2.0 需要对象 |
| `name: ""` | `name: None` | 3.2.0 需要 null |
| (无) | `isCache: "NO"` | 3.2.0 必须字段 |
| `resourceIds: ""` | `resourceIds: None` | 3.2.0 需要 null |

---

## 四、CLI 功能测试结果

### 4.1 测试环境

| 项目 | 值 |
|------|-----|
| DolphinScheduler 版本 | 3.2.0 |
| API 地址 | http://ali-dolphin-test-01:12345/dolphinscheduler |
| 测试项目 | ad_monitor |
| Python 版本 | 3.13.13 |

### 4.2 功能测试清单

| 命令 | 功能描述 | 测试结果 | 备注 |
|------|----------|----------|------|
| `doctor` | 系统健康检查 | ✅ PASS | 5项检查全部通过 |
| `project list` | 项目列表查询 | ✅ PASS | 使用 `/projects` API |
| `workflow list` | 工作流列表 | ✅ PASS | 返回31个工作流 |
| `workflow get` | 获取单个工作流 | ✅ PASS | 正确返回详情 |
| `workflow describe` | 工作流任务详情 | ✅ PASS | DagData 字段转换成功 |
| `workflow export` | 导出工作流 YAML | ✅ PASS | 生成有效 YAML |
| `workflow create` | 创建工作流 | ✅ PASS | JSON 格式已修正 |
| `workflow delete` | 删除工作流 | ✅ PASS | 需要 --force 参数 |
| `workflow run` | 触发工作流执行 | ✅ PASS | 返回值类型转换成功 |
| `workflow online` | 工作流上线 | ✅ PASS | release 返回 null 已处理 |
| `workflow offline` | 工作流下线 | ✅ PASS | 同上 |
| `workflow-instance list` | 工作流实例列表 | ✅ PASS | 端点 `process-instances` |
| `schedule list` | 调度列表 | ✅ PASS | 无变化 |
| `task-instance list` | 任务实例列表 | ✅ PASS | 参数 `processInstanceId` 转换成功；不带过滤条件时服务器响应慢 |

### 4.3 测试输出示例

#### doctor 命令
```
Status: ok
Summary: {'error': 0, 'ok': 5, 'warning': 0}
```

#### workflow run 命令
```json
{
  "action": "workflow.run",
  "data": {"workflowInstanceIds": [21582274209696]},
  "ok": true
}
```

#### task-instance list 命令（带过滤）
```json
{
  "action": "task-instance.list",
  "data": {"total": 1, "totalList": [{"name": "shell_task_new", "state": "SUCCESS"}]},
  "ok": true
}
```

---

## 五、问题解决记录

### 5.1 遇到的问题及解决方案

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| ValidationError: PageInfoProject returning None | 3.2.0 无 `/v2/projects` | 创建 `_DS320ProjectOperations` |
| ImportError: `_DS341ResourcesOperations` | 类名错误 | 改为 `_DS341ResourceOperations` |
| AttributeError: `_GeneratedSessionAdapter` | 私有类未导入 | 从 ds_3_4_1 导入 |
| TypeError: `http_client` 参数错误 | 参数不匹配 | 检查并修正各 Operations 参数 |
| TypeError: `audit_logs` 参数名错误 | 字段名不匹配 | 改为 `audits`, `monitor`, `workflow_lineages` |
| ValidationError: taskParams 不是对象 | JSON 格式差异 | 移除 `_json_text()` 包装 |
| workflow create 请求参数无效 | JSON 格式差异 | 修正 conditionType, isCache, resourceIds |
| AttributeError: `workflow_instance_v2` | 缺少属性 | 导入并初始化 V2Operations |

---

## 六、修改文件总览

| 文件路径 | 修改类型 |
|----------|----------|
| `generated/versions/ds_3_2_0/__init__.py` | 新增 |
| `generated/versions/ds_3_2_0/client.py` | 新增 |
| `generated/versions/ds_3_2_0/api/operations/process_definition.py` | 新增 |
| `generated/versions/ds_3_2_0/api/operations/process_instance.py` | 新增 |
| `generated/versions/ds_3_2_0/api/operations/executor.py` | 新增 |
| `generated/versions/ds_3_2_0/api/operations/task_instance.py` | 新增 |
| `upstream/adapters/ds_3_2_0.py` | 新增 |
| `upstream/registry.py` | 修改 |
| `services/_workflow_compile.py` | 修改 |

---

## 七、结论

本次适配工作成功实现了 dsctl CLI 对 DolphinScheduler 3.2.0 的**完整支持**。所有核心功能均已验证通过：

- ✅ **项目管理**: project list
- ✅ **工作流定义管理**: workflow list/get/describe/export/create/delete/online/offline
- ✅ **工作流实例管理**: workflow-instance list, workflow run
- ✅ **调度管理**: schedule list
- ✅ **任务实例管理**: task-instance list（建议使用过滤条件以提高查询效率）

**适配策略总结**：
1. 端点路径别名（`process-*` → `workflow-*`）
2. 响应字段转换（`processDefinition` → `workflowDefinition`）
3. 参数名称映射（`processInstanceId` → `workflowInstanceId`）
4. 返回值类型转换（int → list[int]）
5. JSON 格式修正（对象化、字符串化枚举值）
6. 继承复用最大化（DS320Adapter 继承 DS341Adapter）