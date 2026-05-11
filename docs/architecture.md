# DolphinScheduler Agent 项目架构设计

## 一、项目概述

DolphinScheduler Agent 是一个智能运维助手，通过接收 DolphinScheduler 告警 webhook，**自动分析错误、评估风险、自动修复问题并重跑失败任务**，同时支持通过钉钉/飞书进行对话式操作。

项目采用 GSD (Get Shit Done) 架构，强调简洁、模块化、职责清晰。

---

## 二、核心架构概念

### 2.1 Agent、Skill 与 Tool 的区分定义

在 LangChain 架构中，三者有明确区别：

| 类型 | 定义 | 特征 | 使用场景 |
|------|------|------|----------|
| **Agent** | 使用 LLM 进行自主决策的实体 | 1. 动态选择工具<br>2. 多步推理规划<br>3. 状态维护<br>4. LLM 驱动决策 | 复杂任务编排、意图理解、流程协调 |
| **Skill** | 特定领域的知识库和分析逻辑 | 1. 预定义分析规则<br>2. 领域知识库<br>3. 不需要 LLM 决策<br>4. 输入→输出固定 | 任务类型专精分析 |
| **Tool** | 具体的功能实现函数 | 1. 单一职责<br>2. 无决策逻辑<br>3. 被 Agent/Skill 调用<br>4. 确定性输出 | CLI 操作、API 调用、数据处理 |

### 2.2 系统中的组件划分

**Dispatcher（不是 Agent，使用预定义规则）**：

| 模块 | 路径 | 职责 | 判断规则 |
|------|------|------|----------|
| Dispatcher | `src/dispatcher.py` | 请求分发 | 告警有固定字段 `processInstanceId`，对话是自由文本，用简单规则判断 |

**2 个真正的 Agent（需要 LLM 决策）**：

| Agent | 路径 | 职责 | 为什么是 Agent |
|-------|------|------|----------------|
| AlertAgent | `src/agent/alert_agent.py` | 告警自动化处理 | 需要规划流程、风险评估、决定是否自动修复、自动调整配置、自动重跑 |
| ChatAgent | `src/agent/chat_agent.py` | 对话交互 | 需要理解意图、提取参数、构建命令、评估风险 |

**Skills 模块（重构为 anthropics/skills 规范）**：

| Skill | 路径 | 职责 | 支持任务类型 |
|-------|------|------|-------------|
| SparkSkill | `skills/spark-error-analyzer/` | Spark 错误分析 | SPARK, SPARK_STREAMING |
| ShellSkill | `skills/shell-error-analyzer/` | Shell 脚本分析 | SHELL |
| PythonSkill | `skills/python-error-analyzer/` | Python 错误分析 | PYTHON |
| DataXSkill | `skills/datax-error-analyzer/` | DataX 同步分析 | DATAX |
| TimeoutAnalyzer | `skills/timeout-analyzer/` | 超时告警分析 | 全类型 |

**Skills 结构（参考 anthropics/skills/pdf 规范）：**

每个 Skill 目录包含：
- `SKILL.md`: 核心工作流（Markdown + YAML frontmatter）
- `*_patterns.md`: 错误模式表（Markdown 表格）
- `scripts/`: Python 脚本（匹配、解析、修复）

---

