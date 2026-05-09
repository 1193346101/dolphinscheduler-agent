@echo off
REM DolphinScheduler Agent - Windows Startup Script

cd /d D:\Project\dolphinscheduler-agent

REM Check if already running
netstat -ano | findstr :8000 >nul
if %errorlevel% == 0 (
    echo Agent already running on port 8000
    exit /b 0
)

REM Set environment variables
set DS_API_URL=http://ali-dolphin-test-01:12345/dolphinscheduler
set DS_API_TOKEN=771c3c883c17618846a5deae40f89d86
set DS_VERSION=3.2.0

REM Start Agent service
echo Starting DolphinScheduler Agent...
start /b python -m uvicorn src.api.webhook_api:app --host 0.0.0.0 --port 8000

REM Wait for startup
timeout /t 5 /nobreak >nul

REM Verify startup success
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% == 0 (
    echo Agent started successfully
) else (
    echo Agent startup failed
)

echo Agent is running. Press Ctrl+C to stop.