@echo off
REM TAOLIE Host Agent Setup Script for Windows
REM This script downloads and installs PostgreSQL, Python dependencies, and sets up the host agent

setlocal enabledelayedexpansion

echo Starting TAOLIE Host Agent installation...

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator
    pause
    exit /b 1
)

echo [INFO] Installing required packages...

REM Install Chocolatey if not present
if not exist "C:\ProgramData\chocolatey\choco.exe" (
    echo [INFO] Installing Chocolatey...
    powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
)

REM Install required packages
echo [INFO] Installing PostgreSQL, Python, and Docker...
choco install -y postgresql python docker-desktop

REM Install Python packages
echo [INFO] Installing Python dependencies...
pip install psycopg2-binary pyyaml requests aiohttp docker

REM Create directories
echo [INFO] Creating directories...
if not exist "C:\ProgramData\taolie-host-agent" mkdir "C:\ProgramData\taolie-host-agent"
if not exist "C:\ProgramData\taolie-host-agent\logs" mkdir "C:\ProgramData\taolie-host-agent\logs"
if not exist "C:\ProgramData\taolie-host-agent\data" mkdir "C:\ProgramData\taolie-host-agent\data"

REM Download agent code from GitHub
echo [INFO] Downloading TAOLIE Host Agent code...
cd /d "C:\ProgramData\taolie-host-agent"
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/BANADDA/host-agent/archive/main.zip' -OutFile 'host-agent.zip'"
powershell -Command "Expand-Archive -Path 'host-agent.zip' -DestinationPath '.' -Force"
xcopy /E /I /Y "host-agent-main\*" "."
rmdir /S /Q "host-agent-main"
del "host-agent.zip"

REM Generate random password for database
echo [INFO] Generating database password...
for /f %%i in ('powershell -Command "[System.Web.Security.Membership]::GeneratePassword(32, 0)"') do set DB_PASSWORD=%%i

REM Start PostgreSQL service
echo [INFO] Starting PostgreSQL service...
net start postgresql-x64-13

REM Create database and user
echo [INFO] Setting up PostgreSQL database...
"C:\Program Files\PostgreSQL\13\bin\psql.exe" -U postgres -c "CREATE DATABASE taolie_host_agent;"
"C:\Program Files\PostgreSQL\13\bin\psql.exe" -U postgres -c "CREATE USER agent WITH PASSWORD '%DB_PASSWORD%';"
"C:\Program Files\PostgreSQL\13\bin\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE taolie_host_agent TO agent;"
"C:\Program Files\PostgreSQL\13\bin\psql.exe" -U postgres -c "ALTER USER agent CREATEDB;"

REM Create configuration file
echo [INFO] Creating configuration file...
(
echo # TAOLIE Host Agent Configuration
echo agent:
echo   id: ""  # Auto-generated
echo   api_key: "your-api-key-here"  # REQUIRED - Get from platform
echo.
echo # Network Configuration ^(REQUIRED^)
echo network:
echo   public_ip: "YOUR_PUBLIC_IP"  # REQUIRED - Replace with your public IP
echo   ports:
echo     ssh: 2222
echo     rental_port_1: 8888
echo     rental_port_2: 9999
echo.
echo # Central Server Configuration
echo server:
echo   base_url: "https://api.taolie.com"  # Replace with your server URL
echo   timeout: 30
echo   retry_attempts: 3
echo.
echo # Monitoring Configuration
echo monitoring:
echo   gpu_interval: 10
echo   health_interval: 60
echo   heartbeat_interval: 30
echo   command_poll_interval: 10
echo   duration_check_interval: 30
echo   metrics_retention_days: 7
echo   health_retention_days: 30
echo.
echo # Database Configuration
echo database:
echo   host: "localhost"
echo   port: 5432
echo   name: "taolie_host_agent"
echo   user: "agent"
echo   password: "%DB_PASSWORD%"
echo.
echo # GPU Configuration
echo gpu:
echo   max_temperature: 85
echo   max_power: 400
echo   min_utilization: 5
echo.
echo # Logging Configuration
echo logging:
echo   level: "INFO"
echo   file: "C:\ProgramData\taolie-host-agent\logs\agent.log"
echo   max_size: "10MB"
echo   backup_count: 5
) > "C:\ProgramData\taolie-host-agent\config.yaml"

REM Configure Windows Firewall
echo [INFO] Configuring Windows Firewall...
netsh advfirewall firewall add rule name="TAOLIE Host Agent SSH" dir=in action=allow protocol=TCP localport=2222
netsh advfirewall firewall add rule name="TAOLIE Host Agent Port 1" dir=in action=allow protocol=TCP localport=8888
netsh advfirewall firewall add rule name="TAOLIE Host Agent Port 2" dir=in action=allow protocol=TCP localport=9999

REM Create Windows service
echo [INFO] Creating Windows service...
sc create "TAOLIEHostAgent" binPath="python -m agent.main" start=auto
sc description "TAOLIEHostAgent" "TAOLIE Host Agent Service"

echo [SUCCESS] TAOLIE Host Agent installation completed!
echo [WARNING] IMPORTANT: Please edit C:\ProgramData\taolie-host-agent\config.yaml and configure:
echo [WARNING] 1. Set your API key
echo [WARNING] 2. Set your public IP address
echo [WARNING] 3. Configure server URL if different
echo.
echo [INFO] To start the agent:
echo [INFO]   sc start TAOLIEHostAgent
echo.
echo [INFO] To check status:
echo [INFO]   sc query TAOLIEHostAgent
echo.
echo [INFO] To view logs:
echo [INFO]   Check C:\ProgramData\taolie-host-agent\logs\agent.log

pause