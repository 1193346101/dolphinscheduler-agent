"""
多项目配置管理

每个 DolphinScheduler 项目可以有独立的:
- API 地址和 Token
- Spark History Server 地址
- YARN ResourceManager 地址 / K8s 配置
- 钉钉企业机器人配置
"""

from dataclasses import dataclass, field
from typing import Optional, List
import yaml
import os

from ..config.settings import settings


@dataclass
class DingTalkConfig:
    """钉钉企业机器人配置"""

    robot_code: str                       # 机器人编码
    client_id: str                        # Client ID
    client_secret: str                     # Client Secret
    notify_users: List[str] = field(default_factory=list)  # 通知接收人（钉钉用户 ID）


@dataclass
class SparkLogConfig:
    """Spark 日志配置"""

    mode: str = "yarn"                    # yarn 或 k8s
    history_url: Optional[str] = None     # Spark History Server URL

    # YARN 配置
    yarn_gateway_url: Optional[str] = None
    yarn_auth_type: str = "basic"
    yarn_username: Optional[str] = None
    yarn_password: Optional[str] = None

    # K8s 配置
    k8s_api_server: Optional[str] = None
    k8s_namespace: str = "spark-apps"
    k8s_kubeconfig_path: Optional[str] = None


@dataclass
class ProjectConfig:
    """单个项目配置"""

    # 基本信息
    name: str                          # 项目名称
    code: int                          # 项目编码
    ds_api_url: str                    # DolphinScheduler API 地址
    ds_api_token: str                  # 项目 Token
    ds_version: str = "3.2.0"          # DS 版本

    # 权限配置
    allowed_users: List[str] = field(default_factory=list)    # 允许操作的用户
    admin_users: List[str] = field(default_factory=list)      # 管理员（可审批高风险操作）

    # 集成配置
    spark_log: Optional[SparkLogConfig] = None
    dingtalk: Optional[DingTalkConfig] = None

    @property
    def effective_spark_history_url(self) -> str:
        """获取有效的 Spark History URL"""
        if self.spark_log and self.spark_log.history_url:
            return self.spark_log.history_url
        return settings.SPARK_HISTORY_URL

    @property
    def effective_spark_mode(self) -> str:
        """获取 Spark 日志模式"""
        if self.spark_log:
            return self.spark_log.mode
        return "yarn"

    @property
    def effective_yarn_gateway_url(self) -> Optional[str]:
        """获取有效的 YARN Gateway URL"""
        if self.spark_log and self.spark_log.yarn_gateway_url:
            return self.spark_log.yarn_gateway_url
        return getattr(settings, "YARN_GATEWAY_URL", None)

    @property
    def effective_dingtalk_config(self) -> Optional[DingTalkConfig]:
        """获取有效的钉钉配置"""
        return self.dingtalk


class ProjectsRegistry:
    """多项目注册表"""

    def __init__(self):
        self._projects: dict[int, ProjectConfig] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        """从配置文件加载项目配置"""
        config_path = os.getenv("PROJECTS_CONFIG_PATH", "config/projects.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "projects" in data:
                    for proj_data in data["projects"]:
                        # 解析钉钉配置
                        dingtalk_data = proj_data.get("dingtalk")
                        dingtalk = None
                        if dingtalk_data:
                            dingtalk = DingTalkConfig(
                                robot_code=dingtalk_data.get("robot_code", ""),
                                client_id=dingtalk_data.get("client_id", ""),
                                client_secret=dingtalk_data.get("client_secret", ""),
                                notify_users=dingtalk_data.get("notify_users", []),
                            )

                        # 解析 Spark 日志配置
                        spark_data = proj_data.get("spark_log")
                        spark_log = None
                        if spark_data:
                            spark_log = SparkLogConfig(
                                mode=spark_data.get("mode", "yarn"),
                                history_url=spark_data.get("history_url"),
                                yarn_gateway_url=spark_data.get("yarn_gateway_url"),
                                yarn_auth_type=spark_data.get("yarn_auth_type", "basic"),
                                yarn_username=spark_data.get("yarn_username"),
                                yarn_password=spark_data.get("yarn_password"),
                                k8s_api_server=spark_data.get("k8s_api_server"),
                                k8s_namespace=spark_data.get("k8s_namespace", "spark-apps"),
                                k8s_kubeconfig_path=spark_data.get("k8s_kubeconfig_path"),
                            )

                        config = ProjectConfig(
                            name=proj_data.get("name", ""),
                            code=proj_data.get("code", 0),
                            ds_api_url=proj_data.get("ds_api_url", ""),
                            ds_api_token=proj_data.get("ds_api_token", ""),
                            ds_version=proj_data.get("ds_version", "3.2.0"),
                            allowed_users=proj_data.get("allowed_users", []),
                            admin_users=proj_data.get("admin_users", []),
                            spark_log=spark_log,
                            dingtalk=dingtalk,
                        )
                        self._projects[config.code] = config

    def get_by_code(self, code: int) -> Optional[ProjectConfig]:
        """根据项目编码获取配置"""
        return self._projects.get(code)

    def get_by_name(self, name: str) -> Optional[ProjectConfig]:
        """根据项目名称获取配置"""
        for config in self._projects.values():
            if config.name == name:
                return config
        return None

    def all_projects(self) -> list[ProjectConfig]:
        """获取所有项目配置"""
        return list(self._projects.values())

    def register(self, config: ProjectConfig) -> None:
        """注册新项目"""
        self._projects[config.code] = config

    def is_user_allowed(self, project_code: int, user_id: str) -> bool:
        """检查用户是否有权限操作项目"""
        config = self.get_by_code(project_code)
        if not config:
            return False
        return user_id in config.allowed_users or user_id in config.admin_users

    def is_admin(self, project_code: int, user_id: str) -> bool:
        """检查用户是否是项目管理员"""
        config = self.get_by_code(project_code)
        if not config:
            return False
        return user_id in config.admin_users


# 全局项目注册表
projects_registry = ProjectsRegistry()


__all__ = ["ProjectConfig", "DingTalkConfig", "SparkLogConfig", "ProjectsRegistry", "projects_registry"]