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

### 5.3 Chat Agent (`src/chat/`)

**职责**: 对话交互，理解用户意图并执行操作

**核心重构 (2026-05-13)**:
- 移除死板的关键词匹配，改用纯 LLM 解析意图
- 危险操作（run_workflow, recover_failure）需要用户确认后才执行
- 查询操作直接执行，无需确认

#### 5.3.1 LangGraph 流程架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Chat Agent 处理流程                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  钉钉消息 → dingtalk_stream.py                                                │
│          ↓                                                                    │
│      ChatGraph.invoke(state)                                                  │
│          ↓                                                                    │
│      parse_intent_node（纯 LLM 解析，移除关键词匹配）                           │
│          ↓                                                                    │
│      route_intent()                                                           │
│          ↓                                                                    │
│      ┌─────────────────────────────────────┐                                 │
│      │ 危险操作（run_workflow/recover_failure）│                              │
│      │                                      │                                 │
│      │   → request_confirmation_node       │                                 │
│      │       ↓                              │                                 │
│      │   发送确认请求到钉钉                  │                                 │
│      │       ↓                              │                                 │
│      │   END（等待用户回复）                 │                                 │
│      │                                      │                                 │
│      │   用户回复"确认" → dingtalk_stream    │                                 │
│      │       ↓                              │                                 │
│      │   check_confirmation_node            │                                 │
│      │       ↓                              │                                 │
│      │   确认 → execute_node                │                                 │
│      │       ↓                              │                                 │
│      │   format_response_node → END         │                                 │
│      └─────────────────────────────────────┘                                 │
│                                                                               │
│      查询操作（query_workflow/query_status等）                                 │
│          ↓                                                                    │
│      直接执行 → format_response_node → END                                    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 5.3.2 状态定义 (ChatState)

```python
class ChatState(TypedDict, total=False):
    # Input Stage
    message: str                   # 用户消息
    user_id: str                   # 用户 ID
    conversation_id: str           # 会话 ID
    
    # Intent Parsing Stage
    intent_type: str               # 意图类型
    query_type: Optional[str]      # 血缘查询类型
    
    # Parameters Stage  
    workflow_code: Optional[str]   # 工作流编码
    workflow_name: Optional[str]   # 工作流名称
    project_name: Optional[str]    # 项目名称
    confirmation_params: Optional[Dict[str, Any]]  # 解析出的参数
    
    # Confirmation Stage（新增）
    pending_confirmation: bool     # 是否等待确认
    confirmation_message: Optional[str]  # 确认消息
    confirmed_action: Optional[str]      # 待确认操作
    confirmation_status: Optional[str]   # pending/confirmed/rejected
    confirmation_id: Optional[str]       # 确认 ID
    execute_approved: bool              # 执行已批准
    
    # Response Stage
    response_content: Optional[str]  # 响应内容
    error_message: Optional[str]     # 错误信息
```

#### 5.3.3 意图解析节点 (parse_intent_node)

**纯 LLM 解析，移除关键词匹配**：

```python
def parse_intent_node(state: ChatState) -> ChatState:
    """
    解析用户消息意图（纯 LLM 解析模式）
    
    流程:
    1. 直接使用 LLM 解析意图
    2. 上下文参数补全
    3. 记录对话记忆
    """
    message = state.get("message", "")
    
    # 纯 LLM 解析（移除关键词匹配）
    result = parse_with_llm(message, context_summary)
    
    return {
        **state,
        "intent_type": result.get("intent_type", "unknown"),
        "workflow_code": result.get("workflow_code"),
        "workflow_name": result.get("workflow_name"),
        "project_name": result.get("project_name"),
        "confirmation_params": result.get("params", {}),  # 保存参数供确认流程使用
    }
```

**LLM Prompt 设计**：

```
分析用户消息，理解用户意图，返回 JSON。

支持的意图类型：
1. run_workflow - 执行/运行工作流（关键词: 执行、运行、启动）
2. query_workflow - 查询工作流列表（关键词: 工作流列表、有哪些工作流）
3. query_workflow_instances - 查工作流实例（关键词: 实例、执行了、运行记录）
4. query_status - 查询工作流状态（关键词: 状态、运行情况）
5. recover_failure - 恢复失败工作流（关键词: 恢复、重跑）
...

返回 JSON:
{
  "intent_type": "意图类型",
  "workflow_code": "工作流编码（数字）",
  "workflow_name": "工作流名称",
  "project_name": "项目名称",
  "params": {"worker_group": "all_worker", "tenant": "项目名称"}
}
```

#### 5.3.4 确认流程节点

**request_confirmation_node**: 发送确认请求

