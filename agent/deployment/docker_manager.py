import logging
import os
import random
import uuid

import docker

from ..api.schemas import InstanceData

client = docker.from_env()
logger = logging.getLogger(__name__)

async def start_container(instance_data: dict, instance_uuid: str, send_live_update) -> dict:
    """Starts a new GPU-enabled container based on instance_data with live updates."""
    # Build the command to set up SSH access for the user
    command = f"/bin/bash -c 'mkdir -p /root/.ssh && echo \"{instance_data['user_ssh_key']}\" >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && while true; do sleep 1000; done'"
    
    await send_live_update("Pulling Docker image...", instance_uuid)
    image_name = instance_data['image_name']
    try:
        client.images.pull(image_name)
    except docker.errors.ImageNotFound:
        await send_live_update(f"Image '{image_name}' not found.", instance_uuid)
        raise
    
    await send_live_update("Starting container...", instance_uuid)
    container = client.containers.run(
        image_name,
        detach=True,
        tty=True,
        command=command,
        name=f"rental-instance-{instance_uuid}",
        device_requests=[
            docker.types.DeviceRequest(
                device_ids=[instance_data['gpu_uuid']], capabilities=[['gpu']]
            )
        ],
        mem_limit=f"{instance_data['memory_limit_mb']}m",
        auto_remove=True
    )
    logger.info(f"Container {container.id} started on GPU {instance_data['gpu_uuid']}")
    return container.attrs

async def start_rental_container(container_config: dict, rental_id: str, send_live_update) -> dict:
    """Starts a rental container with specific configuration."""
    try:
        # Generate random ports for SSH and web access
        ssh_port = random.randint(22000, 22999)
        web_port = random.randint(8000, 8999)
        
        # Build command based on auth type
        if container_config['auth_type'] == 'password':
            password = container_config['password']
            command = f"/bin/bash -c 'echo root:{password} | chpasswd && /usr/sbin/sshd -D'"
        else:  # public_key
            ssh_key = container_config['ssh_key']
            command = f"/bin/bash -c 'mkdir -p /root/.ssh && echo \"{ssh_key}\" >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && /usr/sbin/sshd -D'"
        
        # Set up environment variables
        env_vars = container_config.get('environment_variables', {})
        env_vars.update({
            'CUDA_VISIBLE_DEVICES': '0',
            'RENTAL_ID': rental_id
        })
        
        await send_live_update("Pulling Docker image...", rental_id)
        image_name = container_config['image_name']
        try:
            client.images.pull(image_name)
        except docker.errors.ImageNotFound:
            await send_live_update(f"Image '{image_name}' not found.", rental_id)
            raise
        
        await send_live_update("Starting rental container...", rental_id)
        
        # Set up port mappings
        port_mappings = container_config.get('port_mappings', {})
        ports = {
            '22/tcp': ssh_port,
            '8080/tcp': web_port
        }
        
        # Add custom port mappings
        for host_port, container_port in port_mappings.items():
            ports[f'{container_port}/tcp'] = int(host_port)
        
        container = client.containers.run(
            image_name,
            detach=True,
            tty=True,
            command=command,
            name=f"rental-{rental_id}",
            environment=env_vars,
            ports=ports,
            device_requests=[
                docker.types.DeviceRequest(
                    device_ids=[container_config['gpu_uuid']], 
                    capabilities=[['gpu']]
                )
            ],
            mem_limit=f"{container_config['memory_limit_mb']}m",
            auto_remove=True
        )
        
        # Add port information to container attributes
        container_attrs = container.attrs.copy()
        container_attrs['ssh_port'] = ssh_port
        container_attrs['web_port'] = web_port
        
        logger.info(f"Rental container {container.id} started on GPU {container_config['gpu_uuid']}")
        
        # Send running status update
        await send_live_update(f"Container started with container ID: {container.id}", rental_id)
        
        return container_attrs
        
    except Exception as e:
        logger.error(f"Failed to start rental container: {e}")
        await send_live_update(f"Failed to start rental container: {str(e)}", rental_id)
        raise

def stop_container(container_id: str):
    """Stops and removes a container."""
    try:
        container = client.containers.get(container_id)
        container.stop()
        logger.info(f"Container {container_id} stopped.")
    except docker.errors.NotFound:
        logger.warning(f"Container {container_id} not found, already stopped?")
    except Exception as e:
        logger.error(f"Error stopping container {container_id}: {e}")
