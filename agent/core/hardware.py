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
                def safe_int(value):
                    """Safely convert string to int, handling N/A and [N/A] values."""
                    value = value.strip()
                    if value in ['N/A', '[N/A]', '']:
                        return None
                    try:
                        return int(value)
                    except ValueError:
                        return None
                
                def safe_float(value):
                    """Safely convert string to float, handling N/A and [N/A] values."""
                    value = value.strip()
                    if value in ['N/A', '[N/A]', '']:
                        return None
                    try:
                        return float(value)
                    except ValueError:
                        return None
                
                gpus.append({
                    "uuid": uuid.strip(),
                    "name": name.strip(),
                    "memory_total_mb": safe_int(total_memory),
                    "memory_used_mb": safe_int(used_memory),
                    "temperature_c": safe_int(temp),
                    "power_usage_w": safe_float(power_usage),
                    "power_limit_w": safe_float(power_limit),
                    "utilization_percent": safe_int(utilization),
                    "fan_speed_percent": safe_int(fan_speed)
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
        cpu_model = platform.processor()
        if not cpu_model or cpu_model == "":
            # Try to get CPU model from /proc/cpuinfo
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('model name'):
                            cpu_model = line.split(':')[1].strip()
                            break
            except:
                cpu_model = "Unknown CPU"
        
        cpu_info = {
            "model": cpu_model,
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
            # Try psutil sensors first (most reliable)
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            if entry.current and entry.current > 0:
                                system_temp = entry.current
                                break
                        if system_temp:
                            break
        except Exception as e:
            logger.error(f"Failed to get temperature via psutil: {e}")
        
        if system_temp is None:
            try:
                # Try thermal zones
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp_millicelsius = int(f.read().strip())
                    system_temp = temp_millicelsius / 1000
            except Exception as e:
                logger.error(f"Failed to read thermal zone: {e}")
                # Try sensors command if available
                try:
                    result = subprocess.run(['sensors', '-j'], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        sensors_data = json.loads(result.stdout)
                        # Look for CPU temperature
                        for device, data in sensors_data.items():
                            if 'Core 0' in data or 'Package id 0' in data:
                                for key, value in data.items():
                                    if 'temp1_input' in key or 'Core 0' in key:
                                        if isinstance(value, (int, float)) and value > 0:
                                            system_temp = value
                                            break
                                if system_temp:
                                    break
                except Exception as e2:
                    logger.error(f"Failed to get temperature via sensors: {e2}")
        
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
        
        # Try to get bandwidth info from system
        try:
            # Check if speedtest-cli is available
            result = subprocess.run(['which', 'speedtest-cli'], capture_output=True, text=True)
            if result.returncode == 0:
                # Run a quick speed test
                speed_result = subprocess.run(['speedtest-cli', '--simple'], capture_output=True, text=True, timeout=30)
                if speed_result.returncode == 0:
                    lines = speed_result.stdout.strip().split('\n')
                    for line in lines:
                        if 'Download:' in line:
                            # Extract download speed
                            parts = line.split()
                            if len(parts) >= 2:
                                speed_str = parts[1]
                                if 'Mbit/s' in speed_str:
                                    bandwidth_mbps = float(speed_str.replace('Mbit/s', ''))
                                break
        except:
            pass
        
        # Internet connectivity
        internet_connected = False
        docker_registry_accessible = False
        try:
            # Check Docker Hub API (returns 401 but confirms reachability)
            response = requests.get('https://hub.docker.com/v2/', timeout=5)
            docker_registry_accessible = response.status_code < 500  # Allow 401/403
            internet_connected = True
        except Exception as e:
            logger.error(f"Failed to check Docker registry accessibility: {e}")
            # Fallback: just check internet connectivity
            try:
                response = requests.get('https://httpbin.org/get', timeout=5)
                internet_connected = response.status_code == 200
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
        # Docker version using Python SDK
        docker_version = None
        try:
            docker_version = client.version()['Version']
        except Exception as e:
            logger.error(f"Failed to get Docker version: {e}")
            # Fallback to subprocess if SDK fails
            try:
                result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
                if result.returncode == 0:
                    docker_version = result.stdout.strip()
            except Exception as e2:
                logger.error(f"Fallback Docker version check failed: {e2}")
        
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
            # Fallback: try to get disk usage from docker info
            try:
                result = subprocess.run(['docker', 'system', 'df'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'Images' in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                disk_usage = parts[2]  # Size column
                            break
            except:
                pass
        
        # NVIDIA runtime availability
        nvidia_runtime_available = False
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            if result.returncode == 0:
                nvidia_runtime_available = 'nvidia' in result.stdout.lower()
            else:
                logger.error(f"Docker info failed: returncode={result.returncode}, stderr={result.stderr}")
        except Exception as e:
            logger.error(f"Failed to check Docker info for NVIDIA runtime: {e}")
            # Fallback: check if nvidia-smi works
            try:
                result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
                nvidia_runtime_available = result.returncode == 0
                if result.returncode != 0:
                    logger.error(f"nvidia-smi failed: returncode={result.returncode}, stderr={result.stderr}")
            except Exception as e2:
                logger.error(f"nvidia-smi fallback failed: {e2}")
        
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
        # Use ipinfo.io for comprehensive location data
        provider = "unknown"
        instance_type = "unknown"
        region = "unknown"
        cost_per_hour_usd = None
        
        try:
            response = requests.get('https://ipinfo.io/json', timeout=10)
            if response.status_code == 200:
                ipinfo_data = response.json()
                
                # Extract provider from organization
                org = ipinfo_data.get('org', '')
                if 'Hetzner' in org:
                    provider = "Hetzner"
                elif 'Amazon' in org or 'AWS' in org:
                    provider = "AWS"
                elif 'Google' in org or 'GCP' in org:
                    provider = "GCP"
                elif 'Microsoft' in org or 'Azure' in org:
                    provider = "Azure"
                elif 'DigitalOcean' in org:
                    provider = "DigitalOcean"
                elif 'Linode' in org:
                    provider = "Linode"
                elif 'Vultr' in org:
                    provider = "Vultr"
                elif 'OVH' in org:
                    provider = "OVH"
                else:
                    # Try to extract provider from org string
                    org_lower = org.lower()
                    if 'hetzner' in org_lower:
                        provider = "Hetzner"
                    elif 'amazon' in org_lower or 'aws' in org_lower:
                        provider = "AWS"
                    elif 'google' in org_lower:
                        provider = "GCP"
                    elif 'microsoft' in org_lower or 'azure' in org_lower:
                        provider = "Azure"
                    else:
                        provider = "Other"
                
                # Extract region and location info
                region = ipinfo_data.get('region', 'unknown')
                city = ipinfo_data.get('city', '')
                country = ipinfo_data.get('country', '')
                
                # Create a more descriptive region
                if city and country:
                    region = f"{city}, {country}"
                elif region != 'unknown':
                    region = f"{region}, {country}" if country else region
                
                # Get hostname for instance type detection
                hostname = ipinfo_data.get('hostname', '')
                
                # Try to detect instance type from hostname patterns
                if provider == "AWS" and 'ec2' in hostname.lower():
                    instance_type = "EC2"
                elif provider == "GCP" and 'compute' in hostname.lower():
                    instance_type = "Compute Engine"
                elif provider == "Azure" and 'cloudapp' in hostname.lower():
                    instance_type = "Virtual Machine"
                elif provider == "Hetzner":
                    instance_type = "Cloud Server"
                else:
                    instance_type = "Virtual Machine"
                
                # Estimate cost based on provider and region
                if provider == "Hetzner":
                    cost_per_hour_usd = 0.05  # Approximate for small instances
                elif provider == "AWS":
                    if "us-" in region.lower():
                        cost_per_hour_usd = 0.10
                    else:
                        cost_per_hour_usd = 0.12
                elif provider == "GCP":
                    cost_per_hour_usd = 0.08
                elif provider == "Azure":
                    cost_per_hour_usd = 0.09
                else:
                    cost_per_hour_usd = 0.07  # Generic estimate
                    
        except Exception as e:
            logger.error(f"Failed to get location info from ipinfo.io: {e}")
            
            # Fallback to basic detection
            hostname = socket.gethostname()
            if 'aws' in hostname.lower() or 'ec2' in hostname.lower():
                provider = "AWS"
            elif 'gcp' in hostname.lower() or 'google' in hostname.lower():
                provider = "GCP"
            elif 'azure' in hostname.lower() or 'microsoft' in hostname.lower():
                provider = "Azure"
            elif 'hetzner' in hostname.lower() or 'hcloud' in hostname.lower():
                provider = "Hetzner"
        
        # Additional cloud metadata detection (fallback for specific clouds)
        if provider in ["AWS", "GCP", "Azure"]:
            try:
                if provider == "AWS":
                    response = requests.get('http://169.254.169.254/latest/meta-data/instance-type', timeout=2)
                    if response.status_code == 200:
                        instance_type = response.text.strip()
                elif provider == "GCP":
                    response = requests.get('http://metadata.google.internal/computeMetadata/v1/instance/machine-type', 
                                          headers={'Metadata-Flavor': 'Google'}, timeout=2)
                    if response.status_code == 200:
                        instance_type = response.text.strip().split('/')[-1]
                elif provider == "Azure":
                    response = requests.get('http://169.254.169.254/metadata/instance/compute/vmSize', 
                                          headers={'Metadata': 'true'}, timeout=2)
                    if response.status_code == 200:
                        instance_type = response.text.strip()
            except Exception as e:
                logger.error(f"Failed to get cloud metadata: {e}")
        
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
            logger.info(f"Reporting comprehensive resources: {json.dumps(payload, indent=2)}")
            response = requests.post(f"{settings.api_server_url}/api/hosts/report", json=payload)
            response.raise_for_status()
            logger.info("Successfully reported comprehensive resources.")
        except Exception as e:
            logger.error(f"Failed to report resources to API server: {e}")

        await asyncio.sleep(settings.report_interval_seconds)
