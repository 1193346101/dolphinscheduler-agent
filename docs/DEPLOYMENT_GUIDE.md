# DolphinScheduler Agent 部署操作手册

> **版本:** 1.0
> **更新日期:** 2026-05-12
> **适用环境:** Ubuntu 20.04/22.04, Python 3.8+

---

## 目录

1. [前置准备](#1-前置准备)
2. [安装部署](#2-安装部署)
3. [配置 ngrok](#3-配置-ngrok)
4. [验证测试](#4-验证测试)
5. [DolphinScheduler 告警配置](#5-dolphinscheduler-告警配置)
6. [日常运维](#6-日常运维)
7. [故障排查](#7-故障排查)

---

## 1. 前置准备

### 1.1 获取必要信息

在部署前，需要准备以下信息：

| 配置项 | 获取方式 | 示例 |
|--------|----------|------|
| DS_API_URL | DolphinScheduler 管理员提供 | `http://10.0.0.1:12345/dolphinscheduler` |
| DS_API_TOKEN | DolphinScheduler 用户设置中生成 | 只读权限即可 |
| LLM_API_KEY | 阿里云百炼平台 | 用于错误智能分析 |
| DINGTALK_CLIENT_ID | 钉钉开发者平台 | Stream 模式对话功能 |
| DINGTALK_CLIENT_SECRET | 钉钉开发者平台 | Stream 模式对话功能 |
| ngrok authtoken | https://ngrok.com 注册获取 | 公网访问必需 |

### 1.2 服务器要求

- **操作系统:** Ubuntu 20.04/22.04
- **Python:** 3.8 或更高版本
- **内存:** 最低 2GB，推荐 4GB
- **磁盘:** 最低 10GB（代码仓库需要空间）
- **网络:** 能访问 DolphinScheduler API、钉钉 API、LLM API

### 1.3 权限要求

- **服务器:** root 或 sudo 权限（用于安装服务）
- **DolphinScheduler:** 只读权限即可（list_workflows, describe_workflow）
- **GitLab:** HTTPS clone 权限（用于代码仓库克隆）

---

## 2. 安装部署

### 2.1 下载代码

```bash
# 在服务器上克隆 Agent 代码
cd /opt
git clone https://your-repo/dolphinscheduler-agent.git
cd dolphinscheduler-agent
```

### 2.2 一键安装

```bash
# 运行安装脚本（需要 root 权限）
sudo ./deploy/install.sh
```

安装脚本会自动完成：
- ✅ 安装 Python、nginx、ngrok、git
- ✅ 克隆 spark-etl 代码仓库（用于图谱扫描）
- ✅ 创建项目目录 `/opt/dolphinscheduler-agent`
- ✅ 安装 Python 依赖
- ✅ 配置 systemd 服务
- ✅ 配置 nginx 反向代理

### 2.3 配置环境变量

```bash
# 编辑配置文件
vim /opt/dolphinscheduler-agent/.env
```

**必须配置项：**

```env
# ============ DolphinScheduler API（必须）============
DS_API_URL=http://your-ds-server:12345/dolphinscheduler
DS_API_TOKEN=your-ds-api-token
DS_VERSION=3.2.0

# ============ LLM 配置（必须）============
LLM_API_KEY=your-llm-api-key
LLM_API_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
LLM_MODEL=glm-5

# ============ 钉钉 Stream 模式（对话功能）============
DINGTALK_CLIENT_ID=dingyyink7zqipbyrnf1
DINGTALK_CLIENT_SECRET=your-client-secret
DINGTALK_ROBOT_CODE=dingyyink7zqipbyrnf1
DINGTALK_AGENT_ID=your-agent-id

# ============ 项目配置 ============
DEFAULT_PROJECT_CODE=your-default-project-code
```

### 2.4 配置项目映射

```bash
# 编辑项目配置
vim /opt/dolphinscheduler-agent/config/projects.yaml
```

```yaml
projects:
  - name: ad_monitor
    code: 11598178397184
    ds_api_url: http://your-ds-server:12345/dolphinscheduler
  - name: etl_daily
    code: 12345678901234
    ds_api_url: http://your-ds-server:12345/dolphinscheduler
```

---

## 3. 配置 ngrok

### 3.1 注册 ngrok 账号

1. 访问 https://ngrok.com 注册账号
2. 登录后访问 https://dashboard.ngrok.com/get-started/your-authtoken
3. 复制 authtoken

### 3.2 配置 authtoken

```bash
# 配置 ngrok authtoken
ngrok config add-authtoken YOUR_NGROK_TOKEN

# 验证配置
ngrok config check
```

### 3.3 启动服务

```bash
# 启动 Agent 服务
sudo systemctl start dolphinscheduler-agent

# 启动 ngrok 服务
sudo systemctl start ngrok

# 查看状态
sudo systemctl status dolphinscheduler-agent
sudo systemctl status ngrok
```

### 3.4 获取公网 URL

```bash
# 运行 URL 配置脚本（自动写入 .env）
cd /opt/dolphinscheduler-agent
./deploy/setup_ngrok.sh
```

脚本输出示例：

```
============================================
配置完成!
============================================

服务 URL:
  Webhook 告警: https://abc123.ngrok-free.app/webhook
  知识图谱:     https://abc123.ngrok-free.app/graph/
  健康检查:     https://abc123.ngrok-free.app/health
```

---

## 4. 验证测试

### 4.1 本地健康检查

```bash
# 检查 Agent 服务
curl http://localhost:8080/health

# 预期返回
{"status": "healthy", "version": "1.0"}
```

### 4.2 公网健康检查

```bash
# 使用 ngrok URL 检查
curl https://your-ngrok-url.ngrok-free.app/health
```

### 4.3 测试 Webhook 告警

```bash
# 发送测试告警
curl -X POST https://your-ngrok-url.ngrok-free.app/webhook \
  -H "Content-Type: application/json" \
  -d '{"alerts": "[{\"projectCode\":11598178397184,\"taskType\":\"SHELL\",\"taskState\":\"FAILURE\",\"taskName\":\"test_task\"}]"}'

# 预期返回
{"status": "success", "message": "Alert processed"}
```

### 4.4 测试知识图谱

```bash
# 扫描项目图谱
curl -X POST http://localhost:8080/graph/scan?project_code=11598178397184

# 查看图谱数据
curl http://localhost:8080/graph/data

# 浏览器访问图谱 HTML
https://your-ngrok-url.ngrok-free.app/graph/
```

### 4.5 查看日志

```bash
# Agent 日志
tail -f /opt/dolphinscheduler-agent/logs/agent.log

# ngrok 日志
tail -f /tmp/ngrok.log
```

---

## 5. DolphinScheduler 告警配置

### 5.1 创建 Webhook 告警实例

在 DolphinScheduler 管理界面：

1. **安全中心** → **告警实例管理** → **创建告警实例**

2. 配置参数：

| 参数 | 值 |
|------|-----|
| 告警插件类型 | Webhook |
| 名称 | DolphinScheduler-Agent |
| URL | `https://your-ngrok-url.ngrok-free.app/webhook` |
| 请求方法 | POST |
| 请求参数类型 | JSON |

3. Body Template：

```json
{"alerts": "${alerts}"}
```

### 5.2 创建告警组

1. **安全中心** → **告警组管理** → **创建告警组**

2. 配置参数：

| 参数 | 值 |
|------|-----|
| 告警组名称 | Agent告警组 |
| 告警实例 | 选择刚才创建的 Webhook 实例 |

### 5.3 项目绑定告警组

1. **项目管理** → 选择项目 → **告警组设置**
2. 选择创建的告警组
3. 保存

### 5.4 验证告警

在 DolphinScheduler 中手动触发一个失败任务，验证告警是否到达 Agent。

---

## 6. 日常运维

### 6.1 服务管理命令

```bash
# Agent 服务
sudo systemctl start dolphinscheduler-agent    # 启动
sudo systemctl stop dolphinscheduler-agent     # 停止
sudo systemctl restart dolphinscheduler-agent  # 重启
sudo systemctl status dolphinscheduler-agent   # 状态

# ngrok 服务
sudo systemctl start ngrok     # 启动
sudo systemctl stop ngrok      # 停止
sudo systemctl restart ngrok   # 重启
sudo systemctl status ngrok    # 状态
```

### 6.2 日志查看

```bash
# Agent 日志（实时）
tail -f /opt/dolphinscheduler-agent/logs/agent.log

# Agent 日志（最近 100 行）
tail -100 /opt/dolphinscheduler-agent/logs/agent.log

# ngrok 日志
tail -f /tmp/ngrok.log

# nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### 6.3 URL 变化处理

免费版 ngrok URL 在重启后会变化：

```bash
# 1. 获取新 URL
./deploy/setup_ngrok.sh

# 2. 重启 Agent（加载新配置）
sudo systemctl restart dolphinscheduler-agent

# 3. 更新 DolphinScheduler 告警配置
#    - 安全中心 → 告警实例管理 → 编辑 Webhook 实例
#    - 更新 URL 为新的 ngrok URL
```

### 6.4 更新部署

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
sudo systemctl start ngrok
sudo systemctl start dolphinscheduler-agent

# 更新 URL（如果变化）
./deploy/setup_ngrok.sh
```

### 6.5 图谱维护

```bash
# 手动扫描图谱
curl -X POST http://localhost:8080/graph/scan

# 查看已扫描项目
curl http://localhost:8080/graph/projects

# 更新代码仓库（影响图谱）
cd /opt/spark-etl
git pull
cd /opt/dolphinscheduler-agent
curl -X POST http://localhost:8080/graph/scan
```

---

## 7. 故障排查

### 7.1 Agent 无法启动

**检查步骤：**

```bash
# 1. 查看状态
sudo systemctl status dolphinscheduler-agent

# 2. 查看日志
tail -100 /opt/dolphinscheduler-agent/logs/agent.log

# 3. 手动启动测试
cd /opt/dolphinscheduler-agent
source venv/bin/activate
python -m src all
```

**常见原因：**

| 原因 | 解决方法 |
|------|----------|
| .env 配置缺失 | `vim .env` 补充必要配置 |
| Python 依赖缺失 | `pip install -r requirements.txt` |
| 端口 8080 被占用 | `netstat -tlnp | grep 8080` 检查占用进程 |
| DolphinScheduler API 不可达 | 检查网络连通性 |

### 7.2 ngrok 无法启动

**检查步骤：**

```bash
# 1. 查看状态
sudo systemctl status ngrok

# 2. 查看日志
tail -100 /tmp/ngrok.log

# 3. 验证 authtoken
ngrok config check

# 4. 手动启动测试
ngrok http 8080
```

**常见原因：**

| 原因 | 解决方法 |
|------|----------|
| authtoken 未配置 | `ngrok config add-authtoken YOUR_TOKEN` |
| authtoken 无效 | 重新获取 token |
| 网络问题 | 检查服务器能否访问 ngrok.com |

### 7.3 告警无法接收

**检查步骤：**

```bash
# 1. 检查 Agent 服务
curl http://localhost:8080/health

# 2. 检查 ngrok
curl -s http://127.0.0.1:4040/api/tunnels

# 3. 测试 webhook
curl -X POST https://your-ngrok-url.ngrok-free.app/webhook \
  -H "Content-Type: application/json" \
  -d '{"alerts": "[{\"test\": \"data\"}]"}'

# 4. 检查 DolphinScheduler 告警配置
#    - 告警实例 URL 是否正确
#    - 项目是否绑定告警组
```

### 7.4 钉钉消息无法发送

**检查步骤：**

```bash
# 1. 检查 Stream 配置
grep DINGTALK_CLIENT /opt/dolphinscheduler-agent/.env

# 2. 检查 Webhook 配置
grep DINGTALK_WEBHOOK /opt/dolphinscheduler-agent/.env

# 3. 查看日志中的钉钉错误
grep -i "dingtalk" /opt/dolphinscheduler-agent/logs/agent.log
```

### 7.5 知识图谱扫描失败

**检查步骤：**

```bash
# 1. 检查代码仓库
ls -la /opt/spark-etl

# 2. 检查 DolphinScheduler API
curl -H "token: YOUR_TOKEN" http://your-ds-server:12345/dolphinscheduler/projects

# 3. 检查图谱存储目录
ls -la /opt/dolphinscheduler-agent/data/graph/

# 4. 手动触发扫描并查看日志
curl -X POST http://localhost:8080/graph/scan
tail -50 /opt/dolphinscheduler-agent/logs/agent.log
```

### 7.6 LLM 分析失败

**检查步骤：**

```bash
# 1. 检查 LLM API 配置
grep LLM_API /opt/dolphinscheduler-agent/.env

# 2. 测试 LLM API 连通性
curl -X POST $LLM_API_URL \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "glm-5", "prompt": "test"}'

# 3. 查看日志中的 LLM 错误
grep -i "llm" /opt/dolphinscheduler-agent/logs/agent.log
```

---

## 附录：快速命令参考

```bash
# === 服务管理 ===
sudo systemctl start dolphinscheduler-agent  # 启动 Agent
sudo systemctl start ngrok                   # 启动 ngrok
sudo systemctl restart dolphinscheduler-agent # 重启 Agent
sudo systemctl status dolphinscheduler-agent # 查看状态

# === URL 管理 ===
./deploy/setup_ngrok.sh                      # 获取并配置公网 URL
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])"  # 快速查看 URL

# === 健康检查 ===
curl http://localhost:8080/health            # 本地检查
curl https://YOUR_NGROK_URL/health           # 公网检查

# === 图谱操作 ===
curl -X POST http://localhost:8080/graph/scan # 扫描图谱
curl http://localhost:8080/graph/projects    # 查看项目

# === 日志查看 ===
tail -f /opt/dolphinscheduler-agent/logs/agent.log  # Agent 日志
tail -f /tmp/ngrok.log                        # ngrok 日志
```

---

**文档维护:** 部署相关问题请更新此文档，确保与实际部署流程一致。