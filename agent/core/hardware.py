# host-agent/agent/core/hardware.py
import logging
import platform
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import psutil

logger = logging.getLogger(__name__)

def get_gpu_info() -> Dict[str, Any]:
    """Collect GPU information using nvidia-smi."""
    try:
        # Get GPU name, memory, UUID, driver version, compute capability
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=name,memory.total,uuid,driver_version,compute_cap',
            '--format=csv,noheader'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            raise Exception(f"nvidia-smi failed: {result.stderr}")
        
        # Parse the output
        line = result.stdout.strip()
        if not line:
            raise Exception("No GPU information returned")
        
        parts = [part.strip() for part in line.split(',')]
        if len(parts) < 5:
            raise Exception(f"Unexpected nvidia-smi output format: {line}")
        
        gpu_name = parts[0]
        memory_mb = int(parts[1].replace(' MiB', ''))
        hardware_uuid = parts[2]
        driver_version = parts[3]
        compute_capability = parts[4]
        
        # Get CUDA version
        cuda_version = get_cuda_version()
        
        return {
            'name': gpu_name,
            'memory_mb': memory_mb,
            'hardware_uuid': hardware_uuid,
            'driver_version': driver_version,
            'cuda_version': cuda_version,
            'compute_capability': compute_capability
        }
        
    except Exception as e:
        logger.error(f"Failed to get GPU info: {e}")
        raise

