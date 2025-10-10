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

# Create .env file (required by current image)
cat > .env << 'EOF'
API_SERVER_URL=https://api.taolie.com
AGENT_PORT=8000
REPORT_INTERVAL_SECONDS=30
EOF

# Edit .env with your server URL
nano .env
```

### Step 3: Run PostgreSQL

```bash
docker run -d \
  --name taolie-postgres \
  --restart unless-stopped \
  -e POSTGRES_DB=taolie_host_agent \
  -e POSTGRES_USER=agent \
  -e POSTGRES_PASSWORD=your_db_password \
  -v taolie_postgres_data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16
```

### Step 4: Run Host Agent

```bash
docker run -d \
  --name taolie-host-agent \
  --restart unless-stopped \
  --runtime nvidia \
  --privileged \
  --env-file .env \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v taolie_agent_logs:/var/log/taolie-host-agent \
  -p 8000:8000 \
  ghcr.io/banadda/host-agent:latest
```

### Step 5: Verify

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
