# SecurityGuard 安全监管模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现命令级安全拦截、操作审计日志、高风险告警功能

**Architecture:** 独立 SecurityGuard 模块（constants/guard/audit/alert）+ 在 CLI/HTTP/OSS 调用点集成拦截

**Tech Stack:** Python dataclasses, JSON Lines, DingTalk API

---

## 文件结构

```
src/security/
├── __init__.py        # Modify: 导出新模块
├── approval.py        # [现有] 审批流程
├── constants.py       # Create: 常量定义
├── guard.py           # Create: CommandGuard
├── audit.py           # Create: AuditLogger
├── alert.py           # Create: SecurityAlert

tests/test_security/
├── test_guard.py      # Create: CommandGuard 测试
├── test_audit.py      # Create: AuditLogger 测试
```

---

### Task 1: 创建常量定义模块

**Files:**
- Create: `src/security/constants.py`

- [ ] **Step 1: 创建 constants.py 文件**

```python
# src/security/constants.py

"""
安全监管常量定义

定义禁止命令列表、允许的只读操作
"""

# ===== 命令级禁止列表 =====

# DolphinScheduler CLI 禁止命令
DS_FORBIDDEN_COMMANDS = [
    "delete",           # workflow delete, schedule delete, task delete
    "remove",           # worktree remove
]

# OSS 禁止操作
OSS_FORBIDDEN_OPERATIONS = [
    "cp",               # 上传/复制文件
    "mv",               # 移动文件
    "rm",               # 删除文件
    "put",              # 上传文件
    "sync",             # 同步（可能写入）
]

# HTTP 方法禁止（适用于 YARN、History Server）
HTTP_FORBIDDEN_METHODS = [
    "POST",             # 创建资源
    "PUT",              # 更新资源
    "DELETE",           # 删除资源
    "PATCH",            # 修改资源
]

# ===== 允许的只读操作 =====
ALLOWED_READONLY = {
    "dsctl": ["list", "get", "export", "describe", "digest", "parent"],
    "ossutil": ["ls", "stat"],
    "http": ["GET"],
}


__all__ = [
    "DS_FORBIDDEN_COMMANDS",
    "OSS_FORBIDDEN_OPERATIONS",
    "HTTP_FORBIDDEN_METHODS",
    "ALLOWED_READONLY",
]
```

- [ ] **Step 2: Commit**

```bash
git add src/security/constants.py
git commit -m "feat: 添加安全监管常量定义模块"
```

---

### Task 2: 创建 CommandGuard 模块

**Files:**
- Create: `src/security/guard.py`
- Create: `tests/test_security/test_guard.py`

- [ ] **Step 1: 创建测试目录**

```bash
mkdir -p tests/test_security
```

- [ ] **Step 2: 编写 GuardResult 数据类测试**

```python
# tests/test_security/test_guard.py

"""
CommandGuard 测试
"""

import pytest
from src.security.guard import GuardResult


def test_guard_result_dataclass():
    """测试 GuardResult 数据类"""
    result = GuardResult(
        allowed=True,
        blocked=False,
        reason="",
        operation_type="dsctl",
        operation_detail="workflow list",
        risk_level="LOW",
    )

    assert result.allowed is True
    assert result.blocked is False
    assert result.operation_type == "dsctl"
    assert result.risk_level == "LOW"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `python -c "from src.security.guard import GuardResult"`
Expected: ImportError（模块不存在）

- [ ] **Step 4: 创建 guard.py 基础结构**

```python
# src/security/guard.py

"""
CommandGuard - 命令安全拦截器

对所有系统操作进行安全检查
"""

from dataclasses import dataclass
from typing import List


@dataclass
class GuardResult:
    """安全检查结果"""
    allowed: bool                      # 是否允许执行
    blocked: bool                      # 是否被拦截
    reason: str                        # 拦截原因
    operation_type: str                # 操作类型: dsctl/ossutil/http
    operation_detail: str              # 具体操作详情
    risk_level: str = "LOW"            # 风险等级


