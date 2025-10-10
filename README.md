# TAOLIE Host Agent

GPU host agent for TAOLIE platform. Manages GPU deployments, monitoring, and container orchestration.

## Setup

### Prerequisites
- Ubuntu 20.04+ with NVIDIA GPU
- Docker installed
- NVIDIA Container Toolkit installed

### Step 1: Register and Get API Key

Visit your TAOLIE platform and register your host to get your API key.

### Step 2: Create Configuration

```bash
mkdir ~/taolie-host-agent && cd ~/taolie-host-agent

# Create config.yaml
cat > config.yaml << 'EOF'
agent:
  id: ""
  api_key: "YOUR_API_KEY_HERE"

network:
  public_ip: "YOUR_PUBLIC_IP"
  ports:
    ssh: 2222
    rental_port_1: 8888
    rental_port_2: 9999

server:
  url: "https://api.taolie.com"
  timeout: 30
  retry_attempts: 3

monitoring:
  gpu_interval: 10
  health_interval: 60
  heartbeat_interval: 30
  command_poll_interval: 10
  duration_check_interval: 30

database:
  host: "taolie-postgres"
  port: 5432
  name: "taolie_host_agent"
  user: "agent"
  password: "your_db_password"

gpu:
  max_temperature: 85
  max_power: 400

logging:
  level: "INFO"
  file: "/var/log/taolie-host-agent/agent.log"
EOF

# Edit with your values
nano config.yaml
```

### Step 3: Create Docker Network

```bash
docker network create taolie-network
```

### Step 4: Run PostgreSQL

```bash
docker run -d \
  --name taolie-postgres \
  --restart unless-stopped \
  --network taolie-network \
  -e POSTGRES_DB=taolie_host_agent \
  -e POSTGRES_USER=agent \
  -e POSTGRES_PASSWORD=your_db_password \
  -v taolie_postgres_data:/var/lib/postgresql/data \
  postgres:16
```

### Step 5: Run Host Agent

```bash
docker run -d \
  --name taolie-host-agent \
  --restart unless-stopped \
  --runtime nvidia \
  --privileged \
  --network taolie-network \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/config.yaml:/etc/taolie-host-agent/config.yaml:ro \
  -v taolie_agent_logs:/var/log/taolie-host-agent \
  -p 2222:2222 \
  -p 8888:8888 \
  -p 9999:9999 \
  ghcr.io/banadda/host-agent:latest
```

### Step 6: Verify

```bash
# Check containers
docker ps

# View logs
docker logs -f taolie-host-agent

# Check GPU access
docker exec taolie-host-agent nvidia-smi
```

## Management

```bash
# Stop
docker stop taolie-host-agent taolie-postgres

# Start
docker start taolie-postgres taolie-host-agent

# Update
docker pull ghcr.io/banadda/host-agent:latest
docker stop taolie-host-agent && docker rm taolie-host-agent
# Run Step 4 again

# Logs
docker logs taolie-host-agent -f

# Backup database
docker exec taolie-postgres pg_dump -U agent taolie_host_agent > backup.sql
```

## What It Does

- Monitors GPU health, temperature, and utilization
- Receives deployment commands from TAOLIE platform  
- Pulls Docker images and runs containers with GPU access
- Manages SSH and port mappings for deployed containers
- Reports metrics and status back to platform
- Automatically terminates expired deployments
- Stores deployment history in PostgreSQL database

## Image

Pre-built image: `ghcr.io/banadda/host-agent:latest`  
Auto-built on every push via GitHub Actions
