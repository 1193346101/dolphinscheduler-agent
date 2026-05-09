@echo off
echo ============================================
echo DolphinScheduler Agent - Restart All Services
echo ============================================

echo [1/6] Stopping Python processes...
taskkill /F /IM python.exe 2>nul
if %errorlevel% == 0 (
    echo   >> Python processes stopped
) else (
    echo   >> No Python processes found
)

echo [2/6] Stopping ngrok...
taskkill /F /IM ngrok.exe 2>nul
if %errorlevel% == 0 (
    echo   >> ngrok stopped
) else (
    echo   >> ngrok not running
)

echo [3/6] Clearing logs...
if exist logs (
    del /Q logs\* 2>nul
    echo   >> Logs cleared
) else (
    echo   >> No logs directory
)

echo [4/6] Starting Agent server...
start /B python -m uvicorn src.api.webhook_api:app --host 0.0.0.0 --port 8080
echo   >> Agent starting on port 8080

echo [5/6] Waiting for Agent to initialize...
timeout /t 3 /nobreak >nul

echo [6/6] Starting ngrok...
start /B ngrok http 8080
echo   >> ngrok starting

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
for /f "tokens=2 delims=:" %%a in ('findstr "public_url" temp_ngrok.json') do (
    set NGROK_URL=%%a
)
del temp_ngrok.json 2>nul

echo.
echo Webhook URL: https://reset-taking-porous.ngrok-free.dev/webhook
echo ============================================