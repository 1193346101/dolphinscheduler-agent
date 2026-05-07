# DolphinScheduler 告警 Agent 第二阶段设计文档

## 概述

本文档描述告警 Agent 第二阶段的完善设计，包括日志获取集成、错误分析增强、动作执行实现、审批流程完善和端到端集成测试。

## 实现方案

采用**分层渐进式实现**方案，按基础设施层 → 节点实现层 → 集成层 → 审批层的顺序逐步完善。

---

## 第一部分：整体架构

### 分层结构

```
┌─────────────────────────────────────────────────────┐
│                    审批层                            │
│  ApprovalTool + 超时机制 + 状态持久化                 │
├─────────────────────────────────────────────────────┤
│                    集成层                            │
│  webhook API + 端到端测试 + 配置管理                  │
├─────────────────────────────────────────────────────┤
│                    节点实现层                        │
│  fetch_logs → analyze_error → execute_action        │
│  → notify_dingtalk → store_results                  │
├─────────────────────────────────────────────────────┤
│                    基础设施层                        │
│  SparkHistTool + YARNLogTool + K8sLogTool           │
│  + LLMClient + dsctl wrapper                        │
└─────────────────────────────────────────────────────┘
```

### 实现顺序

| 阶段 | 内容 | 产物 |
|------|------|------|
| **阶段 1** | 基础设施层 | 日志获取工具 + LLM 调用封装 |
| **阶段 2** | 节点实现层 | 完善节点核心逻辑 + 单元测试 |
| **阶段 3** | 集成层 | 端到端测试 + 服务验证 |
| **阶段 4** | 审批层 | 回调处理 + 超时机制 |

---

## 第二部分：基础设施层

### 2.1 日志获取工具

#### SparkHistTool - Spark History Server API

**输入**：
- application_id: Spark 应用 ID
- history_url: Spark History Server 地址（如 `ali-odp-test-02.huan.tv:18082`）

**输出**：
```python
{
    "driver_stdout": "...",
    "driver_stderr": "...",
    "executors": [{"id": "1", "logs": "..."}]
}
```

**API 调用**：
- `GET http://{history_url}/api/v1/applications/{app_id}`
- `GET http://{history_url}/api/v1/applications/{app_id}/logs`

#### YARNLogTool - YARN Gateway (Knox)

**输入**：
- application_id: YARN 应用 ID（`application_xxx_yyy`）
- gateway_url: Knox Gateway 地址
- auth_type: basic/kerberos
- username/password: 认证凭据

**输出**：
```python
{
    "container_1": "driver logs...",
    "container_2": "executor logs..."
}
```

**API 调用**：
- 通过 Knox Gateway 代理：`https://{gateway}/gateway/default/yarn/cluster/ws/v1/cluster/apps/{app_id}`
- 获取 container 日志

#### K8sLogTool - Kubernetes API

**输入**：
- namespace: Spark 应用命名空间（默认 `spark-apps`）
- app_name: Spark 应用名称
- kubeconfig_path: kubeconfig 文件路径（可选）

**输出**：
```python
{
    "driver-pod": "driver logs...",
    "executor-1": "executor logs...",
    "executor-2": "executor logs..."
}
```

**实现方式**：
- 使用 kubernetes-client Python 库
- 通过 pod labels 筛选：`spark-app-name={app_name}`
- 调用 `read_pod_log()` API

#### 统一接口设计

```python
class BaseLogTool:
    """日志获取工具基类"""
    
    def fetch_logs(self, identifier: str, config: dict) -> dict[str, str]:
        """
        获取日志
        
        Args:
            identifier: 应用标识（application_id / pod name）
            config: 工具特定配置
        
        Returns:
            日志字典 {"driver": "...", "executor_1": "..."}
        """
        raise NotImplementedError
```

### 2.2 LLM 调用封装

#### LLMClient - 内部 AI 服务

**服务配置**：
- URL: `https://aiapi-test.huan.tv/anthropic`
- 认证: Bearer token
- 模型: 继承环境变量配置

**调用场景**：
- Skill 预定义规则未匹配（confidence < 0.8）
- 需要补充分析复杂错误模式
- 生成自然语言错误描述

**输入**：
```python
{
    "log_excerpt": "错误日志片段（最多 2000 字符）",
    "task_type": "SPARK",
    "skill_result": {"error_type": "unknown", "confidence": 0.5},
    "context": {"workflow_code": "...", "task_code": "..."}
}
```

**输出**：
```python
{
    "error_category": "RESOURCE|NETWORK|DATA|CONFIG|EXECUTION",
    "error_description": "自然语言描述",
    "suggested_actions": [{"action_type": "...", "description": "..."}],
    "confidence": 0.85
}
```

#### 调用策略

