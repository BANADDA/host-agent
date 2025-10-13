# host-agent/agent/core/deployment.py
import asyncio
import logging
import secrets
import string
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict

from .database import (create_deployment, get_gpu_status, store_gpu_metrics,
                       update_deployment_status, update_gpu_status)

logger = logging.getLogger(__name__)

async def deploy_container(config: Dict[str, Any], deployment_id: str, command_data: Dict[str, Any]):
    """Deploy a container with the specified configuration."""
    try:
        logger.info(f"Starting deployment: {deployment_id}")
        
        # Extract parameters from command_data
        template_type = command_data.get('template_id', command_data.get('template_type', 'custom'))
        duration_minutes = command_data.get('duration_minutes', 60)
        user_id = command_data.get('user_id', 'unknown')
        image = command_data.get('image', 'ubuntu:22.04')
        # Use deployment_id for unique container name to avoid conflicts
        container_name = f'deployment-{deployment_id}'
        
        # Step 1: Validate GPU availability
        gpu_status = await get_gpu_status()
        if not gpu_status:
            raise Exception("GPU status not found")
        
        if gpu_status['status'] != 'available':
            raise Exception(f"GPU not available (status: {gpu_status['status']})")
        
        if not gpu_status['is_healthy']:
            raise Exception("GPU is not healthy")
        
        if gpu_status.get('current_deployment_id'):
            raise Exception("GPU is already in use")
        
        # Step 2: Create deployment record
        deployment_data = {
            'deployment_id': deployment_id,
            'gpu_id': 'gpu-0',
            'template_type': template_type,
            'status': 'deploying',
            'start_time': datetime.now(),
            'duration_minutes': duration_minutes,
            'user_id': user_id,
            'ssh_port': config['network']['ports']['ssh'],
            'rental_port_1': config['network']['ports']['rental_port_1'],
            'rental_port_2': config['network']['ports']['rental_port_2']
        }
        
        await create_deployment(deployment_data)
        
        # Update GPU status
        await update_gpu_status('gpu-0', 
            status='busy',
            current_deployment_id=deployment_id
        )
        
        # Step 3: Pull Docker image
        logger.info(f"Pulling Docker image: {image}")
        await pull_docker_image(image)
        
        # Step 4: Generate credentials
        ssh_username = "gpu-user"
        ssh_password = generate_password(16)
        jupyter_token = generate_token(32)
        
        # Step 5: Create and start container using command_data
        container_id, port_mappings = await create_container(
            deployment_id, image, container_name, config, command_data,
            ssh_username, ssh_password, jupyter_token
        )
        
        # Step 6: Configure container
        await configure_container(deployment_id, ssh_username, ssh_password, jupyter_token)
        
        # Step 7: Health checks
        await verify_container_health(deployment_id, config)
        
        # Step 8: Update deployment with container info
        await update_deployment_status(deployment_id, 'running',
            container_id=container_id,
            ssh_username=ssh_username,
            ssh_password=ssh_password
        )
        
        # Step 9: Notify central server with actual port mappings
        await notify_deployment_success(config, deployment_id, container_id, 
                                       ssh_username, ssh_password, jupyter_token, port_mappings)
        
        logger.info(f"Deployment successful: {deployment_id}")
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        
        # Cleanup on failure
        try:
            await cleanup_failed_deployment(deployment_id)
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed: {cleanup_error}")
        
        raise

async def terminate_deployment(deployment_id: str, container_id: str = None, reason: str = 'user_requested'):
    """Terminate a deployment."""
    try:
        logger.info(f"Terminating deployment: {deployment_id}")
        
        # Get deployment info if container_id not provided
        if not container_id:
            # This would need to be implemented to get container_id from database
            pass
        
        if container_id:
            # Stop container gracefully
            await stop_container(container_id)
            
            # Remove container
            await remove_container(container_id)
        
        # Clean up GPU resources
        await cleanup_gpu_resources()
        
        # Update database
        await update_deployment_status(deployment_id, 'terminated' if reason == 'user_requested' else 'completed')
        await update_gpu_status('gpu-0', 
            status='available',
            current_deployment_id=None
        )
        
        # Notify central server
        await notify_deployment_terminated(deployment_id, reason)
        
        logger.info(f"Termination successful: {deployment_id}")
        
    except Exception as e:
        logger.error(f"Termination failed: {e}")
        raise

def get_docker_image(template_type: str) -> str:
    """Get Docker image name based on template type."""
    image_map = {
        'cuda': 'yourplatform/cuda-template:latest',
        'ubuntu': 'yourplatform/ubuntu-template:latest',
        'pytorch': 'yourplatform/pytorch-template:latest',
        'tensorflow': 'yourplatform/tensorflow-template:latest'
    }
    
    return image_map.get(template_type, 'yourplatform/cuda-template:latest')

