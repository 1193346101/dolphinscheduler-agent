# DolphinScheduler Agent 部署指南

## 目录结构

```
/opt/dolphinscheduler-agent/
├── src/                  # 源代码
├── config/               # 项目配置
├── data/                 # 数据存储
│   └── graph/            # 知识图谱存储
├── logs/                 # 日志目录
├── venv/                 # Python 虚拟环境
├── .env                  # 环境变量配置
├── requirements.txt      # 依赖列表
└── deploy/               # 部署脚本
    ├── install.sh        # 安装脚本
    ├── setup_ngrok.sh    # ngrok URL 配置脚本
    ├── agent.service     # Agent systemd 服务文件
    └── ngrok.service     # ngrok systemd 服务文件
```

## 快速部署

### 1. 一键安装（推荐）

在代码目录下执行：

```bash
sudo ./deploy/install.sh
```

安装脚本会自动完成：
- 安装系统依赖（Python, nginx, ngrok）
- 创建项目目录和虚拟环境
- 克隆 GitLab 代码仓库（用于图谱扫描）
- 安装 Python 依赖
- 配置 systemd 服务（Agent + ngrok）
- 配置 nginx 反向代理

### 2. 配置 ngrok authtoken

安装完成后，需要配置 ngrok authtoken：

```bash
# 1. 注册 ngrok 账号: https://ngrok.com
# 2. 获取 authtoken: https://dashboard.ngrok.com/get-started/your-authtoken
# 3. 配置 authtoken
ngrok config add-authtoken YOUR_TOKEN
```

### 3. 启动服务并获取公网 URL

```bash
# 启动 Agent 服务
sudo systemctl start dolphinscheduler-agent

# 启动 ngrok 服务
sudo systemctl start ngrok

# 获取公网 URL（写入 .env）
./deploy/setup_ngrok.sh
```

运行 `setup_ngrok.sh` 后会自动：
1. 启动 ngrok tunnel
2. 获取公网 URL
3. 写入 `.env` 文件的 `NGROK_BASE_URL`
4. 显示 Webhook URL 和图谱 URL

### 4. 手动安装

```bash
# 安装系统依赖
sudo apt update
sudo apt install python3 python3-pip python3-venv nginx curl -y

# 安装 ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update
sudo apt install -y ngrok

# 配置 ngrok authtoken
ngrok config add-authtoken YOUR_TOKEN

# 创建目录
sudo mkdir -p /opt/dolphinscheduler-agent
sudo mkdir -p /opt/dolphinscheduler-agent/logs
sudo mkdir -p /opt/dolphinscheduler-agent/data/graph

# 复制代码
sudo cp -r src /opt/dolphinscheduler-agent/
sudo cp -r config /opt/dolphinscheduler-agent/
sudo cp .env.example /opt/dolphinscheduler-agent/.env

# 安装 Python 依赖
cd /opt/dolphinscheduler-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
vim .env

# 安装服务
sudo cp deploy/agent.service /etc/systemd/system/dolphinscheduler-agent.service
sudo cp deploy/ngrok.service /etc/systemd/system/ngrok.service
sudo systemctl daemon-reload
sudo systemctl enable dolphinscheduler-agent
sudo systemctl enable ngrok

# 启动服务
sudo systemctl start dolphinscheduler-agent
sudo systemctl start ngrok
```

## 配置说明

### .env 配置文件

```env
# DolphinScheduler API（只读权限即可）
DS_API_URL=http://your-ds-server:12345/dolphinscheduler
DS_API_TOKEN=your_token_here
DS_VERSION=3.2.0

# LLM API（用于错误分析）
LLM_API_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
LLM_API_KEY=your_llm_api_key
LLM_MODEL=glm-5

# 钉钉 Stream 模式（对话功能）
DINGTALK_CLIENT_ID=dingyyink7zqipbyrnf1
DINGTALK_CLIENT_SECRET=your_client_secret

# 钉钉 Webhook（告警通知）
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx

# API 服务配置
API_HOST=0.0.0.0
API_PORT=8080

# 项目配置
PROJECTS_CONFIG_PATH=config/projects.yaml
DEFAULT_PROJECT_CODE=11598178397184

# 知识图谱配置（代码仓库路径）
CODE_ROOT_PATH=/opt/spark-etl
GRAPH_STORAGE_PATH=data/graph

# ngrok 公网地址（由 setup_ngrok.sh 自动生成）
NGROK_BASE_URL=https://your-ngrok-url.ngrok-free.app
```

### projects.yaml 配置

```yaml
projects:
  - name: ad_monitor
    code: 11598178397184
    ds_api_url: http://your-ds-server:12345/dolphinscheduler
```

## 服务管理

```bash
# Agent 服务
sudo systemctl start dolphinscheduler-agent    # 启动
sudo systemctl stop dolphinscheduler-agent     # 停止
sudo systemctl restart dolphinscheduler-agent  # 重启
sudo systemctl status dolphinscheduler-agent   # 状态
tail -f /opt/dolphinscheduler-agent/logs/agent.log  # 日志

# ngrok 服务
sudo systemctl start ngrok     # 启动
sudo systemctl stop ngrok      # 停止
sudo systemctl restart ngrok   # 重启
tail -f /tmp/ngrok.log         # ngrok 日志

# 获取当前公网 URL
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])"
```

