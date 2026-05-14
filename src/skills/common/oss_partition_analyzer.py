"""
OSS 分区历史对比分析器

用于检测分区数据异常：
- 分区完全缺失（PARTITION_MISSING）
- 文件数量异常减少（FILE_COUNT_LOW）
- 总大小异常减少（TOTAL_SIZE_LOW）
- 平均文件大小异常小（AVG_FILE_SIZE_SMALL）

通过 ossutil 获取分区文件列表和大小，与历史基线对比判断异常。
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

# 动态导入配置
_settings_path = Path(__file__).parent.parent.parent / "config" / "settings.py"


def _get_settings():
    """获取配置实例"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("settings", _settings_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.settings


@dataclass
class PartitionMetadata:
    """分区元数据"""
    partition_date: str
    oss_path: str
    file_count: int = 0
    total_size_bytes: int = 0
    avg_file_size_bytes: int = 0
    exists: bool = False
    error: Optional[str] = None
    files: List[str] = field(default_factory=list)


@dataclass
class HistoricalBaseline:
    """历史基线"""
    avg_file_count: float = 0
    avg_total_size_bytes: float = 0
    std_file_count: float = 0
    std_total_size_bytes: float = 0
    min_file_count: int = 0
    max_file_count: int = 0
    min_total_size_bytes: int = 0
    max_total_size_bytes: int = 0
    sample_count: int = 0
    partitions: List[PartitionMetadata] = field(default_factory=list)


@dataclass
class PartitionComparisonResult:
    """分区对比结果"""
    current_partition: PartitionMetadata
    baseline: HistoricalBaseline
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    severity: str = "NORMAL"
    recommendation: Optional[str] = None


