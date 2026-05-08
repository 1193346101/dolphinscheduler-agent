"""
DolphinScheduler Agent Package Entry

使用 python -m src 运行
"""

# 先加载环境变量
from dotenv import load_dotenv
load_dotenv()

from .api.webhook_api import run_server
from .config import settings


def main():
    """Main entry point"""
    print("=" * 60)
    print("DolphinScheduler Agent API Server")
    print("=" * 60)
    print()
    print(f"DS_API_URL: {settings.DS_API_URL}")
    print(f"Server: http://{settings.API_HOST}:{settings.API_PORT}")
    print("-" * 60)

    run_server()


if __name__ == "__main__":
    main()