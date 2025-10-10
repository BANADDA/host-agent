#!/bin/bash

# TAOLIE Host Agent Setup Script for Linux
# This script downloads and installs PostgreSQL, Python dependencies, and sets up the host agent

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root and set sudo accordingly
if [[ $EUID -eq 0 ]]; then
   print_warning "Running as root. Will skip sudo commands."
   SUDO=""
else
   SUDO="sudo"
fi

print_status "Starting TAOLIE Host Agent installation..."

# Update package list
print_status "Updating package list..."
$SUDO apt-get update

# Install required packages (only if not already installed)
print_status "Installing required packages..."

# Check and install PostgreSQL if not present
if ! command -v psql &> /dev/null; then
    print_status "Installing PostgreSQL..."
    $SUDO apt-get install -y postgresql postgresql-contrib
else
    print_status "PostgreSQL already installed, skipping..."
fi

# Check and install Docker if not present
if ! command -v docker &> /dev/null; then
    print_status "Installing Docker..."
    $SUDO apt-get install -y docker.io docker-compose
else
    print_status "Docker already installed, skipping..."
fi

# Install other essential packages if missing
print_status "Installing other essential packages..."
$SUDO apt-get install -y \
    curl \
    wget \
    git \
    python3 \
    python3-pip \
    python3-venv \
    ufw \
    unzip \
    openssl || true

# Start and enable PostgreSQL (if not already running)
if systemctl is-active --quiet postgresql; then
    print_status "PostgreSQL service already running..."
else
    print_status "Starting PostgreSQL service..."
    $SUDO systemctl start postgresql
    $SUDO systemctl enable postgresql
fi

# Start and enable Docker (if not already running)
if systemctl is-active --quiet docker; then
    print_status "Docker service already running..."
else
    print_status "Starting Docker service..."
    $SUDO systemctl start docker
    $SUDO systemctl enable docker
fi

# Add current user to docker group (skip if root)
if [[ $EUID -ne 0 ]]; then
    print_status "Adding user to docker group..."
    $SUDO usermod -aG docker $USER
fi

# Create directories (if not already exist)
print_status "Creating directories..."
$SUDO mkdir -p /etc/taolie-host-agent
$SUDO mkdir -p /var/log/taolie-host-agent
$SUDO mkdir -p /var/lib/taolie-host-agent

# Backup existing config if present
if [ -f /etc/taolie-host-agent/config.yaml ]; then
    print_warning "Existing config.yaml found. Backing up to config.yaml.backup"
    $SUDO cp /etc/taolie-host-agent/config.yaml /etc/taolie-host-agent/config.yaml.backup
fi

# Set permissions (skip chown if root)
if [[ $EUID -ne 0 ]]; then
    $SUDO chown -R $USER:$USER /etc/taolie-host-agent
    $SUDO chown -R $USER:$USER /var/log/taolie-host-agent
    $SUDO chown -R $USER:$USER /var/lib/taolie-host-agent
fi

# Download agent code from GitHub
print_status "Downloading TAOLIE Host Agent code..."
cd /tmp

# Clean up any existing downloads
rm -rf host-agent-main main.zip 2>/dev/null || true

# Download and extract
wget -q https://github.com/BANADDA/host-agent/archive/main.zip
unzip -oq main.zip  # -o flag overwrites without prompting
cd host-agent-main

# Generate random password for database
DB_PASSWORD=$(openssl rand -base64 32)

# Create database and user (skip if already exists)
print_status "Setting up PostgreSQL database..."

# Determine how to run postgres commands
if [[ $EUID -eq 0 ]]; then
    PG_CMD="su - postgres -c"
else
    PG_CMD="sudo -u postgres"
fi

# Check if database exists
if su - postgres -c "psql -lqt" | cut -d \| -f 1 | grep -qw taolie_host_agent; then
    print_status "Database 'taolie_host_agent' already exists, skipping creation..."
else
    print_status "Creating database 'taolie_host_agent'..."
    su - postgres -c "psql -c \"CREATE DATABASE taolie_host_agent;\""
fi

