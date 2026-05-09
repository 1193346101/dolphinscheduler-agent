"""
Configuration settings
GSD: Use environment variables, keep it simple.
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings loaded from environment."""

    # LLM Configuration (Anthropic compatible)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "glm-5")

    # DolphinScheduler Configuration
    DS_API_URL: str = os.getenv("DS_API_URL", "http://localhost:12345/dolphinscheduler")
    DS_API_TOKEN: str = os.getenv("DS_API_TOKEN", "")
    DS_VERSION: str = os.getenv("DS_VERSION", "3.2.0")

    # Graph Configuration
    CODE_ROOT_PATH: str = os.getenv("CODE_ROOT_PATH", "")
    GRAPH_STORAGE_PATH: str = os.getenv("GRAPH_STORAGE_PATH", "data/graph")

    def __post_init__(self):
        if not self.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")


settings = Settings()