## ngrok URL 使用

### Webhook 告警 URL

格式: `${NGROK_BASE_URL}/webhook`

例如: `https://abc123.ngrok-free.app/webhook`

### 知识图谱 HTML URL

格式: `${NGROK_BASE_URL}/graph/`

例如: `https://abc123.ngrok-free.app/graph/`

### 健康检查 URL

格式: `${NGROK_BASE_URL}/health`

例如: `https://abc123.ngrok-free.app/health`

## DolphinScheduler 告警配置

在 DolphinScheduler 中配置告警插件：

**方式 1: Webhook 告警（推荐）**

```
插件类型: Webhook
URL: https://your-ngrok-url.ngrok-free.app/webhook
Method: POST
Content-Type: application/json
Body Template: {"alerts": "${alerts}"}
```

**方式 2: 钉钉群告警 + Agent Stream**

```
插件类型: 钉钉
Webhook URL: https://oapi.dingtalk.com/robot/send?access_token=xxx
```

Agent 通过 DingTalk Stream 模式监听群消息，识别告警并处理。

## 权限要求

Agent 使用只读 DolphinScheduler API 权限即可：

| 功能 | API | 权限要求 |
|------|-----|---------|
| 告警处理 | - | 外部触发 |
| 知识图谱扫描 | list_workflows | 只读 |
| 知识图谱扫描 | describe_workflow | 只读 |
| 获取日志 | 无需 DS API | kubectl logs |

**只读权限配置：**
- 在 DolphinScheduler 中创建用户，只授予项目查看权限
- 无需授予任务执行、修改等权限

## 知识图谱功能

### 扫描项目图谱

```bash
# 扫描默认项目
curl -X POST http://localhost:8080/graph/scan

# 扫描指定项目
curl -X POST "http://localhost:8080/graph/scan?project_code=11598178397184"
```

### 查看图谱数据

```bash
# JSON 格式
curl http://localhost:8080/graph/data

# HTML 可视化（浏览器访问）
https://your-ngrok-url.ngrok-free.app/graph/
```

### 查看已扫描项目

```bash
curl http://localhost:8080/graph/projects
```

## Nginx 配置（本地访问）

Agent 默认监听 `0.0.0.0:8080`，通过 nginx 提供本地访问：

```nginx
server {
    listen 80;
    server_name _;

    # 图谱 HTML 可视化
    location /graph/ {
        alias /opt/dolphinscheduler-agent/data/graph/;
        index graph_viewer.html;
        try_files $uri $uri/ /graph/graph_viewer.html;
    }

    # 静态文件
    location /static/ {
        alias /opt/dolphinscheduler-agent/data/;
    }

    # Webhook API
    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 其他 API
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

**注意：公网访问通过 ngrok，nginx 仅用于本地访问。**

## 测试验证

```bash
# 健康检查（本地）
curl http://localhost:8080/health

# 健康检查（公网）
curl https://your-ngrok-url.ngrok-free.app/health

# 测试 webhook
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"alerts": "[{\"projectCode\":123,\"taskType\":\"SHELL\",\"taskState\":\"FAILURE\"}]"}'

# 测试图谱扫描
curl -X POST http://localhost:8080/graph/scan
```

## 常见问题

### 1. 服务无法启动

检查日志：
```bash
tail -100 /opt/dolphinscheduler-agent/logs/agent.log
```

常见原因：
- `.env` 配置缺失
- Python 依赖未安装
- 端口被占用

### 2. ngrok URL 获取失败

检查：
```bash
# ngrok 是否启动
systemctl status ngrok

# ngrok 日志
tail -100 /tmp/ngrok.log

# authtoken 是否配置
ngrok config check
```

### 3. ngrok URL 变化后配置更新

免费版 ngrok URL 在重启后会变化：

```bash
# 重新运行配置脚本
./deploy/setup_ngrok.sh

# 重启 Agent（让新 URL 生效）
systemctl restart dolphinscheduler-agent

# 更新 DolphinScheduler 告警配置中的 URL
```

**固定 URL 方案：**
- 升级 ngrok 付费版，使用自定义域名
- 或使用其他内网穿透服务（frp, cloudflare tunnel）

### 4. DingTalk Stream 连接失败

检查配置：
```bash
grep DINGTALK_CLIENT .env
```

确保 Client ID 和 Secret 正确。

### 5. 告警无法接收

检查：
- DolphinScheduler 告警插件 URL 是否正确（使用 ngrok URL）
- ngrok 是否正常运行
- Agent 服务是否健康

### 6. 知识图谱扫描失败

检查：
- CODE_ROOT_PATH 是否配置正确
- GitLab 代码仓库是否已克隆
- DolphinScheduler API 只读权限是否配置

## 更新部署

```bash
cd /opt/dolphinscheduler-agent

# 停止服务
sudo systemctl stop dolphinscheduler-agent
sudo systemctl stop ngrok

# 拉取最新代码
git pull

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt

# 重启服务
sudo systemctl start dolphinscheduler-agent
sudo systemctl start ngrok

# 更新 ngrok URL（如果变化）
./deploy/setup_ngrok.sh
```