```python
def request_confirmation_node(state: ChatState) -> ChatState:
    """请求用户确认节点"""
    intent_type = state.get("intent_type")
    params = state.get("confirmation_params", {})
    
    # 构建确认消息
    confirmation_msg = build_confirmation_message(intent_type, params)
    
    # 生成确认 ID
    confirmation_id = f"confirm_{user_id}_{uuid.uuid4().hex[:8]}"
    
    # 发送钉钉确认消息
    dingtalk.send_notification(
        title=f"操作确认 - {intent_type}",
        content=confirmation_msg,
    )
    
    return {
        **state,
        "pending_confirmation": True,
        "confirmation_id": confirmation_id,
        "confirmation_status": "pending",
    }
```

**check_confirmation_node**: 检查确认状态

```python
def check_confirmation_node(state: ChatState) -> ChatState:
    """检查用户确认状态"""
    confirmation_status = state.get("confirmation_status", "pending")
    
    if confirmation_status == "confirmed":
        return {...state, "execute_approved": True}
    elif confirmation_status == "rejected":
        return {...state, "response_content": "操作已取消"}
```

#### 5.3.5 执行节点检查确认状态

**run_workflow_node / recover_failure_node**: 执行前检查确认

```python
def run_workflow_node(state: ChatState) -> ChatState:
    """手动运行工作流"""
    execute_approved = state.get("execute_approved", False)
    
    if not execute_approved:
        return {
            **state,
            "response_content": "❌ 操作未获批准，未执行。请先发送运行指令并确认。",
        }
    
    # 执行工作流...
```

#### 5.3.6 钉钉确认回复处理

**dingtalk_stream.py**: 处理用户确认/取消回复

```python
async def process(self, callback_message: CallbackMessage):
    content = message.get_text_list()[0]
    
    # 检查是否是确认/取消回复
    if content.strip() in ["确认", "✅", "同意", "执行"]:
        # 查找用户的待确认请求
        pending_state = get_pending_confirmation_by_user(user_id)
        update_confirmation_status(confirmation_id, "confirmed")
        # 重新执行流程
        result_state = self.chat_graph.invoke(pending_state)
    
    elif content.strip() in ["取消", "❌", "拒绝"]:
        update_confirmation_status(confirmation_id, "rejected")
        self.reply_markdown("操作取消", "❌ 操作已取消")
```

#### 5.3.7 支持的意图类型

| 意图 | 示例 | 是否需要确认 | 说明 |
|------|------|-------------|------|
| run_workflow | "执行 ad_monitor 的 agent-test 工作流" | ✅ 需要 | 危险操作 |
| recover_failure | "恢复实例 123456" | ✅ 需要 | 危险操作 |
| query_workflow | "ad_monitor 有哪些工作流" | ❌ 不需要 | 查询操作 |
| query_workflow_instances | "今天运行了哪些工作流" | ❌ 不需要 | 查询操作 |
| query_status | "工作流 12345 的状态" | ❌ 不需要 | 查询操作 |
| query_logs | "查看实例 123456 的日志" | ❌ 不需要 | 查询操作 |
| scan_graph | "扫描 ad_monitor 图谱" | ❌ 不需要 | 查询操作 |
| lineage_query | "工作流 12345 的下游" | ❌ 不需要 | 查询操作 |

#### 5.3.8 默认参数规则

| 参数 | 默认值 | 说明 |
|------|--------|------|
| worker_group | all_worker | 默认 Worker 组 |
| tenant | project_name | 默认租户为项目名称（如 ad_monitor 项目用 ad_monitor 租户） |

#### 5.3.9 文件结构

```
src/chat/
├── state.py                    # ChatState 定义（含确认字段）
├── graph.py                    # LangGraph 流程定义（含确认路由）
├── nodes/
│   ├── parse_intent.py         # 意图解析节点（纯 LLM）
│   ├── request_confirmation.py # 请求确认节点（新增）
│   ├── check_confirmation.py   # 检查确认节点（新增）
│   ├── run_workflow.py         # 运行工作流节点（检查确认）
│   ├── recover_failure.py      # 恢复失败节点（检查确认）
│   └── ...其他节点
└── tools/
    └── intent_context.py       # 多轮对话上下文管理

src/integrations/
└── dingtalk_stream.py          # 钉钉 Stream（处理确认回复）
```
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

## 七、Token 消耗统计

### 7.1 Token 消耗追踪

Agent 在执行过程中会自动追踪 LLM Token 消耗，并在通知中展示。

**统计位置**：

| 模块 | 文件 | Token 追踪 |
|------|------|------------|
| `workflow/state.py` | AgentState | `token_consumption`, `token_details` |
| `chat/state.py` | ChatState | `token_consumption`, `token_details` |
| `tools/llm_client.py` | LLMClient | `MODEL_TOKEN_RULES`, `count_tokens()` |

### 7.2 模型 Tokenizer 规则配置

**根据配置的模型选择对应的 tokenizer**：

