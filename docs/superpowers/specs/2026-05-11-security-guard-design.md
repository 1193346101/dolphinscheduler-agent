# SecurityGuard 安全监管模块设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现命令级安全拦截、操作审计日志、高风险告警，保障所有系统操作在安全范围内执行

**Architecture:** 独立 SecurityGuard 模块 + 在 CLI/HTTP/OSS 调用点集成拦截

**Tech Stack:** Python dataclasses, JSON Lines, DingTalk API

---

## 安全监管范围

| 系统 | 限制规则 |
|-----|---------|
| **DolphinScheduler** | delete 命令硬性禁止 |
| **Spark History Server** | 只读权限（禁止 POST/PUT/DELETE/PATCH） |
| **YARN** | 只读权限（禁止 POST/PUT/DELETE/PATCH） |
| **OSS** | 只读权限（禁止 cp/mv/rm/put/sync） |

---

## 模块结构

```
src/security/
├── __init__.py        # 导出 SecurityGuard, AuditLogger 等
├── approval.py        # [现有] 审批流程
├── guard.py           # [新增] CommandGuard - 命令拦截
├── audit.py           # [新增] AuditLogger - 审计日志
├── alert.py           # [新增] SecurityAlert - 高风险告警
├── constants.py       # [新增] 常量定义

logs/audit/            # 审计日志目录（自动创建）
├── 2026-05-11.json    # 每日一个 JSON Lines 文件
```

---

## 常量定义

```python
# src/security/constants.py

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
```

---

## CommandGuard 模块

```python
# src/security/guard.py

"""
CommandGuard - 命令安全拦截器

对所有系统操作进行安全检查：
- DolphinScheduler CLI 命令
- ossutil 命令
- HTTP 请求（YARN、History Server）
"""

from dataclasses import dataclass
from typing import List, Optional
from .constants import (
    DS_FORBIDDEN_COMMANDS,
    OSS_FORBIDDEN_OPERATIONS,
    HTTP_FORBIDDEN_METHODS,
)


@dataclass
class GuardResult:
    """安全检查结果"""
    allowed: bool                      # 是否允许执行
    blocked: bool                      # 是否被拦截
    reason: str                        # 拦截原因（如被禁止）
    operation_type: str                # 操作类型: dsctl/ossutil/http
    operation_detail: str              # 具体操作详情
    risk_level: str = "LOW"            # 风险等级


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
    
    def check_oss_command(self, args: List[str]) -> GuardResult:
        """检查 ossutil 命令是否允许"""
        if not args:
            return GuardResult(allowed=True, blocked=False, reason="", operation_type="ossutil", operation_detail="")
        
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
    
    def _assess_risk(self, args: List[str]) -> str:
        """评估风险等级"""
        cmd_str = " ".join(args).lower()
        
        if "recover" in cmd_str:
            return "HIGH"
        
        if "edit" in cmd_str or "modify" in cmd_str:
            return "MEDIUM"
        
        return "LOW"
```

---

## AuditLogger 模块

```python
# src/security/audit.py

"""
AuditLogger - 操作审计日志

存储格式：本地 JSON Lines 文件，每日一个文件
"""

import json
from datetime import datetime
from typing import Dict, Optional
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
    duration_ms: Optional[int] = None # 执行耗时（毫秒）


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, operation_type: str, operation_detail: str, result: str,
            result_detail: str = "", risk_level: str = "LOW",
            user: Optional[str] = None, source_ip: Optional[str] = None,
            project_code: Optional[int] = None, workflow_code: Optional[int] = None,
            duration_ms: Optional[int] = None) -> None:
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
    
    def log_blocked(self, operation_type: str, operation_detail: str,
                    reason: str, risk_level: str = "CRITICAL") -> None:
        """记录被拦截的操作"""
        self.log(operation_type, operation_detail, "blocked", reason, risk_level)
    
    def log_success(self, operation_type: str, operation_detail: str,
                    risk_level: str = "LOW", duration_ms: Optional[int] = None,
                    project_code: Optional[int] = None,
                    workflow_code: Optional[int] = None) -> None:
        """记录成功的操作"""
        self.log(operation_type, operation_detail, "success", "", risk_level,
                 duration_ms=duration_ms, project_code=project_code,
                 workflow_code=workflow_code)
    
    def log_failed(self, operation_type: str, operation_detail: str,
                   error: str, risk_level: str = "LOW",
                   duration_ms: Optional[int] = None) -> None:
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
```

---

## SecurityAlert 模块

```python
# src/security/alert.py

"""
SecurityAlert - 安全告警发送器

高风险操作执行时发送钉钉告警
"""

from typing import Optional
from datetime import datetime
from ..integrations.dingtalk import DingTalkNotifier


class SecurityAlert:
    """安全告警发送器"""
    
    def __init__(self):
        self.notifier = DingTalkNotifier()
    
    def send_high_risk_alert(self, operation_type: str, operation_detail: str,
                              result: str, risk_level: str,
                              reason: Optional[str] = None) -> bool:
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
    
    def send_blocked_alert(self, operation_type: str, operation_detail: str,
                            reason: str) -> bool:
        """发送禁止操作拦截告警"""
        return self.send_high_risk_alert(operation_type, operation_detail,
                                          "blocked", "CRITICAL", reason)
    
    def send_high_risk_execution_alert(self, operation_type: str,
                                        operation_detail: str, result: str,
                                        error: Optional[str] = None) -> bool:
        """发送高风险执行告警"""
        return self.send_high_risk_alert(operation_type, operation_detail,
                                          result, "HIGH", error)
```

