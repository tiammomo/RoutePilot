@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%\frontend"

echo ============================================
echo   ShuaiTravelAgent - Start Frontend
echo ============================================
echo.

if not exist node_modules (
    echo [1/2] Install frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed
        pause
        exit /b 1
    )
) else (
    echo [1/2] Frontend dependencies already installed
)

echo [2/2] Start frontend server...
echo Frontend: http://localhost:33001
echo.

call npm run dev