```
Skill.analyze(logs) → result
if result.confidence >= 0.9:
    return result  # 高置信度直接使用 Skill 结果
elif result.confidence >= 0.8:
    return result  # 中置信度使用 Skill，可选 LLM 补充
else:
    llm_result = LLMClient.analyze(logs, result)
    return merge_results(result, llm_result)  # 合并，取保守风险等级
```

---

## 第三部分：节点实现层

### 3.1 fetch_logs 节点

**职责**：协调多种日志源获取完整日志

**状态输入**：
- project_config.spark_mode: yarn/k8s
- project_config.spark_history_url
- project_config.yarn_gateway_url / k8s 配置
- alert_raw 中的 logPath（dsctl 日志路径）

**状态输出**：
- driver_logs: dsctl CLI 获取的日志
- spark_logs: Spark History Server 日志
- yarn_logs / k8s_logs: 额外日志源
- log_fetch_error: 失败时的错误信息

**实现逻辑**：

```python
def fetch_logs(state: AgentState) -> AgentState:
    config = state["project_config"]
    spark_mode = config.get("spark_mode", "yarn")
    
    # 1. 获取 dsctl driver 日志（基础）
    driver_logs = fetch_dsctl_logs(state["alert_raw"])
    
    # 2. 获取 Spark History 日志（YARN/K8s 都可用）
    app_id = extract_spark_app_id(driver_logs)
    spark_logs = ""
    if app_id and config.get("spark_history_url"):
        spark_logs = SparkHistTool().fetch_logs(app_id, config)
    
    # 3. 根据模式获取额外日志
    if spark_mode == "yarn":
        yarn_logs = YARNLogTool().fetch_logs(app_id, config)
        return {...state, "driver_logs": driver_logs, 
                "spark_logs": spark_logs, "yarn_logs": yarn_logs}
    else:  # k8s
        k8s_logs = K8sLogTool().fetch_logs(app_id, config)
        return {...state, "driver_logs": driver_logs,
                "spark_logs": spark_logs, "k8s_logs": k8s_logs}
```

### 3.2 analyze_error 节点

**职责**：Skill 分发 + LLM 辅助分析

**状态输入**：
- task_type: SHELL/SPARK/PYTHON/DATAX
- driver_logs, spark_logs 等日志
- project_config

**状态输出**：
- error_patterns: 匹配的错误模式列表
- error_category: RESOURCE/NETWORK/DATA/CONFIG/EXECUTION
- suggested_actions: 建议的动作列表
- knowledge_match: 知识库匹配条目
- confidence_score: 分析置信度

**实现逻辑**：

```python
def analyze_error(state: AgentState) -> AgentState:
    task_type = state["task_type"]
    logs = combine_logs(state)
    
    # 1. Skill 分发
    skill = SkillRouter.get_skill(task_type)  # SparkSkill/ShellSkill/...
    skill_result = skill.analyze(logs, context)
    
    # 2. LLM 辅助（低置信度时）
    if skill_result.confidence < 0.8:
        llm_result = LLMClient().analyze(logs, skill_result, context)
        result = merge_analysis(skill_result, llm_result)
    else:
        result = skill_result
    
    # 3. 查询知识库
    knowledge_match = KnowledgeTool().query(result.error_patterns)
    
    return {...state, 
        "error_patterns": result.error_patterns,
        "error_category": result.error_category,
        "suggested_actions": result.suggested_actions,
        "knowledge_match": knowledge_match,
        "confidence_score": result.confidence}
```

### 3.3 execute_action 节点

**职责**：通过 dsctl CLI 执行已批准的动作

**支持动作类型**：

| 动作类型 | dsctl 命令 | 适用场景 |
|----------|-----------|----------|
| rerun | `workflow-instance rerun {id}` | 临时错误重试 |
| recover-failed | `workflow-instance recover {id} --task {code}` | 从失败任务恢复 |
| config-change | 更新参数 + rerun | 参数配置调整 |
| notify-only | 无 | 仅通知人工处理 |

**状态输入**：
- suggested_actions: 建议动作列表
- approval_status: approved/rejected/timeout/null
- project_config: ds_api_url, ds_api_token

**状态输出**：
- executed_actions: 已执行动作列表
- execution_results: 每个动作的执行结果
- execution_success: 整体是否成功

**实现逻辑**：

```python
def execute_action(state: AgentState) -> AgentState:
    actions = state["suggested_actions"]
    approval_status = state.get("approval_status")
    
    executed = []
    results = []
    
    for action in actions:
        # HIGH/CRITICAL 需要审批
        if action.get("risk_level") in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                results.append({"action": action, "status": "skipped", 
                               "reason": "需要审批"})
                continue
        
        # 执行动作
        result = execute_single_action(action, state)
        executed.append(action)
        results.append(result)
    
    success = all(r.get("status") == "success" for r in results 
                  if r.get("status") != "skipped")
    
    return {...state, "executed_actions": executed, 
            "execution_results": results, "execution_success": success}
```

