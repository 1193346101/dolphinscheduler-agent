# DolphinScheduler Agent 全面测试计划

## 一、告警处理流程测试

### 1.1 日志获取层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| DS API 日志拉取 | dsctl log fetch 参数和返回 | 正确获取日志内容 |
| YARN Container 日志 | YARNLogTool.fetch_container_log | 获取 stdout/stderr |
| Spark History 日志 | SparkHistTool.fetch_logs | 获取 Driver/Executor 日志 |
| 日志智能截取 | smart_extract (首尾+错误块) | 不遗漏关键错误 |

### 1.2 日志预处理层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| 错误块提取 | extract_error_blocks | 正确识别 ERROR/FATAL 块 |
| 配置行提取 | extract_config_lines | 提取 spark.* 配置 |
| Executor事件提取 | extract_executor_events | Executor 生命周期事件 |
| StackTrace 归属 | 错误栈归属到正确位置 | 准确定位错误源 |

### 1.3 错误分析层 (Skills)
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| Spark OOM | spark.analyzer OOM诊断 | 建议调整内存配置 |
| Spark Shuffle失败 | shuffle service错误识别 | 识别shuffle失败原因 |
| DataX同步失败 | datax参数解析、表不存在 | 定位输入/输出表问题 |
| Hive SQL错误 | SQL语法错误、分区不存在 | 识别SQL问题 |
| HDFS路径问题 | OSS验证器检查路径 | 检测分区缺失 |
| 资源配置问题 | ResourceMetrics分析 | 识别配置瓶颈 |
| ClassNotFound | 依赖缺失诊断 | 建议添加依赖 |
| 权限问题 | 认证失败诊断 | 识别权限配置 |

### 1.4 错误报告层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| HTML报告生成 | ReportGenerator | 格式完整、可读性强 |
| 风险评估 | RiskAssessTool | 正确评估风险等级 |
| 下游影响分析 | GraphImpactTool | 分析受影响工作流 |
| 建议准确性 | 修复建议与实际匹配 | 建议可执行且有效 |

### 1.5 复杂错误场景
| 场景 | 验证内容 | 预期结果 |
|------|----------|----------|
| 多错误叠加 | 日志包含多个不同错误 | 分离并独立分析 |
| 错误链分析 | 错误A导致错误B导致错误C | 识别根因和传播链 |
| 跨任务错误 | 当前任务错误影响下游 | 分析血缘影响范围 |
| 隐藏错误 | INFO日志中隐藏关键信息 | 深度挖掘潜在问题 |

---

## 二、血缘关系流程测试

### 2.1 数据获取层 (dsctl)
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| list_workflows | 获取工作流列表 | 正确解析返回JSON |
| describe_workflow | 获取工作流详情 | 任务、依赖、参数完整 |
| list_schedules | 获取调度信息 | cron表达式正确解析 |
| project解析 | resolve项目名到code | 正确映射 |

### 2.2 代码解析层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| jar包名提取 | extract_project_from_jar | 正确提取项目名 |
| 类文件搜索 | CodeSearcher.search_class | 找到正确路径 |
| SQL解析 | SQLParser.extract_tables | 输入/输出表准确 |
| Scala多行SQL | triple-quote SQL提取 | 不遗漏SQL块 |
| DataX JSON解析 | task_params解析 | 输入/输出表准确 |

### 2.3 血缘构建层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| 任务-表关系 | produces/consumes边 | 正确关联 |
| 类-任务映射 | class_maps_to_task | 类名对应任务 |
| 工作流依赖 | workflow_depends_workflow | DEPENDENT任务解析 |
| 隐式依赖检测 | ImplicitDependencyDetector | 检测表级隐式依赖 |

### 2.4 血缘验证层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| 工作流数量匹配 | 图谱 vs DS API | 100%匹配 |
| 任务数量匹配 | 图谱 vs DS API | 100%匹配 |
| 类映射准确率 | 类数 vs Spark任务数 | >90% |
| 输出表识别率 | produces边数 vs 实际 | >90% |
| 隐式依赖预警 | 检测未配置的依赖 | 准确预警 |

### 2.5 HTML展示层
| 测试项 | 验证内容 | 预期结果 |
|--------|----------|----------|
| 项目下拉框 | project_list.js加载 | 正确显示项目 |
| 血缘图渲染 | Mermaid DAG渲染 | 正确显示依赖 |
| 表血缘展示 | 输入/输出表展示 | 清晰展示关系 |
| ngrok外网访问 | 外网可访问HTML | 正常工作 |

---

## 三、测试执行方式

### 3.1 单元测试
```bash
pytest tests/ -v --tb=short
```

### 3.2 集成测试
```bash
python tests/integration/test_alert_flow.py
python tests/integration/test_lineage_flow.py
```

### 3.3 模拟场景测试
使用预设的模拟日志/错误场景测试分析准确度