@echo off
echo ============================================
echo DolphinScheduler Agent - Restart All Services
echo ============================================

echo [1/6] Stopping Python processes...
taskkill /F /IM python.exe 2>nul
if %errorlevel% == 0 (
    echo   ^> Python processes stopped
) else (
    echo   ^> No Python processes found
)

echo [2/6] Stopping ngrok...
taskkill /F /IM ngrok.exe 2>nul
if %errorlevel% == 0 (
    echo   ^> ngrok stopped
) else (
    echo   ^> ngrok not running
)

echo [3/6] Clearing logs...
if exist logs (
    del /Q logs\* 2>nul
    echo   ^> Logs cleared
) else (
    echo   ^> No logs directory
)

cd /d D:\Project\dolphinscheduler-agent

echo [4/6] Starting Agent (Stream + API)...
start /B python -m src all
echo   ^> Agent starting on port 8080 + Stream mode

echo [5/6] Waiting for Agent to initialize...
timeout /t 5 /nobreak >nul

echo [6/6] Starting ngrok for webhook...
start /B ngrok http 8080
echo   ^> ngrok starting

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo Services restarted successfully!
echo ============================================

echo Checking health...
curl -s http://localhost:8080/health

echo.
echo Getting ngrok URL...
curl -s http://localhost:4040/api/tunnels > temp_ngrok.json
type temp_ngrok.json | findstr "public_url"
del temp_ngrok.json 2>nul

echo.
echo Webhook URL: https://reset-taking-porous.ngrok-free.dev/webhook
echo ============================================