"""
CodeSearcher - Code file search by class name

Searches for Java/Scala/Python files by class name.
Used by Scanner to find Spark main class files.

项目名提取策略：
1. 从 jar 包名称提取：ad-monitor-1.0-jar-with-dependencies.jar → ad-monitor
2. 从类名包名推断：tv.huan.ad.monitor.ads.spot → ad-monitor
"""

import os
import re
from typing import Dict, List, Optional

# 项目名映射 - 延迟导入避免循环依赖
try:
    from .project_name_mapping import get_code_project_name
except ImportError:
    # 定义默认映射函数
    def get_code_project_name(ds_project_name: str) -> str:
        if "_" in ds_project_name:
            return ds_project_name.replace("_", "-")
        return ds_project_name


def extract_project_from_jar(jar_name: str) -> Optional[str]:
    """
    从 jar 包名称提取项目名

    Examples:
        ad-monitor-1.0-jar-with-dependencies.jar → ad-monitor
        data-product-2.0.jar → data-product
        huan-union.jar → huan-union

    Args:
        jar_name: jar 包名称或路径

    Returns:
        项目名或 None
    """
    if not jar_name:
        return None

    # 提取文件名（去掉路径）
    filename = os.path.basename(jar_name)

    # 移除版本号和后缀
    # ad-monitor-1.0-jar-with-dependencies.jar
    # pattern: {project}-{version}-{suffix}.jar
    match = re.match(r'^([a-zA-Z0-9_-]+)-[\d.]+', filename)
    if match:
        return match.group(1)

    # 如果没有版本号，直接移除 .jar 后缀
    if filename.endswith('.jar'):
        name = filename[:-4]
        # 移除常见后缀如 -jar-with-dependencies
        name = re.sub(r'-jar-with-dependencies$', '', name)
        return name

    return None


def extract_project_from_class(class_name: str) -> Optional[str]:
    """
    从类名包名推断项目名

    Examples:
        tv.huan.ad.monitor.ads.spot.XXX → ad-monitor
        tv.huan.data.product.XXX → data-product
        tv.huan.huan.union.XXX → huan-union

    Args:
        class_name: 全限定类名

    Returns:
        项目名或 None
    """
    if not class_name:
        return None

    # 包名格式：tv.huan.{project}.{submodule}
    # 提取 tv.huan 之后的部分
    parts = class_name.split('.')
    if len(parts) < 3:
        return None

    # 查找 tv.huan 之后的项目名部分
    if parts[0] == 'tv' and parts[1] == 'huan':
        # parts[2] 是项目名
        project_part = parts[2]
        # 转换：ad → ad, monitor 可能是独立的
        # tv.huan.ad.monitor → ad-monitor
        if len(parts) > 3:
            # 检查是否是组合项目名
            # ad.monitor → ad-monitor
            # data.product → data-product
            combined = f"{parts[2]}-{parts[3]}"
            return combined

        return project_part

    return None


class CodeSearcher:
    """
    Code file searcher that locates files by class name.

    Search Strategy:
    1. First: search within project directory ({code_root}/{code_project_name}/**)
    2. If not found: search globally ({code_root}/**)

    支持项目名映射：ad_monitor -> ad-monitor
    """

    def __init__(self, code_root: str):
        """
        Initialize with code repository root path.

        Args:
            code_root: Root directory containing all code repositories
        """
        self.code_root = code_root

    def class_to_paths(self, class_name: str) -> List[str]:
        """
        Convert class name to possible file paths.

        Handles Scala inner classes by splitting at $.
        Returns paths for .java, .scala, .py files.

        Args:
            class_name: Fully qualified class name (e.g., "com.example.MyClass"
                       or "com.example.Outer$Inner")

        Returns:
            List of possible relative file paths
        """
        paths = []

        # Handle Scala inner classes: Outer$Inner -> Outer
        # Split at $ and take the first part for file path
        simple_class_name = class_name.split('$')[0]

        # Convert class name to path
        # e.g., "com.example.MyClass" -> "com/example/MyClass"
        class_path = simple_class_name.replace('.', os.sep)

        # Generate paths for each supported file extension
        for ext in ['.java', '.scala', '.py']:
            paths.append(f"{class_path}{ext}")

        return paths

    def search_class(self, class_name: str, project_name: str) -> Dict:
        """
        Search for class file by class name.

        First searches in project directory, then globally if not found.

        Args:
            class_name: Fully qualified class name
            project_name: DS project name (e.g., ad_monitor)

        Returns:
            Dict with keys:
            - found: bool
            - file_path: str or null
            - cross_project: bool
            - source_project: str or null
        """
        possible_paths = self.class_to_paths(class_name)

        # 转换项目名：DS 项目名 -> 代码仓库目录名
        code_project_name = get_code_project_name(project_name)

        # First: search within project directory (尝试多种可能的目录名)
        project_dirs = [
            os.path.join(self.code_root, code_project_name),
            os.path.join(self.code_root, project_name),  # 原始名称
            os.path.join(self.code_root, project_name.replace("_", "-")),  # 下划线转短横线
            os.path.join(self.code_root, project_name.replace("-", "_")),  # 短横线转下划线
        ]

        for project_dir in project_dirs:
            if not os.path.isdir(project_dir):
                continue

            for path in possible_paths:
                # 尝试标准 src/main 路径
                src_paths = [
                    os.path.join(project_dir, "src", "main", "scala", path),
                    os.path.join(project_dir, "src", "main", "java", path),
                    os.path.join(project_dir, "src", path),
                    os.path.join(project_dir, path),
                ]

                for full_path in src_paths:
                    if os.path.isfile(full_path):
                        return {
                            "found": True,
                            "file_path": full_path,
                            "cross_project": False,
                            "source_project": os.path.basename(project_dir)
                        }

        # Second: search globally if not found in project
        for path in possible_paths:
            # Search in code_root subdirectories
            for root, dirs, files in os.walk(self.code_root):
                # Skip target directories (compiled classes)
                if 'target' in root:
                    continue

                # 构建 src/main/scala 或 src/main/java 路径
                src_path = os.path.join(root, "src", "main", "scala", path)
                if os.path.isfile(src_path):
                    rel_path = os.path.relpath(src_path, self.code_root)
                    source_project = rel_path.split(os.sep)[0] if os.sep in rel_path else None
                    return {
                        "found": True,
                        "file_path": src_path,
                        "cross_project": True,
                        "source_project": source_project
                    }

                src_path_java = os.path.join(root, "src", "main", "java", path)
                if os.path.isfile(src_path_java):
                    rel_path = os.path.relpath(src_path_java, self.code_root)
                    source_project = rel_path.split(os.sep)[0] if os.sep in rel_path else None
                    return {
                        "found": True,
                        "file_path": src_path_java,
                        "cross_project": True,
                        "source_project": source_project
                    }

        # Not found
        return {
            "found": False,
            "file_path": None,
            "cross_project": False,
            "source_project": None
        }

    def read_file_content(self, file_path: str) -> Optional[str]:
        """
        Read file content with UTF-8 encoding.

        Args:
            file_path: Absolute path to file

        Returns:
            File content as string, or None if file doesn't exist or read fails
        """
        try:
            if not os.path.isfile(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (IOError, OSError, UnicodeDecodeError):
            return None


__all__ = ["CodeSearcher"]