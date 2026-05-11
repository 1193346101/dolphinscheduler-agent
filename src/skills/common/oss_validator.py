"""
OSS 文件验证工具

使用 ossutil 命令验证 OSS 文件/目录是否存在，
用于快速判断数据文件缺失问题。

配置来源：
- OSS_ENDPOINT: OSS 区域地址（如 oss-cn-hangzhou.aliyuncs.com）
- OSS_ACCESS_KEY_ID: 阿里云 AccessKey ID
- OSS_ACCESS_KEY_SECRET: 阿里云 AccessKey Secret
- OSS_BUCKET: 默认 bucket 名称（可选）
"""

import os
import subprocess
import re
from typing import Dict, Optional, List
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OSSConfig:
    """OSS 配置"""
    endpoint: str
    access_key_id: str
    access_key_secret: str
    bucket: Optional[str] = None


@dataclass
class OSSCheckResult:
    """OSS 检查结果"""
    exists: bool
    path: str
    files: List[str] = None
    total_size: int = 0
    error: Optional[str] = None


class OSSValidator:
    """OSS 文件验证工具"""

    _config: Optional[OSSConfig] = None
    _config_file_path: Optional[str] = None

    def __init__(self, config: Optional[OSSConfig] = None):
        """
        初始化 OSS 验证器

        Args:
            config: OSS 配置，如果为 None 则从环境变量读取
        """
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

    def _load_config_from_env(self) -> Optional[OSSConfig]:
        """从环境变量加载 OSS 配置"""
        endpoint = os.getenv("OSS_ENDPOINT")
        access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
        access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
        bucket = os.getenv("OSS_BUCKET")

        if not all([endpoint, access_key_id, access_key_secret]):
            return None

        return OSSConfig(
            endpoint=endpoint,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            bucket=bucket,
        )

    def _init_ossutil_config(self) -> None:
        """初始化 ossutil 配置文件"""
        # 配置文件路径
        self._config_file_path = os.path.expanduser("~/.ossutilconfig_for_agent")

        # 写入配置文件
        config_content = f"""[Credentials]
language=CH
endpoint={self._config.endpoint}
accessKeyID={self._config.access_key_id}
accessKeySecret={self._config.access_key_secret}
"""

        try:
            with open(self._config_file_path, 'w') as f:
                f.write(config_content)
        except IOError as e:
            print(f"[WARN] Failed to write ossutil config: {e}")

    def _run_ossutil(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """
        执行 ossutil 命令（增加安全检查）

        Args:
            args: 命令参数列表
            timeout: 超时时间（秒）

        Returns:
            subprocess.CompletedProcess 结果
        """
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

        cmd = ["ossutil"]

        # 使用指定的配置文件
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
                error="ossutil command timeout",
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

    def check_exists(self, oss_path: str) -> OSSCheckResult:
        """
        检查 OSS 路径是否存在

        Args:
            oss_path: OSS 路径，如 oss://bucket/path/ 或 bucket/path/

        Returns:
            OSSCheckResult 检查结果
        """
        # 规范化路径
        if not oss_path.startswith("oss://"):
            if self._config and self._config.bucket:
                oss_path = f"oss://{self._config.bucket}/{oss_path}"
            else:
                oss_path = f"oss://{oss_path}"

        result = self._run_ossutil(["ls", oss_path, "-d"])

        if result.returncode == 0:
            files = self._parse_ls_output(result.stdout)
            total_size = self._calculate_total_size(result.stdout)
            return OSSCheckResult(
                exists=True,
                path=oss_path,
                files=files,
                total_size=total_size,
            )
        else:
            return OSSCheckResult(
                exists=False,
                path=oss_path,
                error=result.stderr or "Path does not exist",
            )

    def check_partition(self, partition_path: str) -> OSSCheckResult:
        """
        检查分区路径是否有数据文件

        Args:
            partition_path: 分区路径，如 oss://bucket/data/partition=2024-01-01/

        Returns:
            OSSCheckResult 检查结果
        """
        result = self.check_exists(partition_path)

        if result.exists:
            # 进一步检查是否有实际数据文件（不只是目录）
            ls_result = self._run_ossutil(["ls", partition_path])

            if ls_result.returncode == 0:
                files = self._parse_ls_output(ls_result.stdout)
                # 过滤数据文件（.parquet, .csv, .json 等）
                data_files = [
                    f for f in files
                    if any(f.endswith(ext) for ext in ['.parquet', '.csv', '.json', '.txt', '.orc'])
                ]

                if len(data_files) == 0:
                    return OSSCheckResult(
                        exists=True,
                        path=partition_path,
                        files=files,
                        error="Partition exists but no data files found",
                    )

                return OSSCheckResult(
                    exists=True,
                    path=partition_path,
                    files=data_files,
                    total_size=self._calculate_total_size(ls_result.stdout),
                )

        return result

    def get_file_stat(self, oss_path: str) -> Dict:
        """
        获取文件详细信息

        Args:
            oss_path: OSS 文件路径

        Returns:
            文件信息字典
        """
        result = self._run_ossutil(["stat", oss_path])

        if result.returncode == 0:
            return self._parse_stat_output(result.stdout)

        return {"error": result.stderr}

    def _parse_ls_output(self, output: str) -> List[str]:
        """解析 ossutil ls 输出"""
        files = []
        for line in output.split('\n'):
            # ossutil 输出格式: "2024-01-01 10:00:00 1024 bytes oss://bucket/path/file.parquet"
            match = re.search(r'oss://[^\s]+', line)
            if match:
                files.append(match.group(0))
        return files

    def _parse_stat_output(self, output: str) -> Dict:
        """解析 ossutil stat 输出"""
        info = {}
        for line in output.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if key in ['Content-Length', 'Last-Modified', 'ETag', 'Content-Type']:
                    info[key] = value
        return info

    def _calculate_total_size(self, output: str) -> int:
        """计算总大小"""
        total = 0
        for line in output.split('\n'):
            # 匹配文件大小
            match = re.search(r'\s+(\d+)\s+bytes', line)
            if match:
                total += int(match.group(1))
        return total

    def build_oss_path(self, bucket: str, path: str) -> str:
        """
        构建 OSS 路径

        Args:
            bucket: Bucket 名称
            path: 路径

        Returns:
            完整 OSS 路径
        """
        if not path.startswith('/'):
            path = '/' + path
        return f"oss://{bucket}{path}"

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return self._config is not None


def get_oss_validator() -> OSSValidator:
    """获取 OSS 验证器实例"""
    return OSSValidator()


__all__ = [
    "OSSValidator",
    "OSSConfig",
    "OSSCheckResult",
    "get_oss_validator",
]