@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ============================================
echo   ShuaiTravelAgent - Start All Services
echo ============================================
echo.

echo [1/2] Start Web API...
start "ShuaiTravelAgent API" cmd /k "cd /d %ROOT% && start_api.bat"

timeout /t 3 /nobreak >nul

echo [2/2] Start Frontend...
start "ShuaiTravelAgent Frontend" cmd /k "cd /d %ROOT% && start_frontend.bat"

echo.
echo Frontend: http://localhost:33001
echo API:      http://localhost:38000
echo Docs:     http://localhost:38000/rapidoc
echo.
