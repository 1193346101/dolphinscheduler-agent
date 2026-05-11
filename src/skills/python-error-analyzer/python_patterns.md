# Python 错误模式表

错误模式表，用于快速匹配和分类 Python 任务错误。

## KNOWN_NEEDS_LLM

已知错误类型，需要 LLM 进一步分析上下文。

| error_type | pattern | llm_hint |
|------------|---------|----------|
| import_error | `ImportError` | Python 导入错误，检查模块导入路径和依赖 |
| module_not_found | `ModuleNotFoundError` | Python 模块找不到，请分析缺失的模块名和安装方法 |
| syntax_error | `SyntaxError` | Python 语法错误，分析具体位置和原因 |
| indentation_error | `IndentationError\|Indentation` | Python 缩进错误，检查缩进一致性 |
| type_error | `TypeError` | Python 类型错误，分析类型不匹配 |
| value_error | `ValueError` | Python 值错误，分析无效值 |
| key_error | `KeyError` | Python 键错误，请检查字典键是否存在 |
| attribute_error | `AttributeError` | Python 属性错误，检查对象属性或方法是否存在 |
| name_error | `NameError` | Python 名称错误，变量或函数未定义 |
| index_error | `IndexError` | Python 索引错误，检查列表索引范围 |
| zero_division | `ZeroDivisionError` | Python 除零错误 |
| file_not_found | `FileNotFoundError\|No such file or directory` | Python 文件不存在，检查路径是否正确 |
| permission_error | `PermissionError\|Permission denied` | Python 权限错误，检查文件或目录权限 |
| connection_error | `ConnectionError\|Connection refused\|ConnectionResetError` | Python 连接错误，检查目标服务是否运行 |
| connection_timeout | `TimeoutError\|timed out\|ReadTimeout\|ConnectTimeout` | Python 连接超时，检查网络状态 |
| http_error | `HTTPError\|HTTPStatusError\|HTTPConnectionError` | Python HTTP 错误，分析请求和响应 |
| json_decode_error | `JSONDecodeError\|json.decoder.JSONDecodeError` | Python JSON 解析错误，检查 JSON 格式 |
| unicode_error | `UnicodeDecodeError\|UnicodeEncodeError` | Python 编码错误，检查字符编码 |
| os_error | `OSError` | Python 操作系统错误，分析具体原因 |
| runtime_error | `RuntimeError` | Python 运行时错误，分析具体原因 |
| stop_iteration | `StopIteration` | Python 迭代器耗尽 |
| assertion_error | `AssertionError` | Python 断言失败，检查断言条件 |
| not_implemented | `NotImplementedError` | Python 功能未实现 |
| recursion_error | `RecursionError\|maximum recursion depth` | Python 递归深度超限，检查递归逻辑 |
| memory_error | `MemoryError` | Python 内存不足 |
| keyboard_interrupt | `KeyboardInterrupt` | Python 用户中断执行 |
| unbound_local_error | `UnboundLocalError` | Python 局部变量未赋值就使用 |
| overflow_error | `OverflowError` | Python 数值溢出 |
| floating_point_error | `FloatingPointError` | Python 浮点运算错误 |
| environment_error | `EnvironmentError` | Python 环境错误 |
| eof_error | `EOFError` | Python 输入意外结束 |

## Pattern Matching Rules

1. **优先级**: KNOWN_NEEDS_LLM > UNKNOWN
2. **匹配方式**: 正则表达式，忽略大小写 (re.IGNORECASE)
3. **跨行匹配**: 使用 re.DOTALL 处理跨行日志
4. **多模式匹配**: 单个日志可能匹配多个模式，取第一个匹配

## Usage

```python
import re
from pathlib import Path

def load_patterns(file_path: str) -> dict:
    """Load patterns from python_patterns.md"""
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