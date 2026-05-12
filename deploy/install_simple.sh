#!/bin/bash
# DolphinScheduler Agent 简化部署脚本
# 支持 Ubuntu/Debian 和 CentOS/RHEL
# 用法: bash deploy/install_simple.sh
#
# 特性:
# - 在当前目录运行，无需复制到 /opt
# - 使用阿里云镜像加速 pip 安装
# - 最小依赖（仅 Python + ngrok）
# - 无需 nginx（ngrok 直接转发）

set -e

echo "============================================"
echo "DolphinScheduler Agent 简化部署脚本"
echo "============================================"

# 检测系统类型
if [ -f /etc/debian_version ]; then
    OS_TYPE="debian"
elif [ -f /etc/redhat-release ]; then
    OS_TYPE="redhat"
else
    echo "未知系统类型"
    exit 1
fi

echo "系统类型: $OS_TYPE"
echo "部署路径: $(pwd)"

# 1. 检查 Python 版本（需要 3.8+）
echo "[1/4] 检查 Python 版本..."
PYTHON_VERSION=""
for py in python3.10 python3.9 python3.8 python3; do
    if command -v $py &> /dev/null; then
        version=$($py --version 2>&1 | awk '{print $2}')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
            PYTHON_CMD=$py
            PYTHON_VERSION=$version
            echo "使用 Python: $PYTHON_CMD ($PYTHON_VERSION)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "错误: 需要 Python 3.8+"
    echo "当前系统 Python 版本:"
    python3 --version 2>&1 || echo "python3 未安装"
    echo ""
    echo "安装方法:"
    if [ "$OS_TYPE" = "redhat" ]; then
        echo "  sudo yum install -y python39"
    else
        echo "  sudo apt install -y python3.9"
    fi
    exit 1
fi

# 2. 创建虚拟环境并安装依赖
echo "[2/4] 安装 Python 依赖（使用阿里云镜像）..."

if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
fi

source venv/bin/activate

# 配置 pip 使用阿里云镜像
pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
pip config set global.trusted-host mirrors.aliyun.com

pip install --upgrade pip
pip install -r requirements.txt

echo "依赖安装完成"

# 3. 创建必要目录
echo "[3/4] 创建必要目录..."
mkdir -p logs
mkdir -p data/graph
mkdir -p data/approvals

# 4. 安装 ngrok（可选）
echo "[4/4] 安装 ngrok..."
if ! command -v ngrok &> /dev/null; then
    echo "下载 ngrok..."
    curl -Lo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mqp2n/ngrok-v3-stable-linux-amd64.tgz
    sudo tar -xzf /tmp/ngrok.tgz -C /usr/local/bin/
    sudo chmod +x /usr/local/bin/ngrok
    echo "ngrok 安装完成"
else
    echo "ngrok 已安装"
fi

# 配置环境变量（如果不存在）
if [ ! -f ".env" ]; then
    echo ""
    echo "创建 .env 配置文件..."
    cp .env.example .env

    # 自动获取 DolphinScheduler 项目配置（如果 API 可用）
    echo "尝试自动获取 DolphinScheduler 项目配置..."

    DS_API_URL=$(grep DS_API_URL .env.example | cut -d= -f2)
    DS_API_TOKEN=$(grep DS_API_TOKEN .env.example | cut -d= -f2)

    if [ -n "$DS_API_URL" ] && [ -n "$DS_API_TOKEN" ] && [ "$DS_API_URL" != "your-ds-server:12345/dolphinscheduler" ]; then
        echo "从 $DS_API_URL 获取项目列表..."

        # 获取项目列表并生成配置
        python3 << PYEOF
import os
import requests
import yaml

ds_url = os.getenv("DS_API_URL", "$DS_API_URL")
ds_token = os.getenv("DS_API_TOKEN", "$DS_API_TOKEN")

try:
    resp = requests.get(
        f"{ds_url}/projects",
        headers={"token": ds_token},
        params={"pageNo": 1, "pageSize": 100},
        timeout=10
    )
    data = resp.json()
    if data.get("success"):
        projects = data["data"]["totalList"]

        # 生成 projects.yaml
        config = {"projects": []}
        for p in projects:
            config["projects"].append({
                "name": p["name"],
                "code": p["code"],
                "ds_api_url": ds_url
            })

        with open("config/projects.yaml", "w") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        # 更新 .env 默认项目
        if projects:
            default_code = projects[0]["code"]
            with open(".env", "r") as f:
                content = f.read()
            content = content.replace("DEFAULT_PROJECT_CODE=your-default-project-code", f"DEFAULT_PROJECT_CODE={default_code}")
            with open(".env", "w") as f:
                f.write(content)

        print(f"自动配置完成，共 {len(projects)} 个项目")
    else:
        print("获取项目失败，请手动配置")
except Exception as e:
    print(f"自动配置失败: {e}，请手动配置")
PYEOF
    fi
fi

echo ""
echo "============================================"
echo "部署完成!"
echo "============================================"
echo ""
echo "下一步:"
echo "  1. 编辑配置: vim .env"
echo "     必填项: DS_API_URL, DS_API_TOKEN, LLM_API_KEY"
echo ""
echo "  2. 配置 ngrok authtoken:"
echo "     ngrok config add-authtoken YOUR_TOKEN"
echo ""
echo "  3. 启动 Agent:"
echo "     source venv/bin/activate"
echo "     python -m src all"
echo ""
echo "  4. 启动 ngrok（后台）:"
echo "     ngrok http 8080 > /tmp/ngrok.log 2>&1 &"
echo ""
echo "  5. 获取公网 URL:"
echo "     curl -s http://127.0.0.1:4040/api/tunnels | python3 -c \"import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])\""
echo ""
echo "日志路径:"
echo "  Agent: $(pwd)/logs/agent.log"
echo "  ngrok: /tmp/ngrok.log"