### 3.4 notify_dingtalk 节点

**职责**：发送钉钉通知

**状态输入**：
- approval_required: 是否需要审批
- risk_level, error_category, error_patterns
- project_config.dingtalk

**状态输出**：
- notification_sent: 是否已发送
- notification_content: 通知内容
- approval_message_id: 钉钉消息 ID（用于追踪）

**实现逻辑**：

```python
def notify_dingtalk(state: AgentState) -> AgentState:
    dingtalk_config = state["project_config"].get("dingtalk")
    if not dingtalk_config:
        return {...state, "notification_sent": False}
    
    tool = DingTalkEnterpriseTool(
        dingtalk_config["client_id"], 
        dingtalk_config["client_secret"]
    )
    
    if state["approval_required"]:
        content = tool.build_approval_request(...)
        buttons = content["buttons"]
    else:
        content = tool.build_error_notification(...)
        buttons = None
    
    msg_id = tool.send_notification(
        dingtalk_config["robot_code"],
        dingtalk_config["notify_users"],
        content["title"],
        content["content"],
        buttons
    )
    
    return {...state, "notification_sent": True,
            "notification_content": content["content"],
            "approval_message_id": msg_id}
```

### 3.5 store_results 节点

**职责**：存储日志和分析结果

**实现逻辑**：

```python
def store_results(state: AgentState) -> AgentState:
    tool = LogStoreTool()
    
    # 存储日志
    path = tool.store_logs(
        state["workflow_code"],
        state["task_code"],
        state["driver_logs"],
        state["spark_logs"],
        state.get("yarn_logs"),
        state.get("k8s_logs"),
        state["project_config"]["spark_mode"],
        {"error_category": state["error_category"],
         "risk_level": state["risk_level"]}
    )
    
    # 清理过期日志
    deleted = tool.cleanup_old_logs()
    
    return {...state, "log_stored": True, "result_stored": True,
            "log_store_path": path}
```

---

## 第四部分：集成层

### 4.1 端到端测试场景

#### 场景 1：LOW 风险自动修复

```
输入: SPARK 任务 OOM 告警
流程: parse → validate → fetch_logs → analyze(OOM) → assess(LOW)
      → execute(config-change) → notify → store → END
验证: execution_success=True, notification_sent=True
```

#### 场景 2：HIGH 风险审批流程

```
输入: SPARK 任务失败，下游 >5
流程: parse → validate → fetch_logs → analyze → assess(HIGH)
      → impact_analysis → request_approval → END(等待)
回调: 用户批准 → check_approval → execute → notify → store → END
验证: approval_status=approved, execution_success=True
```

#### 场景 3：无效项目告警

```
输入: project_code 不存在
流程: parse → validate → END
验证: project_valid=False
```

#### 场景 4：日志获取失败

```
输入: Spark History Server 不可用
流程: parse → validate → fetch_logs(error) → analyze(降级) → ...
验证: log_fetch_error 设置, 使用 driver_logs 分析
```

### 4.2 测试方法

- 使用 pytest + Mock 模拟外部服务
- Mock dsctl CLI 输出
- Mock DingTalk API 响应
- Mock LLM API 响应
- 验证 LangGraph 状态流转

### 4.3 配置管理

#### 新增环境变量

```bash
LLM_API_URL=https://aiapi-test.huan.tv/anthropic
LLM_API_TOKEN=xxx
APPROVAL_TIMEOUT=1800  # 30 分钟（秒）
```

#### 配置文件更新

`config/projects.yaml` 新增 llm 配置段：

```yaml
projects:
  - name: ad_monitor
    code: 11598158952448
    # ... 现有配置 ...
    
    # LLM 配置（可选，项目级别覆盖）
    llm:
      enabled: true
      model: glm-5
```

---

## 第五部分：审批层

### 5.1 ApprovalTool 设计

**职责**：管理审批请求生命周期

**核心方法**：
- `create_request(state, timeout_minutes)` → request_id
- `get_request(request_id)` → ApprovalRequest
- `update_status(request_id, status)` → bool
- `check_expired()` → List[expired request_ids]

**数据结构**：

```python
@dataclass
class ApprovalRequest:
    request_id: str              # UUID
    workflow_state: AgentState   # LangGraph 状态快照
    created_at: datetime
    expires_at: datetime         # created_at + 30min
    status: Literal["pending", "approved", "rejected", "timeout"]
    dingtalk_message_id: str
```

**持久化**：
- 使用 JSON 文件存储：`data/approvals/{request_id}.json`
- 或使用内存字典（单实例部署）

### 5.2 审批回调处理

