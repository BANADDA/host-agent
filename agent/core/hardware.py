import asyncio
import json
import logging
import os
import platform
import socket
import subprocess
import time
from datetime import datetime

import docker
import psutil
import requests

from ..api.schemas import InstanceInfo
from .config import settings

logger = logging.getLogger(__name__)
client = docker.from_env()

async def get_gpu_info():
    """Use nvidia-smi to get detailed GPU information."""
    try:
        command = ["nvidia-smi", "--query-gpu=uuid,name,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu,fan.speed", "--format=csv,noheader,nounits"]
        output = subprocess.check_output(command, encoding='utf-8').strip()
        gpus = []
        for line in output.split('\n'):
            parts = line.split(',')
            if len(parts) >= 9:
                uuid, name, total_memory, used_memory, temp, power_usage, power_limit, utilization, fan_speed = parts
                gpus.append({
                    "uuid": uuid.strip(),
                    "name": name.strip(),
                    "memory_total_mb": int(total_memory.strip()),
                    "memory_used_mb": int(used_memory.strip()),
                    "temperature_c": int(temp.strip()) if temp.strip() != 'N/A' else None,
                    "power_usage_w": float(power_usage.strip()) if power_usage.strip() != 'N/A' else None,
                    "power_limit_w": float(power_limit.strip()) if power_limit.strip() != 'N/A' else None,
                    "utilization_percent": int(utilization.strip()) if utilization.strip() != 'N/A' else None,
                    "fan_speed_percent": int(fan_speed.strip()) if fan_speed.strip() != 'N/A' else None
                })
        return gpus
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Failed to get GPU info: {e}")
        return []

