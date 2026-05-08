"""
知识库管理 - 管理已确认的错误分析知识

核心规则: 只有 confirmed 状态的知识才能用于分析
"""

import json
import os
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

from ..config import settings


@dataclass
class KnowledgeEntry:
    """知识条目"""

    id: str
    task_type: str                    # SPARK, SHELL, PYTHON, DATAX
    error_type: str                   # oom_executor, syntax_error...
    pattern: str                      # 错误模式（字符串匹配）
    analysis: str                     # 分析内容
    suggestion: str                   # 建议

    # 自动修复配置
    config_fix: Optional[dict] = None  # 配置修复 {"spark.executor.memory": "4g"}
    script_fix: Optional[dict] = None  # 脚本修复 {"wrong_cmd": "correct_cmd"}

    # 状态
    status: str = "pending"           # pending, confirmed, rejected

    # 反馈
    feedback_type: Optional[str] = None  # valid, invalid
    human_suggestion: Optional[str] = None

    # 时间
    created_at: Optional[str] = None
    confirmed_at: Optional[str] = None


class KnowledgeManager:
    """
    知识库管理器

    核心规则:
    1. 只有 status=confirmed 的知识才能用于分析
    2. 新建议默认为 pending，等待人工确认
    3. 知识库存储在 JSON 文件中
    """

    def __init__(self):
        self.base_dir = settings.KNOWLEDGE_BASE_DIR
        self._cache: dict[str, list[KnowledgeEntry]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """加载所有知识库"""
        for task_type in ["spark", "shell", "python", "datax"]:
            self._cache[task_type] = self._load(task_type)

    def _load(self, task_type: str) -> list[KnowledgeEntry]:
        """加载指定类型的知识库"""
        file_path = os.path.join(self.base_dir, task_type, "confirmed.json")
        if not os.path.exists(file_path):
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [KnowledgeEntry(**item) for item in data]

    def _save(self, task_type: str, entries: list[KnowledgeEntry]) -> None:
        """保存知识库"""
        file_path = os.path.join(self.base_dir, task_type, "confirmed.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in entries], f, ensure_ascii=False, indent=2)

    def search_confirmed(
        self,
        task_type: str,
        error_type: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> list[KnowledgeEntry]:
        """
        搜索已确认的知识

        Args:
            task_type: 任务类型
            error_type: 错误类型（可选）
            pattern: 错误模式（可选）

        Returns:
            匹配的知识条目列表
        """
        entries = self._cache.get(task_type.lower(), [])

        # 只返回 confirmed 状态的
        confirmed = [e for e in entries if e.status == "confirmed"]

        if error_type:
            confirmed = [e for e in confirmed if e.error_type == error_type]

        if pattern:
            confirmed = [e for e in confirmed if pattern in e.pattern]

        return confirmed

    def match_error(
        self,
        task_type: str,
        error_message: str,
    ) -> Optional[KnowledgeEntry]:
        """
        根据错误消息匹配知识

        Args:
            task_type: 任务类型
            error_message: 错误消息

        Returns:
            匹配的知识条目（优先返回可自动修复的）
        """
        entries = self.search_confirmed(task_type)

        # 查找匹配
        matches = []
        for entry in entries:
            if entry.pattern in error_message:
                matches.append(entry)

        # 优先返回有自动修复方案的
        for m in matches:
            if m.config_fix or m.script_fix:
                return m

        # 否则返回第一个匹配
        return matches[0] if matches else None

    def add_pending(
        self,
        task_type: str,
        error_type: str,
        pattern: str,
        analysis: str,
        suggestion: str,
    ) -> KnowledgeEntry:
        """
        添加待确认的知识条目

        Args:
            task_type: 任务类型
            error_type: 错误类型
            pattern: 错误模式
            analysis: 分析内容
            suggestion: 建议

        Returns:
            新建的知识条目
        """
        entry = KnowledgeEntry(
            id=f"{task_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            task_type=task_type.upper(),
            error_type=error_type,
            pattern=pattern,
            analysis=analysis,
            suggestion=suggestion,
            status="pending",
            created_at=datetime.now().isoformat(),
        )

        # 添加到 pending 文件
        pending_path = os.path.join(self.base_dir, task_type.lower(), "pending.json")
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)

        pending_entries = []
        if os.path.exists(pending_path):
            with open(pending_path, "r", encoding="utf-8") as f:
                pending_entries = json.load(f)

        pending_entries.append(asdict(entry))

        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_entries, f, ensure_ascii=False, indent=2)

        return entry

    def confirm(
        self,
        entry_id: str,
        feedback: str,
        human_suggestion: Optional[str] = None,
    ) -> bool:
        """
        确认知识条目

        Args:
            entry_id: 条目 ID
            feedback: valid 或 invalid
            human_suggestion: 人工处理建议（invalid 时填写）

        Returns:
            是否成功
        """
        # 从 pending 中找到条目
        for task_type in ["spark", "shell", "python", "datax"]:
            pending_path = os.path.join(self.base_dir, task_type, "pending.json")
            if not os.path.exists(pending_path):
                continue

            with open(pending_path, "r", encoding="utf-8") as f:
                pending_entries = json.load(f)

            for i, entry_data in enumerate(pending_entries):
                if entry_data["id"] == entry_id:
                    entry = KnowledgeEntry(**entry_data)

                    if feedback == "valid":
                        entry.status = "confirmed"
                        entry.confirmed_at = datetime.now().isoformat()

                        # 添加到 confirmed
                        confirmed_entries = self._cache.get(task_type, [])
                        confirmed_entries.append(entry)
                        self._save(task_type, confirmed_entries)
                        self._cache[task_type] = confirmed_entries

                    else:
                        entry.status = "rejected"
                        entry.human_suggestion = human_suggestion

                    # 从 pending 中移除
                    pending_entries.pop(i)

                    with open(pending_path, "w", encoding="utf-8") as f:
                        json.dump(pending_entries, f, ensure_ascii=False, indent=2)

                    return True

        return False


# 全局知识库管理器
knowledge_manager = KnowledgeManager()


__all__ = ["KnowledgeEntry", "KnowledgeManager", "knowledge_manager"]