# Comprehensive Metrics Update - Host Agent

## Summary
Updated the host agent to collect and send comprehensive system information, metrics, and health data to match the updated server endpoints.

## Changes Made

### 1. `agent/core/hardware.py` - New Data Collection Functions

#### Added Functions:
- **`get_gpu_count()`** - Count number of GPUs in the system
- **`get_total_vram_gb()`** - Calculate total VRAM across all GPUs  
- **`get_storage_info()`** - Get storage capacity, usage, and type (SSD/HDD)
- **`get_network_speed()`** - Measure network upload/download speeds and latency
- **`get_uptime_info()`** - Get system uptime and last reboot time
- **`get_comprehensive_system_info()`** - Collect all system info for registration
- **`collect_system_metrics()`** - Collect real-time system metrics (CPU, RAM, storage, network)
- **`calculate_health_scores()`** - Calculate GPU performance and system stability scores

### 2. `agent/main.py` - Updated Registration

#### Changes:
- Updated imports to include new hardware collection functions
- **Modified `register_gpu()` method** to send comprehensive registration data:
  - GPU Information: name, memory, count, driver version, CUDA version
  - Host Information: hostname, OS, CPU count/cores, RAM, total VRAM
  - Storage Information: total, available, type
  - Network Performance: upload/download speeds, latency
  - Uptime and Reliability: uptime hours, last reboot timestamp
  - Network Configuration: IP, ports

### 3. `agent/core/monitoring.py` - Enhanced Monitoring

#### Updated Functions:

**`start_metrics_push()`** - Now sends comprehensive metrics:
- GPU Performance: utilization, VRAM, temperature, power, fan speed
- System Metrics: CPU utilization, RAM used, storage used
- Network Metrics: network utilization, current upload/download speeds
- Uptime: system uptime hours
- Timestamp

**`start_health_push()`** - Now sends comprehensive health data:
- Basic Status: is_healthy, status
- Health Details: temperature_ok, power_ok, network_ok, storage_ok
- Performance Indicators: gpu_performance_score, system_stability_score
- Timestamps

**`process_command()`** - Fixed command parsing:
- Changed from `'type'` to `'command_type'`
- Changed from `'data'` to `'payload'`
- Changed from `'id'` to `'command_id'`
- Changed from `'DEPLOY'` to `'deploy'` (lowercase)
- Added debug logging for raw commands

## API Endpoints Updated

### 1. Registration Endpoint
**POST `/api/host-agents/register`**

Payload now includes:
```json
{
  "host_agent_id": "agent-xxx",
  "gpu_name": "NVIDIA RTX 4090",
  "gpu_memory_mb": 24576,
  "gpu_count": 2,
  "driver_version": "535.86.10",
  "cuda_version": "12.2",
  "hostname": "gpu-server-01",
  "os": "Ubuntu 22.04",
  "cpu_count": 1,
  "cpu_cores": 16,
  "total_ram_gb": 64,
  "total_vram_gb": 49,
  "storage_total_gb": 2000,
  "storage_type": "SSD",
  "storage_available_gb": 1500,
  "upload_speed_mbps": 1000,
  "download_speed_mbps": 1000,
  "latency_ms": 5,
  "uptime_hours": 720,
  "last_reboot": "2025-09-17T10:30:00Z",
  "public_ip": "192.168.1.100",
  "ssh_port": 22,
  "rental_port_1": 8001,
  "rental_port_2": 8002
}
```

### 2. Metrics Endpoint  
**POST `/api/host-agents/metrics`**

Payload now includes:
```json
{
  "agent_id": "agent_001",
  "gpu_uuid": "gpu_abc123",
  "gpu_utilization": 50.5,
  "vram_used_mb": 1024,
  "temperature_celsius": 65.0,
  "power_draw_watts": 250.0,
  "fan_speed_percent": 45.0,
  "cpu_utilization": 25.0,
  "ram_used_gb": 32.5,
  "storage_used_gb": 500.0,
  "network_utilization": 15.0,
  "current_upload_mbps": 50.0,
  "current_download_mbps": 100.0,
  "uptime_hours": 720,
  "timestamp": "2025-10-17T19:30:00Z"
}
```

### 3. Health Endpoint
**POST `/api/host-agents/health`**

Payload now includes:
```json
{
  "agent_id": "agent_001",
  "gpu_uuid": "gpu_abc123",
  "is_healthy": true,
  "status": "available",
  "temperature_ok": true,
  "power_ok": true,
  "network_ok": true,
  "storage_ok": true,
  "gpu_performance_score": 85.5,
  "system_stability_score": 92.0,
  "last_health_check": "2025-10-17T19:30:00Z",
  "timestamp": "2025-10-17T19:30:00Z"
}
```

## Deployment Instructions

### Option 1: Build and Deploy Locally (Recommended for Testing)

```bash
cd ~/taolie-host-agent

# Stop existing containers
docker stop taolie-host-agent taolie-postgres
docker rm taolie-host-agent taolie-postgres

# Build new image with updates
docker build -t taolie-host-agent:local .

# Create network
docker network create taolie-network 2>/dev/null || true

# Start PostgreSQL
docker run -d \
  --name taolie-postgres \
  --restart unless-stopped \
  --network taolie-network \
  -e POSTGRES_DB=taolie_host_agent \
  -e POSTGRES_USER=agent \
  -e POSTGRES_PASSWORD=agent123 \
  -v taolie_postgres_data:/var/lib/postgresql/data \
  postgres:16

# Wait for PostgreSQL
sleep 5
until docker exec taolie-postgres pg_isready -U agent -d taolie_host_agent 2>/dev/null; do
  sleep 2
done

# Start host agent
docker run -d \
  --name taolie-host-agent \
  --restart unless-stopped \
  --runtime nvidia \
  --privileged \
  --network taolie-network \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/config.yaml:/etc/taolie-host-agent/config.yaml \
  -v taolie_agent_logs:/var/log/taolie-host-agent \
  -p 2222:2222 \
  -p 8888:8888 \
  -p 9999:9999 \
  taolie-host-agent:local

# Check logs
docker logs -f taolie-host-agent
```

### Option 2: Push to GitHub and Deploy from Registry

```bash
# Commit changes
git add agent/core/hardware.py agent/core/monitoring.py agent/main.py
git commit -m "Add comprehensive metrics collection and reporting"
git push

# Wait for GitHub Actions to build and push to ghcr.io

# On server: Pull and deploy
docker pull ghcr.io/banadda/host-agent:latest
# Then use same docker run commands as above but with ghcr.io/banadda/host-agent:latest
```

## Testing the Updates

After deployment, verify the logs show:
- ✅ "Comprehensive metrics pushed to server"
- ✅ "Comprehensive health status pushed to server"  
- ✅ Command parsing shows actual command types (not "None - None")

Check the server receives:
- Complete registration data with all system specs
- Real-time metrics including CPU, RAM, storage, network
- Health scores and detailed health status

## Performance Impact

- **Network speed test**: Only runs once at startup (or can be disabled)
- **System metrics collection**: Adds ~1 second per collection cycle (acceptable for 10s interval)
- **Health score calculation**: Negligible performance impact

## Notes

- Network speed testing uses `speedtest-cli` if available, otherwise estimates from interface speed
- Storage type detection works on Linux systems with `lsblk` command
- All new functions have fallback values to prevent failures
- Existing functionality is preserved - only additions and enhancements made

## Files Modified

1. `agent/core/hardware.py` - Added ~290 lines of new collection functions
2. `agent/core/monitoring.py` - Enhanced metrics and health push functions, fixed command parsing
3. `agent/main.py` - Updated registration to use comprehensive system info

