#!/bin/bash

# TAOLIE Host Agent Start Script
# This script starts the host agent with proper configuration

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
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root (use sudo)"
   exit 1
fi

print_status "Starting TAOLIE Host Agent..."

# Check if config file exists
CONFIG_FILE="/etc/taolie-host-agent/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    print_error "Configuration file not found at $CONFIG_FILE"
    print_error "Please run setup.sh first"
    exit 1
fi

# Check if agent code exists
AGENT_DIR="/var/lib/taolie-host-agent"
if [ ! -d "$AGENT_DIR" ]; then
    print_error "Agent code not found at $AGENT_DIR"
    print_error "Please run setup.sh first"
    exit 1
fi

# Check if PostgreSQL is running
print_status "Checking PostgreSQL status..."
if ! systemctl is-active --quiet postgresql; then
    print_warning "PostgreSQL is not running, starting it..."
    systemctl start postgresql
    sleep 5
fi

# Check if database exists and is accessible
print_status "Testing database connection..."
cd "$AGENT_DIR"
if ! python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from agent.core.database import init_database
try:
    asyncio.run(init_database())
    print('Database connection successful')
except Exception as e:
    print(f'Database connection failed: {e}')
    sys.exit(1)
"; then
    print_error "Database connection failed"
    print_error "Please check your database configuration in $CONFIG_FILE"
    exit 1
fi

print_success "Database connection verified"

# Check if required ports are available
print_status "Checking port availability..."
CONFIG_PORTS=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)
    ports = config['network']['ports']
    print(f\"{ports['ssh']} {ports['rental_port_1']} {ports['rental_port_2']}\")
")

for port in $CONFIG_PORTS; do
    if netstat -tuln | grep -q ":$port "; then
        print_warning "Port $port is already in use"
        print_warning "This may cause issues with deployments"
    else
        print_status "Port $port is available"
    fi
done

# Check if GPU is available
print_status "Checking GPU availability..."
if ! command -v nvidia-smi &> /dev/null; then
    print_warning "nvidia-smi not found - GPU may not be available"
else
    if nvidia-smi &> /dev/null; then
        print_success "GPU is available"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | while read line; do
            print_status "GPU: $line"
        done
    else
        print_error "GPU is not accessible"
        print_error "Please check your NVIDIA drivers"
        exit 1
    fi
fi

# Check if Docker is available
print_status "Checking Docker availability..."
if ! command -v docker &> /dev/null; then
    print_error "Docker not found - required for deployments"
    exit 1
fi

if ! docker info &> /dev/null; then
    print_error "Docker is not running or not accessible"
    print_error "Please start Docker service"
    exit 1
fi

print_success "Docker is available"

# Start the agent
print_status "Starting GPU Host Agent service..."

# Set environment variables
export PYTHONPATH="$AGENT_DIR"
export CONFIG_FILE="$CONFIG_FILE"

# Start the agent
cd "$AGENT_DIR"
exec python3 -m agent.main
