# skills/shell-error-analyzer/SKILL.md
---
name: shell-error-analyzer
description: 分析 SHELL 任务执行错误并给出修复建议。当 SHELL 任务失败时触发，适用于语法错误、权限不足、文件不存在、连接被拒绝等。不要用于 SPARK、PYTHON 等其他任务类型。
---

# Shell 错误分析器

## 概述

通过日志预处理 + 模式匹配分析 Shell 脚本错误。

## 处理流程

### 步骤 1：日志预处理

```bash
python skills/common/preprocess_log.py --log "<日志内容>" --task-type SHELL
```

### 步骤 2：匹配错误模式

```bash
python scripts/match_error.py --patterns patterns.md --log "<error_blocks>"
```

### 步骤 3：增强上下文（连接/文件错误时）

```bash
python skills/common/extract_context.py --log "<error_blocks>" --cluster config/cluster_info.md
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 分析提示 |
|---------|---------|---------|
| syntax_error | `syntax error` | Shell 语法错误，分析具体位置 |
| unexpected_eof | `unexpected EOF` | Shell 文件意外结束，引号不闭合 |
| permission_denied | `Permission denied` | Shell 权限不足，检查文件权限 |
| no_such_file | `No such file or directory` | Shell 文件不存在，检查路径 |
| connection_refused | `Connection refused` | Shell 连接被拒绝，检查目标服务 |
| connection_timeout | `Connection timed out` | Shell 连接超时，检查网络 |

---

## 重要规则

1. 必须预处理日志
2. 增强服务上下文 - 连接错误时识别具体服务
3. 验证文件路径 - 文件错误时确认路径是否存在
4. 大多数错误需 LLM - Shell 很少可自动修复