__all__ = ["GuardResult"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -c "from src.security.guard import GuardResult; print('OK')"`
Expected: OK

- [ ] **Step 6: 编写 check_cli_command 测试**

```python
# tests/test_security/test_guard.py（追加）

from src.security.guard import CommandGuard


def test_check_cli_command_allowed():
    """测试允许的 CLI 命令"""
    guard = CommandGuard()
    result = guard.check_cli_command(["workflow", "list"])

    assert result.allowed is True
    assert result.blocked is False
    assert result.operation_type == "dsctl"


def test_check_cli_command_blocked_delete():
    """测试禁止的 delete 命令"""
    guard = CommandGuard()
    result = guard.check_cli_command(["workflow", "delete", "12345"])

    assert result.allowed is False
    assert result.blocked is True
    assert "delete" in result.reason.lower()
    assert result.risk_level == "CRITICAL"


def test_check_cli_command_blocked_remove():
    """测试禁止的 remove 命令"""
    guard = CommandGuard()
    result = guard.check_cli_command(["worktree", "remove", "test"])

    assert result.allowed is False
    assert result.blocked is True
    assert "remove" in result.reason.lower()
    assert result.risk_level == "CRITICAL"


def test_check_cli_command_high_risk_recover():
    """测试 HIGH 风险的 recover 命令"""
    guard = CommandGuard()
    result = guard.check_cli_command(["workflow-instance", "recover-failed", "100001"])

    assert result.allowed is True
    assert result.blocked is False
    assert result.risk_level == "HIGH"


def test_check_cli_command_medium_risk_edit():
    """测试 MEDIUM 风险的 edit 命令"""
    guard = CommandGuard()
    result = guard.check_cli_command(["workflow-instance", "edit", "100001"])

    assert result.allowed is True
    assert result.blocked is False
    assert result.risk_level == "MEDIUM"
```

- [ ] **Step 7: 运行测试验证失败**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py -v`
Expected: FAIL（CommandGuard 类不存在）

- [ ] **Step 8: 实现 CommandGuard.check_cli_command**

```python
# src/security/guard.py（修改）

from dataclasses import dataclass
from typing import List
from .constants import DS_FORBIDDEN_COMMANDS


@dataclass
class GuardResult:
    """安全检查结果"""
    allowed: bool
    blocked: bool
    reason: str
    operation_type: str
    operation_detail: str
    risk_level: str = "LOW"


class CommandGuard:
    """命令安全拦截器"""

    def check_cli_command(self, args: List[str]) -> GuardResult:
        """检查 CLI 命令是否允许执行"""
        for arg in args:
            arg_lower = arg.lower()
            for forbidden in DS_FORBIDDEN_COMMANDS:
                if forbidden in arg_lower:
                    return GuardResult(
                        allowed=False,
                        blocked=True,
                        reason=f"命令 '{arg}' 在禁止列表中，禁止执行",
                        operation_type="dsctl",
                        operation_detail=" ".join(args),
                        risk_level="CRITICAL",
                    )

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="dsctl",
            operation_detail=" ".join(args),
            risk_level=self._assess_risk(args),
        )

    def _assess_risk(self, args: List[str]) -> str:
        """评估风险等级"""
        cmd_str = " ".join(args).lower()

        if "recover" in cmd_str:
            return "HIGH"

        if "edit" in cmd_str or "modify" in cmd_str:
            return "MEDIUM"

        return "LOW"


__all__ = ["GuardResult", "CommandGuard"]
```

- [ ] **Step 9: 运行测试验证通过**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py -v`
Expected: PASS

- [ ] **Step 10: 编写 check_http_request 测试**

```python
# tests/test_security/test_guard.py（追加）

def test_check_http_request_allowed_get():
    """测试允许的 GET 请求"""
    guard = CommandGuard()
    result = guard.check_http_request("GET", "https://yarn/api/apps")

    assert result.allowed is True
    assert result.blocked is False
    assert result.operation_type == "http"
    assert result.risk_level == "LOW"


def test_check_http_request_blocked_post():
    """测试禁止的 POST 请求"""
    guard = CommandGuard()
    result = guard.check_http_request("POST", "https://yarn/api/apps")

    assert result.allowed is False
    assert result.blocked is True
    assert "POST" in result.reason
    assert result.risk_level == "CRITICAL"


def test_check_http_request_blocked_delete():
    """测试禁止的 DELETE 请求"""
    guard = CommandGuard()
    result = guard.check_http_request("DELETE", "https://yarn/api/apps/123")

    assert result.allowed is False
    assert result.blocked is True
    assert "DELETE" in result.reason
    assert result.risk_level == "CRITICAL"
```

- [ ] **Step 11: 运行测试验证失败**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py::test_check_http_request_allowed_get -v`
Expected: FAIL

- [ ] **Step 12: 实现 CommandGuard.check_http_request**

```python
# src/security/guard.py（修改）

from .constants import HTTP_FORBIDDEN_METHODS


class CommandGuard:
    # ... existing code ...

    def check_http_request(self, method: str, url: str) -> GuardResult:
        """检查 HTTP 请求是否允许"""
        method_upper = method.upper()

        if method_upper in HTTP_FORBIDDEN_METHODS:
            return GuardResult(
                allowed=False,
                blocked=True,
                reason=f"HTTP 方法 '{method}' 在禁止列表中，只允许 GET 请求",
                operation_type="http",
                operation_detail=f"{method} {url}",
                risk_level="CRITICAL",
            )

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="http",
            operation_detail=f"{method} {url}",
            risk_level="LOW",
        )
```

- [ ] **Step 13: 运行测试验证通过**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py -v`
Expected: PASS

- [ ] **Step 14: 编写 check_oss_command 测试**

```python
# tests/test_security/test_guard.py（追加）

def test_check_oss_command_allowed_ls():
    """测试允许的 ls 命令"""
    guard = CommandGuard()
    result = guard.check_oss_command(["ls", "oss://bucket/path/"])

    assert result.allowed is True
    assert result.blocked is False
    assert result.operation_type == "ossutil"


def test_check_oss_command_allowed_stat():
    """测试允许的 stat 命令"""
    guard = CommandGuard()
    result = guard.check_oss_command(["stat", "oss://bucket/file"])

    assert result.allowed is True
    assert result.blocked is False


def test_check_oss_command_blocked_rm():
    """测试禁止的 rm 命令"""
    guard = CommandGuard()
    result = guard.check_oss_command(["rm", "oss://bucket/file"])

    assert result.allowed is False
    assert result.blocked is True
    assert "rm" in result.reason.lower()
    assert result.risk_level == "CRITICAL"


def test_check_oss_command_blocked_cp():
    """测试禁止的 cp 命令"""
    guard = CommandGuard()
    result = guard.check_oss_command(["cp", "local.txt", "oss://bucket/file"])

    assert result.allowed is False
    assert result.blocked is True
    assert "cp" in result.reason.lower()
    assert result.risk_level == "CRITICAL"


def test_check_oss_command_blocked_sync():
    """测试禁止的 sync 命令"""
    guard = CommandGuard()
    result = guard.check_oss_command(["sync", "local_dir/", "oss://bucket/"])

    assert result.allowed is False
    assert result.blocked is True


def test_check_oss_command_empty_args():
    """测试空参数"""
    guard = CommandGuard()
    result = guard.check_oss_command([])

    assert result.allowed is True
    assert result.blocked is False
```

- [ ] **Step 15: 运行测试验证失败**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py::test_check_oss_command_allowed_ls -v`
Expected: FAIL

- [ ] **Step 16: 实现 CommandGuard.check_oss_command**

```python
# src/security/guard.py（修改）

from .constants import OSS_FORBIDDEN_OPERATIONS


class CommandGuard:
    # ... existing code ...

    def check_oss_command(self, args: List[str]) -> GuardResult:
        """检查 ossutil 命令是否允许"""
        if not args:
            return GuardResult(
                allowed=True,
                blocked=False,
                reason="",
                operation_type="ossutil",
                operation_detail="",
            )

        sub_command = args[0].lower()

        for forbidden in OSS_FORBIDDEN_OPERATIONS:
            if forbidden == sub_command:
                return GuardResult(
                    allowed=False,
                    blocked=True,
                    reason=f"ossutil 操作 '{sub_command}' 在禁止列表中，只允许 ls/stat",
                    operation_type="ossutil",
                    operation_detail="ossutil " + " ".join(args),
                    risk_level="CRITICAL",
                )

        return GuardResult(
            allowed=True,
            blocked=False,
            reason="",
            operation_type="ossutil",
            operation_detail="ossutil " + " ".join(args),
            risk_level="LOW",
        )
```

- [ ] **Step 17: 运行所有测试验证通过**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_guard.py -v`
Expected: 13 tests PASS

- [ ] **Step 18: Commit**

```bash
git add src/security/guard.py tests/test_security/test_guard.py
git commit -m "feat: 实现 CommandGuard 命令安全拦截器"
```

---

### Task 3: 创建 AuditLogger 模块

**Files:**
- Create: `src/security/audit.py`
- Create: `tests/test_security/test_audit.py`

- [ ] **Step 1: 编写 AuditRecord 数据类测试**

```python
# tests/test_security/test_audit.py

"""
AuditLogger 测试
"""

import pytest
import tempfile
import os
from pathlib import Path


def test_audit_record_dataclass():
    """测试 AuditRecord 数据类"""
    from src.security.audit import AuditRecord

    record = AuditRecord(
        timestamp="2026-05-11T14:30:00",
        operation_type="dsctl",
        operation_detail="workflow list",
        result="success",
        risk_level="LOW",
    )

    assert record.timestamp == "2026-05-11T14:30:00"
    assert record.operation_type == "dsctl"
    assert record.result == "success"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -c "from src.security.audit import AuditRecord"`
Expected: ImportError

- [ ] **Step 3: 创建 audit.py 基础结构**

```python
# src/security/audit.py

"""
AuditLogger - 操作审计日志

存储格式：本地 JSON Lines 文件，每日一个文件
"""

import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AuditRecord:
    """审计记录"""
    timestamp: str                    # ISO 格式时间
    operation_type: str               # dsctl / ossutil / http / approval
    operation_detail: str             # 具体操作详情
    user: Optional[str] = None        # 操作人
    result: str = ""                  # success / failed / blocked
    result_detail: str = ""           # 错误信息摘要
    risk_level: str = "LOW"           # LOW / MEDIUM / HIGH / CRITICAL
    source_ip: Optional[str] = None   # 来源 IP
    project_code: Optional[int] = None
    workflow_code: Optional[int] = None
    duration_ms: Optional[int] = None


__all__ = ["AuditRecord"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -c "from src.security.audit import AuditRecord; print('OK')"`
Expected: OK

- [ ] **Step 5: 编写 AuditLogger 测试**

```python
# tests/test_security/test_audit.py（追加）

from src.security.audit import AuditLogger


def test_audit_logger_init_creates_dir():
    """测试初始化创建目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = os.path.join(tmpdir, "audit")
        logger = AuditLogger(log_dir=log_dir)

        assert Path(log_dir).exists()


def test_audit_logger_log():
    """测试记录审计日志"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)

        logger.log(
            operation_type="dsctl",
            operation_detail="workflow list",
            result="success",
            risk_level="LOW",
        )

        # 检查文件是否创建
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(tmpdir) / f"{date_str}.json"
        assert log_file.exists()

        # 检查内容
        with open(log_file, "r") as f:
            line = f.readline()
            data = json.loads(line)
            assert data["operation_type"] == "dsctl"
            assert data["result"] == "success"


def test_audit_logger_log_blocked():
    """测试记录拦截日志"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)

        logger.log_blocked(
            operation_type="dsctl",
            operation_detail="workflow delete 123",
            reason="命令 'delete' 在禁止列表中",
            risk_level="CRITICAL",
        )

        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(tmpdir) / f"{date_str}.json"

        with open(log_file, "r") as f:
            data = json.loads(f.readline())
            assert data["result"] == "blocked"
            assert data["risk_level"] == "CRITICAL"


def test_audit_logger_log_success():
    """测试记录成功日志"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)

        logger.log_success(
            operation_type="dsctl",
            operation_detail="workflow-instance recover-failed 100",
            risk_level="HIGH",
            duration_ms=350,
        )

        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(tmpdir) / f"{date_str}.json"

        with open(log_file, "r") as f:
            data = json.loads(f.readline())
            assert data["result"] == "success"
            assert data["duration_ms"] == 350


def test_audit_logger_truncates_result_detail():
    """测试截断过长的结果详情"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)

        long_detail = "x" * 1000
        logger.log(
            operation_type="dsctl",
            operation_detail="test",
            result="failed",
            result_detail=long_detail,
        )

        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(tmpdir) / f"{date_str}.json"

        with open(log_file, "r") as f:
            data = json.loads(f.readline())
            assert len(data["result_detail"]) == 500
```

- [ ] **Step 6: 运行测试验证失败**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_audit.py -v`
Expected: FAIL（AuditLogger 类不存在）

- [ ] **Step 7: 实现 AuditLogger 类**

```python
# src/security/audit.py（修改）

import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AuditRecord:
    """审计记录"""
    timestamp: str
    operation_type: str
    operation_detail: str
    user: Optional[str] = None
    result: str = ""
    result_detail: str = ""
    risk_level: str = "LOW"
    source_ip: Optional[str] = None
    project_code: Optional[int] = None
    workflow_code: Optional[int] = None
    duration_ms: Optional[int] = None


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        operation_type: str,
        operation_detail: str,
        result: str,
        result_detail: str = "",
        risk_level: str = "LOW",
        user: Optional[str] = None,
        source_ip: Optional[str] = None,
        project_code: Optional[int] = None,
        workflow_code: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """记录审计日志"""
        record = AuditRecord(
            timestamp=datetime.now().isoformat(),
            operation_type=operation_type,
            operation_detail=operation_detail,
            result=result,
            result_detail=result_detail[:500] if result_detail else "",
            risk_level=risk_level,
            user=user,
            source_ip=source_ip,
            project_code=project_code,
            workflow_code=workflow_code,
            duration_ms=duration_ms,
        )
        self._write_record(record)

    def log_blocked(
        self,
        operation_type: str,
        operation_detail: str,
        reason: str,
        risk_level: str = "CRITICAL",
    ) -> None:
        """记录被拦截的操作"""
        self.log(operation_type, operation_detail, "blocked", reason, risk_level)

    def log_success(
        self,
        operation_type: str,
        operation_detail: str,
        risk_level: str = "LOW",
        duration_ms: Optional[int] = None,
        project_code: Optional[int] = None,
        workflow_code: Optional[int] = None,
    ) -> None:
        """记录成功的操作"""
        self.log(
            operation_type, operation_detail, "success", "", risk_level,
            duration_ms=duration_ms, project_code=project_code,
            workflow_code=workflow_code,
        )

    def log_failed(
        self,
        operation_type: str,
        operation_detail: str,
        error: str,
        risk_level: str = "LOW",
        duration_ms: Optional[int] = None,
    ) -> None:
        """记录失败的操作"""
        self.log(operation_type, operation_detail, "failed", error, risk_level,
                 duration_ms=duration_ms)

    def _write_record(self, record: AuditRecord) -> None:
        """写入审计记录到文件"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{date_str}.json"

        line = json.dumps(asdict(record), ensure_ascii=False)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


__all__ = ["AuditRecord", "AuditLogger"]
```

- [ ] **Step 8: 运行测试验证通过**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/test_audit.py -v`
Expected: 6 tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/security/audit.py tests/test_security/test_audit.py
git commit -m "feat: 实现 AuditLogger 操作审计日志模块"
```

---

### Task 4: 创建 SecurityAlert 模块

**Files:**
- Create: `src/security/alert.py`

- [ ] **Step 1: 创建 alert.py 文件**

```python
# src/security/alert.py

"""
SecurityAlert - 安全告警发送器

高风险操作执行时发送钉钉告警
"""

from typing import Optional
from datetime import datetime


class SecurityAlert:
    """安全告警发送器"""

    def __init__(self):
        from ..integrations.dingtalk import DingTalkNotifier
        self.notifier = DingTalkNotifier()

    def send_high_risk_alert(
        self,
        operation_type: str,
        operation_detail: str,
        result: str,
        risk_level: str,
        reason: Optional[str] = None,
    ) -> bool:
        """发送高风险操作告警"""
        if result == "blocked":
            title = f"⛔ 禁止操作拦截 - {risk_level}"
        elif result == "failed":
            title = f"⚠️ 高风险操作失败 - {risk_level}"
        else:
            title = f"🔴 高风险操作执行 - {risk_level}"

        content = f"""### {title}

**操作类型**: {operation_type}
**操作详情**: {operation_detail}
**执行结果**: {result}
**风险等级**: {risk_level}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        if reason:
            content += f"\n**原因/说明**: {reason}\n"

        if result == "blocked":
            content += "\n---\n💡 此操作已被安全策略拦截，如需执行请联系管理员审核。"
        else:
            content += "\n---\n💡 此操作已被审计日志记录，请确认操作合规。"

        return self.notifier.send_markdown(title, content)

    def send_blocked_alert(
        self,
        operation_type: str,
        operation_detail: str,
        reason: str,
    ) -> bool:
        """发送禁止操作拦截告警"""
        return self.send_high_risk_alert(
            operation_type, operation_detail, "blocked", "CRITICAL", reason
        )

    def send_high_risk_execution_alert(
        self,
        operation_type: str,
        operation_detail: str,
        result: str,
        error: Optional[str] = None,
    ) -> bool:
        """发送高风险执行告警"""
        return self.send_high_risk_alert(
            operation_type, operation_detail, result, "HIGH", error
        )


__all__ = ["SecurityAlert"]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from src.security.alert import SecurityAlert; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/security/alert.py
git commit -m "feat: 实现 SecurityAlert 安全告警模块"
```

---

### Task 5: 更新 security __init__.py 导出

**Files:**
- Modify: `src/security/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# src/security/__init__.py

"""
安全审核模块

提供命令拦截、审计日志、安全告警功能
"""

from .guard import CommandGuard, GuardResult
from .audit import AuditLogger, AuditRecord
from .alert import SecurityAlert
from .constants import (
    DS_FORBIDDEN_COMMANDS,
    OSS_FORBIDDEN_OPERATIONS,
    HTTP_FORBIDDEN_METHODS,
    ALLOWED_READONLY,
)
from .approval import ApprovalWorkflow, ApprovalRequest

__all__ = [
    # 拦截器
    "CommandGuard",
    "GuardResult",

    # 审计
    "AuditLogger",
    "AuditRecord",

    # 告警
    "SecurityAlert",

    # 审批
    "ApprovalWorkflow",
    "ApprovalRequest",

    # 常量
    "DS_FORBIDDEN_COMMANDS",
    "OSS_FORBIDDEN_OPERATIONS",
    "HTTP_FORBIDDEN_METHODS",
    "ALLOWED_READONLY",
]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from src.security import CommandGuard, AuditLogger, SecurityAlert; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/security/__init__.py
git commit -m "feat: 更新 security 模块导出"
```

---

### Task 6: 集成到 dsctl_wrapper.py

**Files:**
- Modify: `src/integrations/dsctl_wrapper.py:46-77`

- [ ] **Step 1: 读取现有 dsctl_wrapper.py**

Run: `head -n 80 /d/Project/dolphinscheduler-agent/src/integrations/dsctl_wrapper.py`

- [ ] **Step 2: 在 DSCLIClient.__init__ 中初始化安全模块**

```python
# src/integrations/dsctl_wrapper.py（修改 __init__ 方法）

class DSCLIClient:
    """dsctl CLI 封装"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        version: str = "3.2.0"
    ):
        self.api_url = api_url or os.environ.get("DS_API_URL", "")
        self.api_token = api_token or os.environ.get("DS_API_TOKEN", "")
        self.version = version

        # 初始化安全模块
        from ..security import CommandGuard, AuditLogger, SecurityAlert
        self.guard = CommandGuard()
        self.audit = AuditLogger()
        self.alert = SecurityAlert()
```

- [ ] **Step 3: 修改 _run_command 方法添加安全检查**

```python
# src/integrations/dsctl_wrapper.py（修改 _run_command 方法）

def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
    """执行 dsctl 命令（增加安全检查）"""
    import time

    # 1. 安全检查
    guard_result = self.guard.check_cli_command(args)

    if guard_result.blocked:
        # 记录拦截日志
        self.audit.log_blocked(
            operation_type="dsctl",
            operation_detail=guard_result.operation_detail,
            reason=guard_result.reason,
            risk_level=guard_result.risk_level,
        )
        # 发送拦截告警
        self.alert.send_blocked_alert(
            operation_type="dsctl",
            operation_detail=guard_result.operation_detail,
            reason=guard_result.reason,
        )
        # 返回错误结果
        return CLIResult(
            success=False,
            stdout="",
            stderr=guard_result.reason,
            returncode=-1,
        )

    # 2. 执行命令
    env = os.environ.copy()
    env["DS_API_URL"] = self.api_url
    env["DS_API_TOKEN"] = self.api_token
    env["DS_VERSION"] = self.version

    cmd = ["python", "-m", "dsctl"] + args

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        cli_result = CLIResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode
        )

        # 3. 记录审计日志
        self.audit.log(
            operation_type="dsctl",
            operation_detail=guard_result.operation_detail,
            result="success" if cli_result.success else "failed",
            result_detail=cli_result.stderr[:200] if cli_result.stderr else "",
            risk_level=guard_result.risk_level,
            duration_ms=elapsed_ms,
        )

        # 4. 高风险操作发送告警
        if guard_result.risk_level == "HIGH":
            self.alert.send_high_risk_execution_alert(
                operation_type="dsctl",
                operation_detail=guard_result.operation_detail,
                result="success" if cli_result.success else "failed",
                error=cli_result.stderr if not cli_result.success else None,
            )

        return cli_result

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.time() - start_time) * 1000)
        self.audit.log_failed(
            operation_type="dsctl",
            operation_detail=guard_result.operation_detail,
            error="Command timed out",
            risk_level=guard_result.risk_level,
            duration_ms=elapsed_ms,
        )
        return CLIResult(
            success=False,
            stdout="",
            stderr="Command timed out",
            returncode=-1
        )