## 三、功能架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DolphinScheduler Agent                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                              API 入口层                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Webhook    │  │  Chat       │  │  Feedback   │  │  Approval   │         │
│  │  API        │  │  API        │  │  API        │  │  API        │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
│        │                │                │                │                 │
│        ▼                ▼                ▼                ▼                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                         Dispatcher (预定义规则)                              │
│                                                                              │
│                    ┌───────────────────────────────┐                        │
│                    │       Dispatcher              │                        │
│                    │   ○ 不是 Agent (简单规则判断)  │                        │
│                    │   有 processInstanceId → Alert │                        │
│                    │   用户自由文本 → Chat          │                        │
│                    └───────────────────────────────┘                        │
│                              │              │                               │
│                    ┌─────────┘              └─────────┐                     │
│                    ▼                                  ▼                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                           Agent 层 (LLM 驱动)                                │
│                                                                              │
│         ┌──────────────────────────────┐   ┌──────────────────────────────┐ │
│         │      ★ Alert Agent           │   │      ★ Chat Agent            │ │
│         │  (告警自动化处理)             │   │  (对话意图理解与执行)         │ │
│         │                              │   │                              │ │
│         │  核心能力:                    │   │  核心能力:                    │ │
│         │  • 规划分析流程               │   │  • 理解用户意图               │ │
│         │  • 选择分析 Skill             │   │  • 提取参数                   │ │
│         │  • 自动风险评估               │   │  • 构建 CLI 命令              │ │
│         │  • 低风险自动修复             │   │  • 风险评估                   │ │
│         │  • 自动调整工作流配置         │   │  • 执行或审批                 │ │
│         │  • 自动重跑失败任务           │   │                              │ │
│         │  • 高风险发起审批             │   │                              │ │
│         │  • 发送结果通知               │   │                              │ │
│         └──────────────────────────────┘   └──────────────────────────────┘ │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Skills 层 (anthropics/skills 规范)                  │
│                                                                              │
│  公共模块: skills/common/                                                    │
│  ├── preprocess_log.py      # 日志降噪（所有 skill 共用）                    │
│  ├── extract_context.py     # IP/域名/HDFS 提取                              │
│  └── cluster_lookup.py      # 集群配置关联                                   │
│                                                                              │
│  Skill 目录 (SKILL.md + patterns.md + scripts/):                            │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────┐│
│  │ spark-error-    │ │ shell-error-    │ │ python-error-   │ │ datax-error-││
│  │ analyzer        │ │ analyzer        │ │ analyzer        │ │ analyzer    ││
│  │                 │ │                 │ │                 │ │             ││
│  │ SKILL.md        │ │ SKILL.md        │ │ SKILL.md        │ │ SKILL.md    ││
│  │ spark_patterns  │ │ shell_patterns  │ │ python_patterns │ │ datax_pattn ││
│  │ scripts/        │ │ scripts/        │ │ scripts/        │ │ scripts/    ││
│  │  match_error.py │ │  match_error.py │ │  match_error.py │ │match_error  ││
│  │  build_fix.py   │ │                 │ │  traceback.py   │ │             ││
│  │  calc_resource  │ │                 │ │                 │ │             ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ timeout-analyzer                                                         ││
│  │ SKILL.md + scripts/analyze_timeout.py + scripts/check_cluster.py        ││
│  │ (超时分析: 报错重试 + 资源等待)                                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                           Tools 层 (功能实现)                                │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ LogFetcher │ │ Impact     │ │ Workflow   │ │ Knowledge  │ │ SparkHist │ │
│  │ Tool       │ │ Analyzer   │ │ Operator   │ │ Searcher   │ │ Fetcher   │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ YARN Log   │ │ Risk       │ │ AutoFix    │ │ DingTalk   │ │ Approval  │ │
│  │ Fetcher    │ │ Assessor   │ │ Executor   │ │ Notifier   │ │ Requester │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                         外部集成层                                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ DS CLI      │ │ Spark Hist  │ │ YARN RM     │ │ DingTalk/   │           │
│  │ (dsctl)     │ │ Server      │ │             │ │ Feishu      │           │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、目录结构

