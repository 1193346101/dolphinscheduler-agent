"""
Chat API module - DingTalk webhook endpoints.

Provides FastAPI router for handling DingTalk chat messages.
"""

from .dingtalk_webhook import router

__all__ = ["router"]