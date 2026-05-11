"""
审计日志模块
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
    operation_type: str               # dsctl/ossutil/http/approval
    operation_detail: str            # 操作详情
    user: Optional[str] = None       # 操作人
    result: str = ""                 # success/failed/blocked
    result_detail: str = ""          # 错误摘要（截断至500字符）
    risk_level: str = "LOW"          # LOW/MEDIUM/HIGH/CRITICAL
    source_ip: Optional[str] = None  # 来源IP
    project_code: Optional[int] = None
    workflow_code: Optional[int] = None
    duration_ms: Optional[int] = None  # 执行耗时


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, log_dir: str = "logs/audit"):
        """初始化审计日志记录器

        Args:
            log_dir: 日志目录路径
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self,
            operation_type: str,
            operation_detail: str,
            result: str,
            result_detail: str = "",
            risk_level: str = "LOW",
            user: Optional[str] = None,
            source_ip: Optional[str] = None,
            project_code: Optional[int] = None,
            workflow_code: Optional[int] = None,
            duration_ms: Optional[int] = None) -> None:
        """通用记录方法

        Args:
            operation_type: 操作类型 (dsctl/ossutil/http/approval)
            operation_detail: 操作详情
            result: 结果 (success/failed/blocked)
            result_detail: 结果详情
            risk_level: 风险等级 (LOW/MEDIUM/HIGH/CRITICAL)
            user: 操作人
            source_ip: 来源IP
            project_code: 项目代码
            workflow_code: 工作流代码
            duration_ms: 执行耗时(毫秒)
        """
        record = AuditRecord(
            timestamp=datetime.now().isoformat(),
            operation_type=operation_type,
            operation_detail=operation_detail,
            user=user,
            result=result,
            result_detail=self._truncate(result_detail, 500),
            risk_level=risk_level,
            source_ip=source_ip,
            project_code=project_code,
            workflow_code=workflow_code,
            duration_ms=duration_ms
        )
        self._write_record(record)

    def log_blocked(self,
                    operation_type: str,
                    operation_detail: str,
                    reason: str,
                    risk_level: str = "CRITICAL",
                    user: Optional[str] = None,
                    source_ip: Optional[str] = None,
                    project_code: Optional[int] = None,
                    workflow_code: Optional[int] = None) -> None:
        """记录被拦截操作

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            reason: 拦截原因
            risk_level: 风险等级（默认CRITICAL）
            user: 操作人
            source_ip: 来源IP
            project_code: 项目代码
            workflow_code: 工作流代码
        """
        self.log(
            operation_type=operation_type,
            operation_detail=operation_detail,
            result="blocked",
            result_detail=reason,
            risk_level=risk_level,
            user=user,
            source_ip=source_ip,
            project_code=project_code,
            workflow_code=workflow_code
        )

    def log_success(self,
                    operation_type: str,
                    operation_detail: str,
                    risk_level: str = "LOW",
                    duration_ms: Optional[int] = None,
                    user: Optional[str] = None,
                    source_ip: Optional[str] = None,
                    project_code: Optional[int] = None,
                    workflow_code: Optional[int] = None,
                    result_detail: str = "") -> None:
        """记录成功操作

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            risk_level: 风险等级
            duration_ms: 执行耗时(毫秒)
            user: 操作人
            source_ip: 来源IP
            project_code: 项目代码
            workflow_code: 工作流代码
            result_detail: 结果详情
        """
        self.log(
            operation_type=operation_type,
            operation_detail=operation_detail,
            result="success",
            result_detail=result_detail,
            risk_level=risk_level,
            duration_ms=duration_ms,
            user=user,
            source_ip=source_ip,
            project_code=project_code,
            workflow_code=workflow_code
        )

    def log_failed(self,
                   operation_type: str,
                   operation_detail: str,
                   error: str,
                   risk_level: str = "LOW",
                   duration_ms: Optional[int] = None,
                   user: Optional[str] = None,
                   source_ip: Optional[str] = None,
                   project_code: Optional[int] = None,
                   workflow_code: Optional[int] = None) -> None:
        """记录失败操作

        Args:
            operation_type: 操作类型
            operation_detail: 操作详情
            error: 错误信息
            risk_level: 风险等级
            duration_ms: 执行耗时(毫秒)
            user: 操作人
            source_ip: 来源IP
            project_code: 项目代码
            workflow_code: 工作流代码
        """
        self.log(
            operation_type=operation_type,
            operation_detail=operation_detail,
            result="failed",
            result_detail=error,
            risk_level=risk_level,
            duration_ms=duration_ms,
            user=user,
            source_ip=source_ip,
            project_code=project_code,
            workflow_code=workflow_code
        )

    def _truncate(self, text: str, max_length: int) -> str:
        """截断文本到指定长度

        Args:
            text: 原始文本
            max_length: 最大长度

        Returns:
            截断后的文本
        """
        if len(text) <= max_length:
            return text
        return text[:max_length]

    def _write_record(self, record: AuditRecord) -> None:
        """写入审计记录到文件

        文件格式: logs/audit/YYYY-MM-DD.json（JSON Lines 格式）

        Args:
            record: 审计记录
        """
        # 生成日期文件名
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{today}.json"

        # 以 JSON Lines 格式追加写入
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")