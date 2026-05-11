# skills/shell-error-analyzer/shell_patterns.md

# Shell 错误模式表

## KNOWN_NEEDS_LLM（需 LLM 分析）

| error_type | pattern | llm_hint |
|------------|---------|----------|
| syntax_error | `syntax error` | Shell 语法错误，分析具体位置和原因 |
| unexpected_eof | `unexpected EOF` | Shell 文件意外结束，通常是引号不闭合 |
| unexpected_eof_quote | `unexpected EOF while looking for matching` | Shell 引号或括号不闭合 |
| unexpected_token | `unexpected token` | Shell 出现意外符号 |
| variable_unset | `parameter null or not set` | Shell 变量为空或未定义 |
| bad_substitution | `bad substitution` | Shell 变量替换语法错误 |
| no_such_file | `No such file or directory` | Shell 文件不存在，检查路径 |
| permission_denied | `Permission denied` | Shell 权限不足 |
| connection_refused | `Connection refused` | Shell 网络连接被拒绝 |
| connection_timeout | `Connection timed out` | Shell 网络连接超时 |
| host_unreachable | `Host unreachable` | Shell 主机不可达 |
| dns_error | `unknown host` | Shell DNS 解析失败 |
| disk_full | `no space left` | Shell 磁盘空间不足 |
| memory_error | `cannot allocate` | Shell 内存分配失败 |
| broken_pipe | `Broken pipe` | Shell 管道断开 |
| segfault | `Segmentation fault` | Shell 程序段错误 |
| killed | `Killed` | Shell 进程被终止 |