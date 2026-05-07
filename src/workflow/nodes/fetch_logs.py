"""
fetch_logs 节点

获取 Spark 任务日志 - 完整实现
"""

from typing import Dict
from ..state import AgentState
from ...tools.spark_hist import SparkHistTool
from ...tools.yarn_log import YARNLogTool
from ...tools.k8s_log import K8sLogTool
from ...integrations.dsctl_wrapper import DSCLIClient


def fetch_logs(state: AgentState) -> AgentState:
    """
    获取日志

    协调多种日志源:
    1. dsctl CLI - driver 基础日志
    2. Spark History Server - Spark 日志
    3. YARN Gateway / K8s API - 运行环境日志

    Args:
        state: 当前状态

    Returns:
        更新后的状态 (driver_logs, spark_logs, yarn_logs/k8s_logs, log_fetch_error)
    """
    project_config = state.get("project_config")

    if not project_config:
        return {
            **state,
            "driver_logs": None,
            "spark_logs": None,
            "yarn_logs": None,
            "k8s_logs": None,
            "log_fetch_error": "无项目配置",
        }

    spark_mode = project_config.get("spark_mode", "yarn")
    spark_history_url = project_config.get("spark_history_url", "")

    # 1. 获取 dsctl driver 日志
    driver_logs = None
    log_fetch_error = None

    try:
        dsctl = DSCLIClient(
            api_url=project_config.get("ds_api_url", ""),
            api_token=project_config.get("ds_api_token", "")
        )

        task_instance_id = state["alert_raw"].get("taskInstanceId")
        if task_instance_id:
            result = dsctl.get_task_logs(task_instance_id)
            if result.success:
                driver_logs = result.stdout
            else:
                log_fetch_error = f"dsctl 日志获取失败: {result.stderr}"
    except Exception as e:
        log_fetch_error = f"dsctl 异常: {str(e)}"

    # 2. 获取 Spark History 日志
    spark_logs = None
    app_id = None

    if spark_history_url and driver_logs:
        try:
            spark_tool = SparkHistTool(history_url=spark_history_url)
            app_id = spark_tool.extract_app_id(driver_logs)

            if app_id:
                spark_logs_dict = spark_tool.fetch_logs(app_id)
                spark_logs = "\n".join(f"{k}: {v}" for k, v in spark_logs_dict.items())
        except Exception as e:
            if not log_fetch_error:
                log_fetch_error = f"Spark History 异常: {str(e)}"

    # 3. 根据模式获取额外日志
    yarn_logs = None
    k8s_logs = None

    if spark_mode == "yarn" and app_id:
        try:
            yarn_gateway_url = project_config.get("yarn_gateway_url", "")
            if yarn_gateway_url:
                yarn_tool = YARNLogTool(
                    gateway_url=yarn_gateway_url,
                    username=project_config.get("yarn_username"),
                    password=project_config.get("yarn_password")
                )
                yarn_logs_dict = yarn_tool.fetch_logs(app_id)
                yarn_logs = "\n".join(f"{k}: {v[:1000]}" for k, v in yarn_logs_dict.items())
        except Exception:
            pass

    elif spark_mode == "k8s":
        try:
            k8s_namespace = project_config.get("k8s_namespace", "spark-apps")
            k8s_tool = K8sLogTool(namespace=k8s_namespace)

            # 从 app_id 提取 app_name
            if app_id:
                app_name = app_id.replace("application_", "")
                k8s_logs_dict = k8s_tool.fetch_logs(app_name)
                k8s_logs = k8s_logs_dict
        except Exception:
            pass

    return {
        **state,
        "driver_logs": driver_logs,
        "spark_logs": spark_logs,
        "yarn_logs": yarn_logs,
        "k8s_logs": k8s_logs,
        "log_fetch_error": log_fetch_error,
    }


__all__ = ["fetch_logs"]