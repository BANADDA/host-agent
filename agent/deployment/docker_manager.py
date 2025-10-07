import logging
import os
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
