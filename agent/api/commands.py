import logging
import uuid

from fastapi import APIRouter, HTTPException

from ..deployment import docker_manager
from ..core.state import agent_instance_id, websocket_connections
from .schemas import InstanceData, InstanceID

router = APIRouter()
logger = logging.getLogger(__name__)

async def send_live_update(message: str, instance_uuid: str = None):
    """Sends a live status update to the server via WebSocket."""
    if agent_instance_id in websocket_connections:
        try:
            await websocket_connections[agent_instance_id].send_json({
                "status": "live_update",
                "agent_id": agent_instance_id,
                "instance_uuid": instance_uuid,
                "message": message
            })
        except Exception as e:
            logger.error(f"Failed to send WebSocket update: {e}")

@router.post("/start_instance")
async def start_instance(instance_data: InstanceData):
    """Endpoint for the server to start a new container instance."""
    logger.info(f"Received request to start instance: {instance_data.model_dump()}")
    instance_uuid = str(uuid.uuid4())
    try:
        await send_live_update(f"Starting deployment for instance {instance_uuid}...", instance_uuid)
        container_info = await docker_manager.start_container(instance_data.model_dump(), instance_uuid, send_live_update)
        await send_live_update(f"Instance {instance_uuid} started with container ID {container_info.get('Id')}", instance_uuid)
        return {"message": "Instance started successfully", "container_id": container_info.get('Id')}
    except Exception as e:
        logger.error(f"Failed to start instance: {e}")
        await send_live_update(f"Deployment failed for instance {instance_uuid}: {str(e)}", instance_uuid)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/terminate_instance")
async def terminate_instance(instance: InstanceID):
    """Endpoint for the server to terminate a running container instance."""
    logger.info(f"Received request to terminate instance: {instance.container_id}")
    try:
        await send_live_update(f"Terminating instance {instance.container_id}...", instance.container_id)
        docker_manager.stop_container(instance.container_id)
        await send_live_update(f"Instance {instance.container_id} terminated.", instance.container_id)
        return {"message": "Instance terminated successfully"}
    except Exception as e:
        logger.error(f"Failed to terminate instance: {e}")
        await send_live_update(f"Termination failed for instance {instance.container_id}: {str(e)}", instance.container_id)
        raise HTTPException(status_code=500, detail=str(e))
