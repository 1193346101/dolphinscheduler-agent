# DataX Error Patterns

错误模式表，用于快速匹配和分类 DataX 数据同步任务错误。

## KNOWN_NEEDS_LLM

DataX 错误大多需要 LLM 进一步分析上下文。

### 连接错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| connection_refused | `Communications link failure` | DataX 源端数据库连接失败，请检查数据库连接配置（URL、用户名、密码）以及网络连通性 |
| connection_refused_mysql | `Could not create connection to database server` | DataX MySQL 连接失败，请检查 MySQL 服务是否运行、连接配置是否正确 |
| connection_refused_oracle | `IO Error: The Network Adapter could not establish` | DataX Oracle 连接失败，请检查 Oracle 监听器状态和连接配置 |
| connection_refused_postgresql | `Connection refused.*PostgreSQL` | DataX PostgreSQL 连接失败，请检查 PostgreSQL 服务状态 |
| connection_refused_sqlserver | `无法连接到服务器|Cannot connect to` | DataX SQL Server 连接失败，请检查 SQL Server 服务和端口 |
| auth_failed | `Access denied for user` | DataX 数据库认证失败，请检查用户名和密码是否正确 |
| auth_failed_mysql | `Using password: YES` | DataX MySQL 认证失败，密码错误或用户权限不足 |
| auth_failed_oracle | `ORA-01017: invalid credential` | DataX Oracle 认证失败，用户名或密码错误 |
| timeout | `connect timed out` | DataX 连接超时，请检查网络连通性和防火墙设置 |
| timeout_socket | `SocketTimeoutException|Read timed out` | DataX Socket 超时，请检查网络延迟和超时配置 |
| host_unknown | `Unknown host|Unable to resolve host` | DataX 无法解析主机名，请检查 DNS 配置或 hosts 文件 |

### 数据库对象错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| table_not_found | `Table.*doesn't exist|Table.*不存在` | DataX 表不存在，请检查表名是否正确，注意大小写和 Schema |
| table_not_found_oracle | `ORA-00942: table or view does not exist` | DataX Oracle 表不存在，请检查表名和 Schema |
| table_not_found_mysql | `Table '.*' doesn't exist` | DataX MySQL 表不存在，请检查表名和数据库名 |
| column_mismatch | `Unknown column` | DataX 列名不匹配，请检查源表和目标表的列名配置 |
| column_mismatch_oracle | `ORA-00904: invalid identifier` | DataX Oracle 列名无效，请检查列名是否正确 |
| column_not_found | `Column '.*' not found` | DataX 列不存在，请检查列名配置 |

### 数据转换错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| type_conversion | `Data truncation|Data truncated` | DataX 数据截断，请检查字段长度是否足够 |
| type_conversion_charset | `Incorrect string value|Incorrect column value` | DataX 字符编码错误，请检查字符集配置（如 Emoji、中文） |
| type_conversion_number | `Out of range value|Data too long` | DataX 数值溢出或数据过长，请检查字段类型和长度 |
| type_conversion_datetime | `Incorrect datetime value|Invalid datetime format` | DataX 日期时间格式错误，请检查日期格式配置 |
| type_conversion_null | `Column '.*' cannot be null` | DataX 非空字段插入空值，请检查数据清洗规则 |
| type_mismatch | `Type mismatch|Conversion failed` | DataX 类型不匹配，请检查源字段和目标字段类型 |

### 主键/约束错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| primary_key_dup | `Duplicate entry.*for key 'PRIMARY'` | DataX 主键冲突，请分析数据是否有重复主键，考虑去重或使用 REPLACE INTO 模式 |
| unique_key_dup | `Duplicate entry.*for key '.*'` | DataX 唯一键冲突，请检查数据是否有重复 |
| foreign_key_error | `Cannot add or update a child row: a foreign key constraint fails` | DataX 外键约束错误，请检查关联数据是否存在 |
| constraint_error | `Constraint violation|Integrity constraint` | DataX 约束违反，请检查数据完整性约束 |

