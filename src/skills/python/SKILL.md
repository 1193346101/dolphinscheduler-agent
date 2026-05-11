---
name: python-error-analyzer
description: 分析 PYTHON 任务执行错误。当 PYTHON 任务失败时触发，适用于导入错误、语法错误、类型错误等。不要用于 SPARK、SHELL 等其他任务类型。
task_types:
  - PYTHON
version: "1.0.0"
---

# Python 错误分析器

## 概述

通过日志预处理 + 模式匹配分析 Python 脚本错误。

## 处理流程

### 步骤 1：日志预处理

```python
from skills.common.preprocess_log import preprocess_log

result = preprocess_log(log_content, task_type="python")
# 返回: config_lines, error_blocks, app_info, data_metrics, resource_stats
```

提取内容：
- **config_lines**: Python 相关配置行 (PYTHONPATH, virtualenv 等)
- **error_blocks**: 完整的错误堆栈块
- **app_info**: 应用信息
- **data_metrics**: 数据指标

### 步骤 2：解析 Traceback

调用 `scripts/analyze_traceback.py` 解析 Python traceback：

```python
from skills.python_error_analyzer.scripts.analyze_traceback import analyze_traceback

traceback_info = analyze_traceback(error_block)
# 返回: error_type, error_message, file_path, line_number, function_name, root_cause
```

解析内容：
- **Traceback (most recent call last):** 标记 traceback 开始
- **File "{file}", line {line}, in {function}:** 调用栈帧
- **错误类型和消息:** 最终错误（如 NameError: name 'x' is not defined）
- **root_cause:** 调用链中的最后一个（通常是实际出错位置）

### 步骤 3：匹配错误模式

调用 `scripts/match_error.py` 匹配已知错误模式：

```python
from skills.python_error_analyzer.scripts.match_error import match_error

match = match_error(error_blocks, patterns_file="patterns.md")
# 返回: error_type, category, pattern, llm_hint
```

模式分类：
- **AUTO_FIXABLE**: 可自动修复（如简单配置问题）
- **KNOWN_NEEDS_LLM**: 已知类型，需 LLM 分析
- **UNKNOWN**: 未知错误，完全交给 LLM

### 步骤 4：构建输出

根据匹配结果构建分析输出：

```json
{
  "error_type": "import_error",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "ModuleNotFoundError: No module named 'requests'",
  "targets": {
    "file_path": "/path/to/script.py",
    "line_number": 5,
    "function_name": "<module>"
  },
  "traceback": {
    "frames": [
      {"file": "/path/to/script.py", "line": 5, "function": "<module>", "code": "import requests"}
    ],
    "root_cause": {"file": "/path/to/script.py", "line": 5, "function": "<module>"}
  },
  "fix": null,
  "llm_hint": "Python 模块找不到，请分析缺失的模块名和安装方法"
}
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 分析提示 |
|---------|---------|---------|
| import_error | `ImportError\|ModuleNotFoundError` | Python 导入错误，检查模块是否安装 |
| module_not_found | `ModuleNotFoundError` | Python 模块找不到，需安装依赖 |
| syntax_error | `SyntaxError` | Python 语法错误，分析具体位置 |
| indentation_error | `IndentationError` | Python 缩进错误，检查缩进一致性 |
| type_error | `TypeError` | Python 类型错误，分析类型不匹配 |
| value_error | `ValueError` | Python 值错误，分析无效值 |
| key_error | `KeyError` | Python 键错误，检查字典键是否存在 |
| attribute_error | `AttributeError` | Python 属性错误，检查对象属性 |
| name_error | `NameError` | Python 名称错误，变量未定义 |
| index_error | `IndexError` | Python 索引错误，检查列表索引范围 |
| zero_division | `ZeroDivisionError` | Python 除零错误 |
| file_not_found | `FileNotFoundError` | Python 文件不存在，检查路径 |
| permission_error | `PermissionError\|Permission denied` | Python 权限错误 |
| connection_error | `ConnectionError\|Connection refused` | Python 连接错误 |
| timeout_error | `TimeoutError\|timeout` | Python 超时错误 |
| runtime_error | `RuntimeError` | Python 运行时错误 |

---

## 重要规则

1. 必须预处理日志
2. 解析完整 traceback - 提取所有调用栈帧
3. 识别 root_cause - traceback 中最后一个文件是出错位置
4. 大多数错误需 LLM - Python 错误通常需要代码分析

---

## Examples

### Example 1: ModuleNotFoundError

**Input Log:**
```
Traceback (most recent call last):
  File "/opt/script.py", line 5, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'
```

**Output:**
```json
{
  "error_type": "module_not_found",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "ModuleNotFoundError: No module named 'requests'",
  "targets": {
    "file_path": "/opt/script.py",
    "line_number": 5,
    "function_name": "<module>"
  },
  "traceback": {
    "frames": [
      {"file": "/opt/script.py", "line": 5, "function": "<module>", "code": "import requests"}
    ],
    "root_cause": {"file": "/opt/script.py", "line": 5, "function": "<module>"}
  },
  "fix": null,
  "llm_hint": "Python 模块找不到，请分析缺失的模块名和安装方法"
}
```

### Example 2: KeyError

**Input Log:**
```
Traceback (most recent call last):
  File "/opt/script.py", line 12, in process_data
    value = data['key']
  File "/opt/script.py", line 8, in main
    process_data(data)
KeyError: 'key'
```

**Output:**
```json
{
  "error_type": "key_error",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "KeyError: 'key'",
  "targets": {
    "file_path": "/opt/script.py",
    "line_number": 12,
    "function_name": "process_data"
  },
  "traceback": {
    "frames": [
      {"file": "/opt/script.py", "line": 12, "function": "process_data", "code": "value = data['key']"},
      {"file": "/opt/script.py", "line": 8, "function": "main", "code": "process_data(data)"}
    ],
    "root_cause": {"file": "/opt/script.py", "line": 12, "function": "process_data"}
  },
  "fix": null,
  "llm_hint": "Python 键错误，请检查字典键是否存在"
}
```

### Example 3: SyntaxError

**Input Log:**
```
  File "/opt/script.py", line 15
    if x = 5:
         ^
SyntaxError: invalid syntax. Maybe you meant '==' or ':=' instead of '='?
```

**Output:**
```json
{
  "error_type": "syntax_error",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "SyntaxError: invalid syntax. Maybe you meant '==' or ':=' instead of '='?",
  "targets": {
    "file_path": "/opt/script.py",
    "line_number": 15,
    "function_name": null
  },
  "traceback": {
    "frames": [],
    "root_cause": {"file": "/opt/script.py", "line": 15, "function": null}
  },
  "fix": null,
  "llm_hint": "Python 语法错误，分析具体位置和原因"
}
```

## Dependencies

- `skills/common/preprocess_log.py` - 日志预处理
- `skills/python-error-analyzer/scripts/match_error.py` - 模式匹配
- `skills/python-error-analyzer/scripts/analyze_traceback.py` - Traceback 解析
- `skills/python-error-analyzer/patterns.md` - 错误模式表