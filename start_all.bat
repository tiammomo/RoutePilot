@echo off
cd /d D:\projects\shuai\ShuaiTravelAgent

echo Starting Agent Service...
start "Agent" cmd /k "call conda activate agents && cd /d D:\projects\shuai\ShuaiTravelAgent && python run_agent.py"

timeout /t 5 /nobreak >nul

echo Starting API Service...
start "API" cmd /k "call conda activate agents && cd /d D:\projects\shuai\ShuaiTravelAgent && python run_api.py"

timeout /t 5 /nobreak >nul

echo Starting Frontend...
start "Frontend" cmd /k "cd /d D:\projects\shuai\ShuaiTravelAgent\frontend && npm run dev"

echo All services started!
echo Agent: localhost:50051
echo API: localhost:38000
echo Frontend: localhost:33001
pause
