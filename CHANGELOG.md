# DolphinScheduler Agent 变更日志

## [2026-05-13] Chat 模块重构 + Token 消耗统计 + 真实资源数据获取 + 错误分析报告

### Chat 模块重构（LLM-first 意图解析 + 用户确认流程）

#### 核心改动
- **移除关键词匹配**: `parse_intent_node` 改为纯 LLM 解析，不再依赖 `IntentParser` 关键词匹配
- **用户确认流程**: 危险操作（run_workflow, recover_failure）需要用户确认后才执行
- **默认参数规则**: worker_group="all_worker", tenant=project_name

#### 新增文件
- **request_confirmation.py**: 发送钉钉确认请求，存储待确认请求
- **check_confirmation.py**: 检查用户确认状态，设置 execute_approved

#### 修改文件
- **state.py**: 新增确认相关字段（pending_confirmation, confirmation_status, execute_approved 等）
- **parse_intent.py**: 重构为纯 LLM 解析，移除 IntentParser 调用
- **graph.py**: 新增确认流程路由（run_workflow → request_confirmation → check_confirmation → execute）
- **dingtalk_stream.py**: 处理用户"确认"/"取消"回复，更新确认状态并重新执行流程
- **run_workflow.py**: 执行前检查 execute_approved，使用 worker_group 和 tenant 参数
- **recover_failure.py**: 执行前检查 execute_approved
- **nodes/__init__.py**: 导出新节点

#### 修复
- **llm_client.py**: 修复 f-string 格式化报错（`{"ech hello": "echo hello"}` 导致 ValueError）

### 新增功能

#### 错误分析报告（新增）
- **report_generator.py**: 生成完整的错误分析报告（HTML + JSON）
  - 包含分析过程、Skill 预判结果、LLM 验证、资源数据、风险评估
  - 用户可通过链接查看详细分析过程，验证 Agent 分析逻辑
- **report_api.py**: 提供报告查看 API
  - `GET /report/{report_id}`: 查看报告（支持 html/json 格式）
  - `GET /report/list`: 列出报告列表
- **state.py**: 新增 `report_id`, `report_url` 字段
- **notify.py**: 钉钉通知底部添加"详细分析报告"链接

#### Token 消耗统计
- **state.py**: 新增 `token_consumption` 和 `token_details` 字段追踪 LLM 消耗
- **llm_client.py**: 
  - 新增 `MODEL_TOKEN_RULES` 定义不同模型的 tokenizer 规则
  - 新增 `count_tokens(text, model)` 根据模型计算 Token
  - 解析 API 返回的 `usage` 字段获取真实 Token 消耗
- **notify.py**: 钉钉通知底部显示 Token 消耗统计

#### 真实资源数据获取
- **resource_metrics.py**: 从 YARN ResourceManager 和 Spark History Server 获取真实资源数据
  - `fetch_yarn_app_info()`: 获取容器资源使用、诊断信息
  - `fetch_spark_history_metrics()`: 获取 Executor metrics、Shuffle 数据量
  - `get_comprehensive_metrics()`: 综合所有数据源
- **settings.py**: 新增 `YARN_USERNAME`, `YARN_PASSWORD` 支持 LDAP 认证
- **.env**: 配置 YARN/Spark History URL 和认证信息

#### 按需调用 API
- **analyzer.py**: 只在以下情况调用 YARN/Spark History API：
  - 资源类问题（RESOURCE_SUGGESTED）
  - 日志信息不足（UNKNOWN）
  - error_blocks 为空

#### Driver 日志配置优先策略
- **analyzer.py**: 配置信息优先从 Driver 日志 `config_lines` 提取
  - `spark.driver.memory` → `driver_memory`
  - `spark.executor.memory` → `executor_memory`
  - History/YARN 仅用于深度分析补充（metrics、诊断信息）
  - 打印 `[SparkSkill] Driver config: {...}` 日志便于调试

#### 移除置信度系统
- **state.py**: 移除 `confidence_score` 字段定义和默认值
- **store.py**: 移除存储中的 `confidence_score` 字段
- **report_generator.py**: 移除报告中的置信度显示
- **analyze.py**: 改用 `error_category` 判断分析结果有效性
  - `if llm_result.get("error_category")` 替代 `if confidence > 0.7`

### 改进

#### calculate_resource.py 简化
- 只返回 DolphinScheduler UI 支持的 5 个参数：
  - `driver_memory`, `driver_cores`
  - `executor_memory`, `executor_cores`, `executor_instances`

#### 测试更新
- **test_llm_client.py**: 更新测试以匹配新的 API 响应格式

### 文档更新
- **architecture.md**: 新增 Chat 模块详细设计（5.3节），包含 LangGraph 流程、ChatState 定义、确认流程
- **宣讲文稿.md**: 更新 3.4 章节，新增 LLM-first 解析和用户确认流程说明
- **CHANGELOG.md**: 新建，记录所有历史改动

---

## [2026-05-12] Skills 模块重构

### 新增

- **pattern_matcher.py**: 公共模式匹配模块，从 patterns.md 解析错误模式
- **scripts/match_error.py**: Spark Skill 匹配脚本

### 改进

- **analyzer.py**: 移除硬编码模式表，使用 PatternMatcher
- **patterns.md**: 维护所有错误模式（人可编辑）

---

## [2026-05-11] 安全审计与命令防护

### 新增

- **CommandGuard**: CLI 命令安全检查
- **AuditLogger**: 操作审计日志

---

## [2026-05-08] 知识图谱集成

### 新增

- **GraphScanner**: 扫描项目工作流依赖
- **GraphQuerier**: 血缘查询（上游/下游）
- **SQLParser**: SQL 语句解析提取表名

---

## [2026-05-07] Alert Agent Phase 2

### 新增

- **workflow/state.py**: AgentState TypedDict 定义
- **workflow/nodes/**: 分析流程节点（parse, fetch_logs, analyze, risk, execute, notify）
- **integrations/dsctl_wrapper.py**: dsctl CLI 封装

---

## 初始版本 [2026-05-01]

- 基础 Alert Agent 框架
- Skills 模块（SparkSkill, ShellSkill, PythonSkill, DataXSkill）
- 钉钉机器人集成