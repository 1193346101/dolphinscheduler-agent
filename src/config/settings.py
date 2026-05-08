"""
全局配置 - 从环境变量加载
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    """全局配置"""

    # LLM 配置
    LLM_API_KEY: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    LLM_API_URL: str = field(default_factory=lambda: os.getenv("LLM_API_URL", ""))
    LLM_MODEL: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-6"))

    # DolphinScheduler API 配置（复用 dsctl 的环境变量）
    DS_API_URL: str = field(default_factory=lambda: os.getenv("DS_API_URL", ""))
    DS_API_TOKEN: str = field(default_factory=lambda: os.getenv("DS_API_TOKEN", ""))
    DS_VERSION: str = field(default_factory=lambda: os.getenv("DS_VERSION", "3.2.0"))

    # 钉钉机器人
    DINGTALK_WEBHOOK: str = field(default_factory=lambda: os.getenv("DINGTALK_WEBHOOK", ""))
    DINGTALK_SECRET: str = field(default_factory=lambda: os.getenv("DINGTALK_SECRET", ""))

    # 飞书机器人
    FEISHU_WEBHOOK: str = field(default_factory=lambda: os.getenv("FEISHU_WEBHOOK", ""))
    FEISHU_APP_ID: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    FEISHU_APP_SECRET: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))

    # 日志存储
    LOG_RETENTION_DAYS: int = field(default_factory=lambda: int(os.getenv("LOG_RETENTION_DAYS", "7")))
    LOG_MAX_SIZE_MB: int = field(default_factory=lambda: int(os.getenv("LOG_MAX_SIZE_MB", "500")))
    LOG_DIR: str = field(default_factory=lambda: os.getenv("LOG_DIR", "logs"))

    # 安全配置 - 自动修复风险阈值
    AUTO_FIX_MAX_RISK: str = field(default_factory=lambda: os.getenv("AUTO_FIX_MAX_RISK", "MEDIUM"))
    APPROVAL_TIMEOUT_MINUTES: int = field(default_factory=lambda: int(os.getenv("APPROVAL_TIMEOUT_MINUTES", "30")))

    # Spark History Server（全局默认）
    SPARK_HISTORY_URL: str = field(default_factory=lambda: os.getenv("SPARK_HISTORY_URL", ""))
    SPARK_HISTORY_TIMEOUT: int = field(default_factory=lambda: int(os.getenv("SPARK_HISTORY_TIMEOUT", "30")))

    # YARN ResourceManager（全局默认）
    YARN_RM_URL: str = field(default_factory=lambda: os.getenv("YARN_RM_URL", ""))
    YARN_RM_TIMEOUT: int = field(default_factory=lambda: int(os.getenv("YARN_RM_TIMEOUT", "30")))

    # API 服务
    API_HOST: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    API_PORT: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8080")))

    # 知识库
    KNOWLEDGE_BASE_DIR: str = field(default_factory=lambda: os.getenv("KNOWLEDGE_BASE_DIR", "knowledge_base"))

    # 知识图谱
    GRAPH_STORAGE_PATH: str = field(default_factory=lambda: os.getenv("GRAPH_STORAGE_PATH", "data/graph"))
    CODE_ROOT_PATH: str = field(default_factory=lambda: os.getenv("CODE_ROOT_PATH", ""))

    # 默认项目（用于 Chat Agent）
    DEFAULT_PROJECT_CODE: str = field(default_factory=lambda: os.getenv("DEFAULT_PROJECT_CODE", ""))

    # 项目配置文件
    PROJECTS_CONFIG_PATH: str = field(default_factory=lambda: os.getenv("PROJECTS_CONFIG_PATH", "config/projects.yaml"))

    def validate(self) -> None:
        """验证必要配置"""
        if not self.LLM_API_KEY:
            raise ValueError("LLM_API_KEY 环境变量必须设置")

    @property
    def auto_fix_allowed_risks(self) -> set[str]:
        """获取允许自动修复的风险等级"""
        max_risk = self.AUTO_FIX_MAX_RISK
        if max_risk == "LOW":
            return {"LOW"}
        elif max_risk == "MEDIUM":
            return {"LOW", "MEDIUM"}
        else:
            return {"LOW", "MEDIUM", "HIGH"}


# 全局配置实例
settings = Settings()