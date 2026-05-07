# DolphinScheduler Agent 完整设计文档

## 概述

本文档包含两部分：
1. **告警 Agent Phase 2 剩余部分** - 节点实现层、集成层、审批层
2. **对话模块** - 钉钉交互式对话 + 工作流血缘分析 + dsctl 操作

---

# 第一部分：告警 Agent Phase 2 剩余设计

## 当前进度

| Phase | 状态 | 内容 |
|-------|------|------|
| Phase 1 | ✅ 已完成 | 基础设施层 (SparkHistTool, YARNLogTool, K8sLogTool, LLMClient, DSCLIClient) |
| Phase 2 | 🔄 进行中 | 节点实现层 (fetch_logs ✅, analyze_error ✅, execute/notify/store 待完成) |
| Phase 3 | ⏳ 待执行 | 集成层 (端到端测试) |
| Phase 4 | ⏳ 待执行 | 审批层 (ApprovalTool + 回调) |

---

## Phase 2 剩余：节点实现层

### Task 8: execute_action 节点

**职责**：执行已批准的修复动作

**支持动作类型**：

| 动作类型 | dsctl 命令 | 适用场景 |
|----------|-----------|----------|
| rerun | workflow_instance_rerun | 临时错误重试 |
| recover-failed | workflow_instance_recover | 从失败任务恢复 |
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
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    
    for action in actions:
        # HIGH/CRITICAL 需要审批
        if action["risk_level"] in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                continue  # 跳过
        
        # 执行动作
        result = execute_single_action(action, state)
```

---

### Task 9: notify_dingtalk 节点

**职责**：发送钉钉通知

**状态输入**：
- approval_required: 是否需要审批
- risk_level, error_category, error_patterns
- project_config.dingtalk

**状态输出**：
- notification_sent: 是否已发送
- notification_content: 通知内容
- approval_message_id: 钉钉消息 ID

**通知类型**：
- 无需审批：错误分析通知
- 需审批：审批请求通知（带批准/拒绝按钮）

---

### Task 10: store_results 节点

**职责**：存储日志和分析结果

**实现**：使用 LogStoreTool 存储到本地文件，清理过期日志

---

## Phase 3：集成层

### Task 11: 端到端集成测试

**测试场景**：

| 场景 | 流程 | 验证点 |
|------|------|--------|
| LOW 风险自动修复 | parse → validate → fetch_logs → analyze → assess(LOW) → execute → notify | execution_success=True |
| HIGH 风险审批流程 | parse → ... → assess(HIGH) → request_approval → END | approval_required=True |
| 审批回调继续 | check_approval → execute → notify | approval_status=approved |
| 无效项目告警 | parse → validate → END | project_valid=False |
| 日志获取失败 | fetch_logs(error) → analyze(降级) | log_fetch_error 设置 |

---

## Phase 4：审批层

### Task 12: ApprovalTool - 审批管理工具

**职责**：管理审批请求生命周期

**核心方法**：
- `create_request(state, timeout_minutes)` → request_id
- `get_request(request_id)` → ApprovalRequest
- `update_status(request_id, status)` → bool
- `check_expired()` → List[expired_ids]

**数据结构**：
```python
@dataclass
class ApprovalRequest:
    request_id: str              # UUID
    workflow_state: AgentState   # 状态快照
    created_at: datetime
    expires_at: datetime         # 30分钟超时
    status: Literal["pending", "approved", "rejected", "timeout"]
    dingtalk_message_id: str