# Check if user exists
if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='agent'\"" | grep -q 1; then
    print_status "User 'agent' already exists, updating password..."
    su - postgres -c "psql -c \"ALTER USER agent WITH PASSWORD '$DB_PASSWORD';\""
else
    print_status "Creating user 'agent'..."
    su - postgres -c "psql -c \"CREATE USER agent WITH PASSWORD '$DB_PASSWORD';\""
fi

su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE taolie_host_agent TO agent;\""
su - postgres -c "psql -c \"ALTER USER agent CREATEDB;\""

# Create configuration file
print_status "Creating configuration file..."
$SUDO tee /etc/taolie-host-agent/config.yaml > /dev/null << EOF
# TAOLIE Host Agent Configuration
agent:
  id: ""  # Auto-generated
  api_key: "your-api-key-here"  # REQUIRED - Get from platform

# Network Configuration (REQUIRED)
network:
  public_ip: "YOUR_PUBLIC_IP"  # REQUIRED - Replace with your public IP
  ports:
    ssh: 2222
    rental_port_1: 8888
    rental_port_2: 9999

# Central Server Configuration
server:
  base_url: "https://api.taolie.com"  # Replace with your server URL
  timeout: 30
  retry_attempts: 3

# Monitoring Configuration
monitoring:
  gpu_interval: 10
  health_interval: 60
  heartbeat_interval: 30
  command_poll_interval: 10
  duration_check_interval: 30
  metrics_retention_days: 7
  health_retention_days: 30

# Database Configuration
database:
  host: "localhost"
  port: 5432
  name: "taolie_host_agent"
  user: "agent"
  password: "$DB_PASSWORD"

# GPU Configuration
gpu:
  max_temperature: 85
  max_power: 400
  min_utilization: 5

# Logging Configuration
logging:
  level: "INFO"
  file: "/var/log/taolie-host-agent/agent.log"
  max_size: "10MB"
  backup_count: 5
EOF

# Install Python dependencies
print_status "Installing Python dependencies..."
pip3 install --break-system-packages -r requirements.txt

# Create systemd service
print_status "Creating systemd service..."
$SUDO tee /etc/systemd/system/taolie-host-agent.service > /dev/null << EOF
[Unit]
Description=TAOLIE Host Agent
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/var/lib/taolie-host-agent
ExecStart=/usr/bin/python3 -m agent.main
Restart=always
RestartSec=10
Environment=PYTHONPATH=/var/lib/taolie-host-agent

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=taolie-host-agent

[Install]
WantedBy=multi-user.target
EOF

# Copy agent code to system directory
print_status "Installing agent code..."
$SUDO cp -r agent /var/lib/taolie-host-agent/
$SUDO cp requirements.txt /var/lib/taolie-host-agent/
$SUDO cp config.yaml /var/lib/taolie-host-agent/

# Set permissions
$SUDO chown -R root:root /var/lib/taolie-host-agent
$SUDO chmod +x /var/lib/taolie-host-agent/agent/main.py

# Configure log rotation
print_status "Configuring log rotation..."
$SUDO tee /etc/logrotate.d/taolie-host-agent > /dev/null << EOF
/var/log/taolie-host-agent/*.log {
    daily
    missingok
    rotate 5
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        systemctl reload taolie-host-agent > /dev/null 2>&1 || true
    endscript
}
EOF

# Reload systemd
$SUDO systemctl daemon-reload

# Clean up
cd /
rm -rf /tmp/host-agent-main /tmp/main.zip

print_success "TAOLIE Host Agent installation completed!"
print_warning "IMPORTANT: Please edit /etc/taolie-host-agent/config.yaml and configure:"
print_warning "1. Set your API key"
print_warning "2. Set your public IP address"
print_warning "3. Configure server URL if different"

print_status "To start the agent:"
print_status "  $SUDO systemctl start taolie-host-agent"
print_status "  $SUDO systemctl enable taolie-host-agent"

print_status "To check status:"
print_status "  $SUDO systemctl status taolie-host-agent"

print_status "To view logs:"
print_status "  $SUDO journalctl -u taolie-host-agent -f"