def get_system_info():
    """Get comprehensive system information."""
    try:
        # System info
        hostname = socket.gethostname()
        os_info = platform.platform()
        kernel = platform.release()
        uptime_seconds = time.time() - psutil.boot_time()
        
        # CPU info
        cpu_info = {
            "model": platform.processor(),
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "usage_percent": psutil.cpu_percent(interval=1)
        }
        
        # Memory info
        memory = psutil.virtual_memory()
        memory_info = {
            "total_mb": int(memory.total / 1024 / 1024),
            "used_mb": int(memory.used / 1024 / 1024),
            "available_mb": int(memory.available / 1024 / 1024)
        }
        
        # Disk info
        disk = psutil.disk_usage('/')
        disk_info = {
            "total_gb": int(disk.total / 1024 / 1024 / 1024),
            "used_gb": int(disk.used / 1024 / 1024 / 1024),
            "available_gb": int(disk.free / 1024 / 1024 / 1024)
        }
        
        return {
            "hostname": hostname,
            "os": os_info,
            "kernel": kernel,
            "uptime_seconds": int(uptime_seconds),
            "cpu": cpu_info,
            "memory": memory_info,
            "disk": disk_info
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return {}

def get_health_info():
    """Get hardware health information."""
    try:
        # System temperature (if available)
        system_temp = None
        try:
            # Try to get system temperature from thermal zones
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_millicelsius = int(f.read().strip())
                system_temp = temp_millicelsius / 1000
        except:
            pass
        
        # Last reboot time
        last_reboot = datetime.fromtimestamp(psutil.boot_time()).isoformat() + 'Z'
        
        return {
            "system_temperature_c": system_temp,
            "last_reboot": last_reboot
        }
    except Exception as e:
        logger.error(f"Failed to get health info: {e}")
        return {}

def get_network_info():
    """Get network and connectivity information."""
    try:
        # Public IP (simplified - in production you'd want a more robust method)
        public_ip = None
        try:
            response = requests.get('https://api.ipify.org', timeout=5)
            public_ip = response.text.strip()
        except:
            pass
        
        # Network speed test (simplified)
        bandwidth_mbps = None
        latency_ms = None
        try:
            # Simple latency test
            start = time.time()
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            latency_ms = (time.time() - start) * 1000
        except:
            pass
        
        # Internet connectivity
        internet_connected = False
        docker_registry_accessible = False
        try:
            response = requests.get('https://registry-1.docker.io', timeout=5)
            docker_registry_accessible = response.status_code == 200
            internet_connected = True
        except:
            pass
        
        return {
            "public_ip": public_ip,
            "bandwidth_mbps": bandwidth_mbps,
            "latency_ms": latency_ms,
            "internet_connected": internet_connected,
            "docker_registry_accessible": docker_registry_accessible
        }
    except Exception as e:
        logger.error(f"Failed to get network info: {e}")
        return {}

def get_docker_info():
    """Get Docker environment information."""
    try:
        # Docker version
        docker_version = None
        try:
            result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
            docker_version = result.stdout.strip()
        except:
            pass
        
        # Container info
        containers = client.containers.list()
        containers_running = len([c for c in containers if c.status == 'running'])
        containers_total = len(containers)
        
        # Images count
        images = client.images.list()
        images_count = len(images)
        
        # Docker disk usage
        disk_usage = None
        try:
            result = subprocess.run(['docker', 'system', 'df', '--format', 'json'], capture_output=True, text=True)
            if result.returncode == 0:
                df_data = json.loads(result.stdout)
                for item in df_data:
                    if item['Type'] == 'Images':
                        disk_usage = item['Size']
        except:
            pass
        
        # NVIDIA runtime availability
        nvidia_runtime_available = False
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            nvidia_runtime_available = 'nvidia' in result.stdout.lower()
        except:
            pass
        
        return {
            "version": docker_version,
            "containers_running": containers_running,
            "containers_total": containers_total,
            "images_count": images_count,
            "disk_usage_gb": disk_usage,
            "nvidia_runtime_available": nvidia_runtime_available
        }
    except Exception as e:
        logger.error(f"Failed to get Docker info: {e}")
        return {}

def get_location_info():
    """Get location and provider information."""
    try:
        # Try to detect cloud provider
        provider = "unknown"
        instance_type = "unknown"
        region = "unknown"
        cost_per_hour_usd = None
        
        # AWS detection
        try:
            response = requests.get('http://169.254.169.254/latest/meta-data/instance-type', timeout=2)
            if response.status_code == 200:
                provider = "AWS"
                instance_type = response.text.strip()
                # Get region
                region_response = requests.get('http://169.254.169.254/latest/meta-data/placement/region', timeout=2)
                if region_response.status_code == 200:
                    region = region_response.text.strip()
        except:
            pass
        
        # GCP detection
        try:
            response = requests.get('http://metadata.google.internal/computeMetadata/v1/instance/machine-type', 
                                  headers={'Metadata-Flavor': 'Google'}, timeout=2)
            if response.status_code == 200:
                provider = "GCP"
                instance_type = response.text.strip().split('/')[-1]
        except:
            pass
        
        # Azure detection
        try:
            response = requests.get('http://169.254.169.254/metadata/instance/compute/vmSize', 
                                  headers={'Metadata': 'true'}, timeout=2)
            if response.status_code == 200:
                provider = "Azure"
                instance_type = response.text.strip()
        except:
            pass
        
        # Cost estimation (simplified)
        if provider == "AWS" and "p3" in instance_type:
            cost_per_hour_usd = 3.06  # Example for p3.2xlarge
        elif provider == "GCP" and "n1" in instance_type:
            cost_per_hour_usd = 1.50  # Example
        
        return {
            "region": region,
            "datacenter": f"{provider.lower()}-cloud",
            "provider": provider,
            "instance_type": instance_type,
            "cost_per_hour_usd": cost_per_hour_usd
        }
    except Exception as e:
        logger.error(f"Failed to get location info: {e}")
        return {}

def get_status_info():
    """Get status and alerts information."""
    try:
        alerts = []
        overall_status = "healthy"
        
        # Check for potential issues
        try:
            # Check disk space
            disk = psutil.disk_usage('/')
            if disk.percent > 90:
                alerts.append("High disk usage")
                overall_status = "warning"
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                alerts.append("High memory usage")
                overall_status = "warning"
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 95:
                alerts.append("High CPU usage")
                overall_status = "warning"
                
        except:
            pass
        
        # Maintenance info (placeholder)
        last_maintenance = "2024-01-10T00:00:00Z"
        next_maintenance = "2024-02-10T00:00:00Z"
        
        return {
            "overall": overall_status,
            "alerts": alerts,
            "last_maintenance": last_maintenance,
            "next_maintenance": next_maintenance
        }
    except Exception as e:
        logger.error(f"Failed to get status info: {e}")
        return {"overall": "unknown", "alerts": [], "last_maintenance": None, "next_maintenance": None}

def get_running_instances() -> list[InstanceInfo]:
    """Get a list of containers managed by this agent."""
    try:
        containers = client.containers.list(filters={"name": "rental-instance"})
        return [InstanceInfo(id=c.id, name=c.name) for c in containers]
    except Exception as e:
        logger.error(f"Failed to get running containers: {e}")
        return []

async def report_resources(agent_instance_id: str):
    """Continuously report comprehensive resources to the central API server."""
    while True:
        try:
            # Gather all monitoring data
            gpus = await get_gpu_info()
            instances = get_running_instances()
            system = get_system_info()
            health = get_health_info()
            network = get_network_info()
            docker_info = get_docker_info()
            location = get_location_info()
            status = get_status_info()
            
            # Build comprehensive payload
            payload = {
                "agent_id": agent_instance_id,
                "timestamp": datetime.now().isoformat() + 'Z',
                "gpus": gpus,
                "instances": instances,
                "system": system,
                "health": health,
                "network": network,
                "docker": docker_info,
                "location": location,
                "status": status
            }
            
            logger.info(f"Reporting comprehensive resources: {json.dumps(payload, indent=2)}")
            response = requests.post(f"{settings.api_server_url}/api/hosts/report", json=payload)
            response.raise_for_status()
            logger.info("Successfully reported comprehensive resources.")
        except Exception as e:
            logger.error(f"Failed to report resources to API server: {e}")

        await asyncio.sleep(settings.report_interval_seconds)
