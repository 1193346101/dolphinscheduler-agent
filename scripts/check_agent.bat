@echo off
REM DolphinScheduler Agent - Health Check Script

cd /d D:\Project\dolphinscheduler-agent

REM Check port
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% neq 0 (
    echo [ERROR] Agent not running on port 8000
    echo Restarting...
    call scripts\start_agent.bat
    exit /b 1
)

REM Check health status
curl -s http://localhost:8000/health > health_check.json 2>&1

REM Parse JSON to check status
for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open('health_check.json')); print(d.get('status',''))"') do (
    set STATUS=%%a
)

if "%STATUS%" == "healthy" (
    echo [OK] Agent is healthy
    del health_check.json
    exit /b 0
) else (
    echo [ERROR] Agent unhealthy: %STATUS%
    del health_check.json
    exit /b 1
)