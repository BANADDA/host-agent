# Host Agent

A host agent that manages GPU deployments with PostgreSQL database, network configuration, and comprehensive monitoring.

## Features

- **PostgreSQL Database**: Local database with comprehensive schema for GPU status, deployments, metrics, and health monitoring
- **Network Configuration**: Configurable public IP and port mapping for SSH and services
- **7 Monitoring Threads**: GPU monitoring, health checks, heartbeat, command polling, metrics push, health push, and duration monitoring
- **Docker Integration**: Automated container deployment with GPU access and port mapping
- **Health Monitoring**: Comprehensive GPU health checks and status reporting
- **Central Server Integration**: Registration and communication with central platform
- **Multi-platform Support**: Works on Linux and Windows
- **Docker Image**: Pre-built containerized version for easy deployment

## Quick Start

### System Requirements
- Ubuntu 20.04+ or Windows 10/11
- NVIDIA GPU with CUDA support
- Docker installed and running
- PostgreSQL 12+ (auto-installed by setup script)
- Public IP address or domain name
- API key from central platform

### Installation

#### Linux (Ubuntu/Debian)
```bash
# Download and run the installation script (can be run as root or with sudo)
curl -fsSL https://raw.githubusercontent.com/BANADDA/host-agent/main/setup.sh | bash

# Or with sudo if not running as root:
# curl -fsSL https://raw.githubusercontent.com/BANADDA/host-agent/main/setup.sh | sudo bash
```

#### Windows
```cmd
# Download and run the installation script
powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/BANADDA/host-agent/main/setup.bat' -OutFile 'setup.bat'; .\setup.bat"
```

### Configuration

Edit the configuration file:
```bash
# Linux
sudo nano /etc/taolie-host-agent/config.yaml

# Windows
notepad C:\ProgramData\taolie-host-agent\config.yaml
```

Required settings:
```yaml
agent:
  api_key: "your-api-key-here"  # Get from central platform

network:
  public_ip: "21.1.12.69"  # Your public IP or domain
  ports:
    ssh: 2222
    rental_port_1: 8888
    rental_port_2: 9999
```

### Firewall Configuration

#### Linux (UFW)
```bash
sudo ufw allow 2222/tcp
sudo ufw allow 8888/tcp
sudo ufw allow 9999/tcp
```

#### Windows
```cmd
netsh advfirewall firewall add rule name="SSH" dir=in action=allow protocol=TCP localport=2222
netsh advfirewall firewall add rule name="Port 1" dir=in action=allow protocol=TCP localport=8888
netsh advfirewall firewall add rule name="Port 2" dir=in action=allow protocol=TCP localport=9999
```

### Start the Agent

#### Linux
```bash
# Start service
sudo systemctl start taolie-host-agent
sudo systemctl enable taolie-host-agent

# Check status
sudo systemctl status taolie-host-agent

# View logs
sudo journalctl -u taolie-host-agent -f
```

#### Windows
```cmd
# Start agent
python -m agent.main

# Or use the start script
start_agent.bat
```

### Docker Deployment

#### Using Docker Compose
```bash
# Download docker-compose.yml and config.yaml
curl -fsSL https://raw.githubusercontent.com/BANADDA/host-agent/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/BANADDA/host-agent/main/config.yaml -o config.yaml

# Edit config.yaml with your settings
nano config.yaml

# Start with Docker Compose
docker-compose up -d
```

#### Using Pre-built Image
```bash
# Pull the latest image
docker pull ghcr.io/BANADDA/host-agent:latest

# Run with GPU support
docker run -d \
  --name taolie-host-agent \
  --gpus all \
  --privileged \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /etc/taolie-host-agent:/etc/taolie-host-agent:ro \
  -p 2222:2222 -p 8888:8888 -p 9999:9999 \
  ghcr.io/BANADDA/host-agent:latest
```

## Configuration File

The configuration file (`config.yaml`) contains all settings for the host agent:

```yaml
# Host Agent Configuration
agent:
  id: ""  # Auto-generated
  api_key: "your-api-key-here"  # REQUIRED

# Network Configuration (REQUIRED)
network:
  public_ip: "123.45.67.89"  # REQUIRED
  ports:
    ssh: 2222
    rental_port_1: 8888
    rental_port_2: 9999

# Central Server Configuration
server:
  url: "https://api.yourplatform.com"
  timeout: 10

# Monitoring Configuration
monitoring:
  heartbeat_interval: 30
  command_poll_interval: 10
  metrics_push_interval: 10
  health_push_interval: 60
  duration_check_interval: 30

# Database Configuration
database:
  host: "localhost"
  port: 5432
  name: "taolie_host_agent"
  user: "agent"
  password: "auto-generated"

# GPU Configuration (auto-populated)
gpu:
  uuid: ""

# Logging
logging:
  level: "INFO"
  file: "/var/log/taolie-host-agent/agent.log"
  max_size_mb: 100
  max_files: 5
```

## Database Schema

The system uses PostgreSQL with the following main tables:

- **gpu_status**: GPU information and current status
- **deployments**: Active and historical deployments
- **gpu_metrics**: Performance metrics over time
- **gpu_health_history**: Health check results
- **health_checks**: Deployment-specific health checks
- **command_queue**: Commands from central server

## Monitoring Threads

The system runs 7 background monitoring threads:

1. **GPU Monitoring** (10s): Collects GPU metrics and utilization
2. **GPU Health Check** (60s): Performs comprehensive health checks
3. **Heartbeat** (30s): Sends keep-alive to central server
4. **Command Polling** (10s): Polls for new commands from server
5. **Metrics Push** (10s): Pushes metrics to central server
6. **Health Push** (60s): Pushes health status to central server
7. **Duration Monitor** (30s): Monitors for expired deployments

## Deployment Workflow

### Automatic Deployment
1. User rents GPU on platform
2. Platform sends DEPLOY command to agent
3. Agent validates GPU availability
4. Agent pulls Docker image
5. Agent creates container with port mapping
6. Agent configures SSH and Jupyter access
7. Agent performs health checks
8. Agent notifies platform with access information

### Port Mapping
- **SSH Port (2222)**: Terminal access for management
- **Rental Port 1 (8888)**: Primary application port (Jupyter, web apps)
- **Rental Port 2 (9999)**: Secondary application port (APIs, services)

### Access Information
Users receive:
- SSH credentials for terminal access
- Jupyter Lab URL with token
- Custom application port access
- Full connection details

## Termination Workflow

### Automatic Termination
- Duration monitor checks for expired deployments
- Sends warning to container (30s before expiry)
- Stops container gracefully
- Cleans up GPU resources
- Updates database
- Notifies central server

### Manual Termination
- User requests early termination
- Platform sends TERMINATE command
- Agent stops container immediately
- Calculates usage and refund
- Updates database
- Notifies central server

## Health Monitoring

The system performs comprehensive health checks:

- **Driver Responsiveness**: Tests nvidia-smi response
- **Temperature Monitoring**: Checks GPU temperature
- **Power Monitoring**: Monitors power draw
- **ECC Error Detection**: Checks for memory errors
- **Fan Operation**: Verifies fan functionality

## Logging

Logs are written to:
- **Console**: Real-time status and errors
- **File**: `/var/log/gpu-host-agent/agent.log`
- **Systemd Journal**: `journalctl -u gpu-host-agent`

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   sudo netstat -tuln | grep :2222
   sudo lsof -i :2222
   ```

2. **Database Connection Failed**
   ```bash
   sudo systemctl status postgresql
   sudo -u postgres psql -c "\\l"
   ```

3. **GPU Not Accessible**
   ```bash
   nvidia-smi
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

4. **Container Creation Failed**
   ```bash
   docker images
   docker pull yourplatform/cuda-template:latest
   ```

### Log Analysis

