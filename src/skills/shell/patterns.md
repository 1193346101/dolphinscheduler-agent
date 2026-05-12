# Shell 错误模式表

错误模式表，用于快速匹配和分类 Shell 任务错误。

## AUTO_FIXABLE

可直接修复的简单问题（路径验证等）。

| error_type | pattern | fix_action |
|------------|---------|------------|
| oss_path_verified_exists | `No such file or directory.*oss://` | {"action_type": "path_verification", "use_ossutil": true} |
| hdfs_path_verified_exists | `No such file or directory.*hdfs://` | {"action_type": "path_verification", "use_hdfs_check": true} |

## KNOWN_NEEDS_LLM

已知错误类型，需要 LLM 进一步分析上下文。

### 命令错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| command_not_found | `command not found` | Shell 命令未找到，请检查命令是否存在或拼写是否正确 |
| command_not_found_line | `line.*command not found` | Shell 命令未找到，请检查脚本中的命令拼写 |

### 语法错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| syntax_error | `syntax error` | Shell 语法错误，分析具体位置和原因（如引号不闭合、括号不匹配等） |
| unexpected_eof | `unexpected EOF` | Shell 文件意外结束，通常是引号或括号不闭合导致 |
| unexpected_eof_quote | `unexpected EOF while looking for matching` | Shell 引号或括号不闭合，请定位具体位置 |
| unexpected_token | `unexpected token` | Shell 出现意外符号，请分析原因 |
| unexpected_end | `unexpected end of file` | Shell 脚本结构不完整。常见原因：(1) 引号不闭合；(2) 括号不闭合；(3) if/for/while 缺少 fi/end/done |
| newline_unexpected | `newline unexpected` | Shell 新行位置错误，通常是引号未闭合导致命令跨行 |

### 变量错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| variable_unset | `parameter null or not set` | Shell 变量为空或未定义，请分析变量来源和赋值逻辑 |
| variable_not_found | `variable not found` | Shell 变量未找到，请检查变量定义和使用 |
| bad_substitution | `bad substitution` | Shell 变量替换语法错误，请检查 ${} 语法 |
| array_index_error | `array index` | Shell 数组索引错误，请检查数组操作 |

### 文件/路径错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| no_such_file | `No such file or directory` | Shell 文件或目录不存在，请检查路径是否正确、文件是否存在 |
| file_not_found | `File not found` | Shell 文件不存在，请检查文件路径 |
| directory_not_exist | `cannot access` | Shell 无法访问路径，请检查路径和权限 |
| path_not_found | `path not found` | Shell 路径不存在，请检查路径配置 |

### 权限错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| permission_denied | `Permission denied` | Shell 权限不足，请分析需要什么权限、如何获取 |
| access_denied | `Access denied` | Shell 访问被拒绝，请检查权限配置 |
| cannot_execute | `cannot execute` | Shell 无法执行，可能是权限或文件格式问题 |
| operation_not_permitted | `Operation not permitted` | Shell 操作不被允许，请检查权限和系统限制 |

### 参数/选项错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| invalid_option | `invalid option` | Shell 命令参数无效，请检查参数格式和可用选项 |
| option_requires_arg | `option requires an argument` | Shell 选项需要参数，请检查参数是否缺失 |
| missing_argument | `missing argument` | Shell 缺少参数，请检查命令参数数量 |
| extra_argument | `too many arguments` | Shell 参数过多，请检查命令参数数量 |

### 管道/重定向错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| broken_pipe | `Broken pipe` | Shell 管道断开，请分析管道进程状态 |
| pipe_failed | `pipe failed` | Shell 管道创建失败，请检查系统资源 |
| redirect_error | `cannot redirect` | Shell 重定向失败，请检查输出路径和权限 |
| input_output_error | `Input/output error` | Shell I/O 错误，可能是磁盘或文件问题 |

### 进程/信号错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| process_killed | `Killed` | Shell 进程被终止，可能是内存不足或信号终止 |
| process_terminated | `Terminated` | Shell 进程被终止，请分析终止原因 |
| segfault | `Segmentation fault` | Shell 程序段错误，通常是代码 bug 或内存问题 |
| exit_code_error | `exited with` | Shell 命令异常退出，请分析退出原因和退出码 |
| fork_failed | `fork failed` | Shell 创建子进程失败，可能是系统资源不足 |

### 编码/环境错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| encoding_error | `encoding` | Shell 编码问题，请检查字符编码设置 |
| locale_error | `locale` | Shell 语言环境设置问题，请检查 locale 配置 |
| env_not_found | `environment variable` | Shell 环境变量问题，请检查环境变量是否定义 |
| home_not_set | `HOME not set` | Shell HOME 环境变量未设置 |

### 资源错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| memory_error | `cannot allocate` | Shell 内存分配失败，可能是内存不足 |
| disk_full | `no space left` | Shell 磁盘空间不足，请清理磁盘或更换路径 |
| quota_exceeded | `quota exceeded` | Shell 资源配额超限，请检查配额设置 |
| resource_limit | `too many` | Shell 资源限制，可能是进程或文件数超限 |

### 网络/连接错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| connection_refused | `Connection refused` | Shell 网络连接被拒绝，请检查目标服务是否运行 |
| connection_timeout | `Connection timed out` | Shell 网络连接超时，请检查网络状态和超时设置 |
| host_unreachable | `Host unreachable` | Shell 主机不可达，请检查网络连通性 |
| network_error | `network unreachable` | Shell 网络不可达，请检查网络配置 |
| dns_error | `unknown host` | Shell DNS 解析失败，请检查主机名和 DNS 配置 |

### 工具特定错误

| error_type | pattern | llm_hint |
|------------|---------|----------|
| grep_error | `grep:` | grep 命令错误，请检查 grep 参数和输入 |
| sed_error | `sed:` | sed 命令错误，请检查 sed 语法和输入 |
| awk_error | `awk:` | awk 命令错误，请检查 awk 语法和输入 |
| find_error | `find:` | find 命令错误，请检查 find 参数和路径 |
| ssh_error | `ssh:` | ssh 连接错误，请检查 SSH 配置和目标主机 |
| curl_error | `curl:` | curl 请求错误，请检查 URL 和参数 |
| docker_error | `docker:` | Docker 命令错误，请检查 Docker 配置和容器状态 |
| kubectl_error | `kubectl:` | kubectl 命令错误，请检查 Kubernetes 配置和资源状态 |

## Pattern Matching Rules

1. **优先级**: AUTO_FIXABLE > KNOWN_NEEDS_LLM > UNKNOWN
2. **匹配方式**: 正则表达式，忽略大小写 (re.IGNORECASE)
3. **跨行匹配**: 使用 re.DOTALL 处理跨行日志
4. **多模式匹配**: 单个日志可能匹配多个模式，取第一个匹配