```
dolphinscheduler-agent/
├── src/
│   ├── dispatcher.py                   # ○ Dispatcher（请求分发，预定义规则）
│   │
│   ├── agent/                          # Agent 模块（只有 2 个真正的 Agent）
│   │   ├── __init__.py
│   │   ├── alert_agent.py              # ★ Alert Agent（告警自动化处理）
│   │   ├── chat_agent.py               # ★ Chat Agent（对话意图理解与执行）
│   │   │
│   │   ├── tools/                      # Agent Tools（LangChain Tools）
│   │   │   ├── __init__.py
│   │   │   ├── log_tools.py            # LogFetcherTool
│   │   │   ├── impact_tools.py         # ImpactAnalyzerTool
│   │   │   ├── workflow_tools.py       # WorkflowOperatorTool（修改、重跑）
│   │   │   ├── knowledge_tools.py      # KnowledgeSearchTool
│   │   │   ├── spark_history_tools.py  # SparkHistoryFetcherTool
│   │   │   ├── yarn_tools.py           # YarnLogFetcherTool
│   │   │   ├── risk_tools.py           # RiskAssessorTool（风险评估）
│   │   │   ├── autofix_tools.py        # AutoFixExecutorTool（自动修复执行）
│   │   │   ├── notification_tools.py   # DingTalkNotifierTool, FeishuNotifierTool
│   │   │   ├── approval_tools.py       # ApprovalRequestTool（高风险审批）
│   │   │   └── lineage_tools.py        # LineageAnalyzerTool
│   │   │
│   │   └── parser/                     # 解析器（非 Agent，纯函数）
│   │       ├── __init__.py
│   │       ├── alert_parser.py         # 告警内容解析
│   │       ├── log_parser.py           # 日志内容解析
│   │       ├── intent_parser.py        # 用户意图解析
│   │       └── code_parser.py          # 代码语法解析
│   │
│   ├── skills/                         # Skills 模块（anthropics/skills 规范）
│   │   ├── __init__.py
│   │   ├── registry.py                 # Skill 注册表（统一入口）
│   │   │
│   │   ├── common/                     # 公共模块
│   │   │   ├── preprocess_log.py       # 日志降噪（智能提取）
│   │   │   ├── extract_context.py      # IP/域名/HDFS 提取
│   │   │   └── cluster_lookup.py       # 集群配置关联
│   │   │
│   │   ├── spark-error-analyzer/       # Spark 错误分析 Skill
│   │   │   ├── SKILL.md                # 工作流定义
│   │   │   ├── spark_patterns.md       # 错误模式表（Markdown）
│   │   │   └── scripts/
│   │   │       ├── match_error.py      # 匹配脚本
│   │   │       ├── analyze_traceback.py# 堆栈深度解析
│   │   │       ├── build_fix.py        # 构建修复方案
│   │   │       └── calculate_resource.py# 资源建议（最高2倍）
│   │   │
│   │   ├── shell-error-analyzer/       # Shell 错误分析 Skill
│   │   │   ├── SKILL.md
│   │   │   ├── shell_patterns.md
│   │   │   └── scripts/
│   │   │       ├── match_error.py
│   │   │       └── analyze_traceback.py
│   │   │
│   │   ├── python-error-analyzer/      # Python 错误分析 Skill
│   │   │   ├── SKILL.md
│   │   │   ├── python_patterns.md
│   │   │   └── scripts/
│   │   │       ├── match_error.py
│   │   │       └── analyze_traceback.py# Python traceback 深度解析
│   │   │
│   │   ├── datax-error-analyzer/       # DataX 错误分析 Skill
│   │   │   ├── SKILL.md
│   │   │   ├── datax_patterns.md
│   │   │   └── scripts/
│   │   │       └── match_error.py
│   │   │
│   │   └── timeout-analyzer/           # 超时分析 Skill
│   │       ├── SKILL.md
│   │       └── scripts/
│   │           ├── analyze_timeout.py  # 超时根因分析
│   │           └── check_cluster.py    # 集群资源状态
│   │
│   ├── integrations/                   # 外部系统集成（客户端）
│   │   ├── __init__.py
│   │   ├── ds_cli.py                   # DolphinScheduler CLI (dsctl) 集成
│   │   ├── spark_history.py            # Spark History Server API 客户端
│   │   ├── yarn.py                     # YARN ResourceManager API 客户端
│   │   ├── dingtalk.py                 # 钉钉机器人 API 客户端
│   │   ├── feishu.py                   # 飞书机器人 API 客户端
│   │   └── webhook.py                  # Webhook 接收服务
│   │
│   ├── knowledge/                      # 知识库模块
│   │   ├── __init__.py
│   │   ├── manager.py                  # 知识库管理器
│   │   ├── models.py                   # KnowledgeEntry 模型
│   │   ├── store.py                    # 知识库存储（JSON 文件）
│   │   └── feedback.py                 # 反馈处理
│   │
│   ├── security/                       # 安全审核模块
│   │   ├── __init__.py
│   │   ├── auditor.py                  # SecurityAuditor
│   │   ├── risk_assessor.py            # RiskAssessor（风险等级判定）
│   │   └── approval.py                 # ApprovalWorkflow
│   │
│   ├── lineage/                        # 血缘分析模块
│   │   ├── __init__.py
│   │   ├── workflow_dependency.py      # 工作流依赖分析
│   │   ├── table_lineage.py            # 表血缘分析
│   │   ├── graph_builder.py            # 图构建器
│   │   └── visualizer.py               # Mermaid/GraphViz 可视化
│   │
│   ├── storage/                        # 存储模块
│   │   ├── __init__.py
│   │   ├── log_store.py                # 日志存储（7天清理）
│   │   └── cache.py                    # 内存缓存
│   │
│   ├── api/                            # API 服务（FastAPI）
│   │   ├── __init__.py
│   │   ├── webhook_api.py              # /webhook 端点
│   │   ├── chat_api.py                 # /chat 端点
│   │   ├── feedback_api.py             # /feedback 端点
│   │   └── approval_api.py             # /approval 端点
│   │   │
│   │   └── models/                     # API 请求/响应模型
│   │       ├── __init__.py
│   │       ├── alert_request.py        # Alert Webhook 请求模型
│   │       ├── chat_request.py         # Chat 请求模型
│   │       ├── feedback_request.py     # Feedback 请求模型
│   │       └── approval_request.py     # Approval 请求模型
│   │
│   ├── config/                         # 配置模块
│   │   ├── __init__.py
│   │   ├── settings.py                 # 全局环境变量配置
│   │   ├── projects.py                 # 多项目配置
│   │   └── prompts.py                  # Agent Prompt 模板
│   │
│   └── models/                         # 公共数据模型
│       ├── __init__.py
│       ├── alert.py                    # AlertInfo, AlertContext
│       ├── analysis.py                 # ErrorAnalysis, AnalysisResult
│       ├── suggestion.py               # Suggestion, AutoFixAction
│       ├── impact.py                   # ImpactReport, ImpactLevel
│       ├── risk.py                     # RiskLevel, RiskAssessment
│       └── workflow.py                 # WorkflowInfo, TaskInfo
│
├── config/                             # 配置文件目录
│   ├── projects.yaml                   # 多项目配置文件
│   └── cluster_info.md                 # 集群配置（IP/服务映射，Markdown）
│
├── data/                               # 数据目录
│   ├── metrics/                        # 每日任务执行指标
│   │   ├── 2026-05-10.json             # 每日采集数据
│   │   ├── 2026-05-11.json
│   │   └── summary/                    # 汇总数据
│   │       └── workflow_xxx.json       # 按工作流汇总
│   │
│   ├── graph/                          # 知识图谱数据
│   │   ├── xxx_graph.json              # 工作流依赖图
│   │   └── graph_viewer.html           # 可视化
│   │
│   └── knowledge_base/                 # 知识库数据目录（增强版）
│       ├── spark_oom.md                # 通用知识
│       ├── projects/                   # 项目历史
│       │   └ 21451302002208/
│       │       ├── spark_errors.md     # 项目历史修复记录
│       │       └ workflow_errors.md
│       └── approved/                   # 人工确认知识
│           └── spark_oom_approved.md
│
├── logs/                               # 日志目录
│   ├── spark_history/                  # Spark History 日志（7天清理）
│   ├── yarn/                           # YARN 日志（7天清理）
│   └── agent/                          # Agent 运行日志
│
├── tests/                              # 测试目录
│   ├── test_agent/                     # Agent 测试
│   ├── test_skills/                    # Skills 测试
│   ├── test_tools/                     # Tools 测试
│   └── test_integrations/              # 集成测试
│
├── docs/                               # 文档目录
│   ├── architecture.md                 # 本文档
│   ├── agents_guide.md                 # Agent 开发指南
│   ├── skills_guide.md                 # Skill 开发指南
│   └── tools_reference.md              # Tools 参考
│
├── .env.example                        # 环境变量示例
├── pyproject.toml                      # 项目配置（Poetry）
├── requirements.txt                    # 依赖（pip）
└── README.md                           # 项目说明
```

