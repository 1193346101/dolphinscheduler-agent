"""
项目名映射配置

DolphinScheduler 项目名与代码仓库目录名的映射关系

常见映射规则：
- DS: ad_monitor -> Code: ad-monitor
- DS: data_product -> Code: data-product
"""

from typing import Dict

# 项目名映射表（DS项目名 -> 代码仓库目录名）
PROJECT_NAME_MAPPING: Dict[str, str] = {
    # 广告相关
    "ad_monitor": "ad-monitor",
    "ad_fission": "ad-fission",
    "ad_link": "ad-link",
    "ad_link_lift": "ad-link-lift",
    "ad_sdk": "ad-sdk",
    "ad_server": "ad-server",
    "ad_closed_data": "ad-closed-data",
    "ad_interactive": "ad-interactive",

    # 数据相关
    "data_product": "data-product",
    "data_statistics": "data-statistics",
    "data_sync": "ch_data_sync",
    "data_clean": "ibs-data-cleaning",
    "data_lake": "huan-album",

    # 其他项目
    "huan_union": "huan-union",
    "csm_huan": "csm_huan",
    "tv_zone": "tv-zone-live",
    "tv_zone_real_time": "tv-zone-live",
    "qc_analysis": "qc_analysis",
    "cluster_monitor": "m-collect",
    "ch_data_sync": "ch_data_sync",
    "kdt_bigdata": "kdt_bigdata",
}


def get_code_project_name(ds_project_name: str) -> str:
    """
    将 DolphinScheduler 项目名转换为代码仓库目录名

    Args:
        ds_project_name: DS 项目名（如 ad_monitor）

    Returns:
        代码仓库目录名（如 ad-monitor）
    """
    # 直接匹配
    if ds_project_name in PROJECT_NAME_MAPPING:
        return PROJECT_NAME_MAPPING[ds_project_name]

    # 尝试下划线转短横线
    if "_" in ds_project_name:
        converted = ds_project_name.replace("_", "-")
        return converted

    # 尝试短横线转下划线
    if "-" in ds_project_name:
        converted = ds_project_name.replace("-", "_")
        return converted

    return ds_project_name


__all__ = ["PROJECT_NAME_MAPPING", "get_code_project_name"]