```

- [ ] **Step 4: 验证导入**

Run: `python -c "from src.integrations.dsctl_wrapper import DSCLIClient; c = DSCLIClient(); print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add src/integrations/dsctl_wrapper.py
git commit -m "feat: dsctl_wrapper 集成安全检查拦截"
```

---

### Task 7: 集成到 yarn_log.py

**Files:**
- Modify: `src/tools/yarn_log.py:18-36`

- [ ] **Step 1: 在 YARNLogTool.__init__ 中初始化安全模块**

```python
# src/tools/yarn_log.py（修改 __init__ 方法）

class YARNLogTool:
    """YARN Gateway 日志获取工具"""

    def __init__(
        self,
        gateway_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(username, password) if username and password else None

        # 初始化安全模块
        from ..security import CommandGuard, AuditLogger
        self.guard = CommandGuard()
        self.audit = AuditLogger()
```

- [ ] **Step 2: 修改 fetch_logs 方法添加安全检查**

```python
# src/tools/yarn_log.py（修改 fetch_logs 方法开头）

def fetch_logs(self, application_id: str) -> Dict[str, str]:
    """获取 YARN 应用信息（增加安全检查）"""
    url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"

    # 安全检查
    guard_result = self.guard.check_http_request("GET", url)

    if guard_result.blocked:
        self.audit.log_blocked(
            operation_type="http",
            operation_detail=guard_result.operation_detail,
            reason=guard_result.reason,
        )
        return {"error": guard_result.reason}

    # 执行请求...
    try:
        response = requests.get(
            url,
            auth=self.auth,
            timeout=15,
            verify=False
        )

        if response.status_code != 200:
            self.audit.log_failed("http", f"GET {url}", f"HTTP {response.status_code}")
            return {"error": f"HTTP {response.status_code}", "url": url}

        # ... 解析响应 ...

        # 记录审计
        self.audit.log_success("http", f"GET {url}", "LOW")

        return logs

    except requests.RequestException as e:
        self.audit.log_failed("http", f"GET {url}", str(e))
        return {"error": str(e)}
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/yarn_log.py
git commit -m "feat: yarn_log 集成安全检查拦截"
```

---

### Task 8: 集成到 oss_validator.py

**Files:**
- Modify: `src/skills/common/oss_validator.py:47-61`

- [ ] **Step 1: 在 OSSValidator.__init__ 中初始化安全模块**

```python
# src/skills/common/oss_validator.py（修改 __init__ 方法）

class OSSValidator:
    """OSS 文件验证工具"""

    _config: Optional[OSSConfig] = None
    _config_file_path: Optional[str] = None

    def __init__(self, config: Optional[OSSConfig] = None):
        if config:
            self._config = config
        else:
            self._config = self._load_config_from_env()

        # 初始化 ossutil 配置文件
        if self._config:
            self._init_ossutil_config()

        # 初始化安全模块
        from ...security import CommandGuard, AuditLogger, SecurityAlert
        self.guard = CommandGuard()
        self.audit = AuditLogger()
        self.alert = SecurityAlert()
```

- [ ] **Step 2: 修改 _run_ossutil 方法添加安全检查**

```python
# src/skills/common/oss_validator.py（修改 _run_ossutil 方法）

def _run_ossutil(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """执行 ossutil 命令（增加安全检查）"""

    # 安全检查
    guard_result = self.guard.check_oss_command(args)

    if guard_result.blocked:
        self.audit.log_blocked(
            operation_type="ossutil",
            operation_detail=guard_result.operation_detail,
            reason=guard_result.reason,
            risk_level=guard_result.risk_level,
        )
        self.alert.send_blocked_alert(
            operation_type="ossutil",
            operation_detail=guard_result.operation_detail,
            reason=guard_result.reason,
        )
        return subprocess.CompletedProcess(
            args=["ossutil"] + args,
            returncode=-1,
            stdout="",
            stderr=guard_result.reason,
        )

    # 执行命令
    cmd = ["ossutil"]

    if self._config_file_path:
        cmd.extend(["-c", self._config_file_path])

    cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # 记录审计
        self.audit.log_success(
            operation_type="ossutil",
            operation_detail="ossutil " + " ".join(args),
            risk_level="LOW",
        )

        return result

    except subprocess.TimeoutExpired:
        self.audit.log_failed(
            operation_type="ossutil",
            operation_detail="ossutil " + " ".join(args),
            error="Command timed out",
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=-1,
            stdout="",
            stderr="ossutil command timeout",
        )

    except FileNotFoundError:
        self.audit.log_failed(
            operation_type="ossutil",
            operation_detail="ossutil " + " ".join(args),
            error="ossutil not installed",
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=-2,
            stdout="",
            stderr="ossutil not installed. Please install from: https://help.aliyun.com/document_detail/50452.html",
        )
```

- [ ] **Step 3: Commit**

```bash
git add src/skills/common/oss_validator.py
git commit -m "feat: oss_validator 集成安全检查拦截"
```

---

### Task 9: 运行完整测试验证

- [ ] **Step 1: 运行所有 security 测试**

Run: `cd /d/Project/dolphinscheduler-agent && python -m pytest tests/test_security/ -v`
Expected: All PASS

- [ ] **Step 2: 运行集成测试验证导入**

Run: `python -c "
from src.integrations.dsctl_wrapper import DSCLIClient
from src.tools.yarn_log import YARNLogTool
from src.skills.common.oss_validator import OSSValidator
print('All imports OK')
"`
Expected: All imports OK

- [ ] **Step 3: 手动测试拦截功能**

Run: `python -c "
from src.integrations.dsctl_wrapper import DSCLIClient

c = DSCLIClient()
result = c._run_command(['workflow', 'delete', '123'])
print(f'Blocked: {result.success}')
print(f'Reason: {result.stderr}')
"`
Expected: Blocked: False, Reason: 命令 'delete' 在禁止列表中

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat: SecurityGuard 安全监管模块完成集成"
```

---

## 实现完成后

推送所有更改到远程仓库:
```bash
git push origin main
```