---

## 五、Dispatcher 与 Agent 详细设计

### 5.1 Dispatcher (`src/dispatcher.py`)

**职责**: 请求分发，根据预定义规则判断请求类型

**为什么不是 Agent**:
- 告警请求有固定字段 `processInstanceId`、`taskCode`
- 对话请求是用户自由文本
- 用简单的规则判断即可，不需要 LLM

```python
def dispatch_request(request: dict) -> None:
    """
    Dispatcher - 请求分发（不是 Agent）
    
    ○ 不使用 LLM，用预定义规则判断
    
    判断规则:
    1. 检查是否有 processInstanceId 字段 → 告警请求
    2. 检查是否有 taskCode 字段 → 告警请求
    3. 否则 → 对话请求
    
    流程:
    - 告警请求 → 调用 AlertAgent.handle_alert()
    - 对话请求 → 调用 ChatAgent.handle_chat()
    """
    if "processInstanceId" in request or "taskCode" in request:
        # 告警请求
        alert_agent = AlertAgent()
        return alert_agent.handle_alert(request)
    else:
        # 对话请求
        chat_agent = ChatAgent()
        return chat_agent.handle_chat(request)
```

### 5.2 Alert Agent (`src/agent/alert_agent.py`)

**职责**: 告警自动化处理，从分析到修复全流程

**核心能力**:
- 规划分析流程
- 选择分析 Skill
- **自动风险评估**
- **低风险自动修复**
- **自动调整工作流配置**
- **自动重跑失败任务**
- 高风险发起审批
- 发送结果通知

