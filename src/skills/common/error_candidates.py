"""
Error Candidate Storage - 新错误模式候选存储

当 Skill 无法匹配已知错误模式时，调用 LLM 分析并记录结果。
人工审核后可将高质量候选添加到 patterns.md。

流程：
1. Skill 匹配失败 -> UNKNOWN
2. 调用 LLM 分析 -> 获取 error_type 建议
3. 保存候选到 error_candidates/{skill_name}_candidates.json
4. 人工审核 -> 添加到 patterns.md -> 删除候选
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ErrorCandidate:
    """错误模式候选"""

    # 基本信息
    skill_name: str                      # spark, shell, datax, python
    suggested_type: str                  # LLM建议的错误类型名
    suggested_pattern: str               # LLM建议的正则模式
    suggested_category: str              # LLM建议的类别 (KNOWN_NEEDS_LLM, etc.)
    suggested_hint: str                  # LLM建议的提示

    # 原始日志
    original_log: str                    # 原始错误日志片段
    log_excerpt: str                     # 提取的关键片段

    # LLM 分析结果
    llm_confidence: float                # LLM 分析置信度
    llm_description: str                 # LLM 的详细描述

    # 元数据
    timestamp: str                       # 发现时间
    task_type: str                       # 任务类型
    status: str = "pending"              # pending / approved / rejected

    # 审核信息
    reviewed_by: Optional[str] = None    # 审核人
    reviewed_at: Optional[str] = None    # 审核时间
    review_note: Optional[str] = None    # 审核备注


class ErrorCandidateStore:
    """
    错误候选存储管理器

    存储结构：
    error_candidates/
        spark_candidates.json
        shell_candidates.json
        datax_candidates.json
        python_candidates.json
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化

        Args:
            base_dir: 存储目录（默认在项目根目录下）
        """
        if base_dir is None:
            # 默认在 skills 目录下
            base_dir = str(Path(__file__).parent.parent.parent / "error_candidates")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file(self, skill_name: str) -> Path:
        """获取候选文件路径"""
        return self.base_dir / f"{skill_name}_candidates.json"

    def add(self, candidate: ErrorCandidate) -> bool:
        """
        添加新的错误候选

        Args:
            candidate: 错误候选对象

        Returns:
            是否成功添加
        """
        file_path = self._get_file(candidate.skill_name)

        # 加载现有候选
        candidates = self.load(candidate.skill_name)

        # 检查是否已存在相似候选
        for existing in candidates:
            if existing.get("original_log") == candidate.original_log:
                # 已存在，不重复添加
                return False

        # 添加新候选
        candidates.append(asdict(candidate))

        # 保存
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[CandidateStore] Error saving: {e}")
            return False

    def load(self, skill_name: str) -> List[Dict]:
        """
        加载指定 skill 的候选列表

        Args:
            skill_name: skill 名称

        Returns:
            候选列表
        """
        file_path = self._get_file(skill_name)

        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CandidateStore] Error loading: {e}")
            return []

    def get_pending(self, skill_name: str) -> List[Dict]:
        """
        获取待审核的候选

        Args:
            skill_name: skill 名称

        Returns:
            待审核候选列表
        """
        candidates = self.load(skill_name)
        return [c for c in candidates if c.get("status") == "pending"]

    def approve(self, skill_name: str, candidate_id: int, reviewer: str = "system", note: str = "") -> bool:
        """
        批准候选（已添加到 patterns.md 后调用）

        Args:
            skill_name: skill 名称
            candidate_id: 候选索引
            reviewer: 审核人
            note: 备注

        Returns:
            是否成功
        """
        candidates = self.load(skill_name)

        if candidate_id < 0 or candidate_id >= len(candidates):
            return False

        candidates[candidate_id]["status"] = "approved"
        candidates[candidate_id]["reviewed_by"] = reviewer
        candidates[candidate_id]["reviewed_at"] = datetime.now().isoformat()
        candidates[candidate_id]["review_note"] = note

        # 保存
        file_path = self._get_file(skill_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[CandidateStore] Error approving: {e}")
            return False

    def reject(self, skill_name: str, candidate_id: int, reviewer: str = "system", note: str = "") -> bool:
        """
        拒绝候选

        Args:
            skill_name: skill 名称
            candidate_id: 候选索引
            reviewer: 审核人
            note: 拒绝原因

        Returns:
            是否成功
        """
        candidates = self.load(skill_name)

        if candidate_id < 0 or candidate_id >= len(candidates):
            return False

        candidates[candidate_id]["status"] = "rejected"
        candidates[candidate_id]["reviewed_by"] = reviewer
        candidates[candidate_id]["reviewed_at"] = datetime.now().isoformat()
        candidates[candidate_id]["review_note"] = note

        # 保存
        file_path = self._get_file(skill_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[CandidateStore] Error rejecting: {e}")
            return False

    def clear_approved(self, skill_name: str) -> int:
        """
        清除已批准的候选（定期清理）

        Args:
            skill_name: skill 名称

        Returns:
            清除数量
        """
        candidates = self.load(skill_name)
        remaining = [c for c in candidates if c.get("status") != "approved"]

        file_path = self._get_file(skill_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(remaining, f, ensure_ascii=False, indent=2)
            return len(candidates) - len(remaining)
        except Exception as e:
            print(f"[CandidateStore] Error clearing: {e}")
            return 0


def create_candidate_from_llm(
    skill_name: str,
    original_log: str,
    llm_result: Dict,
    task_type: str = ""
) -> ErrorCandidate:
    """
    从 LLM 分析结果创建错误候选

    Args:
        skill_name: skill 名称
        original_log: 原始日志
        llm_result: LLM 分析结果
        task_type: 任务类型

    Returns:
        ErrorCandidate 对象
    """
    # 从 LLM 结果提取建议信息
    suggested_type = llm_result.get("error_category", "unknown").lower()
    suggested_hint = llm_result.get("error_description", "")

    # 生成候选模式（从日志中提取关键片段）
    log_excerpt = extract_pattern_candidate(original_log)

    # 生成建议的正则模式
    suggested_pattern = generate_pattern_from_excerpt(log_excerpt)

    return ErrorCandidate(
        skill_name=skill_name,
        suggested_type=suggested_type,
        suggested_pattern=suggested_pattern,
        suggested_category="KNOWN_NEEDS_LLM",  # 默认建议类别
        suggested_hint=suggested_hint,
        original_log=original_log[:500],  # 限制长度
        log_excerpt=log_excerpt,
        llm_confidence=llm_result.get("confidence", 0.5),
        llm_description=suggested_hint,
        timestamp=datetime.now().isoformat(),
        task_type=task_type,
        status="pending"
    )


def extract_pattern_candidate(log: str, max_len: int = 100) -> str:
    """
    从日志中提取可作为模式候选的关键片段

    Args:
        log: 原始日志
        max_len: 最大长度

    Returns:
        关键片段
    """
    # 去掉时间戳和INFO/DEBUG等前缀
    import re

    # 常见日志前缀
    patterns = [
        r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+',  # 时间戳
        r'^\[?\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\]?\s*',  # 时间戳
        r'\b(INFO|DEBUG|WARN|WARNING)\b\s*',  # INFO/DEBUG前缀
        r'^\s+',  # 开头空白
    ]

    cleaned = log
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)

    # 只保留关键错误信息
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]

    return cleaned.strip()


def generate_pattern_from_excerpt(excerpt: str) -> str:
    """
    从日志片段生成建议的正则模式

    Args:
        excerpt: 日志片段

    Returns:
        建议的正则模式
    """
    import re

    # 替换具体值为通用模式
    pattern = excerpt

    # 数字 -> \d+
    pattern = re.sub(r'\b\d+\b', r'\\d+', pattern)

    # 路径 -> 保持结构但简化
    pattern = re.sub(r'/[\w/]+', r'.*', pattern, count=1)

    # 如果结果太复杂，直接用原文作为模式
    if len(pattern) > 50 or '\\' in pattern:
        # 简化：直接包含原文
        return excerpt

    return pattern


__all__ = [
    "ErrorCandidate",
    "ErrorCandidateStore",
    "create_candidate_from_llm",
    "extract_pattern_candidate",
    "generate_pattern_from_excerpt",
]