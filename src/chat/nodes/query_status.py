"""
Query Status Node - 查询工作流状态
"""

import json
from typing import Dict, Any

from ..state import ChatState
from ...integrations import DSCLIClient
from ...config.projects import projects_registry
from ...config import settings


def query_status_node(state: ChatState) -> ChatState:
    """
    查询工作流状态

    Args:
        state: ChatState with workflow_code populated

    Returns:
        Updated ChatState with workflow status
    """
    workflow_code = state.get("workflow_code", "")

    if not workflow_code:
        return {
            **state,
            "error_message": "请提供工作流code",
            "response_content": "请提供工作流code，例如：工作流 12345 的状态",
        }

    # 调用 dsctl 查询工作流状态
    client = DSCLIClient(
        api_url=settings.DS_API_URL,
        api_token=settings.DS_API_TOKEN,
        version=settings.DS_VERSION,
    )

    # 查询工作流定义状态
    result = client.get_workflow(workflow_code)

    if not result.success:
        return {
            **state,
            "error_message": result.stderr or "查询失败",
            "response_content": f"查询工作流状态失败: {result.stderr or '未知错误'}",
        }

    # 解析结果
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            inner_data = data.get("data", data)
            name = inner_data.get("name", "未命名")
            code = inner_data.get("code", workflow_code)
            release_state = inner_data.get("releaseState", "UNKNOWN")
            description = inner_data.get("description", "")
            create_time = inner_data.get("createTime", "")
            update_time = inner_data.get("updateTime", "")
        else:
            name = "未命名"
            code = workflow_code
            release_state = "UNKNOWN"
            description = ""
            create_time = ""
            update_time = ""
    except json.JSONDecodeError:
        name = "未命名"
        release_state = "UNKNOWN"

    # 状态图标
    state_icon = {
        "ONLINE": "✅ 已上线",
        "OFFLINE": "⬇️ 已下线",
        "SCHEDULE": "🕐 定时调度",
    }.get(release_state, f"❓ {release_state}")

    # 格式化响应
    response = f"""### 工作流状态

**名称**: {name}
**Code**: {code}
**状态**: {state_icon}
**描述**: {description or '无'}
**创建时间**: {create_time}
**更新时间**: {update_time}"""

    return {
        **state,
        "result_data": {"workflow": data if isinstance(data, dict) else {}},
        "response_content": response,
        "workflow_name": name,
    }


__all__ = ["query_status_node"]