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