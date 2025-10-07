import asyncio
import json
import logging
import subprocess

import docker
import requests

from ..api.schemas import InstanceInfo
from .config import settings

logger = logging.getLogger(__name__)
client = docker.from_env()

async def get_gpu_info():
    """Use nvidia-smi to get detailed GPU information."""
    try:
        command = ["nvidia-smi", "--query-gpu=uuid,name,memory.total,memory.used", "--format=csv,noheader,nounits"]
        output = subprocess.check_output(command, encoding='utf-8').strip()
        gpus = []
        for line in output.split('\n'):
            uuid, name, total_memory, used_memory = line.split(',')
            gpus.append({
                "uuid": uuid.strip(),
                "name": name.strip(),
                "memory_total_mb": int(total_memory.strip()),
                "memory_used_mb": int(used_memory.strip())
            })
        return gpus
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Failed to get GPU info: {e}")
        return []

def get_running_instances() -> list[InstanceInfo]:
    """Get a list of containers managed by this agent."""
    try:
        containers = client.containers.list(filters={"name": "rental-instance"})
        return [{"id": c.id, "name": c.name} for c in containers]
    except Exception as e:
        logger.error(f"Failed to get running containers: {e}")
        return []

async def report_resources(agent_instance_id: str):
    """Continuously report resources to the central API server."""
    while True:
        try:
            gpus = await get_gpu_info()
            instances = get_running_instances()
            payload = {
                "agent_id": agent_instance_id,
                "gpus": gpus,
                "instances": instances
            }
            logger.info(f"Reporting resources: {payload}")
            response = requests.post(f"{settings.api_server_url}/api/hosts/report", json=payload)
            response.raise_for_status()
            logger.info("Successfully reported resources.")
        except Exception as e:
            logger.error(f"Failed to report resources to API server: {e}")

        await asyncio.sleep(settings.report_interval_seconds)