```bash
# View real-time logs
tail -f /var/log/taolie-host-agent/agent.log

# View systemd logs
journalctl -u taolie-host-agent -f

# Check specific errors
grep ERROR /var/log/taolie-host-agent/agent.log
```

## API Integration

The agent communicates with the central server via REST API:

- **Registration**: `POST /api/host-agents/register`
- **Heartbeat**: `POST /api/host-agents/{agent_id}/heartbeat`
- **Commands**: `GET /api/host-agents/{agent_id}/commands`
- **Metrics**: `POST /api/host-agents/metrics`
- **Health**: `POST /api/host-agents/health`
- **Deployments**: `POST /api/deployments/{id}/success`

## Security

- All API communication uses HTTPS
- Database credentials are auto-generated
- SSH passwords are randomly generated per deployment
- Jupyter tokens are cryptographically secure
- Container isolation with GPU passthrough

## Performance

- **GPU Monitoring**: 10-second intervals
- **Health Checks**: 60-second intervals
- **Command Polling**: 10-second intervals
- **Metrics Storage**: 24-hour retention
- **Log Rotation**: Daily with 5-day retention

## Technical Workflow

### Agent Registration Process
```
1. Collect GPU specs (nvidia-smi)
2. Collect host specs (CPU, RAM, OS)
3. Configure network (IP, ports)
4. Register with central platform
```

### Deployment Process
```
1. Receive DEPLOY command
2. Validate GPU availability
3. Pull Docker image
4. Create container with GPU access
5. Configure SSH & Jupyter
6. Perform health checks
7. Notify platform with access info
```

### Monitoring & Management
```
- GPU metrics collection (10s intervals)
- Health monitoring (60s intervals)
- Heartbeat to platform (30s intervals)
- Command polling (10s intervals)
- Auto-termination (30s intervals)
- Resource cleanup
```

## Advanced Configuration

### Custom Docker Templates

Create your own GPU-enabled containers:

```dockerfile
# Custom template example
FROM nvidia/cuda:11.8-devel-ubuntu22.04

# Install your specific tools
RUN apt-get update && apt-get install -y \
    python3-pip \
    jupyter \
    your-custom-tools

# Configure for TAOLIE
ENV DEPLOYMENT_ID=""
ENV SSH_USERNAME=""
ENV SSH_PASSWORD=""
ENV JUPYTER_TOKEN=""

# Start services
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root"]
```

### Network Security

```yaml
# Advanced network configuration
network:
  public_ip: "your-domain.com"
  ports:
    ssh: 2222
    rental_port_1: 8888
    rental_port_2: 9999
  security:
    enable_ssl: true
    ssl_cert: "/path/to/cert.pem"
    ssl_key: "/path/to/key.pem"
    allowed_ips: ["192.168.1.0/24"]  # Optional IP restrictions
```

### Monitoring & Alerting

```yaml
# Enhanced monitoring
monitoring:
  gpu_thresholds:
    temperature_max: 85
    power_max: 400
    utilization_min: 5
  alerts:
    email: "admin@yourdomain.com"
    webhook: "https://your-webhook.com/alerts"
  retention:
    metrics_days: 30
    logs_days: 7
```

## Deployment Strategies

### Single GPU Setup
```bash
# One GPU, one agent
./setup.sh
sudo systemctl start taolie-host-agent
```

### Multi-GPU Setup
```bash
# Multiple GPUs, multiple agents
for gpu in 0 1 2 3; do
  cp config.yaml config-gpu$gpu.yaml
  # Edit config-gpu$gpu.yaml for each GPU
  sudo systemctl start taolie-host-agent-gpu$gpu
done
```

### Cluster Deployment
```bash
# Docker Swarm or Kubernetes
docker stack deploy -c docker-compose.yml taolie-cluster
```

## Support

For issues and support:
1. Check logs: `/var/log/taolie-host-agent/agent.log`
2. Verify configuration: `config.yaml`
3. Test network: `curl ifconfig.me`
4. Check GPU: `nvidia-smi`
5. Verify Docker: `docker info`

## License

This project is licensed under the MIT License.
