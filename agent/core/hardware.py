# host-agent/agent/core/hardware.py
import logging
import platform
import subprocess
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
        # Check 5: Fan operational
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            fan_speed = float(result.stdout.strip())
            if fan_speed > 0:
                health_status['fan_operational'] = True
            else:
                health_status['error_count'] += 1
                health_status['error_message'] = "Fan not operational"
        else:
            health_status['error_count'] += 1
            health_status['error_message'] = "Could not read fan speed"
            
    except Exception as e:
        health_status['error_count'] += 1
        health_status['error_message'] = f"Fan check error: {e}"
    
    # Determine overall health status
    if health_status['error_count'] == 0:
        health_status['health_status'] = 'healthy'
    elif health_status['error_count'] <= 2:
        health_status['health_status'] = 'warning'
    else:
        health_status['health_status'] = 'unhealthy'
    
    return health_status