"""
DolphinScheduler Agent Package Entry

使用方式：
- python -m src           # 启动所有服务（Stream + API，推荐）
- python -m src all       # 启动所有服务（Stream + API）
- python -m src stream    # 仅启动钉钉 Stream 模式（无需公网地址）
- python -m src api       # 仅启动 API 服务（需要公网地址）
- python -m src chat      # 启动交互式对话
"""

# 先加载环境变量
from dotenv import load_dotenv
load_dotenv()

import sys
import os
import signal
import subprocess
from .api.webhook_api import run_server
from .config import settings
from .dispatcher import ChatAgent


def kill_port_process(port: int) -> bool:
    """
    关闭占用指定端口的进程

    Args:
        port: 端口号

    Returns:
        是否成功关闭
    """
    import platform

    system = platform.system()

    try:
        if system == "Windows":
            # Windows: 使用 netstat 找到占用端口的 PID
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5
            )

            # 解析输出找到占用端口的 PID
            pids_to_kill = []
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids_to_kill.append(int(pid))

            # 关闭进程
            for pid in pids_to_kill:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], timeout=5)
                    print(f"[PORT] 已关闭进程 PID: {pid}")
                except Exception as e:
                    print(f"[PORT] 无法关闭 PID {pid}: {e}")

            return len(pids_to_kill) > 0

        else:
            # Linux/Mac: 使用 lsof 或 fuser
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.stdout.strip():
                pids = result.stdout.strip().splitlines()
                for pid in pids:
                    try:
                        subprocess.run(["kill", "-9", pid], timeout=5)
                        print(f"[PORT] 已关闭进程 PID: {pid}")
                    except Exception as e:
                        print(f"[PORT] 无法关闭 PID {pid}: {e}")
                return True

            return False

    except Exception as e:
        print(f"[PORT] 检查端口失败: {e}")
        return False


def ensure_port_free(port: int) -> None:
    """
    确保端口空闲，如果被占用则关闭

    Args:
        port: 端口号
    """
    print(f"[PORT] 检查端口 {port}...")

    if kill_port_process(port):
        print(f"[PORT] 端口 {port} 已被占用，已自动关闭旧进程")
        # 等待端口释放
        import time
        time.sleep(2)
    else:
        print(f"[PORT] 端口 {port} 空闲")


def main():
    """Main entry point"""
    # 解析命令行参数
    args = sys.argv[1:]
    mode = args[0] if args else "all"

    # 检查并关闭已有端口（api 或 all 模式）
    if mode in ("all", "api"):
        port = settings.API_PORT or 8080
        ensure_port_free(port)

    if mode == "all":
        run_all_services()
    elif mode == "stream":
        run_dingtalk_stream()
    elif mode == "api":
        run_api_server()
    elif mode == "chat":
        run_chat_repl()
    else:
        print(f"未知模式: {mode}")
        print("用法: python -m src [all|stream|api|chat]")
        sys.exit(1)


def run_all_services():
    """同时启动 Stream 和 API 服务"""
    print("=" * 60)
    print("DolphinScheduler Agent - 完整服务")
    print("=" * 60)
    print()
    print("启动服务:")
    print("  1. 钉钉 Stream 模式（对话功能）")
    print("  2. API 服务（告警 webhook）")
    print()
    print(f"Client ID: {settings.DINGTALK_CLIENT_ID}")
    print(f"DS_API_URL: {settings.DS_API_URL}")
    print(f"API Server: http://{settings.API_HOST}:{settings.API_PORT}")
    print("-" * 60)

    from .integrations.dingtalk_stream import DingTalkStreamClient

    # 启动 Stream 服务（后台线程）
    stream_client = DingTalkStreamClient()
    stream_thread = threading.Thread(target=stream_client.run, daemon=True)
    stream_thread.start()

    print("[Stream] 后台线程已启动")

    # 启动 API 服务（主线程）
    print("[API] 启动主服务...")
    run_server()


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
    # 添加 threading 导入
    import threading
    main()