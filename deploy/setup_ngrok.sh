#!/bin/bash
# ngrok URL 配置脚本
# 用法: ./deploy/setup_ngrok.sh

set -e

PROJECT_DIR="/opt/dolphinscheduler-agent"
ENV_FILE="$PROJECT_DIR/.env"
API_PORT=8080

echo "============================================"
echo "ngrok URL 配置脚本"
echo "============================================"

# 检查 ngrok 是否安装
if ! command -v ngrok &> /dev/null; then
    echo "ngrok 未安装，正在安装..."
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
    sudo apt update
    sudo apt install -y ngrok
fi

# 检查 ngrok authtoken 是否配置
if ! ngrok config check &> /dev/null; then
    echo ""
    echo "请先配置 ngrok authtoken:"
    echo "  1. 注册 ngrok 账号: https://ngrok.com"
    echo "  2. 获取 authtoken: https://dashboard.ngrok.com/get-started/your-authtoken"
    echo "  3. 运行: ngrok config add-authtoken YOUR_TOKEN"
    echo ""
    exit 1
fi

# 停止已有的 ngrok 进程
echo "[1/4] 停止已有 ngrok 进程..."
pkill -f ngrok || true
sleep 2

# 启动 ngrok（后台运行）
echo "[2/4] 启动 ngrok..."
ngrok http $API_PORT --log=stdout > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!
sleep 5

# 获取 ngrok 公网 URL
echo "[3/4] 获取公网 URL..."
NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

if [ -z "$NGROK_URL" ]; then
    echo "获取 ngrok URL 失败，请检查 ngrok 是否正常启动"
    echo "日志: cat /tmp/ngrok.log"
    exit 1
fi

echo "公网 URL: $NGROK_URL"

# 更新 .env 文件
echo "[4/4] 更新 .env 文件..."

# 添加 NGROK_BASE_URL
if grep -q "NGROK_BASE_URL" "$ENV_FILE"; then
    sed -i "s|NGROK_BASE_URL=.*|NGROK_BASE_URL=$NGROK_URL|" "$ENV_FILE"
else
    echo "" >> "$ENV_FILE"
    echo "# ============ ngrok 公网地址 ============ #" >> "$ENV_FILE"
    echo "NGROK_BASE_URL=$NGROK_URL" >> "$ENV_FILE"
fi

# 生成各服务 URL
WEBHOOK_URL="$NGROK_URL/webhook"
GRAPH_URL="$NGROK_URL/graph/"
HEALTH_URL="$NGROK_URL/health"

echo ""
echo "============================================"
echo "配置完成!"
echo "============================================"
echo ""
echo "服务 URL:"
echo "  Webhook 告警: $WEBHOOK_URL"
echo "  知识图谱:     $GRAPH_URL"
echo "  健康检查:     $HEALTH_URL"
echo ""
echo "DolphinScheduler 告警配置:"
echo "  插件类型: Webhook"
echo "  URL: $WEBHOOK_URL"
echo "  Method: POST"
echo "  Content-Type: application/json"
echo ""
echo "ngrok 进程 PID: $NGROK_PID"
echo "日志文件: /tmp/ngrok.log"
echo ""
echo "注意事项:"
echo "  1. ngrok URL 在重启后会变化，需要重新运行此脚本"
echo "  2. 如需固定 URL，请升级 ngrok 付费版使用自定义域名"
echo "  3. 停止 ngrok: pkill -f ngrok"