```

**持久化**：JSON 文件存储 `data/approvals/{request_id}.json`

---

### Task 13: 审批回调处理

**API 端点**：`GET /approval/{request_id}?action=approve|reject`

**处理流程**：
1. 验证参数和请求状态
2. 更新审批状态
3. 继续工作流执行

**超时机制**：后台线程定时检查过期请求，标记 timeout 并发送通知

---

## 剩余任务文件结构

**新建文件**：
```
src/tools/approval_tool.py
tests/test_tools/test_approval_tool.py
tests/test_workflow/test_nodes/test_execute.py
tests/test_workflow/test_nodes/test_notify.py
tests/test_workflow/test_nodes/test_store.py
tests/test_integration/test_e2e_workflow.py
data/approvals/
```

**修改文件**：
```
src/workflow/nodes/execute.py
src/workflow/nodes/notify.py
src/workflow/nodes/store.py
src/workflow/nodes/approval.py
src/api/webhook_api.py
src/tools/__init__.py
```

---

# 第二部分：对话模块设计

## 功能概述

**核心功能**：
- 工作流血缘分析 - 上游/下游依赖、定时调度时序关系
- 数据血缘分析 - Spark SQL 解析表输入输出关系
- dsctl 操作 - 上线、修改、新增、执行、补数工作流
- 节点信息查询 - 节点类型、参数、前后依赖
- 影响风险评估 - 告警和对话场景都调用

**交互方式**：钉钉群组机器人对话

---

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    钉钉接入层                            │
│  消息接收 → 消息解析 → 会话状态管理 → 消息回复           │
├─────────────────────────────────────────────────────────┤
│                    对话 Agent (LangGraph)               │
│  ┌─────────────┬─────────────┬─────────────┬──────────┐ │
│  │ 意图识别    │ 工具调用    │ 血缘分析    │ 响应生成 │ │
│  │ 节点        │ 节点        │ 节点        │ 节点      │ │
│  └─────────────┴─────────────┴─────────────┴──────────┘ │
│  复用 Alert Agent 的风险评估、钉钉通知组件              │
├─────────────────────────────────────────────────────────┤
│                    血缘解析服务                          │
│  ┌─────────────┬─────────────┬─────────────┬──────────┐ │
│  │ 离线解析器  │ 实时解析器  │ 血缘存储    │ 权限控制 │ │
│  │ (首次扫描)  │ (按需解析)  │ (本地文件)  │ (群组)   │ │
│  └─────────────┴─────────────┴─────────────┴──────────┘ │
│  SQL解析：Python正则提取 + Java jar精确解析              │
├─────────────────────────────────────────────────────────┤
│                    DolphinScheduler API                  │
│  工作流定义、依赖关系、节点信息、dsctl 操作              │
└─────────────────────────────────────────────────────────┘
```

---

## 对话 Agent 流程

**LangGraph 节点流程**：

```
用户消息 → parse_intent → route_action → execute → format_response → 回复用户
                    ↓
            ┌──────┴──────┐
            │ 分支路由    │
            ├──────┬──────┤
            │      │      │
     dsctl操作  血缘查询  风险评估
```

**节点职责**：

| 节点 | 输入 | 输出 |
|------|------|------|
| parse_intent | 用户消息 | intent_type, params, session_context |
| execute_dsctl | intent, params | 操作结果 |
| query_lineage | workflow_code, query_type | 血缘数据 |
| assess_risk | workflow_code, action_type | 风险评估结果 |
| format_response | 执行结果 | 钉钉消息内容 |

**intent_type 类型**：
- `dsctl_operate` - 上线、修改、执行、补数等
- `lineage_query` - 依赖关系、节点信息、表血缘查询
- `risk_assess` - 影响风险评估
- `help` - 使用帮助

---

## 血缘解析服务

### 解析流程

**首次扫描**（用户触发）：
```
用户触发扫描 → 扫描全部工作流 → 解析血缘 → 存储
```

**按需解析**：
```
用户提问 → 查缓存 → 有则直接返回
                → 无则实时解析 → 存储 → 返回
```

**告警触发**：
```
告警 Agent → 查缓存 → 有则直接用于风险评估
                    → 无则实时解析 → 存储 → 使用
```

### SQL 解析方式

**Python 正则提取**（简单 SQL）：
- 匹配 `INSERT INTO/OVERWRITE TABLE xxx`
- 匹配 `FROM xxx`、`JOIN xxx`
- 快速返回初步结果

**Java jar 精确解析**（复杂 SQL）：
- 解析 Spark SQL 语法树
- 提取完整血缘链路（多层 JOIN、子查询）
- 通过 subprocess 调用，传入 SQL 文本，返回 JSON

### 血缘存储结构

```
data/lineage/
├── workflows/           # 工作流血缘
│   ├── 123.json         # 单个工作流血缘
│   └── 456.json
├── tables/              # 表血缘索引（反向查询）
│   └── hive.db.table_a.json
└── cache.json           # 解析状态缓存
```

**单个工作流血缘文件示例**：
```json
{
  "workflow_code": 123,
  "workflow_name": "daily_etl",
  "tables_input": ["hive.db.source_table"],
  "tables_output": ["hive.db.target_table"],
  "upstream_workflows": [456, 789],
  "downstream_workflows": [111, 222],
  "parsed_at": "2026-05-07T10:00:00",
  "source": "realtime"
}
```

---

## 钉钉交互设计

### 消息格式

**用户消息示例**：
- `分析工作流 123 的下游依赖`
- `上线工作流 456`
- `工作流 789 的表血缘是什么`
- `补数工作流 111 从昨天到今天`

**Agent 回复格式**（Markdown卡片）：
```markdown
### 工作流 123 血缘分析

**上游依赖**: 无
**下游依赖**: 456 (daily_summary), 789 (weekly_report)
**定时调度**: 每天 08:00

**产出表**: hive.db.target_table
**消费表**: hive.db.source_table

---
点击查看详情
```