```python
class AlertAgent:
    """
    告警自动化处理 Agent
    
    ★ Agent 特征:
    1. 使用 LLM 规划处理流程
    2. 根据任务类型动态选择 Skill
    3. 判断是否需要增强分析
    4. 整合结果生成修复方案
    5. 自动风险评估（判断风险等级）
    6. 低风险: 自动调整配置 + 自动重跑
    7. 高风险: 发起审批，等待人工确认
    8. 发送结果通知
    
    工具集:
    - parse_alert: 解析告警字段
    - fetch_task_logs: 拉取 DS 任务日志
    - analyze_impact: 分析下游影响
    - select_skill: 选择分析 Skill
    - enhance_analysis: 拉取 Spark History/YARN 日志
    - search_knowledge: 搜索已确认知识库
    - assess_risk: 自动风险评估（判断风险等级）
    - modify_workflow_config: 自动修改工作流配置参数
    - recover_workflow: 自动恢复失败任务
    - request_approval: 高风险发起审批
    - send_notification: 发送通知
    """
    
    tools = [
        parse_alert_tool,
        fetch_task_logs_tool,
        analyze_impact_tool,
        select_skill_tool,
        enhance_analysis_tool,
        search_knowledge_tool,
        assess_risk_tool,           # 自动风险评估
        modify_workflow_config_tool, # 自动修改配置
        recover_workflow_tool,       # 自动重跑
        request_approval_tool,       # 高风险审批
        send_notification_tool,
    ]
    
    system_prompt = """
    你是 DolphinScheduler 告警自动化处理 Agent。
    
    当收到告警时，你需要执行完整的自动化处理流程：
    
    ## 分析阶段
    1. 使用 parse_alert 解析告警，了解失败任务基本信息
    2. 并行执行: fetch_task_logs (拉取日志) + analyze_impact (分析下游影响)
    3. 使用 select_skill 根据 taskType 选择分析 Skill
    4. 调用 Skill.analyze() 获取错误分析结果
    5. 如需要，使用 enhance_analysis 拉取 Spark History/YARN 日志
    6. 使用 search_knowledge 搜索已确认的知识库
    
    ## 决策阶段
    7. 使用 LLM 整合分析结果，生成修复方案
    
    8. **使用 assess_risk 进行自动风险评估**:
       - 判断修复操作的风险等级
       - 低风险: 配置调整、简单脚本修改 → 自动执行
       - 高风险: 删除操作、影响多个下游 → 需审批
    
    ## 自动修复（低风险）
    9a. 使用 modify_workflow_config 自动修改配置参数
        - 如: 增加 Executor 内存 spark.executor.memory=4g
        - 如: 修改 Shell 脚本的拼写错误
    10a. 使用 recover_workflow 自动恢复失败任务
    11a. 使用 send_notification 发送成功通知
    
    ## 审批流程（高风险）
    9b. 使用 request_approval 发起审批请求
    10b. 使用 send_notification 发送审批通知，等待人工确认
    
    ## 风险等级判断规则
    - LOW: 配置参数调整（内存、并发数等）
    - LOW: 简单脚本拼写错误修正
    - MEDIUM: 依赖包上传、环境变量修改
    - HIGH: 删除任务、修改任务依赖关系
    - CRITICAL: 删除工作流、跨项目修改
    
    注意:
    - 自动修复前必须先评估风险
    - 自动修复后需监控执行状态
    - 高风险操作必须等待审批
    """
```

**告警处理流程图**:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Alert Agent 处理流程                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        分析阶段                                      │    │
│  │                                                                      │    │
│  │  1. parse_alert (解析告警)                                           │    │
│  │     │                                                                │    │
│  │     ▼                                                                │    │
│  │  2. 并行执行:                                                        │    │
│  │     ├── fetch_task_logs (拉取 DS 任务日志)                           │    │
│  │     └── analyze_impact (分析下游影响)                                │    │
│  │     │                                                                │    │
│  │     ▼                                                                │    │
│  │  3. select_skill (根据 taskType 选择 Skill)                         │    │
│  │     │                                                                │    │
│  │     ├─── SPARK ────→ SparkSkill.analyze()                           │    │
│  │     ├─── SHELL ────→ ShellSkill.analyze()                           │    │
│  │     ├─── PYTHON ───→ PythonSkill.analyze()                          │    │
│  │     ├─── DATAX ────→ DataXSkill.analyze()                           │    │
│  │     └─── 其他 ─────→ DefaultSkill.analyze()                         │    │
│  │     │                                                                │    │
│  │     ▼                                                                │    │
│  │  4. 如需要: enhance_analysis (SparkSkill 可拉取额外日志)             │    │
│  │     │                                                                │    │
│  │     ▼                                                                │    │
│  │  5. search_knowledge (搜索已确认知识库)                              │    │
│  │     │                                                                │    │
│  │     ▼                                                                │    │
│  │  6. LLM 整合分析结果 → 生成修复方案                                  │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        决策阶段                                      │    │
│  │                                                                      │    │
│  │  7. assess_risk (自动风险评估)                                       │    │
│  │     │                                                                │    │
│  │     ├─────────────────────────────────────────┐                     │    │
│  │     │                                         │                     │    │
│  │     │  LOW/MEDIUM (低风险)                    │  HIGH/CRITICAL (高风险)│    │
│  │     │                                         │                     │    │
│  │     ▼                                         ▼                     │    │
│  │  ┌───────────────────────────────┐   ┌───────────────────────────────┐ │    │
│  │  │     自动修复流程               │   │     审批流程                   │ │    │
│  │  │                               │   │                               │ │    │
│  │  │  8a. modify_workflow_config   │   │  8b. request_approval         │ │    │
│  │  │      (自动修改配置参数)         │   │      (发起审批请求)           │ │    │
│  │  │      │                        │   │      │                        │ │    │
│  │  │      ▼                        │   │      ▼                        │ │    │
│  │  │  9a. recover_workflow         │   │  9b. send_notification        │ │    │
│  │  │      (自动重跑失败任务)         │   │      (发送审批通知)           │ │    │
│  │  │      │                        │   │      │                        │ │    │
│  │  │      ▼                        │   │      ▼                        │ │    │
│  │  │  10a. send_notification       │   │  10b. 等待人工审批结果         │ │    │
│  │  │      (发送成功通知)            │   │                               │ │    │
│  │  │                               │   │                               │ │    │
│  │  └───────────────────────────────┘   └───────────────────────────────┘ │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Chat Agent (`src/agent/chat_agent.py`)

