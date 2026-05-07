"""
DolphinScheduler Agent - Entry Point

启动 API 服务接收告警和对话请求
使用 LangGraph 状态机处理告警
"""

import os
from dotenv import load_dotenv

load_dotenv()

from src.api import run_server
from src.config import settings


def main():
    """Main entry point - 启动 API 服务"""
    print("=" * 60)
    print("DolphinScheduler Agent Ready (LangGraph Edition)")
    print("=" * 60)
    print()
    print("API Endpoints:")
    print("  POST /webhook    - 接收 DS 告警（LangGraph 状态机处理）")
    print("  POST /chat       - 对话交互")
    print("  POST /feedback   - 知识库反馈")
    print("  GET  /approval   - 审批处理")
    print("  GET  /health     - 健康检查")
    print()
    print(f"Server: http://{settings.API_HOST}:{settings.API_PORT}")
    print("-" * 60)

    run_server()


if __name__ == "__main__":
    main()