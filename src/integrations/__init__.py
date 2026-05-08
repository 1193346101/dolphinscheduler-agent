"""
外部系统集成
"""

from .ds_cli import DSCLIClient, CLIResult
from .dingtalk import DingTalkNotifier

__all__ = ["DSCLIClient", "CLIResult", "DingTalkNotifier"]