**职责**: 对话交互，理解用户意图并执行操作

```python
class ChatAgent:
    """
    对话交互 Agent
    
    ★ Agent 特征:
    1. 使用 LLM 理解用户意图
    2. 从对话中提取参数
    3. 构建 CLI 命令
    4. 评估风险决定执行还是审批
    
    工具集:
    - understand_intent: 理解用户意图
    - extract_parameters: 提取参数
    - build_cli_command: 构建 CLI 命令
    - assess_risk: 评估风险等级
    - execute_cli_command: 执行 CLI 命令
    - request_approval: 发起审批
    - reply_to_user: 回复用户
    
    支持的意图:
    - run_workflow: "运行 a项目的工作流xxx"
    - backfill: "补数日期 2026-01-01 到 2026-01-10"
    - query_status: "工作流xxx现在什么状态"
    - query_logs: "查看工作流xxx的最新日志"
    - recover_failure: "恢复工作流xxx的失败任务"
    - analyze_lineage: "分析表xxx的上下游血缘"
    """
    
    tools = [
        understand_intent_tool,
        extract_parameters_tool,
        build_cli_command_tool,
        assess_risk_tool,
        execute_cli_command_tool,
        request_approval_tool,
        reply_to_user_tool,
    ]
```

---

## 六、Skills 详细设计（anthropics/skills 规范）

### 6.1 Skills 架构概述