```python
MODEL_TOKEN_RULES = {
    # OpenAI GPT 系列：使用 tiktoken（精确计算）
    "gpt-4": {"type": "tiktoken", "encoding": "cl100k_base"},
    "gpt-4o": {"type": "tiktoken", "encoding": "o200k_base"},
    "gpt-3.5-turbo": {"type": "tiktoken", "encoding": "cl100k_base"},

    # Claude 系列：估算（Anthropic 未公开 tokenizer）
    "claude-3-opus": {"type": "estimate", "chinese_ratio": 1.5, "english_ratio": 4},
    "claude-3-sonnet": {"type": "estimate", "chinese_ratio": 1.5, "english_ratio": 4},
    "claude-sonnet-4-6": {"type": "estimate", "chinese_ratio": 1.5, "english_ratio": 4},

    # GLM 系列：估算（智谱未公开 tokenizer，中文略好）
    "glm-4": {"type": "estimate", "chinese_ratio": 1.2, "english_ratio": 4},
    "glm-5": {"type": "estimate", "chinese_ratio": 1.2, "english_ratio": 4},

    # 默认
    "default": {"type": "estimate", "chinese_ratio": 1.5, "english_ratio": 4},
}
```

### 7.3 Token 计算函数

```python
def count_tokens(text: str, model: str) -> int:
    """
    根据模型计算 Token 数量

    优先级：
    1. 使用 tiktoken（如果模型支持且已安装）
    2. 使用模型特定的估算规则
    3. 使用默认估算规则
    """
    rule = MODEL_TOKEN_RULES.get(model, MODEL_TOKEN_RULES["default"])

    if rule["type"] == "tiktoken":
        import tiktoken
        enc = tiktoken.get_encoding(rule["encoding"])
        return len(enc.encode(text))
    else:
        return estimate_tokens(text, rule["chinese_ratio"], rule["english_ratio"])
```

### 7.4 API 真实 Token 获取

优先获取 API 返回的真实 Token 使用量：

```python
# Anthropic 格式
usage = response.json().get("usage", {})
input_tokens = usage.get("input_tokens", 0)
output_tokens = usage.get("output_tokens", 0)

# OpenAI 格式（备用）
input_tokens = usage.get("prompt_tokens", 0)
output_tokens = usage.get("completion_tokens", 0)
```

### 7.5 LLM 调用点与 Token 消耗

**告警流程 (Alert Agent)**：

| 节点 | LLM 调用条件 | Token 消耗范围 |
|------|--------------|----------------|
| `analyze` | AUTO_FIXABLE | 0 tokens |
| `analyze` | RESOURCE_SUGGESTED | ~1500-2000 tokens |
| `analyze` | KNOWN_NEEDS_LLM | ~1500-2000 tokens |
| `analyze` | UNKNOWN | ~3000 tokens |
| 其他节点 | 无 LLM 调用 | 0 tokens |

**对话流程 (Chat Agent)**：

| 节点 | LLM 调用条件 | Token 消耗范围 |
|------|--------------|----------------|
| `parse_intent` | 明确关键词 | 0 tokens |
| `parse_intent` | 模糊表达 | ~400-900 tokens |
| `parse_intent` | 多轮对话 | ~500-1000 tokens/轮 |
| 其他节点 | 无 LLM 调用 | 0 tokens |

### 7.6 通知展示

钉钉通知中会显示 Token 消耗统计：

```
### Token 消耗
- **总计:** 1800 tokens
- **analyze_resource:** input=1200, output=600
```

---

## 八、错误分析报告

### 8.1 报告生成功能

**设计目标**: 生成完整的错误分析报告，让用户验证 Agent 分析逻辑是否正确。

**文件位置**：

| 文件 | 功能 |
|------|------|
| `tools/report_generator.py` | 生成 HTML + JSON 格式报告 |
| `api/report_api.py` | 报告查看 API 端点 |

### 8.2 报告存储目录

```
data/reports/
└── 2026-05-13/                 # 按日期分组
    └── 12345/                   # 工作流 code
        └── report_143022_111/   # 报告 ID（时间+task_code）
            ├── report.html      # HTML 页面（用户友好）
            └── report.json      # JSON 数据（程序可解析）
```

### 8.3 报告内容

| 章节 | 内容 |
|------|------|
| 基本信息 | 项目、工作流、任务、实例 ID |
| 分析流程 | 每个节点的输入/输出 |
| 错误分析 | Skill 预判结果、LLM 分析结果、错误类型、分析过程、推理依据 |
| 资源数据 | Driver 日志配置、YARN ResourceManager、Spark History Server 数据 |
| 风险评估 | 风险等级、下游任务数、风险因素 |
| 修复建议 | 动作类型、配置变更 |
| 执行结果 | 执行状态、命令输出 |
| Token 消耗 | 总消耗、各节点明细 |

### 8.4 报告 API 端点

```
GET /report/list                    # 报告列表
GET /report/{report_id}             # 查看报告（HTML）
GET /report/{report_id}/json        # 查看报告（JSON）
```

### 8.5 钉钉通知集成

通知底部添加报告链接：

```
### 📋 详细分析报告
[点击查看完整分析报告](http://host:port/report/{report_id})
```

---

## 九、自动风险评估与修复

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