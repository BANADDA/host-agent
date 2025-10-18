# host-agent/agent/core/monitoring.py
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

import requests

from .database import (get_expired_deployments, get_gpu_status,
                       store_gpu_metrics, store_health_check,
                       update_deployment_status, update_gpu_status)
from .deployment import terminate_deployment
from .hardware import (calculate_health_scores, check_gpu_health,
                       collect_gpu_metrics, collect_system_metrics,
                       get_uptime_info)

logger = logging.getLogger(__name__)

async def start_gpu_monitoring(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 1: GPU Monitoring - Collect GPU metrics every interval seconds."""
    logger.info("GPU monitoring thread started")
    
    while True:
        try:
            # Collect GPU metrics
            metrics = collect_gpu_metrics()
            
            # Get current deployment ID if any
            gpu_status = await get_gpu_status()
            deployment_id = gpu_status.get('current_deployment_id') if gpu_status else None
            
            # Store metrics in database
            await store_gpu_metrics('gpu-0', metrics, deployment_id)
            
            # Update GPU status with current metrics
            await update_gpu_status('gpu-0', 
                gpu_utilization=metrics['gpu_utilization'],
                vram_used_mb=metrics['vram_used_mb'],
                temperature_celsius=metrics['temperature_celsius'],
                power_draw_watts=metrics['power_draw_watts'],
                fan_speed_percent=metrics['fan_speed_percent']
            )
            
            logger.debug(f"GPU metrics collected: {metrics['gpu_utilization']:.1f}% utilization")
            
        except Exception as e:
            logger.error(f"Error in GPU monitoring: {e}")
        
        await asyncio.sleep(interval)

async def start_health_monitoring(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 2: GPU Health Check - Check GPU health every interval seconds."""
    logger.info("GPU health monitoring thread started")
    
    while True:
        try:
            # Perform health check
            health_data = check_gpu_health()
            
            # Store health check results
            await store_health_check('gpu-0', health_data)
            
            # Update GPU health status
            await update_gpu_status('gpu-0',
                is_healthy=(health_data['health_status'] == 'healthy'),
                last_health_check=datetime.now(),
                consecutive_failures=0 if health_data['health_status'] == 'healthy' else 1
            )
            
            if health_data['health_status'] != 'healthy':
                logger.warning(f"GPU health check failed: {health_data['error_message']}")
            
        except Exception as e:
            logger.error(f"Error in health monitoring: {e}")
        
        await asyncio.sleep(interval)

async def start_heartbeat(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 3: Heartbeat - Send heartbeat to central server every interval seconds."""
    logger.info("Heartbeat thread started")
    
    while True:
        try:
            # Send heartbeat to server
            await send_heartbeat(config, agent_id)
            logger.debug("Heartbeat sent to server")
            
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
        
        await asyncio.sleep(interval)

async def start_command_polling(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 4: Command Polling - Poll for commands from central server every interval seconds."""
    logger.info("Command polling thread started")
    
    while True:
        try:
            # Poll for commands
            commands = await poll_commands(config, agent_id)
            
            if commands:
                logger.info(f"Received {len(commands)} commands")
                
                # Process each command
                for command in commands:
                    await process_command(config, agent_id, command)
            
        except Exception as e:
            logger.error(f"Error in command polling: {e}")
        
        await asyncio.sleep(interval)

async def start_metrics_push(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 5: Metrics Push - Push GPU metrics to central server every interval seconds."""
    logger.info("Metrics push thread started")
    
    while True:
        try:
            # Collect GPU and system metrics
            gpu_metrics = collect_gpu_metrics()
            system_metrics = collect_system_metrics()
            uptime_info = get_uptime_info()
            gpu_status = await get_gpu_status()
            
            # Prepare comprehensive metrics payload
            payload = {
                'agent_id': agent_id,
                'gpu_uuid': gpu_status.get('gpu_uuid') if gpu_status else None,
                
                # GPU Performance Metrics
                'gpu_utilization': gpu_metrics['gpu_utilization'],
                'vram_used_mb': gpu_metrics['vram_used_mb'],
                'temperature_celsius': gpu_metrics['temperature_celsius'],
                'power_draw_watts': gpu_metrics['power_draw_watts'],
                'fan_speed_percent': gpu_metrics['fan_speed_percent'],
                
                # System Metrics
                'cpu_utilization': system_metrics['cpu_utilization'],
                'ram_used_gb': system_metrics['ram_used_gb'],
                'storage_used_gb': system_metrics['storage_used_gb'],
                
                # Network Metrics
                'network_utilization': system_metrics['network_utilization'],
                'current_upload_mbps': system_metrics['current_upload_mbps'],
                'current_download_mbps': system_metrics['current_download_mbps'],
                
                # Uptime
                'uptime_hours': uptime_info['uptime_hours'],
                
                'timestamp': datetime.now().isoformat()
            }
            
            # Push to server
            await push_metrics(config, payload)
            logger.debug("Comprehensive metrics pushed to server")
            
        except Exception as e:
            logger.error(f"Error pushing metrics: {e}")
        
        await asyncio.sleep(interval)

async def start_health_push(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 6: Health Push - Push health status to central server every interval seconds."""
    logger.info("Health push thread started")
    
    while True:
        try:
            # Get current health status and metrics
            gpu_status = await get_gpu_status()
            health_data = check_gpu_health()
            gpu_metrics = collect_gpu_metrics()
            
            # Calculate performance scores
            scores = calculate_health_scores(gpu_metrics, health_data)
            
            if gpu_status:
                # Prepare comprehensive health payload
                last_check = gpu_status.get('last_health_check')
                payload = {
                    'agent_id': agent_id,
                    'gpu_uuid': gpu_status.get('gpu_uuid'),
                    'is_healthy': gpu_status.get('is_healthy', False),
                    'status': gpu_status.get('status', 'unknown'),
                    
                    # Health Details
                    'temperature_ok': health_data.get('temperature_normal', True),
                    'power_ok': health_data.get('power_normal', True),
                    'network_ok': True,  # Simplified - could add network check
                    'storage_ok': True,  # Simplified - could add storage check
                    
                    # Performance Indicators
                    'gpu_performance_score': scores['gpu_performance_score'],
                    'system_stability_score': scores['system_stability_score'],
                    
                    'last_health_check': last_check.isoformat() if last_check else None,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Push to server
                await push_health(config, payload)
                logger.debug("Comprehensive health status pushed to server")
            
        except Exception as e:
            logger.error(f"Error pushing health status: {e}")
        
        await asyncio.sleep(interval)

async def start_duration_monitor(config: Dict[str, Any], agent_id: str, interval: int):
    """Thread 7: Duration Monitor - Check for expired deployments every interval seconds."""
    logger.info("Duration monitor thread started")
    
    while True:
        try:
            # Check for expired deployments
            expired_deployments = await get_expired_deployments()
            
            if expired_deployments:
                logger.info(f"Found {len(expired_deployments)} expired deployments")
                
                for deployment in expired_deployments:
                    logger.info(f"Auto-terminating expired deployment: {deployment['deployment_id']}")
                    
                    # Terminate the deployment
                    await terminate_deployment(
                        deployment['deployment_id'],
                        deployment['container_id'],
                        'duration_expired'
                    )
            
        except Exception as e:
            logger.error(f"Error in duration monitoring: {e}")
        
        await asyncio.sleep(interval)

async def send_heartbeat(config: Dict[str, Any], agent_id: str):
    """Send heartbeat to central server."""
    try:
        url = f"{config['server']['url']}/api/host-agents/{agent_id}/heartbeat"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'agent_id': agent_id,
            'timestamp': datetime.now().isoformat(),
            'status': 'online'
        }
        
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=config['server']['timeout']
        )
        
        if response.status_code != 200:
            logger.warning(f"Heartbeat failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")

async def poll_commands(config: Dict[str, Any], agent_id: str) -> list:
    """Poll for commands from central server."""
    try:
        url = f"{config['server']['url']}/api/host-agents/{agent_id}/commands"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            url, 
            headers=headers, 
            timeout=config['server']['timeout']
        )
        
        if response.status_code == 200:
            data = response.json()
            commands = data.get('commands', [])
            logger.debug(f"Poll response: {response.text[:500]}")  # Log first 500 chars
            return commands
        else:
            logger.warning(f"Command polling failed: {response.status_code} - {response.text[:200]}")
            return []
            
    except Exception as e:
        logger.error(f"Failed to poll commands: {e}")
        return []

async def process_command(config: Dict[str, Any], agent_id: str, command: Dict[str, Any]):
    """Process a command from the central server."""
    command_id = None
    try:
        # Log raw command for debugging
        import json
        logger.info(f"Raw command received: {json.dumps(command, indent=2)}")
        
        command_type = command.get('command_type')  # Fixed: was 'type'
        command_data = command.get('payload', {})   # Fixed: was 'data'
        command_id = command.get('command_id')      # Fixed: was 'id'
        
        logger.info(f"Processing command: type={command_type}, id={command_id}, keys={list(command.keys())}")
        
        if command_type == 'deploy':  # Fixed: was 'DEPLOY'
            # Pass command_id as deployment_id
            await handle_deploy_command(config, command_id, command_data)
        elif command_type == 'terminate':  # Fixed: was 'TERMINATE'
            await handle_terminate_command(config, command_data)
        else:
            logger.warning(f"Unknown command type: {command_type}")
        
    except Exception as e:
        logger.error(f"Error processing command: {e}")
    finally:
        # Always acknowledge command, even if it failed
        # This prevents the server from re-sending the same command
        if command_id:
            await acknowledge_command(config, agent_id, command_id)

async def handle_deploy_command(config: Dict[str, Any], command_id: str, command_data: Dict[str, Any]):
    """Handle DEPLOY command."""
    from .deployment import deploy_container

    # Use command_id as deployment_id
    deployment_id = command_id
    
    # Map server payload format to expected format
    template_type = command_data.get('template_id', command_data.get('template_type', 'custom'))
    duration_minutes = command_data.get('duration_minutes', 60)  # Default 60 minutes
    user_id = command_data.get('user_id', 'unknown')
    
    # Log the full payload for debugging
    logger.info(f"Deploying container: {deployment_id}")
    logger.info(f"Template: {template_type}, Duration: {duration_minutes}min, User: {user_id}")
    logger.info(f"Image: {command_data.get('image')}, Container: {command_data.get('container_name')}")
    
    try:
        # Pass the full command_data so deployment can access image, ports, etc.
        await deploy_container(config, deployment_id, command_data)
        logger.info(f"Deployment successful: {deployment_id}")
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise

async def handle_terminate_command(config: Dict[str, Any], command_data: Dict[str, Any]):
    """Handle TERMINATE command."""
    deployment_id = command_data.get('deployment_id')
    reason = command_data.get('reason', 'user_requested')
    
    logger.info(f"Terminating deployment: {deployment_id}")
    
    try:
        await terminate_deployment(deployment_id, None, reason)
        logger.info(f"Termination successful: {deployment_id}")
    except Exception as e:
        logger.error(f"Termination failed: {e}")
        raise

async def acknowledge_command(config: Dict[str, Any], agent_id: str, command_id: str):
    """Acknowledge command processing."""
    try:
        url = f"{config['server']['url']}/api/host-agents/{agent_id}/commands/{command_id}/ack"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'status': 'processed',
            'timestamp': datetime.now().isoformat()
        }
        
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=config['server']['timeout']
        )
        
        if response.status_code != 200:
            logger.warning(f"Command acknowledgment failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Failed to acknowledge command: {e}")

async def push_metrics(config: Dict[str, Any], payload: Dict[str, Any]):
    """Push metrics to central server."""
    try:
        url = f"{config['server']['url']}/api/host-agents/metrics"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=config['server']['timeout']
        )
        
        if response.status_code != 200:
            logger.warning(f"Metrics push failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Failed to push metrics: {e}")

async def push_health(config: Dict[str, Any], payload: Dict[str, Any]):
    """Push health status to central server."""
    try:
        url = f"{config['server']['url']}/api/host-agents/health"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=config['server']['timeout']
        )
        
        if response.status_code != 200:
            logger.warning(f"Health push failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Failed to push health status: {e}")