### 权限错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| permission_denied | `Permission denied|Access denied` | DataX 权限不足，请检查数据库用户权限 |
| select_denied | `SELECT command denied` | DataX 查询权限被拒绝，请检查 SELECT 权限 |
| insert_denied | `INSERT command denied` | DataX 插入权限被拒绝，请检查 INSERT 权限 |
| update_denied | `UPDATE command denied` | DataX 更新权限被拒绝，请检查 UPDATE 权限 |
| delete_denied | `DELETE command denied` | DataX 删除权限被拒绝，请检查 DELETE 权限 |

### 配置错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| config_error | `Configuration error` | DataX 配置错误，请检查 job 配置文件 |
| json_parse_error | `JSON parse error|com.alibaba.fastjson.JSONException` | DataX JSON 配置解析失败，请检查 JSON 格式是否正确 |
| config_missing | `Required field.*is missing` | DataX 必填字段缺失，请检查配置完整性 |
| config_invalid | `Invalid configuration|Invalid parameter` | DataX 配置参数无效，请检查参数值范围 |

### 性能/资源错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| speed_limit | `speed limit exceeded` | DataX 速度限制，请检查流量控制配置 |
| channel_error | `channel error|Channel closed unexpectedly` | DataX Channel 错误，请检查并发配置 |
| memory_error | `OutOfMemoryError|cannot allocate memory` | DataX 内存不足，请检查 JVM 内存配置 |
| disk_full | `No space left on device` | DataX 磁盘空间不足，请清理临时文件 |

### 读写错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| read_error | `Read error|Error reading from source` | DataX 读取源端数据失败，请检查源端状态 |
| write_error | `Write error|Error writing to sink` | DataX 写入目标端失败，请检查目标端状态 |
| batch_write_failed | `batch write failed|BatchUpdateException` | DataX 批量写入失败，请分析失败的具体批次和原因 |
| dirty_record | `Dirty record|脏数据` | DataX 脏数据记录，请检查数据质量问题 |

### Oracle 特定错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| ora_12154 | `ORA-12154: TNS:could not resolve` | DataX Oracle TNS 解析失败，请检查 tnsnames.ora 配置 |
| ora_12514 | `ORA-12514: TNS:listener does not currently know` | DataX Oracle 服务名不存在，请检查 SERVICE_NAME 配置 |
| ora_12541 | `ORA-12541: TNS:no listener` | DataX Oracle 监听器未启动，请检查监听器状态 |
| ora_12899 | `ORA-12899: value too large for column` | DataX Oracle 字段值过长，请检查字段长度 |

### MySQL 特定错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| mysql_1366 | `Incorrect string value` | DataX MySQL 字符编码错误，请检查字符集配置 |
| mysql_1045 | `Access denied for user` | DataX MySQL 认证失败，请检查用户名密码 |
| mysql_1153 | `max_allowed_packet` | DataX MySQL 包大小超限，请调整 max_allowed_packet |

### PostgreSQL 特定错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| pg_connection | `Connection refused.*5432` | DataX PostgreSQL 连接失败，请检查服务状态 |
| pg_auth | `FATAL: password authentication failed` | DataX PostgreSQL 认证失败，请检查用户名密码 |
| pg_schema | `schema ".*" does not exist` | DataX PostgreSQL Schema 不存在，请检查 Schema 配置 |

## Pattern Matching Rules

1. **优先级**: 按照表格顺序匹配，第一个匹配的模式为准
2. **匹配方式**: 正则表达式，忽略大小写 (re.IGNORECASE)
3. **跨行匹配**: 使用 re.DOTALL 处理跨行日志
4. **多模式匹配**: 单个日志可能匹配多个模式，取第一个匹配

## Usage

```python
import re
from pathlib import Path

def load_patterns(file_path: str) -> dict:
    """Load patterns from datax_patterns.md"""
    patterns = {"KNOWN_NEEDS_LLM": {}}
    # Parse markdown tables and populate patterns
    return patterns

def match_error(log_content: str, patterns: dict) -> tuple:
    """Match error patterns in log content"""
    for category, error_patterns in patterns.items():
        for error_type, (pattern, llm_hint) in error_patterns.items():
            if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
                return error_type, category, pattern, llm_hint
    return "unknown", "UNKNOWN", None, None
```