Skills 模块重构为 [anthropics/skills](https://github.com/anthropics/skills) 规范格式：

**核心变化：**

| 原实现 | 新设计 | 改进 |
|--------|--------|------|
| Python 类硬编码模式 | SKILL.md + patterns.md | 人可编辑维护 |
| ShellSkill 370+ 行拼写映射 | **移除** | 减少 token 消耗 |
| 固定前200后300行日志 | 智能预处理（日志降噪） | 提取关键信息 |
| 无超时分析 | timeout-analyzer Skill | 报错重试 + 资源等待 |
| 无历史数据支撑 | 每日采集任务指标 | 超时分析、频率统计 |

### 6.2 Skill 目录结构

每个 Skill 参考 pdf skill 结构：

```
skills/
├── spark-error-analyzer/
│   ├── SKILL.md              # 工作流定义（<100 lines）
│   ├── spark_patterns.md     # 错误模式表（Markdown 表格）
│   └── scripts/
│       ├── match_error.py    # 匹配脚本（读取 MD，输出 JSON）
│       ├── analyze_traceback.py  # 堆栈深度解析
│       ├── build_fix.py      # 构建修复方案
│       └── calculate_resource.py # 资源建议（最高2倍）
│
├── common/                   # 公共模块（所有 Skill 共用）
│   ├── preprocess_log.py     # 日志降噪（智能提取配置、错误块）
│   ├── extract_context.py    # IP/域名/HDFS 提取
│   └── cluster_lookup.py     # 集群配置关联
│
└── registry.py               # 统一注册表
```

### 6.3 SKILL.md 格式示例

```markdown
---
name: spark-error-analyzer
description: Analyze Spark task execution errors. Use when SPARK task fails.
---

# Spark Error Analyzer

## Quick Reference

| Category | Example Patterns | Action |
|----------|------------------|--------|
| OOM | `OutOfMemoryError` | AUTO_FIXABLE |
| ClassNotFound | `ClassNotFoundException` | KNOWN_NEEDS_LLM |
| Shuffle | `FetchFailedException` | KNOWN_NEEDS_LLM |

## Workflow

1. Run `common/preprocess_log.py` (日志降噪)
2. Run `scripts/match_error.py --patterns spark_patterns.md`
3. If AUTO_FIXABLE → `scripts/build_fix.py`
4. Output JSON with error_type, fix, llm_hint
```

### 6.4 日志降噪（preprocess_log.py）

```python
def preprocess_log(log_content: str) -> Dict:
    """智能提取关键信息，替代固定前200后300行"""
    return {
        'config_lines': [],      # Spark/Hadoop 配置
        'error_blocks': [],      # 完整错误堆栈
        'resource_stats': [],    # 资源统计
        'data_metrics': {},      # 数据量（Spark Event Log）
        'app_info': {}           # Application ID
    }

    # 效果：500 行 → 20-50 行关键信息
```

### 6.5 数据量检测（从日志提取）

```python
def extract_data_metrics_from_event_log(event_log: str) -> Dict:
    """从 Spark Event Log 提取数据量"""
    return {
        'input_bytes': ...,      # 输入数据量
        'output_bytes': ...,     # 输出数据量
        'shuffle_read_bytes': ...,# Shuffle 读
        'shuffle_write_bytes': ...,# Shuffle 写
        'memory_spilled': ...,   # Spill 到磁盘（关键）
        'stage_metrics': [...]   # Stage 级别指标
    }
```

### 6.6 超时分析（timeout-analyzer）

**触发超时的两个原因：**

| 原因 | 分析方式 | 定位 |
|-----|---------|-----|
| 任务报错重试 | retry_count > 0 + 错误类型 | 哪个任务报错 |
| 资源等待 | queue_wait_time vs 历史（7天） | 集群资源竞争 |

```python
def analyze_timeout_alert(workflow_code: str) -> Dict:
    # 原因1: 任务报错重试
    if task['retry_count'] > 0:
        return {'type': 'task_error_retry', 'task': ..., 'error_type': ...}
    
    # 原因2: 资源等待
    if task['queue_wait_time'] > avg_queue_wait * 2:
        return {'type': 'resource_waiting', 'cluster_utilization': ...}
```

### 6.7 知识库增强（项目历史）

```
data/knowledge_base/projects/{workflow_code}/spark_errors.md

| 错误类型 | 发生时间 | 原配置 | 修复配置 | 结果 |
|---------|---------|-------|---------|-----|
| oom_executor | 2026-05-10 | 2g | 4g | ✅ SUCCESS |

匹配优先级：项目历史 > 通用知识 > LLM 分析
```

### 6.8 资源建议（最高2倍）

```python
def calculate_resource_suggestion(error_type: str, current: Dict, historical: List):
    # 1. 优先历史成功配置
    # 2. 默认翻倍（上限2倍）
    # 3. 检查集群上限
    suggested = min(current * 2, cluster_limit)
```

### 6.9 堆栈深度解析

```python
def parse_python_traceback(log: str) -> Dict:
    return {
        'error_type': 'KeyError',
        'error_message': "'column_name'",
        'call_chain': [
            {'file': '/app/transform.py', 'line': 45, 'function': 'process_data'}
        ],
        'root_cause': {'file': 'transform.py', 'line': 45}
    }
```

### 6.10 每日数据采集

```python
def collect_daily_task_metrics(date: str):
    """采集任务执行指标"""
    return {
        'queue_wait_time': ...,  # 提交→开始运行
        'exec_duration': ...,    # 真实执行时长
        'requested_memory': ...,# 请求内存
        'retry_count': ...       # 重试次数
    }
    # 存储: data/metrics/{date}.json
```

---

## 七、自动风险评估与修复

### 7.1 风险等级定义 (`src/security/risk_assessor.py`)

```python
class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"           # 低风险: 配置调整、简单脚本修改
    MEDIUM = "medium"     # 中风险: 依赖上传、环境变量修改
    HIGH = "high"         # 高风险: 删除任务、修改依赖关系
    CRITICAL = "critical" # 严重风险: 删除工作流、跨项目修改

class RiskAssessor:
    """
    风险评估器
    
    根据修复动作评估风险等级:
    
    自动修复动作的风险判定:
    | 修复动作 | 风险等级 | 说明 |
    |----------|----------|------|
    | 修改内存配置 | LOW | 只影响当前任务，可回滚 |
    | 修改并发数配置 | LOW | 只影响当前任务，可回滚 |
    | 修正脚本拼写错误 | LOW | 小改动，影响范围小 |
    | 上传依赖包 | MEDIUM | 可能影响其他任务 |
    | 修改环境变量 | MEDIUM | 可能影响其他任务 |
    | 修改任务依赖关系 | HIGH | 影响工作流结构 |
    | 删除任务 | HIGH | 不可逆操作 |
    | 删除工作流 | CRITICAL | 严重影响，需审批 |
    """
    
    def assess_fix_action(self, action: AutoFixAction, impact: ImpactReport) -> RiskAssessment:
        """评估修复动作的风险"""
        risk_level = self._get_action_risk(action.action_type)
        
        # 考虑下游影响
        if impact.impact_level == ImpactLevel.CRITICAL:
            risk_level = max(risk_level, RiskLevel.HIGH)
        
        return RiskAssessment(
            risk_level=risk_level,
            affected_downstream=impact.affected_workflow_count,
            requires_approval=risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL],
        )
```

### 7.2 自动修复执行 (`src/agent/tools/autofix_tools.py`)

```python
class AutoFixExecutorTool(BaseTool):
    """
    自动修复执行器
    
    执行步骤:
    1. 根据修复动作类型调用对应工具
    2. modify_config: 修改工作流配置参数
    3. modify_script: 修改任务脚本内容
    4. 执行后记录变更日志
    """
    
    name = "execute_auto_fix"
    
    def _run(self, action: AutoFixAction, workflow_code: int, task_code: int) -> FixResult:
        """执行自动修复"""
        if action.action_type == "modify_config":
            # 调用 dsctl 修改配置
            return self._modify_workflow_config(workflow_code, task_code, action.config_changes)
        elif action.action_type == "modify_script":
            # 调用 dsctl 修改脚本
            return self._modify_task_script(task_code, action.script_changes)
```

---

## 八、钉钉/飞书交互设计

### 8.1 自动修复成功通知

```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "告警自动修复成功",
    "text": "### 任务失败告警 - 已自动修复\n\n**项目**: ad_monitor\n**工作流**: spark_sync\n**任务**: sync_task\n**失败时间**: 2026-05-06 14:30:00\n\n---\n\n### 错误分析\n\n**错误类型**: SparkOutOfMemoryError (Executor OOM)\n**分析**: Executor 内存不足\n\n---\n\n### 自动修复\n\n**风险等级**: 低风险\n**修复动作**: 自动调整配置\n- spark.executor.memory: 2g → 4g\n\n**修复结果**: 已自动重跑任务\n\n---\n\n### 执行结果\n\n**状态**: 成功\n**重跑时间**: 14:35:00\n**耗时**: 5 分钟\n\n---\n\n### 下游影响\n\n**影响工作流**: 0 个（无下游依赖）"
  }
}
```

### 8.2 高风险审批请求通知

```json
{
  "msgtype": "actionCard",
  "actionCard": {
    "title": "高风险操作审批",
    "text": "### 待审批操作\n\n**操作类型**: 删除工作流\n**风险等级**: 严重风险\n**工作流**: deprecated_workflow\n**影响范围**: 下游 3 个工作流依赖此工作流\n\n---\n\n### 错误背景\n\n此工作流已废弃，建议删除以清理资源。\n\n---\n\n### 审批请求\n\n此操作风险较高，需要管理员审批。",
    "btnOrientation": "1",
    "btns": [
      {"title": "批准 ✓", "actionURL": "http://agent-api/approval/xxx?type=approve"},
      {"title": "拒绝 ✗", "actionURL": "http://agent-api/approval/xxx?type=reject"}
    ]
  }
}
```

---

## 九、实现优先级

### Phase 1: 基础框架 (第1-2周)

1. 项目结构搭建
2. Dispatcher 实现（预定义规则）
3. 配置模块实现
4. DS CLI 集成 (dsctl 调用)

### Phase 2: Alert Agent 核心 (第3-4周)

1. Alert Agent 实现（分析流程）
2. 4 个主要 Skills 实现
3. Spark History/YARN 集成

### Phase 3: 自动修复能力 (第5-6周)

1. RiskAssessor 实现
2. AutoFixExecutor 实现
3. 自动修改配置功能
4. 自动重跑功能

### Phase 4: Chat Agent (第7-8周)

1. Chat Agent 实现
2. 意图理解和参数提取
3. CLI 命令构建

### Phase 5: 知识库与通知 (第9-10周)

1. Knowledge Manager 实现
2. 钉钉/飞书 Bot 集成
3. 反馈处理机制

### Phase 6: 审批流程 (第11-12周)

1. Approval Workflow 实现
2. 审批 API 实现
3. 审批结果处理

---

## 十、总结

### 核心架构

| 组件 | 类型 | 数量 | 说明 |
|------|------|------|------|
| Dispatcher | 函数 | 1 | 请求分发（预定义规则） |
| Agent | LLM 驱动 | 2 | AlertAgent + ChatAgent |
| Skill | 预定义规则 | 4 | Spark/Shell/Python/DataX |
| Tool | 功能实现 | 10+ | CLI、API、通知等 |

### Alert Agent 核心能力

1. **自动分析**: 日志分析 + 下游影响分析
2. **自动风险评估**: 判断修复操作风险等级
3. **自动修复**:
   - 低风险: 自动调整配置 + 自动重跑
   - 高风险: 发起审批等待人工确认
4. **自动通知**: 成功/失败/审批通知

### 关键设计决策

| 决策 | 原因 |
|------|------|
| Dispatcher 不用 LLM | 告警有固定字段，简单规则即可判断 |
| Skills 不用 LLM | 错误分析有固定模式，预定义规则更可靠 |
| 自动风险评估 | 不同错误类型有不同的风险等级 |
| 低风险自动修复 | OOM 等常见错误可自动调整配置并重跑 |
| 高风险审批流程 | 删除等高风险操作必须人工确认 |