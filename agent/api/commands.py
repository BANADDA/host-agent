import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..core.database import (get_expired_rentals, mark_rental_terminated,
                             store_rental_in_db)
from ..core.state import agent_instance_id, websocket_connections
from ..deployment import docker_manager
from .schemas import InstanceData, InstanceID, RentalRequest, RentalResponse

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

async def send_rental_update(instance_uuid: str, status: str, message: str, container_id: str = None):
    """Send rental status update via WebSocket."""
    if agent_instance_id in websocket_connections:
        try:
            update_data = {
                "instance_uuid": instance_uuid,
                "status": status,
                "message": message
            }
            
            if container_id:
                update_data["container_id"] = container_id
            
            await websocket_connections[agent_instance_id].send_json(update_data)
        except Exception as e:
            logger.error(f"Failed to send rental update: {e}")

async def send_rental_ready_update(instance_uuid: str, container_info: dict, rental_request: RentalRequest):
    """Send final ready status with connection info."""
    import socket
    
    if agent_instance_id in websocket_connections:
        try:
            # Get host IP
            host_ip = socket.gethostbyname(socket.gethostname())
            
            # Prepare connection info
            connection_info = {
                "ssh_host": host_ip,
                "ssh_port": container_info.get('ssh_port', 22),
                "username": "root" if rental_request.auth_type == "password" else "root",
                "password": rental_request.password if rental_request.auth_type == "password" else None
            }
            
            # Prepare GPU info
            gpu_info = {
                "gpu_id": "0",
                "gpu_name": rental_request.gpu_type,
                "memory_allocated": "16GB"  # Default, could be dynamic
            }
            
            # Prepare access info
            access_info = {
                "ssh_command": f"ssh -p {connection_info['ssh_port']} {connection_info['username']}@{host_ip}",
                "jupyter_url": f"http://{host_ip}:{container_info.get('web_port', 8080)}",
                "vnc_url": f"vnc://{host_ip}:5900"
            }
            
            update_data = {
                "instance_uuid": instance_uuid,
                "status": "ready",
                "message": "GPU instance is ready for use",
                "container_id": container_info.get('Id'),
                "connection_info": connection_info,
                "gpu_info": gpu_info,
                "access_info": access_info
            }
            
            await websocket_connections[agent_instance_id].send_json(update_data)
        except Exception as e:
            logger.error(f"Failed to send ready update: {e}")

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

@router.post("/rent", response_model=RentalResponse)
async def create_rental(rental_request: RentalRequest):
    """Endpoint for the server to create a new rental instance."""
    logger.info(f"Received rental request: {rental_request.model_dump()}")
    
    try:
        # Generate rental ID (this will be the instance_uuid)
        rental_id = str(uuid.uuid4())
        
        # Send initial status update
        await send_rental_update(rental_id, "creating", "Starting container creation...", None)
        
        # Find available GPU
        gpu_uuid = await find_available_gpu(rental_request.gpu_type)
        if not gpu_uuid:
            await send_rental_update(rental_id, "error", f"No {rental_request.gpu_type} GPUs available on this host", None)
            return RentalResponse(
                success=False,
                message=f"No {rental_request.gpu_type} GPUs available on this host"
            )
        
        # Prepare container configuration
        container_config = {
            "image_name": rental_request.os_image,
            "gpu_uuid": gpu_uuid,
            "memory_limit_mb": 8192,  # Default memory limit
            "environment_variables": rental_request.environment_variables,
            "port_mappings": rental_request.port_mappings,
            "auth_type": rental_request.auth_type,
            "password": rental_request.password,
            "ssh_key": rental_request.ssh_key,
            "instance_name": rental_request.instance_name,
            "rental_id": rental_id,
            "duration_hours": rental_request.duration_hours
        }
        
        # Start container with status updates
        container_info = await docker_manager.start_rental_container(container_config, rental_id, send_rental_update)
        
        # Store rental in database
        await store_rental_in_db(rental_id, rental_request, container_info)
        
        # Start auto-termination timer
        await start_rental_timer(rental_id, rental_request.duration_hours)
        
        # Send final ready status
        await send_rental_ready_update(rental_id, container_info, rental_request)
        
        return RentalResponse(
            success=True,
            message=f"Rental {rental_id} started successfully",
            container_id=container_info.get('Id'),
            ssh_port=container_info.get('ssh_port', 22),
            web_port=container_info.get('web_port', 8080),
            rental_id=rental_id
        )
        
    except Exception as e:
        logger.error(f"Failed to create rental: {e}")
        await send_rental_update(rental_id if 'rental_id' in locals() else None, "error", f"Rental creation failed: {str(e)}", None)
        return RentalResponse(
            success=False,
            message=f"Failed to create rental: {str(e)}"
        )

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