---

## 集成调用点

### 1. dsctl_wrapper.py 改动

在 `_run_command` 方法中增加安全检查：

```python
def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
    import time
    
    # 1. 安全检查
    guard_result = self.guard.check_cli_command(args)
    
    if guard_result.blocked:
        self.audit.log_blocked("dsctl", guard_result.operation_detail,
                               guard_result.reason, guard_result.risk_level)
        self.alert.send_blocked_alert("dsctl", guard_result.operation_detail,
                                       guard_result.reason)
        return CLIResult(success=False, stdout="", stderr=guard_result.reason,
                         returncode=-1)
    
    # 2. 执行命令
    start_time = time.time()
    # ... subprocess.run ...
    elapsed_ms = int((time.time() - start_time) * 1000)
    
    # 3. 记录审计
    self.audit.log("dsctl", guard_result.operation_detail,
                   "success" if result.returncode == 0 else "failed",
                   result.stderr[:200] if result.stderr else "",
                   guard_result.risk_level, duration_ms=elapsed_ms)
    
    # 4. 高风险告警
    if guard_result.risk_level == "HIGH":
        self.alert.send_high_risk_execution_alert(
            "dsctl", guard_result.operation_detail,
            "success" if result.returncode == 0 else "failed",
            result.stderr if result.returncode != 0 else None)
    
    return CLIResult(...)
```

### 2. yarn_log.py 改动

在 `fetch_logs` 方法中增加安全检查：

```python
def fetch_logs(self, application_id: str) -> Dict[str, str]:
    url = f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"
    
    guard_result = self.guard.check_http_request("GET", url)
    
    if guard_result.blocked:
        self.audit.log_blocked("http", guard_result.operation_detail,
                               guard_result.reason)
        return {"error": guard_result.reason}
    
    # ... requests.get ...
    
    self.audit.log_success("http", f"GET {url}", "LOW")
    
    return logs
```

### 3. oss_validator.py 改动

在 `_run_ossutil` 方法中增加安全检查：

```python
def _run_ossutil(self, args: List[str], timeout: int = 30):
    guard_result = self.guard.check_oss_command(args)
    
    if guard_result.blocked:
        self.audit.log_blocked("ossutil", guard_result.operation_detail,
                               guard_result.reason, guard_result.risk_level)
        self.alert.send_blocked_alert("ossutil", guard_result.operation_detail,
                                       guard_result.reason)
        return subprocess.CompletedProcess(args=["ossutil"] + args,
                                            returncode=-1, stdout="",
                                            stderr=guard_result.reason)
    
    # ... subprocess.run ...
    
    self.audit.log_success("ossutil", "ossutil " + " ".join(args), "LOW")
    
    return result
```

---

## 告警触发规则

| 触发条件 | 告警类型 |
|---------|---------|
| 被拦截的禁止命令（delete、rm 等） | 禁止操作拦截告警 |
| HIGH 级别操作执行成功/失败（recover-failed） | 高风险执行告警 |
| LOW/MEDIUM 级别操作 | 仅记录审计日志，不发送告警 |

---

## 审计日志格式示例

```json
{"timestamp": "2026-05-11T14:30:00.123", "operation_type": "dsctl", "operation_detail": "workflow delete 12345", "result": "blocked", "result_detail": "命令 'delete' 在禁止列表中，禁止执行", "risk_level": "CRITICAL"}
{"timestamp": "2026-05-11T14:31:00.456", "operation_type": "dsctl", "operation_detail": "workflow-instance recover-failed 100001", "result": "success", "risk_level": "HIGH", "duration_ms": 350}
{"timestamp": "2026-05-11T14:32:00.789", "operation_type": "ossutil", "operation_detail": "ossutil ls oss://bucket/path/", "result": "success", "risk_level": "LOW"}
{"timestamp": "2026-05-11T14:33:00.012", "operation_type": "http", "operation_detail": "GET https://yarn/api/apps/app_123", "result": "success", "risk_level": "LOW"}
```

---

## 实现文件清单

| 文件 | 操作 | 说明 |
|-----|------|------|
| `src/security/constants.py` | Create | 常量定义 |
| `src/security/guard.py` | Create | CommandGuard 模块 |
| `src/security/audit.py` | Create | AuditLogger 模块 |
| `src/security/alert.py` | Create | SecurityAlert 模块 |
| `src/security/__init__.py` | Modify | 导出新模块 |
| `src/integrations/dsctl_wrapper.py` | Modify | 集成安全检查 |
| `src/tools/yarn_log.py` | Modify | 集成安全检查 |
| `src/skills/common/oss_validator.py` | Modify | 集成安全检查 |