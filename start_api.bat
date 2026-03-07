@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "UV_EXE=uv"
where uv >nul 2>&1
if errorlevel 1 (
    set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
)
if not exist "%UV_EXE%" (
    echo ERROR: uv not found. Please install uv or add it to PATH.
    pause
    exit /b 1
)

echo ============================================
echo   ShuaiTravelAgent - Start API
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Create local Python 3.13 venv with uv...
    call "%UV_EXE%" python install 3.13
    call "%UV_EXE%" venv .venv --python 3.13
    if errorlevel 1 (
        echo ERROR: failed to create .venv
        pause
        exit /b 1
    )
) else (
    echo [1/3] Local .venv found
)

echo [2/3] Check Python dependencies...
call .\.venv\Scripts\python.exe -c "import fastapi, langchain, pytest" >nul 2>&1
if errorlevel 1 (
    echo Missing dependencies, installing from requirements.txt...
    call "%UV_EXE%" pip install --python ".\.venv\Scripts\python.exe" -r requirements.txt
    if errorlevel 1 (
        echo ERROR: dependency installation failed
        pause
        exit /b 1
    )
) else (
    echo Dependencies already satisfied
)

echo [3/3] Start Web API...
echo API: http://localhost:38000
echo Docs: http://localhost:38000/rapidoc
echo.

call .\.venv\Scripts\python.exe run_api.py