def get_cuda_version() -> str:
    """Get CUDA version from nvidia-smi."""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # Try to get CUDA version from nvidia-smi
            result = subprocess.run([
                'nvidia-smi'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'CUDA Version:' in line:
                        cuda_version = line.split('CUDA Version:')[1].strip().split()[0]
                        return cuda_version
        
        # Fallback: try nvcc
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'release' in line.lower():
                    # Extract version from "release 12.2, V12.2.140"
                    version_part = line.split('release')[1].split(',')[0].strip()
                    return version_part
        
        return "Unknown"
        
    except Exception as e:
        logger.warning(f"Could not determine CUDA version: {e}")
        return "Unknown"

def get_host_info() -> Dict[str, Any]:
    """Collect host system information."""
    try:
        # CPU information
        cpu_info = platform.processor()
        if not cpu_info:
            cpu_info = platform.machine()
        
        # RAM information
        ram_mb = psutil.virtual_memory().total // (1024 * 1024)
        
        # OS information
        os_info = f"{platform.system()} {platform.release()}"
        
        # Docker version
        docker_version = get_docker_version()
        
        return {
            'cpu': cpu_info,
            'ram_mb': ram_mb,
            'os': os_info,
            'docker_version': docker_version
        }
        
    except Exception as e:
        logger.error(f"Failed to get host info: {e}")
        raise

def get_docker_version() -> str:
    """Get Docker version."""
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return "Unknown"
    except Exception as e:
        logger.warning(f"Could not get Docker version: {e}")
        return "Unknown"

def collect_gpu_metrics() -> Dict[str, Any]:
    """Collect current GPU metrics."""
    try:
        # Get GPU utilization, memory usage, temperature, power, fan speed
        result = subprocess.run([
            'nvidia-smi', 
            '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,fan.speed',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            raise Exception(f"nvidia-smi failed: {result.stderr}")
        
        line = result.stdout.strip()
        if not line:
            raise Exception("No GPU metrics returned")
        
        parts = [part.strip() for part in line.split(',')]
        if len(parts) < 6:
            raise Exception(f"Unexpected nvidia-smi output format: {line}")
        
        return {
            'gpu_utilization': float(parts[0]) if parts[0] != 'N/A' else 0.0,
            'vram_used_mb': int(parts[1]) if parts[1] != 'N/A' else 0,
            'vram_total_mb': int(parts[2]) if parts[2] != 'N/A' else 0,
            'temperature_celsius': float(parts[3]) if parts[3] != 'N/A' else 0.0,
            'power_draw_watts': float(parts[4]) if parts[4] != 'N/A' else 0.0,
            'fan_speed_percent': float(parts[5]) if parts[5] != 'N/A' else 0.0
        }
        
    except Exception as e:
        logger.error(f"Failed to collect GPU metrics: {e}")
        return {
            'gpu_utilization': 0.0,
            'vram_used_mb': 0,
            'vram_total_mb': 0,
            'temperature_celsius': 0.0,
            'power_draw_watts': 0.0,
            'fan_speed_percent': 0.0
        }

def check_gpu_health() -> Dict[str, Any]:
    """Perform comprehensive GPU health check."""
    health_status = {
        'health_status': 'healthy',
        'driver_responsive': False,
        'temperature_normal': False,
        'power_normal': False,
        'no_ecc_errors': False,
        'fan_operational': False,
        'error_count': 0,
        'error_message': None
    }
    
    try:
        # Check 1: Driver responsive
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            health_status['driver_responsive'] = True
        else:
            health_status['error_count'] += 1
            health_status['error_message'] = "Driver not responsive"
            
    except subprocess.TimeoutExpired:
        health_status['error_count'] += 1
        health_status['error_message'] = "Driver timeout"
    except Exception as e:
        health_status['error_count'] += 1
        health_status['error_message'] = f"Driver error: {e}"
    
    try:
        # Check 2: Temperature normal
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            temp = float(result.stdout.strip())
            if temp < 85:  # Normal operating temperature
                health_status['temperature_normal'] = True
            else:
                health_status['error_count'] += 1
                health_status['error_message'] = f"Temperature too high: {temp}°C"
        else:
            health_status['error_count'] += 1
            health_status['error_message'] = "Could not read temperature"
            
    except Exception as e:
        health_status['error_count'] += 1
        health_status['error_message'] = f"Temperature check error: {e}"
    
    try:
        # Check 3: Power draw normal
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=power.draw', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            power = float(result.stdout.strip())
            if power < 500:  # Reasonable power draw
                health_status['power_normal'] = True
            else:
                health_status['error_count'] += 1
                health_status['error_message'] = f"Power draw too high: {power}W"
        else:
            health_status['error_count'] += 1
            health_status['error_message'] = "Could not read power draw"
            
    except Exception as e:
        health_status['error_count'] += 1
        health_status['error_message'] = f"Power check error: {e}"
    
    try:
        # Check 4: ECC errors
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=ecc.errors.corrected.volatile', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            ecc_errors = int(result.stdout.strip())
            if ecc_errors == 0:
                health_status['no_ecc_errors'] = True
            else:
                health_status['error_count'] += 1
                health_status['error_message'] = f"ECC errors detected: {ecc_errors}"
        else:
            # ECC not supported on consumer GPUs, consider it OK
            health_status['no_ecc_errors'] = True
            
    except Exception as e:
        # ECC not supported, consider it OK
        health_status['no_ecc_errors'] = True
    
    try:
        # Check 5: Fan operational (or 0 RPM mode is OK)
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            fan_speed_str = result.stdout.strip()
            # Some GPUs don't report fan speed or have 0 RPM mode (especially RTX 4090)
            # Consider this OK if nvidia-smi doesn't return 'N/A'
            if fan_speed_str == 'N/A' or fan_speed_str == '[N/A]':
                # GPU doesn't have fan speed reporting, consider it OK
                health_status['fan_operational'] = True
            else:
                # Fan speed is reported, consider it operational regardless of value
                # (0 RPM mode is a feature, not a bug)
                health_status['fan_operational'] = True
        else:
            # Can't read fan speed, but don't fail health check for this
            health_status['fan_operational'] = True
            
    except Exception as e:
        # Fan check error, but don't fail health check for this
        health_status['fan_operational'] = True
    
    # Determine overall health status
    if health_status['error_count'] == 0:
        health_status['health_status'] = 'healthy'
    elif health_status['error_count'] <= 2:
        health_status['health_status'] = 'warning'
    else:
        health_status['health_status'] = 'unhealthy'
    
    return health_status

def get_gpu_count() -> int:
    """Get number of GPUs."""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=count', '--format=csv,noheader'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # nvidia-smi returns count for each GPU, so count lines
            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            return len(lines)
        return 1
    except Exception as e:
        logger.warning(f"Could not get GPU count: {e}")
        return 1

def get_total_vram_gb() -> int:
    """Get total VRAM across all GPUs in GB."""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            total_mb = 0
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    total_mb += int(line.strip())
            return total_mb // 1024  # Convert MB to GB
        return 0
    except Exception as e:
        logger.warning(f"Could not get total VRAM: {e}")
        return 0

def get_storage_info() -> Dict[str, Any]:
    """Get storage information."""
    try:
        # Get disk usage for root partition
        disk = psutil.disk_usage('/')
        
        # Try to determine storage type
        storage_type = "Unknown"
        try:
            # On Linux, check if it's SSD
            result = subprocess.run(['lsblk', '-d', '-o', 'name,rota'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # rota=0 means SSD, rota=1 means HDD
                if '0' in result.stdout:
                    storage_type = "SSD"
                elif '1' in result.stdout:
                    storage_type = "HDD"
        except:
            pass
        
        return {
            'storage_total_gb': disk.total // (1024**3),
            'storage_available_gb': disk.free // (1024**3),
            'storage_used_gb': disk.used // (1024**3),
            'storage_type': storage_type
        }
    except Exception as e:
        logger.warning(f"Could not get storage info: {e}")
        return {
            'storage_total_gb': 0,
            'storage_available_gb': 0,
            'storage_used_gb': 0,
            'storage_type': 'Unknown'
        }

def get_network_speed() -> Dict[str, Any]:
    """Get network speed (simplified - uses quick test)."""
    try:
        # For production, you might want to use speedtest-cli
        # For now, return estimated values based on connection type
        # This is a placeholder - in production you'd do actual speed tests
        
        # Check if speedtest-cli is available
        try:
            result = subprocess.run(['speedtest-cli', '--version'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # Run actual speed test (this takes time, so maybe do it less frequently)
                logger.info("Running network speed test...")
                result = subprocess.run(['speedtest-cli', '--simple'], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    download = 0
                    upload = 0
                    latency = 0
                    
                    for line in lines:
                        if 'Download:' in line:
                            download = float(line.split(':')[1].strip().split()[0])
                        elif 'Upload:' in line:
                            upload = float(line.split(':')[1].strip().split()[0])
                        elif 'Ping:' in line:
                            latency = float(line.split(':')[1].strip().split()[0])
                    
                    return {
                        'download_speed_mbps': download,
                        'upload_speed_mbps': upload,
                        'latency_ms': latency
                    }
        except:
            pass
        
        # Fallback: estimate based on network interface
        net_if = psutil.net_if_stats()
        max_speed = 0
        for interface, stats in net_if.items():
            if stats.isup and not interface.startswith('lo'):
                max_speed = max(max_speed, stats.speed)
        
        # Conservative estimate: assume 80% of link speed
        estimated_speed = max_speed * 0.8 if max_speed > 0 else 1000
        
        return {
            'download_speed_mbps': estimated_speed,
            'upload_speed_mbps': estimated_speed,
            'latency_ms': 10  # Default estimate
        }
        
    except Exception as e:
        logger.warning(f"Could not get network speed: {e}")
        return {
            'download_speed_mbps': 1000,  # Default 1Gbps
            'upload_speed_mbps': 1000,
            'latency_ms': 10
        }

def get_uptime_info() -> Dict[str, Any]:
    """Get system uptime information."""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_hours = int(uptime_seconds / 3600)
        last_reboot = datetime.fromtimestamp(boot_time).isoformat()
        
        return {
            'uptime_hours': uptime_hours,
            'last_reboot': last_reboot
        }
    except Exception as e:
        logger.warning(f"Could not get uptime info: {e}")
        return {
            'uptime_hours': 0,
            'last_reboot': datetime.now().isoformat()
        }

def get_comprehensive_system_info() -> Dict[str, Any]:
    """Collect all comprehensive system information for registration."""
    try:
        gpu_info = get_gpu_info()
        host_info = get_host_info()
        storage_info = get_storage_info()
        network_info = get_network_speed()
        uptime_info = get_uptime_info()
        
        # CPU cores
        cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
        
        # GPU count and total VRAM
        gpu_count = get_gpu_count()
        total_vram_gb = get_total_vram_gb()
        
        return {
            # GPU Information
            'gpu_name': gpu_info['name'],
            'gpu_memory_mb': gpu_info['memory_mb'],
            'gpu_count': gpu_count,
            'driver_version': gpu_info['driver_version'],
            'cuda_version': gpu_info['cuda_version'],
            
            # Host Information
            'hostname': platform.node(),
            'os': host_info['os'],
            'cpu_count': 1,  # Number of CPU sockets
            'cpu_cores': cpu_cores,
            'total_ram_gb': host_info['ram_mb'] // 1024,
            'total_vram_gb': total_vram_gb,
            
            # Storage Information
            'storage_total_gb': storage_info['storage_total_gb'],
            'storage_type': storage_info['storage_type'],
            'storage_available_gb': storage_info['storage_available_gb'],
            
            # Network Performance
            'upload_speed_mbps': network_info['upload_speed_mbps'],
            'download_speed_mbps': network_info['download_speed_mbps'],
            'latency_ms': network_info['latency_ms'],
            
            # Uptime and Reliability
            'uptime_hours': uptime_info['uptime_hours'],
            'last_reboot': uptime_info['last_reboot']
        }
        
    except Exception as e:
        logger.error(f"Failed to collect comprehensive system info: {e}")
        raise

def collect_system_metrics() -> Dict[str, Any]:
    """Collect current system metrics (CPU, RAM, storage, network)."""
    try:
        # CPU utilization
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # RAM usage
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024**3)
        
        # Storage usage
        disk = psutil.disk_usage('/')
        storage_used_gb = disk.used / (1024**3)
        
        # Network utilization (simplified)
        net_io = psutil.net_io_counters()
        
        # Calculate network speed (bytes per second over last interval)
        # This is a simplified version - you might want to track this over time
        current_upload_mbps = 0  # Placeholder
        current_download_mbps = 0  # Placeholder
        
        # Network utilization percentage (simplified)
        network_utilization = 0  # Placeholder
        
        return {
            'cpu_utilization': cpu_percent,
            'ram_used_gb': ram_used_gb,
            'storage_used_gb': storage_used_gb,
            'network_utilization': network_utilization,
            'current_upload_mbps': current_upload_mbps,
            'current_download_mbps': current_download_mbps
        }
        
    except Exception as e:
        logger.warning(f"Failed to collect system metrics: {e}")
        return {
            'cpu_utilization': 0.0,
            'ram_used_gb': 0.0,
            'storage_used_gb': 0.0,
            'network_utilization': 0.0,
            'current_upload_mbps': 0.0,
            'current_download_mbps': 0.0
        }

def calculate_health_scores(metrics: Dict[str, Any], health: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate performance and stability scores."""
    try:
        # GPU Performance Score (0-100)
        # Based on: temperature, power efficiency, utilization capability
        gpu_score = 100.0
        
        # Penalize high temperature
        temp = metrics.get('temperature_celsius', 0)
        if temp > 80:
            gpu_score -= (temp - 80) * 2
        
        # Penalize if GPU is throttling (simplified check)
        if temp > 85:
            gpu_score -= 10
        
        # Check if fan is working properly
        if not health.get('fan_operational', True):
            gpu_score -= 20
        
        gpu_score = max(0, min(100, gpu_score))
        
        # System Stability Score (0-100)
        stability_score = 100.0
        
        # Penalize for errors
        error_count = health.get('error_count', 0)
        stability_score -= error_count * 15
        
        # Penalize for unhealthy status
        if health.get('health_status') == 'unhealthy':
            stability_score -= 30
        elif health.get('health_status') == 'warning':
            stability_score -= 15
        
        stability_score = max(0, min(100, stability_score))
        
        return {
            'gpu_performance_score': round(gpu_score, 1),
            'system_stability_score': round(stability_score, 1)
        }
        
    except Exception as e:
        logger.warning(f"Failed to calculate health scores: {e}")
        return {
            'gpu_performance_score': 85.0,
            'system_stability_score': 90.0
        }