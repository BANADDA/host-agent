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

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root. Please run as a regular user with sudo privileges."
   exit 1
fi

print_status "Starting TAOLIE Host Agent installation..."

# Update package list
print_status "Updating package list..."
sudo apt-get update

# Install required packages
print_status "Installing required packages..."
sudo apt-get install -y \
    curl \
    wget \
    git \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    docker.io \
    docker-compose \
    ufw \
    nvidia-container-toolkit

# Start and enable PostgreSQL
print_status "Starting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Start and enable Docker
print_status "Starting Docker service..."
sudo systemctl start docker
sudo systemctl enable docker

# Add current user to docker group
print_status "Adding user to docker group..."
sudo usermod -aG docker $USER

# Create directories
print_status "Creating directories..."
sudo mkdir -p /etc/taolie-host-agent
sudo mkdir -p /var/log/taolie-host-agent
sudo mkdir -p /var/lib/taolie-host-agent

# Set permissions
sudo chown -R $USER:$USER /etc/taolie-host-agent
sudo chown -R $USER:$USER /var/log/taolie-host-agent
sudo chown -R $USER:$USER /var/lib/taolie-host-agent

# Download agent code from GitHub
print_status "Downloading TAOLIE Host Agent code..."
cd /tmp
wget -q https://github.com/BANADDA/host-agent/archive/main.zip
unzip -q main.zip
cd host-agent-main

# Generate random password for database
DB_PASSWORD=$(openssl rand -base64 32)

# Create database and user
print_status "Setting up PostgreSQL database..."
sudo -u postgres psql -c "CREATE DATABASE taolie_host_agent;"
sudo -u postgres psql -c "CREATE USER agent WITH PASSWORD '$DB_PASSWORD';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE taolie_host_agent TO agent;"
sudo -u postgres psql -c "ALTER USER agent CREATEDB;"

# Create configuration file
print_status "Creating configuration file..."
cat > /etc/taolie-host-agent/config.yaml << EOF
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
pip3 install -r requirements.txt

# Create systemd service
print_status "Creating systemd service..."
sudo tee /etc/systemd/system/taolie-host-agent.service > /dev/null << EOF
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
sudo cp -r agent /var/lib/taolie-host-agent/
sudo cp requirements.txt /var/lib/taolie-host-agent/
sudo cp config.yaml /var/lib/taolie-host-agent/

# Set permissions
sudo chown -R root:root /var/lib/taolie-host-agent
sudo chmod +x /var/lib/taolie-host-agent/agent/main.py

# Configure log rotation
print_status "Configuring log rotation..."
sudo tee /etc/logrotate.d/taolie-host-agent > /dev/null << EOF
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
sudo systemctl daemon-reload

# Clean up
cd /
rm -rf /tmp/host-agent-main /tmp/main.zip

print_success "TAOLIE Host Agent installation completed!"
print_warning "IMPORTANT: Please edit /etc/taolie-host-agent/config.yaml and configure:"
print_warning "1. Set your API key"
print_warning "2. Set your public IP address"
print_warning "3. Configure server URL if different"

print_status "To start the agent:"
print_status "  sudo systemctl start taolie-host-agent"
print_status "  sudo systemctl enable taolie-host-agent"

print_status "To check status:"
print_status "  sudo systemctl status taolie-host-agent"

print_status "To view logs:"
print_status "  sudo journalctl -u taolie-host-agent -f"