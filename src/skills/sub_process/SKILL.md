---
name: sub_process
description: SUB_PROCESS 子工作流失败追踪，递归查找子工作流中的失败任务
task_types:
  - SUB_PROCESS
version: "1.0.0"
---

# SUB_PROCESS Skill

## 功能

SUB_PROCESS 任务失败时，日志中只有"子工作流执行失败"的提示，真正的错误在子工作流的任务日志中。

本 Skill 实现：
1. 从日志中提取子工作流的 definitionCode
2. 尝试调用 dsctl 获取子工作流的失败实例和失败任务
3. 如果无法连接 dsctl，给出明确的追踪指引

## 错误模式

| error_type | pattern | 说明 |
|------------|---------|------|
| sub_workflow_failed | FAILURE | 子工作流执行失败，需追踪子工作流日志 |

## 分析流程

```
SUB_PROCESS 日志
    ├── 提取 processDefinitionCode (子工作流定义)
    ├── 尝试 dsctl workflow-instance list 获取最近实例
    ├── 尝试 dsctl workflow-instance digest 获取失败任务
    ├── 尝试 dsctl task-instance log 获取失败任务日志
    └── 如无法连接，返回指引信息
```