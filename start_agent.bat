@echo off
REM TAOLIE Host Agent Start Script for Windows
REM This script starts the host agent with proper configuration

setlocal enabledelayedexpansion

echo [INFO] Starting TAOLIE Host Agent...

REM Check if config file exists
set CONFIG_FILE=C:\ProgramData\taolie-host-agent\config.yaml
if not exist "%CONFIG_FILE%" (
    echo [ERROR] Configuration file not found at %CONFIG_FILE%
    echo [ERROR] Please run setup.bat first
    pause
    exit /b 1
)

REM Check if agent code exists
set AGENT_DIR=C:\ProgramData\taolie-host-agent
if not exist "%AGENT_DIR%\agent" (
    echo [ERROR] Agent code not found at %AGENT_DIR%
    echo [ERROR] Please run setup.bat first
    pause
    exit /b 1
)

REM Check if PostgreSQL is running
echo [INFO] Checking PostgreSQL status...
sc query postgresql >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] PostgreSQL service not found
    echo [WARNING] Please ensure PostgreSQL is installed and running
) else (
    sc query postgresql | find "RUNNING" >nul
    if %errorLevel% neq 0 (
        echo [WARNING] PostgreSQL is not running, attempting to start...
        net start postgresql
        timeout /t 5 /nobreak >nul
    )
)

REM Check if required ports are available
echo [INFO] Checking port availability...
netstat -an | find ":2222" >nul
if %errorLevel% equ 0 (
    echo [WARNING] Port 2222 is already in use
) else (
    echo [INFO] Port 2222 is available
)

netstat -an | find ":8888" >nul
if %errorLevel% equ 0 (
    echo [WARNING] Port 8888 is already in use
) else (
    echo [INFO] Port 8888 is available
)

netstat -an | find ":9999" >nul
if %errorLevel% equ 0 (
    echo [WARNING] Port 9999 is already in use
) else (
    echo [INFO] Port 9999 is available
)

REM Check if GPU is available
echo [INFO] Checking GPU availability...
where nvidia-smi >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] nvidia-smi not found - GPU may not be available
) else (
    nvidia-smi >nul 2>&1
    if %errorLevel% neq 0 (
        echo [ERROR] GPU is not accessible
        echo [ERROR] Please check your NVIDIA drivers
        pause
        exit /b 1
    ) else (
        echo [SUCCESS] GPU is available
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
    )
)

REM Check if Docker is available
echo [INFO] Checking Docker availability...
where docker >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Docker not found - required for deployments
    pause
    exit /b 1
)

docker info >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Docker is not running or not accessible
    echo [ERROR] Please start Docker Desktop
    pause
    exit /b 1
)

echo [SUCCESS] Docker is available

REM Start the agent
echo [INFO] Starting GPU Host Agent service...

REM Set environment variables
set PYTHONPATH=%AGENT_DIR%
set CONFIG_FILE=%CONFIG_FILE%

REM Start the agent
cd /d "%AGENT_DIR%"
python -m agent.main
