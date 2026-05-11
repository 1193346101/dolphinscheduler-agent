"""
外部系统集成

注意: DSCLIClient 在两个文件中定义:
- dsctl_wrapper.py: 简化版，无 settings 依赖
- ds_cli.py: 完整版，依赖 settings

直接导入 dsctl_wrapper 以避免 settings 依赖问题

dingtalk.py 和 ds_cli.py 需要完整的 src 包导入，不适合在脚本中直接导入
"""

# 只导入无 settings 依赖的模块
from .dsctl_wrapper import DSCLIClient, CLIResult

# dingtalk 和 ds_cli 需要从完整包导入
# from .dingtalk import DingTalkNotifier
# from .ds_cli import DSCLIClient, CLIResult

__all__ = ["DSCLIClient", "CLIResult", "DingTalkNotifier"]