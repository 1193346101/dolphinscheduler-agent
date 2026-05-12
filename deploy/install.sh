#!/bin/bash
# DolphinScheduler Agent 部署脚本
# 从 GitHub 直接 clone 部署
# 用法: sudo ./install.sh

set -e

PROJECT_DIR="/opt/dolphinscheduler-agent"
SERVICE_NAME="dolphinscheduler-agent"
CODE_DIR="/opt/spark-etl"

# GitHub 仓库地址
AGENT_REPO="https://github.com/1193346101/dolphinscheduler-agent.git"
DSCTL_REPO="https://github.com/1193346101/dolphinscheduler-cli.git"

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
elif [ -f /etc/redhat-release ]; then
    OS_TYPE="redhat"
    PKG_MANAGER="yum"
else
    echo "未知系统类型，请手动安装依赖"
    exit 1
fi

echo "系统类型: $OS_TYPE"
echo "包管理器: $PKG_MANAGER"

# 1. 安装系统依赖
echo "[1/8] 安装系统依赖..."
if [ "$OS_TYPE" = "debian" ]; then
    apt update
    apt install -y python3 python3-pip python3-venv nginx git curl unzip
elif [ "$OS_TYPE" = "redhat" ]; then
    yum install -y python3 python3-pip nginx git curl unzip
fi

# 2. 克隆 Agent 代码
echo "[2/8] 克隆 Agent 代码..."
if [ -d "$PROJECT_DIR" ]; then
    echo "目录已存在，更新代码..."
    cd $PROJECT_DIR
    git pull || true
else
    git clone $AGENT_REPO $PROJECT_DIR
fi

cd $PROJECT_DIR

# 3. 克隆 dsctl CLI（修改版本，适配 3.2.0）
echo "[3/8] 克隆 dsctl CLI..."
DSCTL_DIR="$PROJECT_DIR/dsctl"
if [ -d "$DSCTL_DIR" ]; then
    echo "dsctl 已存在，更新代码..."
    cd $DSCTL_DIR
    git pull || true
else
    git clone $DSCTL_REPO $DSCTL_DIR
fi

# 4. 克隆 spark-etl 代码仓库（用于图谱扫描）
echo "[4/8] 克隆 spark-etl 代码仓库..."
if [ ! -d "$CODE_DIR" ]; then
    git clone https://fengxiaoping:726580zw@gitlab-bigdata.huan.tv/etl/spark-etl.git $CODE_DIR || {
        echo "GitLab 克隆失败，请手动配置代码仓库"
    }
fi

# 5. 创建目录结构
echo "[5/8] 创建目录结构..."
mkdir -p $PROJECT_DIR/logs
mkdir -p $PROJECT_DIR/data/graph

# 6. 安装 Python 依赖
echo "[6/8] 安装 Python 依赖..."
cd $PROJECT_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 安装 dsctl
cd $DSCTL_DIR
pip install -e .
cd $PROJECT_DIR
echo "dsctl 已安装"

# 7. 配置环境变量
echo "[7/8] 配置环境变量..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env
fi
# 更新路径配置
sed -i "s|CODE_ROOT_PATH=.*|CODE_ROOT_PATH=$CODE_DIR|" $PROJECT_DIR/.env || true
sed -i "s|GRAPH_STORAGE_PATH=.*|GRAPH_STORAGE_PATH=$PROJECT_DIR/data/graph|" $PROJECT_DIR/.env || true

# 8. 安装 systemd 服务
echo "[8/8] 安装 systemd 服务..."
cp $PROJECT_DIR/deploy/agent.service /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# 配置 nginx
echo "配置 nginx..."
if [ "$OS_TYPE" = "debian" ]; then
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled
    cp $PROJECT_DIR/deploy/nginx.conf /etc/nginx/sites-available/dolphinscheduler-agent || \
    cat > /etc/nginx/sites-available/dolphinscheduler-agent << 'EOF'
server {
    listen 80;
    server_name _;

    location /graph/ {
        alias /opt/dolphinscheduler-agent/data/graph/;
        index graph_viewer.html;
    }

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
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
    }

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
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
echo "  dsctl: $DSCTL_DIR"
echo "  spark-etl: $CODE_DIR"
echo ""
echo "服务管理:"
echo "  启动: systemctl start $SERVICE_NAME"
echo "  停止: systemctl stop $SERVICE_NAME"
echo "  重启: systemctl restart $SERVICE_NAME"
echo "  状态: systemctl status $SERVICE_NAME"
echo "  日志: tail -f $PROJECT_DIR/logs/agent.log"
echo ""
echo "下一步:"
echo "  1. 编辑配置: vim $PROJECT_DIR/.env"
echo "  2. 启动服务: systemctl start $SERVICE_NAME"