class OSSPartitionAnalyzer:
    """OSS 分区历史分析器"""

    def __init__(self):
        from .oss_validator import OSSValidator
        self.validator = OSSValidator()

    def extract_partition_date(self, oss_path: str) -> Optional[str]:
        """
        从 OSS 路径提取分区日期

        支持格式：
        - dt=2026-05-13
        - date=2026-05-13
        - /2026-05-13/
        - /2026/05/13/

        Args:
            oss_path: OSS 路径

        Returns:
            日期字符串（YYYY-MM-DD）或 None
        """
        patterns = [
            r'(?:dt|date|day)=([0-9]{4}-[0-9]{2}-[0-9]{2})',
            r'(?:dt|date|day)=([0-9]{8})',
            r'/([0-9]{4}-[0-9]{2}-[0-9]{2})/',
            r'/([0-9]{4}/[0-9]{2}/[0-9]{2})/',
        ]

        for pattern in patterns:
            match = re.search(pattern, oss_path)
            if match:
                date_str = match.group(1)
                if '/' in date_str:
                    date_str = date_str.replace('/', '-')
                # 处理 8 位数字格式（20260513 -> 2026-05-13）
                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                return date_str

        return None

    def extract_partition_key(self, oss_path: str) -> str:
        """
        从 OSS 路径提取分区键名

        Args:
            oss_path: OSS 路径

        Returns:
            分区键名（如 "dt", "date"）或 "dt" 作为默认
        """
        match = re.search(r'(dt|date|day)=', oss_path)
        if match:
            return match.group(1)
        return "dt"

    def extract_base_path(self, oss_path: str, partition_date: str) -> str:
        """
        提取基础路径（去掉分区部分）

        Args:
            oss_path: OSS 路径
            partition_date: 分区日期

        Returns:
            基础路径
        """
        # 尝试去掉分区部分
        patterns = [
            f'/dt={partition_date}',
            f'/date={partition_date}',
            f'/day={partition_date}',
            f'/{partition_date}',
        ]

        for pattern in patterns:
            if pattern in oss_path:
                base = oss_path.split(pattern)[0]
                return base.rstrip("/") + "/"

        # 无法提取，返回原路径的父目录
        return oss_path.rsplit("/", 1)[0] + "/"

    def build_partition_path(
        self,
        base_path: str,
        partition_date: str,
        partition_key: str = "dt"
    ) -> str:
        """
        构建分区路径

        Args:
            base_path: 基础路径（oss://bucket/path/）
            partition_date: 日期（YYYY-MM-DD）
            partition_key: 分区键名

        Returns:
            完整分区路径
        """
        base = base_path.rstrip("/")
        return f"{base}/{partition_key}={partition_date}/"

    def get_partition_metadata(self, partition_path: str) -> PartitionMetadata:
        """
        获取分区元数据

        使用 ossutil ls 获取文件列表和大小。

        Args:
            partition_path: 分区路径

        Returns:
            PartitionMetadata
        """
        partition_date = self.extract_partition_date(partition_path) or ""

        # 使用 ossutil ls 获取文件列表
        result = self.validator._run_ossutil(["ls", partition_path])

        if result.returncode != 0:
            return PartitionMetadata(
                partition_date=partition_date,
                oss_path=partition_path,
                file_count=0,
                total_size_bytes=0,
                avg_file_size_bytes=0,
                exists=False,
                error=result.stderr[:200] if result.stderr else "分区不存在",
            )

        # 解析文件列表
        files = self.validator._parse_ls_output(result.stdout)

        # 过滤数据文件
        data_extensions = ['.parquet', '.csv', '.json', '.txt', '.orc', '.avro', '.snappy', '.gz']
        data_files = [
            f for f in files
            if any(f.lower().endswith(ext) for ext in data_extensions)
        ]

        # 计算总大小
        total_size = self.validator._calculate_total_size(result.stdout)

        file_count = len(data_files)
        avg_file_size = total_size // file_count if file_count > 0 else 0

        return PartitionMetadata(
            partition_date=partition_date,
            oss_path=partition_path,
            file_count=file_count,
            total_size_bytes=total_size,
            avg_file_size_bytes=avg_file_size,
            exists=True,
            files=data_files[:10],  # 只保留前10个文件名
        )

    def get_historical_partitions(
        self,
        base_path: str,
        current_date: str,
        days: int = 7,
        partition_key: str = "dt"
    ) -> List[PartitionMetadata]:
        """
        获取历史分区元数据

        Args:
            base_path: 基础路径
            current_date: 当前分区日期（YYYY-MM-DD）
            days: 查询天数（不含当天）
            partition_key: 分区键名

        Returns:
            历史分区元数据列表
        """
        try:
            current_dt = datetime.strptime(current_date, "%Y-%m-%d")
        except ValueError:
            return []

        historical = []

        for i in range(1, days + 1):  # 不含当天
            past_date = current_dt - timedelta(days=i)
            date_str = past_date.strftime("%Y-%m-%d")

            partition_path = self.build_partition_path(base_path, date_str, partition_key)
            metadata = self.get_partition_metadata(partition_path)
            historical.append(metadata)

        return historical

    def calculate_baseline(
        self,
        historical: List[PartitionMetadata]
    ) -> HistoricalBaseline:
        """
        计算历史基线

        只统计有效分区（有数据的）。

        Args:
            historical: 历史分区数据

        Returns:
            HistoricalBaseline
        """
        # 过滤有效分区
        valid_partitions = [p for p in historical if p.exists and p.file_count > 0]

        if not valid_partitions:
            return HistoricalBaseline(
                avg_file_count=0,
                avg_total_size_bytes=0,
                std_file_count=0,
                std_total_size_bytes=0,
                min_file_count=0,
                max_file_count=0,
                min_total_size_bytes=0,
                max_total_size_bytes=0,
                sample_count=0,
                partitions=historical,
            )

        file_counts = [p.file_count for p in valid_partitions]
        total_sizes = [p.total_size_bytes for p in valid_partitions]

        # 计算平均值
        avg_file_count = sum(file_counts) / len(file_counts)
        avg_total_size = sum(total_sizes) / len(total_sizes)

        # 计算标准差
        def std_dev(values, avg):
            if len(values) < 2:
                return 0
            variance = sum((v - avg) ** 2 for v in values) / len(values)
            return variance ** 0.5

        std_file_count = std_dev(file_counts, avg_file_count)
        std_total_size = std_dev(total_sizes, avg_total_size)

        return HistoricalBaseline(
            avg_file_count=avg_file_count,
            avg_total_size_bytes=avg_total_size,
            std_file_count=std_file_count,
            std_total_size_bytes=std_total_size,
            min_file_count=min(file_counts),
            max_file_count=max(file_counts),
            min_total_size_bytes=min(total_sizes),
            max_total_size_bytes=max(total_sizes),
            sample_count=len(valid_partitions),
            partitions=historical,
        )

    def detect_anomalies(
        self,
        current: PartitionMetadata,
        baseline: HistoricalBaseline
    ) -> List[Dict[str, Any]]:
        """
        检测异常

        异常类型：
        - PARTITION_MISSING: 分区完全缺失
        - FILE_COUNT_LOW: 文件数量远低于历史最小值
        - FILE_COUNT_BELOW_AVG: 文件数量低于历史平均值
        - TOTAL_SIZE_LOW: 总大小远低于历史平均
        - TOTAL_SIZE_BELOW_AVG: 总大小低于历史平均值
        - AVG_FILE_SIZE_SMALL: 平均文件大小异常小（空文件）

        Args:
            current: 当前分区元数据
            baseline: 历史基线

        Returns:
            异常列表
        """
        anomalies = []

        # 1. 分区完全缺失
        if not current.exists or current.file_count == 0:
            anomalies.append({
                "type": "PARTITION_MISSING",
                "severity": "CRITICAL",
                "message": f"分区 {current.partition_date} 完全缺失或无数据文件",
                "expected_file_count": int(baseline.avg_file_count) if baseline.avg_file_count > 0 else "未知",
                "actual_file_count": 0,
            })
            return anomalies  # 分区缺失时不再检测其他异常

        # 如果没有历史基线，无法判断异常
        if baseline.sample_count == 0:
            anomalies.append({
                "type": "NO_HISTORY_DATA",
                "severity": "LOW",
                "message": "无历史数据基线，无法判断异常",
            })
            return anomalies

        # 2. 文件数量异常减少
        if baseline.min_file_count > 0:
            if current.file_count < baseline.min_file_count * 0.5:
                anomalies.append({
                    "type": "FILE_COUNT_LOW",
                    "severity": "HIGH",
                    "message": f"文件数量 ({current.file_count}) 远低于历史最小值 ({baseline.min_file_count})",
                    "expected_min": baseline.min_file_count,
                    "actual": current.file_count,
                    "deviation_percent": round((baseline.avg_file_count - current.file_count) / baseline.avg_file_count * 100, 1),
                })
            elif current.file_count < baseline.avg_file_count - baseline.std_file_count * 2:
                anomalies.append({
                    "type": "FILE_COUNT_BELOW_AVG",
                    "severity": "MEDIUM",
                    "message": f"文件数量 ({current.file_count}) 低于历史平均值 ({int(baseline.avg_file_count)})",
                    "expected_avg": int(baseline.avg_file_count),
                    "actual": current.file_count,
                })

        # 3. 总大小异常减少
        if baseline.avg_total_size_bytes > 0:
            size_ratio = current.total_size_bytes / baseline.avg_total_size_bytes
            if size_ratio < 0.3:  # 低于历史平均 30%
                anomalies.append({
                    "type": "TOTAL_SIZE_LOW",
                    "severity": "HIGH",
                    "message": f"总大小 ({current.total_size_bytes // (1024*1024)}MB) 远低于历史平均 ({int(baseline.avg_total_size_bytes // (1024*1024))}MB)",
                    "expected_avg_mb": int(baseline.avg_total_size_bytes // (1024*1024)),
                    "actual_mb": current.total_size_bytes // (1024*1024),
                    "deviation_percent": round((1 - size_ratio) * 100, 1),
                })
            elif size_ratio < 0.5:
                anomalies.append({
                    "type": "TOTAL_SIZE_BELOW_AVG",
                    "severity": "MEDIUM",
                    "message": f"总大小 ({current.total_size_bytes // (1024*1024)}MB) 低于历史平均 50%",
                })

        # 4. 平均文件大小异常小（可能空文件）
        if current.avg_file_size_bytes < 1024 and current.file_count > 0:  # < 1KB
            anomalies.append({
                "type": "AVG_FILE_SIZE_SMALL",
                "severity": "HIGH",
                "message": f"平均文件大小 ({current.avg_file_size_bytes} bytes) 异常小，可能存在空文件",
                "avg_file_size_bytes": current.avg_file_size_bytes,
            })

        return anomalies

    def _determine_severity(self, anomalies: List[Dict]) -> str:
        """根据异常列表确定严重级别"""
        if not anomalies:
            return "NORMAL"

        severities = [a.get("severity", "LOW") for a in anomalies]

        if "CRITICAL" in severities:
            return "CRITICAL"
        elif "HIGH" in severities:
            return "HIGH"
        elif "MEDIUM" in severities:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_recommendation(
        self,
        anomalies: List[Dict],
        current: PartitionMetadata
    ) -> Optional[str]:
        """生成修复建议"""
        if not anomalies:
            return "分区数据正常，符合历史基线"

        anomaly_types = [a.get("type") for a in anomalies]

        if "PARTITION_MISSING" in anomaly_types:
            return "检查数据任务是否执行成功，或上游数据源是否有数据"

        if "FILE_COUNT_LOW" in anomaly_types:
            return "检查 Spark 任务是否输出正确，可能存在 Partition 倾斜导致部分文件丢失"

        if "TOTAL_SIZE_LOW" in anomaly_types:
            return "检查数据内容是否正确，可能存在数据截断或字段丢失"

        if "AVG_FILE_SIZE_SMALL" in anomaly_types:
            return "检查是否存在空文件，Spark 任务可能输出异常"

        if "NO_HISTORY_DATA" in anomaly_types:
            return "无历史数据基线，建议等待后续数据积累后再判断"

        return "建议检查数据任务执行日志"

    def compare_partition(
        self,
        base_path: str,
        current_date: str,
        days: int = 7,
        partition_key: str = "dt"
    ) -> PartitionComparisonResult:
        """
        对比当前分区与历史基线

        Args:
            base_path: 基础路径
            current_date: 当前分区日期
            days: 历史对比天数
            partition_key: 分区键名

        Returns:
            PartitionComparisonResult
        """
        # 1. 获取当前分区元数据
        current_path = self.build_partition_path(base_path, current_date, partition_key)
        current_metadata = self.get_partition_metadata(current_path)

        # 2. 获取历史分区元数据
        historical = self.get_historical_partitions(base_path, current_date, days, partition_key)

        # 3. 计算基线
        baseline = self.calculate_baseline(historical)

        # 4. 检测异常
        anomalies = self.detect_anomalies(current_metadata, baseline)

        # 5. 确定严重级别
        severity = self._determine_severity(anomalies)

        # 6. 生成建议
        recommendation = self._generate_recommendation(anomalies, current_metadata)

        return PartitionComparisonResult(
            current_partition=current_metadata,
            baseline=baseline,
            anomalies=anomalies,
            severity=severity,
            recommendation=recommendation,
        )


def analyze_partition_health(
    oss_path: str,
    days: int = 7
) -> PartitionComparisonResult:
    """
    分析分区健康状况（便捷入口函数）

    Args:
        oss_path: OSS 分区路径（包含 dt=YYYY-MM-DD）
        days: 历史对比天数

    Returns:
        PartitionComparisonResult
    """
    analyzer = OSSPartitionAnalyzer()

    # 提取分区日期
    partition_date = analyzer.extract_partition_date(oss_path)
    if not partition_date:
        return PartitionComparisonResult(
            current_partition=PartitionMetadata(
                partition_date="",
                oss_path=oss_path,
                file_count=0,
                total_size_bytes=0,
                avg_file_size_bytes=0,
                exists=False,
                error="无法从路径提取分区日期",
            ),
            baseline=HistoricalBaseline(
                avg_file_count=0,
                avg_total_size_bytes=0,
                std_file_count=0,
                std_total_size_bytes=0,
                min_file_count=0,
                max_file_count=0,
                min_total_size_bytes=0,
                max_total_size_bytes=0,
                sample_count=0,
                partitions=[],
            ),
            anomalies=[{
                "type": "INVALID_PATH",
                "severity": "CRITICAL",
                "message": "路径格式不支持，无法提取分区日期",
            }],
            severity="CRITICAL",
            recommendation="请使用分区路径格式，如 oss://bucket/path/dt=2026-05-13/",
        )

    # 提取分区键和基础路径
    partition_key = analyzer.extract_partition_key(oss_path)
    base_path = analyzer.extract_base_path(oss_path, partition_date)

    return analyzer.compare_partition(base_path, partition_date, days, partition_key)


__all__ = [
    "OSSPartitionAnalyzer",
    "PartitionMetadata",
    "HistoricalBaseline",
    "PartitionComparisonResult",
    "analyze_partition_health",
]