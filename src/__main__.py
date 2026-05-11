"""
DolphinScheduler Agent Package Entry

使用方式：
- python -m src           # 启钉钉 Stream 模式（默认，推荐）
- python -m src stream    # 启动钉钉 Stream 模式（无需公网地址）
- python -m src api       # 启动 API 服务（需要公网地址）
- python -m src chat      # 启动交互式对话
"""

# 先加载环境变量
from dotenv import load_dotenv
load_dotenv()

import sys
from .api.webhook_api import run_server
from .config import settings
from .dispatcher import ChatAgent


def main():
    """Main entry point"""
    # 解析命令行参数
    args = sys.argv[1:]
    mode = args[0] if args else "stream"

    if mode == "stream":
        run_dingtalk_stream()
    elif mode == "api":
        run_api_server()
    elif mode == "chat":
        run_chat_repl()
    else:
        print(f"未知模式: {mode}")
        print("用法: python -m src [stream|api|chat]")
        sys.exit(1)


def run_dingtalk_stream():
    """启动钉钉 Stream 模式"""
    print("=" * 60)
    print("DolphinScheduler Agent - 钉钉 Stream 模式")
    print("=" * 60)
    print()
    print("无需公网地址，直接从钉钉服务器拉取消息")
    print()
    print(f"Client ID: {settings.DINGTALK_CLIENT_ID}")
    print(f"DS_API_URL: {settings.DS_API_URL}")
    print("-" * 60)

    from .integrations.dingtalk_stream import DingTalkStreamClient
    client = DingTalkStreamClient()
    client.run()


def run_api_server():
    """启动 API 服务"""
    print("=" * 60)
    print("DolphinScheduler Agent API Server")
    print("=" * 60)
    print()
    print(f"DS_API_URL: {settings.DS_API_URL}")
    print(f"Server: http://{settings.API_HOST}:{settings.API_PORT}")
    print("-" * 60)

    run_server()


def run_chat_repl():
    """启动交互式对话 REPL"""
    print("=" * 60)
    print("DolphinScheduler Agent Chat REPL")
    print("=" * 60)
    print()
    print("支持的对话意图:")
    print("  - 扫描项目 X 图谱")
    print("  - 工作流 Y 的下游/上游依赖")
    print("  - 表 T 被谁消费/产出")
    print("  - 展示工作流 Y 的影响链路")
    print("  - 运行工作流、查看状态、恢复失败等")
    print()
    print("输入 'quit' 或 'exit' 退出")
    print("-" * 60)

    # 初始化 ChatAgent
    agent = ChatAgent()

    # REPL 循环
    while True:
        try:
            # 读取用户输入
            message = input("\n请输入消息: ").strip()

            if not message:
                continue

            if message.lower() in ("quit", "exit", "q"):
                print("再见!")
                break

            # 发送到 ChatAgent 处理
            result = agent.handle_chat({
                "message": message,
                "user_id": "repl_user",
            })

            # 显示结果
            print_response(result)

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"错误: {e}")


def print_response(result: dict):
    """格式化打印响应结果"""
    status = result.get("status", "unknown")

    if status == "success":
        print(f"\n✅ 处理成功")
        if result.get("response"):
            print(f"\n{result['response']}")
        if result.get("result_data"):
            print(f"\n数据: {result['result_data']}")
    elif status == "need_info":
        print(f"\n⚠️ 需要更多信息: {result.get('message', '')}")
    elif status == "need_params":
        print(f"\n⚠️ 检测到意图: {result.get('intent', '')}")
        print(f"   {result.get('message', '')}")
    elif status == "error":
        print(f"\n❌ 错误: {result.get('message', '')}")
    else:
        print(f"\n结果: {result}")


if __name__ == "__main__":
    main()