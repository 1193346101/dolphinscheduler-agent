@echo off
REM DolphinScheduler Agent - Stop Script

cd /d D:\Project\dolphinscheduler-agent

REM Find process on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    set PID=%%a
)

if defined PID (
    echo Stopping Agent (PID: %PID%)...
    taskkill /F /PID %PID%
    echo Agent stopped
) else (
    echo Agent not running
)