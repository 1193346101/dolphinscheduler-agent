---
name: dependent
description: DEPENDENT 依赖检查失败追踪，递归查找依赖工作流中的失败任务
task_types:
  - DEPENDENT
version: "1.0.0"
---

# DEPENDENT Skill

## 功能

DEPENDENT 任务检查其他工作流的执行状态，如果依赖的工作流失败，
DEPENDENT 任务也会失败，但日志中只有"依赖检查失败"的信息。

本 Skill 实现：
1. 从日志中提取依赖的工作流列表
2. 分析依赖结果 (FAILED)
3. 给出追踪指引：需要查看哪个依赖工作流失败

## 错误模式

| error_type | pattern | 说明 |
|------------|---------|------|
| dependent_check_failed | Dependent result is: FAILED | 依赖检查失败 |
| dependent_waiting_timeout | timeout | 依赖等待超时 |

## 分析流程

```
DEPENDENT 日志
    ├── 提取 dependTaskList (依赖列表)
    ├── 提取每个依赖的 definitionCode
    ├── 分析依赖结果 (FAILED)
    └── 返回指引：查看哪个依赖工作流失败
```