### 会话状态管理

```
session_id = user_id + conversation_id

session_state:
  - last_intent: "lineage_query"
  - last_workflow: 123
  - last_result: {...}
  - created_at: timestamp
  - expires_at: created_at + 30min
```

**多轮对话示例**：
```
用户: 分析工作流 123
Agent: [返回 123 的血缘结果]
用户: 它的风险评估
Agent: [基于 session 中 last_workflow=123 做风险评估]
```

---

## 权限控制设计

**基于群组的白名单配置** `config/permissions.yaml`：

```yaml
groups:
  "group_id_运维群":
    permissions:
      - dsctl_operate      # 上线、执行、补数
      - lineage_query      # 血缘查询
      - risk_assess        # 风险评估
  
  "group_id_开发群":
    permissions:
      - lineage_query
      - risk_assess
  
  "group_id_数据分析群":
    permissions:
      - lineage_query
```

**权限检查流程**：
```
parse_intent → 获取群组 ID + intent_type
    → 查 permissions.yaml
    → intent_type 在该群组 permissions 中 → 允许执行
    → 否则 → 回复 "当前群组无权限执行此操作"
```

---

## 文件结构

**新增文件**：
```
src/
├── chat/                      # 对话模块
│   ├── __init__.py
│   ├── agent.py               # 对话 Agent 主入口
│   ├── graph.py               # LangGraph 流程定义
│   ├── state.py               # 对话状态定义
│   ├── nodes/
│   │   ├── parse_intent.py    # 意图解析
│   │   ├── execute_dsctl.py   # dsctl 操作执行
│   │   ├── query_lineage.py   # 血缘查询
│   │   ├── assess_risk.py     # 风险评估
│   │   └── format_response.py # 响应格式化
│   ├── tools/
│   │   ├── intent_parser.py   # 意图解析工具
│   │   └── dsctl_executor.py  # dsctl 命令封装
│   └── api/
│   │   └── dingtalk_webhook.py # 钉钉消息接收
├── lineage/                   # 血缘解析服务
│   ├── __init__.py
│   ├── service.py             # 血缘服务主入口
│   ├── parser/
│   │   ├── python_extractor.py # Python 正则提取
│   │   ├── java_parser.py      # Java jar 调用封装
│   │   └── jar/                # Java 解析 jar 包存放
│   ├── workflow_parser.py     # DS 工作流依赖解析
│   ├── storage.py             # 本地文件存储
│   └── scanner.py             # 工作流扫描器
├── tools/
│   └── permission.py          # 权限控制工具
data/
├── lineage/                   # 血缘数据存储
│   ├── workflows/
│   ├── tables/
│   └── cache.json
├── approvals/                 # 审批请求存储
config/
├── permissions.yaml           # 群组权限配置
tests/
├── test_chat/
├── test_lineage/
```

**复用 Alert Agent 组件**：
- `src/tools/risk_assess.py` - 风险评估工具
- `src/tools/dingtalk_enterprise.py` - 钉钉消息发送
- `src/tools/impact.py` - 影响分析工具
- `src/integrations/ds_cli.py` - DolphinScheduler API 调用

---

## 实现优先级

### Alert Agent Phase 2 剩余

| 顺序 | Task | 内容 |
|------|------|------|
| 1 | Task 8 | execute_action 节点 |
| 2 | Task 9 | notify_dingtalk 节点 |
| 3 | Task 10 | store_results 节点 |
| 4 | Task 11 | 端到端集成测试 |
| 5 | Task 12 | ApprovalTool |
| 6 | Task 13 | 审批回调 |

### 对话模块实现

| Phase | 内容 | 产物 | 依赖 |
|-------|------|------|------|
| Phase 1 | 血缘解析基础 | Python 正则提取 + 本地存储 + 工作流依赖解析 | 无 |
| Phase 2 | 对话 Agent 核心 | 意图解析 + 血缘查询 + 钉钉交互 | Phase 1 |
| Phase 3 | Java 精确解析 | Java jar 解析 Spark SQL | Phase 1 |
| Phase 4 | dsctl 操作 | 上线/执行/补数 + 权限控制 | Phase 2 |
| Phase 5 | 风险评估集成 | 复用 Alert Agent 风险评估 | Phase 2, Alert Agent 完成 |

---

## 总结

**完整实现顺序**：

1. 先完成 Alert Agent Phase 2 剩余 (Tasks 8-13)
2. 再实现对话模块 Phase 1-2（基础功能）
3. 最后完善对话模块 Phase 3-5（完整能力）

Alert Agent 完成后，其风险评估和钉钉组件可直接复用于对话模块。