async def pull_docker_image(image_name: str):
    """Pull Docker image if not already present."""
    try:
        # Check if image exists locally
        result = subprocess.run(['docker', 'images', '-q', image_name], 
                              capture_output=True, text=True, timeout=10)
        
        if not result.stdout.strip():
            logger.info(f"Pulling Docker image: {image_name}")
            result = subprocess.run(['docker', 'pull', image_name], 
                                  capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"Failed to pull image: {result.stderr}")
            
            logger.info("Docker image pulled successfully")
        else:
            logger.info("Using cached Docker image")
            
    except subprocess.TimeoutExpired:
        raise Exception("Docker pull timeout")
    except Exception as e:
        raise Exception(f"Docker pull failed: {e}")

def generate_password(length: int) -> str:
    """Generate a random password."""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for _ in range(length))

def generate_token(length: int) -> str:
    """Generate a random token."""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

async def create_container(deployment_id: str, image_name: str, container_name: str,
                          config: Dict[str, Any], command_data: Dict[str, Any],
                          ssh_username: str, ssh_password: str, jupyter_token: str) -> str:
    """Create and start Docker container."""
    try:
        # Build docker run command
        cmd = [
            'docker', 'run', '-d',
            '--name', container_name,
            '--gpus', 'all',
            '--shm-size=8g',
        ]
        
        # Add restart policy from command_data or use default
        restart_policy = command_data.get('restart_policy', 'unless-stopped')
        cmd.extend(['--restart', restart_policy])
        
        # Add port mappings from command_data
        # Use dynamic port allocation to avoid conflicts
        ports = command_data.get('ports', {})
        port_mappings = {}
        for requested_port, container_port in ports.items():
            # Allocate a random port in range 30000-39999
            import random
            allocated_port = random.randint(30000, 39999)
            cmd.extend(['-p', f"{allocated_port}:{container_port}"])
            port_mappings[container_port] = allocated_port
            logger.info(f"Allocated host port {allocated_port} for container port {container_port}")
        
        # Add environment variables from command_data
        env_vars = command_data.get('environment', {})
        env_vars.update({
            'DEPLOYMENT_ID': deployment_id,
            'SSH_USERNAME': ssh_username,
            'SSH_PASSWORD': ssh_password,
            'JUPYTER_TOKEN': jupyter_token
        })
        for key, value in env_vars.items():
            cmd.extend(['-e', f"{key}={value}"])
        
        # Add volumes from command_data
        volumes = command_data.get('volumes', {})
        for host_path, container_path in volumes.items():
            cmd.extend(['-v', f"{host_path}:{container_path}"])
        
        # Add image
        cmd.append(image_name)
        
        # Add command if specified
        container_command = command_data.get('command')
        if container_command:
            cmd.extend(['bash', '-c', container_command])
        
        logger.info(f"Creating container: {deployment_id}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            raise Exception(f"Failed to create container: {result.stderr}")
        
        container_id = result.stdout.strip()
        logger.info(f"Container created: {container_id}")
        
        # Wait for container to be ready
        await asyncio.sleep(10)
        
        return container_id, port_mappings
        
    except subprocess.TimeoutExpired:
        raise Exception("Container creation timeout")
    except Exception as e:
        raise Exception(f"Container creation failed: {e}")

async def configure_container(deployment_id: str, ssh_username: str, 
                            ssh_password: str, jupyter_token: str):
    """Configure the container after creation."""
    try:
        # Set up SSH access
        ssh_commands = [
            f"useradd -m -s /bin/bash {ssh_username}",
            f"echo '{ssh_username}:{ssh_password}' | chpasswd",
            f"usermod -aG sudo {ssh_username}",
            "service ssh restart"
        ]
        
        for cmd in ssh_commands:
            result = subprocess.run(['docker', 'exec', deployment_id, 'bash', '-c', cmd],
                                  capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning(f"SSH setup command failed: {cmd}")
        
        # Start Jupyter Lab
        jupyter_cmd = f"""
        su - {ssh_username} -c "
        jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --NotebookApp.token={jupyter_token}
        "
        """
        
        result = subprocess.run(['docker', 'exec', '-d', deployment_id, 'bash', '-c', jupyter_cmd],
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.warning("Failed to start Jupyter Lab")
        
        logger.info("Container configured successfully")
        
    except Exception as e:
        logger.error(f"Container configuration failed: {e}")
        raise

async def verify_container_health(deployment_id: str, config: Dict[str, Any]):
    """Verify container health and accessibility."""
    try:
        # Check if container is running
        result = subprocess.run(['docker', 'ps', '--filter', f'name={deployment_id}'],
                              capture_output=True, text=True, timeout=10)
        
        if deployment_id not in result.stdout:
            raise Exception("Container is not running")
        
        # Check GPU accessibility
        result = subprocess.run(['docker', 'exec', deployment_id, 'nvidia-smi'],
                            capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            raise Exception("GPU not accessible in container")
        
        # Check port accessibility
        ports = [
            config['network']['ports']['ssh'],
            config['network']['ports']['rental_port_1'],
            config['network']['ports']['rental_port_2']
        ]
        
        for port in ports:
            result = subprocess.run(['netstat', '-tuln'], capture_output=True, text=True, timeout=5)
            if f":{port}" not in result.stdout:
                raise Exception(f"Port {port} is not listening")
        
        logger.info("Container health checks passed")
        
    except Exception as e:
        logger.error(f"Container health check failed: {e}")
        raise

async def stop_container(container_id: str):
    """Stop Docker container gracefully."""
    try:
        result = subprocess.run(['docker', 'stop', '--time', '30', container_id],
                              capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            logger.warning(f"Failed to stop container gracefully: {result.stderr}")
            # Force kill if graceful stop failed
            subprocess.run(['docker', 'kill', container_id], timeout=30)
        
        logger.info(f"Container stopped: {container_id}")
        
    except Exception as e:
        logger.error(f"Failed to stop container: {e}")
        raise

async def remove_container(container_id: str):
    """Remove Docker container."""
    try:
        result = subprocess.run(['docker', 'rm', container_id],
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise Exception(f"Failed to remove container: {result.stderr}")
        
        logger.info(f"Container removed: {container_id}")
        
    except Exception as e:
        logger.error(f"Failed to remove container: {e}")
        raise

async def cleanup_gpu_resources():
    """Clean up GPU resources after deployment termination."""
    try:
        # Check GPU memory usage
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            memory_used = int(result.stdout.strip())
            if memory_used > 100:  # More than 100MB used
                logger.warning("GPU memory not fully released, resetting...")
                subprocess.run(['nvidia-smi', '--gpu-reset'], timeout=30)
                await asyncio.sleep(5)
        
        logger.info("GPU resources cleaned")
        
    except Exception as e:
        logger.error(f"GPU cleanup failed: {e}")

async def cleanup_failed_deployment(deployment_id: str):
    """Clean up resources when deployment fails."""
    try:
        # Try to stop and remove container if it exists
        result = subprocess.run(['docker', 'ps', '-a', '--filter', f'name={deployment_id}'],
                              capture_output=True, text=True, timeout=10)
        
        if deployment_id in result.stdout:
            subprocess.run(['docker', 'stop', deployment_id], timeout=30)
            subprocess.run(['docker', 'rm', deployment_id], timeout=30)
        
        # Update database
        await update_deployment_status(deployment_id, 'failed')
        await update_gpu_status('gpu-0', 
            status='available',
            current_deployment_id=None
        )
        
        logger.info(f"Failed deployment cleaned up: {deployment_id}")
        
    except Exception as e:
        logger.error(f"Failed deployment cleanup error: {e}")

async def notify_deployment_success(config: Dict[str, Any], deployment_id: str, container_id: str,
                                  ssh_username: str, ssh_password: str, jupyter_token: str, port_mappings: Dict[str, int]):
    """Notify central server of successful deployment."""
    try:
        import requests
        
        url = f"{config['server']['url']}/api/deployments/{deployment_id}/success"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        # Get the SSH port from port_mappings (container port 22)
        ssh_port = port_mappings.get('22', port_mappings.get(22, config['network']['ports']['ssh']))
        
        payload = {
            'deployment_id': deployment_id,
            'status': 'running',
            'container_id': container_id,
            'access_info': {
                'public_ip': config['network']['public_ip'],
                'ssh': {
                    'host': config['network']['public_ip'],
                    'port': ssh_port,
                    'username': ssh_username,
                    'password': ssh_password,
                    'command': f"ssh {ssh_username}@{config['network']['public_ip']} -p {ssh_port}"
                },
                'port_mappings': port_mappings,  # Include all actual port mappings
                'rental_ports': {
                    'port_1': {
                        'port': config['network']['ports']['rental_port_1'],
                        'url': f"http://{config['network']['public_ip']}:{config['network']['ports']['rental_port_1']}",
                        'description': 'Jupyter Lab',
                        'token': jupyter_token,
                        'full_url': f"http://{config['network']['public_ip']}:{config['network']['ports']['rental_port_1']}/?token={jupyter_token}"
                    },
                    'port_2': {
                        'port': config['network']['ports']['rental_port_2'],
                        'url': f"http://{config['network']['public_ip']}:{config['network']['ports']['rental_port_2']}",
                        'description': 'Custom application port'
                    }
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=config['server']['timeout'])
        
        if response.status_code == 200:
            logger.info("Deployment success notification sent")
        else:
            logger.warning(f"Deployment notification failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Failed to notify deployment success: {e}")

async def notify_deployment_terminated(deployment_id: str, reason: str):
    """Notify central server of deployment termination."""
    try:
        import requests

        # This would need the config to be passed in
        # For now, just log the termination
        logger.info(f"Deployment terminated: {deployment_id} (reason: {reason})")
        
    except Exception as e:
        logger.error(f"Failed to notify deployment termination: {e}")
