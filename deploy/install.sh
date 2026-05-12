#!/bin/bash
# DolphinScheduler Agent 部署脚本
# 支持 Ubuntu/Debian 和 CentOS/RHEL
# 用法: sudo ./install.sh

set -e

PROJECT_DIR="/opt/dolphinscheduler-agent"
SERVICE_NAME="dolphinscheduler-agent"
CODE_DIR="/opt/spark-etl"

echo "============================================"
echo "DolphinScheduler Agent 部署脚本"
echo "============================================"

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 权限运行: sudo ./install.sh"
    exit 1
fi

# 检测系统类型
if [ -f /etc/debian_version ]; then
    OS_TYPE="debian"
    PKG_MANAGER="apt"
    PKG_INSTALL="apt install -y"
    NGINX_CONF_DIR="/etc/nginx/sites-available"
elif [ -f /etc/redhat-release ]; then
    OS_TYPE="redhat"
    PKG_MANAGER="yum"
    PKG_INSTALL="yum install -y"
    NGINX_CONF_DIR="/etc/nginx/conf.d"
else
    echo "未知系统类型，请手动安装依赖"
    exit 1
fi

echo "系统类型: $OS_TYPE"
echo "包管理器: $PKG_MANAGER"

# 1. 安装依赖
echo "[1/10] 安装系统依赖..."
if [ "$OS_TYPE" = "debian" ]; then
    apt update
    apt install -y python3 python3-pip python3-venv nginx git curl
elif [ "$OS_TYPE" = "redhat" ]; then
    yum install -y python3 python3-pip nginx git curl
    # CentOS 需要额外安装 venv
    pip3 install virtualenv || yum install -y python3-virtualenv
fi

# 2. 创建项目目录
echo "[2/10] 创建项目目录..."
mkdir -p $PROJECT_DIR
mkdir -p $PROJECT_DIR/logs
mkdir -p $PROJECT_DIR/data/graph

# 3. 安装 ngrok
echo "[3/10] 安装 ngrok..."
if ! command -v ngrok &> /dev/null; then
    if [ "$OS_TYPE" = "debian" ]; then
        curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
        echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | tee /etc/apt/sources.list.d/ngrok.list
        apt update
        apt install -y ngrok
    elif [ "$OS_TYPE" = "redhat" ]; then
        # CentOS 直接下载二进制
        curl -Lo /tmp/ngrok.zip https://bin.equinox.io/c/bNyj1mqp2n/ngrok-v3-stable-linux-amd64.zip
        unzip -o /tmp/ngrok.zip -d /usr/local/bin/
        chmod +x /usr/local/bin/ngrok
    fi
fi

# 4. 克隆代码仓库（用于图谱扫描）
echo "[4/10] 克隆 spark-etl 代码仓库..."
if [ ! -d "$CODE_DIR" ]; then
    mkdir -p $CODE_DIR
    # 配置 GitLab 访问（使用 HTTPS 避免 SSH 配置）
    git clone https://fengxiaoping:726580zw@gitlab-bigdata.huan.tv/etl/spark-etl.git $CODE_DIR || {
        echo "GitLab 克隆失败，请手动配置代码仓库"
        echo "命令: git clone git@gitlab-bigdata.huan.tv:etl/spark-etl.git $CODE_DIR"
    }
fi

# 5. 复制 Agent 代码
echo "[5/10] 复制 Agent 代码..."
if [ -f "src/__main__.py" ]; then
    cp -r src $PROJECT_DIR/
    cp -r config $PROJECT_DIR/ 2>/dev/null || true
    cp -r data $PROJECT_DIR/ 2>/dev/null || true
    cp .env $PROJECT_DIR/ 2>/dev/null || cp .env.example $PROJECT_DIR/.env
    cp requirements.txt $PROJECT_DIR/
else
    echo "请在代码目录下运行此脚本"
    exit 1
fi

# 6. 安装 Python 依赖
echo "[6/10] 安装 Python 依赖..."
cd $PROJECT_DIR
python3 -m venv venv || virtualenv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 7. 配置环境变量
echo "[7/10] 配置环境变量..."
# 设置代码仓库路径
sed -i "s|CODE_ROOT_PATH=.*|CODE_ROOT_PATH=$CODE_DIR|" .env || true
sed -i "s|GRAPH_STORAGE_PATH=.*|GRAPH_STORAGE_PATH=$PROJECT_DIR/data/graph|" .env || true

# 8. 安装 systemd 服务
echo "[8/10] 安装 systemd 服务..."
cp deploy/agent.service /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# 9. 安装 ngrok 服务
echo "[9/10] 安装 ngrok 服务..."
cp deploy/ngrok.service /etc/systemd/system/ngrok.service
systemctl daemon-reload
systemctl enable ngrok

# 10. 配置 nginx（提供 HTML 可视化和 webhook）
echo "[10/10] 配置 nginx..."
if [ "$OS_TYPE" = "debian" ]; then
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled
    cat > /etc/nginx/sites-available/dolphinscheduler-agent << 'EOF'
server {
    listen 80;
    server_name _;

    location /graph/ {
        alias /opt/dolphinscheduler-agent/data/graph/;
        index graph_viewer.html;
        try_files $uri $uri/ /graph/graph_viewer.html;
    }

    location /static/ {
        alias /opt/dolphinscheduler-agent/data/;
    }

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:8080;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/dolphinscheduler-agent /etc/nginx/sites-enabled/
elif [ "$OS_TYPE" = "redhat" ]; then
    cat > /etc/nginx/conf.d/dolphinscheduler-agent.conf << 'EOF'
server {
    listen 80;
    server_name _;

    location /graph/ {
        alias /opt/dolphinscheduler-agent/data/graph/;
        index graph_viewer.html;
        try_files $uri $uri/ /graph/graph_viewer.html;
    }

    location /static/ {
        alias /opt/dolphinscheduler-agent/data/;
    }

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:8080;
    }
}
EOF
fi

nginx -t && systemctl reload nginx || systemctl start nginx

echo ""
echo "============================================"
echo "部署完成!"
echo "============================================"
echo ""
echo "目录结构:"
echo "  Agent: $PROJECT_DIR"
echo "  代码仓库: $CODE_DIR"
echo "  图谱数据: $PROJECT_DIR/data/graph/"
echo ""
echo "服务管理:"
echo "  启动 Agent: systemctl start $SERVICE_NAME"
echo "  停止 Agent: systemctl stop $SERVICE_NAME"
echo "  重启 Agent: systemctl restart $SERVICE_NAME"
echo "  状态 Agent: systemctl status $SERVICE_NAME"
echo "  日志 Agent: tail -f $PROJECT_DIR/logs/agent.log"
echo ""
echo "  启动 ngrok: systemctl start ngrok"
echo "  停止 ngrok: systemctl stop ngrok"
echo "  ngrok 日志: tail -f /tmp/ngrok.log"
echo ""
echo "下一步:"
echo "  1. 配置 ngrok authtoken: ngrok config add-authtoken YOUR_TOKEN"
echo "  2. 编辑配置: vim $PROJECT_DIR/.env"
echo "  3. 配置项目: vim $PROJECT_DIR/config/projects.yaml"
echo "  4. 启动服务: systemctl start $SERVICE_NAME && systemctl start ngrok"
echo "  5. 获取公网 URL: curl -s http://127.0.0.1:4040/api/tunnels | python3 -c \"import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])\""