**API 端点**：`GET /approval/{request_id}?action=approve|reject`

**处理流程**：

```python
@router.get("/approval/{request_id}")
async def handle_approval(request_id: str, action: str):
    # 1. 验证参数
    if action not in ["approve", "reject"]:
        raise HTTPException(400, "Invalid action")
    
    # 2. 获取审批请求
    approval = ApprovalTool().get_request(request_id)
    if not approval:
        raise HTTPException(404, "Request not found")
    
    if approval.status != "pending":
        raise HTTPException(400, f"Already {approval.status}")
    
    # 3. 更新状态
    approval_status = "approved" if action == "approve" else "rejected"
    ApprovalTool().update_status(request_id, approval_status)
    
    # 4. 继续工作流
    workflow = AlertWorkflowGraph()
    result = workflow.continue_from_approval(approval.workflow_state, approval_status)
    
    return {"status": "processed", "approval_status": approval_status,
            "execution_success": result.get("execution_success")}
```

### 5.3 超时机制

**实现方式**：后台定时检查线程

```python
class ApprovalTimeoutChecker:
    def __init__(self, interval_seconds=60):
        self.interval = interval_seconds
        self._thread = threading.Thread(target=self._run, daemon=True)
    
    def start(self):
        self._thread.start()
    
    def _run(self):
        while True:
            time.sleep(self.interval)
            expired = ApprovalTool().check_expired()
            for request_id in expired:
                ApprovalTool().update_status(request_id, "timeout")
                # 发送超时通知
                notify_timeout(request_id)
```

**启动时机**：在 webhook_api 服务启动时初始化

---

## 第六部分：文件结构

### 新增文件

```
src/
├── tools/
│   ├── spark_hist.py         # SparkHistTool
│   ├── yarn_log.py           # YARNLogTool
│   ├── k8s_log.py            # K8sLogTool
│   ├── llm_client.py         # LLMClient
│   └── approval.py           # ApprovalTool
│   └── knowledge.py          # KnowledgeTool
│   └── impact.py             # ImpactTool (已存在)
├── integrations/
│   └── dsctl_wrapper.py      # dsctl CLI 封装
├── workflow/
│   └── nodes/
│       ├── fetch_logs.py     # 完善
│       ├── analyze.py        # 完善
│       ├── execute.py        # 完善
│       ├── notify.py         # 完善
│       └── store.py          # 完善
│       └── approval.py       # request_approval/check_approval 完善
tests/
├── tools/
│   ├── test_spark_hist.py
│   ├── test_yarn_log.py
│   ├── test_k8s_log.py
│   ├── test_llm_client.py
│   └── test_approval.py
├── integration/
│   └── test_e2e_workflow.py  # 端到端测试
data/
└── approvals/                # 审批请求存储目录
```

### 修改文件

- `src/workflow/nodes/fetch_logs.py` - 完善实现
- `src/workflow/nodes/analyze.py` - 完善实现
- `src/workflow/nodes/execute.py` - 完善实现
- `src/workflow/nodes/notify.py` - 完善实现
- `src/workflow/nodes/store.py` - 完善实现
- `src/workflow/nodes/approval.py` - 完善实现
- `src/api/webhook_api.py` - 添加审批回调
- `config/projects.yaml` - 添加 llm 配置
- `requirements.txt` - 添加 kubernetes-client

---

## 第七部分：依赖

### Python 包

```text
kubernetes>=28.0.0     # K8sLogTool
langgraph>=0.2.0       # 已添加
langchain-core>=0.3.0  # 已添加
requests>=2.28.0       # 已添加
pyyaml>=6.0            # 已添加
pytest>=7.0.0          # 已添加
```

### 外部服务依赖

| 服务 | 用途 | 配置位置 |
|------|------|----------|
| Spark History Server | Spark 日志 | project.spark_log.history_url |
| YARN Gateway (Knox) | YARN 日志 | project.spark_log.yarn_gateway_url |
| Kubernetes API | K8s 日志 | project.spark_log.k8s_* |
| 内部 AI 服务 | LLM 分析 | LLM_API_URL 环境变量 |
| DingTalk API | 通知 | project.dingtalk |
| DolphinScheduler API | dsctl 执行 | project.ds_api_url |

---

## 附录：风险等级与审批关系

| 风险等级 | 自动执行 | 审批要求 |
|----------|----------|----------|
| LOW | ✅ 直接执行 | 无 |
| MEDIUM | ✅ 直接执行 | 无 |
| HIGH | ❌ 等待审批 | 30 分钟内批准 |
| CRITICAL | ❌ 等待审批 | 30 分钟内批准 |

**审批超时处理**：
- 超时后标记为 timeout
- 发送超时通知到钉钉
- 不执行任何动作，仅记录日志