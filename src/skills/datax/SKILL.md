---
name: datax-error-analyzer
description: 分析 DataX 数据同步任务执行错误，适用于数据库连接失败、数据转换异常、权限问题等。不要用于 SPARK、SHELL 等其他任务类型。
task_types:
  - DATAX
version: "1.0.0"
---

# DataX Error Analyzer Skill

分析 DataX 数据同步任务执行错误，提供错误分类、修复建议和 LLM 提示。

## Processing Steps

### 1. 日志预处理

调用 `preprocess_log.py` 提取关键信息：

```python
from skills.common.preprocess_log import preprocess_log

result = preprocess_log(log_content, task_type="datax")
# 返回: config_lines, error_blocks, job_info, data_metrics
```

提取内容：
- **config_lines**: DataX job 配置行 (job.content.reader, job.content.writer)
- **error_blocks**: 完整的错误堆栈块
- **job_info**: Job ID, Channel 数量, 速度配置
- **data_metrics**: 同步数据量指标 (total_records, total_bytes, speed)

### 2. 匹配错误模式

调用 `scripts/match_error.py` 匹配已知错误模式：

```python
from skills.datax_error_analyzer.scripts.match_error import match_error

match = match_error(error_blocks, patterns_file="patterns.md")
# 返回: error_type, category, pattern, llm_hint
```

模式分类：
- **KNOWN_NEEDS_LLM**: 已知类型，需 LLM 分析（DataX 大多数错误需人工干预）
- **UNKNOWN**: 未知错误，完全交给 LLM

### 3. 增强上下文

对于连接/权限错误，补充环境上下文：

```python
if error_type in ["connection_refused", "auth_failed", "timeout"]:
    context = enrich_context(error_type, job_info)
    # 补充: 数据库类型、连接串、网络状态
```

### 4. 分析数据量指标

对于数据转换/写入错误，分析数据量：

```python
if error_type in ["type_conversion", "column_mismatch", "primary_key_dup"]:
    metrics_analysis = analyze_data_metrics(data_metrics)
    # 分析: 数据量、错误批次、问题记录
```

### 5. 匹配知识库

查询历史相似案例：

```python
kb_match = match_knowledge_base(error_type, error_message)
# 返回: similar_cases, solutions
```

## Output Format

```json
{
  "error_type": "connection_refused",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "Communications link failure\nThe last packet sent successfully...",
  "targets": {
    "job_id": "job_1234567890",
    "source_type": "mysql",
    "sink_type": "oracle"
  },
  "data_metrics": {
    "total_records": 0,
    "total_bytes": 0,
    "speed_records_per_sec": 0
  },
  "fix": null,
  "llm_hint": "DataX 源端数据库连接失败，请检查数据库连接配置（URL、用户名、密码）以及网络连通性",
  "confidence": 0.9
}
```

## Error Categories

### KNOWN_NEEDS_LLM

DataX 错误大多需要 LLM 进一步分析：

| 错误类型 | 典型模式 | 分析提示 |
|---------|---------|---------|
| connection_refused | `Communications link failure` | 源端数据库连接失败，检查 URL/网络 |
| auth_failed | `Access denied for user` | 数据库认证失败，检查用户名/密码 |
| table_not_found | `Table.*doesn't exist` | 表不存在，检查表名/Schema |
| column_mismatch | `Unknown column` | 列名不匹配，检查列配置 |
| type_conversion | `Data truncation` | 类型转换失败，检查字段类型 |
| primary_key_dup | `Duplicate entry` | 主键冲突，检查数据去重 |
| timeout | `connect timed out` | 连接超时，检查网络/防火墙 |
| permission_denied | `Permission denied` | 权限不足，检查用户权限 |
| config_error | `Configuration error` | 配置错误，检查 JSON 格式 |
| speed_limit | `speed limit exceeded` | 速度限制，检查流量控制 |

完整模式定义见 [patterns.md](./patterns.md)

## Dependencies

- `skills/common/preprocess_log.py` - 日志预处理
- `skills/datax-error-analyzer/scripts/match_error.py` - 模式匹配
- `skills/datax-error-analyzer/patterns.md` - 错误模式表

## Examples

### Example 1: 数据库连接失败

**Input Log:**
```
2024-01-01 10:00:00.000 [job-0] ERROR RdbmsReader$Task - 
com.mysql.jdbc.exceptions.jdbc4.CommunicationsException: Communications link failure
The last packet sent successfully to the server was 0 milliseconds ago.
    at com.mysql.jdbc.Util.handleNewInstance(Util.java:425)
```

**Output:**
```json
{
  "error_type": "connection_refused",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "com.mysql.jdbc.exceptions.jdbc4.CommunicationsException: Communications link failure",
  "targets": {"job_id": "job-0", "source_type": "mysql"},
  "data_metrics": {},
  "fix": null,
  "llm_hint": "DataX 源端数据库连接失败，请检查数据库连接配置（URL、用户名、密码）以及网络连通性"
}
```

### Example 2: 主键冲突

**Input Log:**
```
2024-01-01 10:00:00.000 [job-0] ERROR Writer$Task - 
com.mysql.jdbc.exceptions.jdbc4.MySQLIntegrityConstraintViolationException: Duplicate entry '123' for key 'PRIMARY'
    at com.mysql.jdbc.Util.handleNewInstance(Util.java:425)
```

**Output:**
```json
{
  "error_type": "primary_key_dup",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "MySQLIntegrityConstraintViolationException: Duplicate entry '123' for key 'PRIMARY'",
  "targets": {"job_id": "job-0", "sink_type": "mysql"},
  "data_metrics": {"total_records": 10000},
  "fix": null,
  "llm_hint": "DataX 主键冲突，请分析数据是否有重复主键，考虑去重或使用 REPLACE INTO 模式"
}
```

### Example 3: 类型转换错误

**Input Log:**
```
2024-01-01 10:00:00.000 [job-0] ERROR Transformer$Task - 
Data truncation: Incorrect string value: '\xF0\x9F\x98\x80' for column 'content' at row 100
```

**Output:**
```json
{
  "error_type": "type_conversion",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "Data truncation: Incorrect string value for column 'content'",
  "targets": {"job_id": "job-0"},
  "data_metrics": {"total_records": 100},
  "fix": null,
  "llm_hint": "DataX 类型转换失败，源字段包含 Emoji 等特殊字符，目标字段编码可能不支持，请检查字符集配置"
}
```