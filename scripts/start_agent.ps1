# DolphinScheduler Agent - PowerShell Startup Script
# 自动检测并关闭已有端口，然后启动服务

param(
    [string]$Mode = "all",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$ProjectPath = "D:\Project\dolphinscheduler-agent"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "DolphinScheduler Agent - PowerShell 启动脚本" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# 切换到项目目录
Set-Location $ProjectPath

# 加载环境变量
if (Test-Path ".env") {
    Write-Host "[ENV] 加载 .env 文件..." -ForegroundColor Yellow
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $value
        }
    }
}

# 检查并关闭已有端口
Write-Host "[PORT] 检查端口 $Port..." -ForegroundColor Yellow
$connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($connections) {
    Write-Host "[PORT] 发现端口 $Port 已被占用，正在关闭..." -ForegroundColor Warning
    foreach ($conn in $connections) {
        $pid = $conn.OwningProcess
        try {
            Stop-Process -Id $pid -Force
            Write-Host "[PORT] 已关闭进程 PID: $pid" -ForegroundColor Green
        } catch {
            Write-Host "[PORT] 无法关闭进程 PID: $pid: $_" -ForegroundColor Red
        }
    }
    # 等待端口释放
    Start-Sleep -Seconds 2
} else {
    Write-Host "[PORT] 端口 $Port 空闲" -ForegroundColor Green
}

# 显示配置
Write-Host ""
Write-Host "启动配置:" -ForegroundColor Cyan
Write-Host "  模式: $Mode"
Write-Host "  端口: $Port"
Write-Host "  Client ID: $env:DINGTALK_CLIENT_ID"
Write-Host "  DS_API_URL: $env:DS_API_URL"
Write-Host "-" * 60

# 启动服务
Write-Host "[START] 启动服务..." -ForegroundColor Yellow

switch ($Mode) {
    "api" {
        Write-Host "启动 API 服务（告警 webhook）..."
        python -m uvicorn src.api.webhook_api:app --host 0.0.0.0 --port $Port --reload
    }
    "stream" {
        Write-Host "启动钉钉 Stream 模式（对话功能）..."
        python -m src stream
    }
    "chat" {
        Write-Host "启动交互式对话 REPL..."
        python -m src chat
    }
    default {
        Write-Host "启动完整服务（Stream + API）..."
        python -m src
    }
}