"""
Storage - JSON 文件存储管理

管理图谱和索引文件的读写
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Optional


class GraphStorage:
    """
    图谱存储管理

    文件命名规则:
    - 主图谱: {project_code}_graph.json
    - 索引: {project_code}_index_{index_type}.json
    """

    DEFAULT_DATA_DIR = "data/graph"

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        """
        初始化

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def save_graph(self, project_code: str, graph_data: Dict) -> None:
        """
        保存主图谱

        Args:
            project_code: 项目代码
            graph_data: 图谱数据
        """
        path = self._get_graph_path(project_code)

        # 路径穿越防护
        safe_path = self._sanitize_path(path)

        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

    def load_graph(self, project_code: str) -> Optional[Dict]:
        """
        加载主图谱

        Args:
            project_code: 项目代码

        Returns:
            图谱数据或 None
        """
        path = self._get_graph_path(project_code)
        safe_path = self._sanitize_path(path)

        if not os.path.exists(safe_path):
            return None

        with open(safe_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_index(self, project_code: str, index_type: str, index_data: Dict) -> None:
        """
        保存索引

        Args:
            project_code: 项目代码
            index_type: 索引类型 (downstream, table_consumer, workflow_nodes)
            index_data: 索引数据
        """
        path = self._get_index_path(project_code, index_type)
        safe_path = self._sanitize_path(path)

        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

    def load_index(self, project_code: str, index_type: str) -> Optional[Dict]:
        """
        加载索引

        Args:
            project_code: 项目代码
            index_type: 索引类型

        Returns:
            索引数据或 None
        """
        path = self._get_index_path(project_code, index_type)
        safe_path = self._sanitize_path(path)

        if not os.path.exists(safe_path):
            return None

        with open(safe_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def graph_exists(self, project_code: str) -> bool:
        """
        检查图谱是否存在

        Args:
            project_code: 项目代码

        Returns:
            是否存在
        """
        path = self._get_graph_path(project_code)
        return os.path.exists(path)

    def _get_graph_path(self, project_code: str) -> str:
        """获取图谱文件路径"""
        # 清理 project_code
        safe_code = self._sanitize_code(str(project_code))
        return os.path.join(self.data_dir, f"{safe_code}_graph.json")

    def _get_index_path(self, project_code: str, index_type: str) -> str:
        """获取索引文件路径"""
        safe_code = self._sanitize_code(str(project_code))
        safe_type = self._sanitize_code(index_type)
        return os.path.join(self.data_dir, f"{safe_code}_index_{safe_type}.json")

    def _sanitize_code(self, code: str) -> str:
        """清理代码字符串"""
        # 只保留字母、数字、下划线
        return re.sub(r'[^\w]', '_', code) if code else "unknown"

    def _sanitize_path(self, path: str) -> str:
        """路径安全检查"""
        # 确保路径在 data_dir 内部
        abs_path = os.path.abspath(path)
        abs_data_dir = os.path.abspath(self.data_dir)

        if not abs_path.startswith(abs_data_dir):
            raise ValueError(f"路径穿越攻击: {path}")

        return abs_path


__all__ = ["GraphStorage"]