async def find_available_gpu(gpu_type: str) -> Optional[str]:
    """Find an available GPU of the specified type."""
    try:
        # Import here to avoid circular imports
        from ..core.hardware import get_gpu_info
        
        gpus = await get_gpu_info()
        for gpu in gpus:
            if gpu.get('name') == gpu_type and gpu.get('memory_used_mb', 0) == 0:
                return gpu.get('uuid')
        
        return None
    except Exception as e:
        logger.error(f"Failed to find available GPU: {e}")
        return None

async def start_rental_timer(rental_id: str, duration_hours: int):
    """Start a timer to auto-terminate the rental after the specified duration."""
    try:
        # Calculate delay in seconds
        delay_seconds = duration_hours * 3600
        
        # Start the timer in the background
        asyncio.create_task(auto_terminate_rental(rental_id, delay_seconds))
        
        logger.info(f"Started auto-termination timer for rental {rental_id} ({duration_hours} hours)")
        
    except Exception as e:
        logger.error(f"Failed to start rental timer: {e}")

async def auto_terminate_rental(rental_id: str, delay_seconds: int):
    """Auto-terminate a rental after the specified delay."""
    try:
        # Wait for the specified duration
        await asyncio.sleep(delay_seconds)
        
        # Get rental info from database
        from ..core.database import get_active_rentals
        active_rentals = await get_active_rentals()
        
        rental_info = next((r for r in active_rentals if r['rental_id'] == rental_id), None)
        if not rental_info:
            logger.warning(f"Rental {rental_id} not found or already terminated")
            return
        
        # Terminate the container
        container_id = rental_info['container_id']
        try:
            docker_manager.stop_container(container_id)
            await mark_rental_terminated(rental_id)
            await send_live_update(f"Rental {rental_id} auto-terminated after {delay_seconds/3600:.1f} hours", rental_id)
            logger.info(f"Rental {rental_id} auto-terminated successfully")
        except Exception as e:
            logger.error(f"Failed to auto-terminate rental {rental_id}: {e}")
            await send_live_update(f"Auto-termination failed for rental {rental_id}: {str(e)}", rental_id)
            
    except Exception as e:
        logger.error(f"Failed to auto-terminate rental {rental_id}: {e}")

async def check_expired_rentals():
    """Check for expired rentals and terminate them."""
    try:
        expired_rentals = await get_expired_rentals()
        
        for rental in expired_rentals:
            rental_id = rental['rental_id']
            container_id = rental['container_id']
            instance_name = rental['instance_name']
            
            try:
                # Terminate the container
                docker_manager.stop_container(container_id)
                await mark_rental_terminated(rental_id)
                await send_live_update(f"Expired rental {rental_id} ({instance_name}) terminated", rental_id)
                logger.info(f"Expired rental {rental_id} terminated successfully")
                
            except Exception as e:
                logger.error(f"Failed to terminate expired rental {rental_id}: {e}")
                await send_live_update(f"Failed to terminate expired rental {rental_id}: {str(e)}", rental_id)
                
    except Exception as e:
        logger.error(f"Failed to check expired rentals: {e}")
