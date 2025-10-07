from pydantic import BaseModel, Field


class InstanceData(BaseModel):
    """Data model for starting a new instance."""
    image_name: str = Field(..., description="The Docker image to use for the instance.")
    user_ssh_key: str = Field(..., description="The user's public SSH key.")
    gpu_uuid: str = Field(..., description="The UUID of the GPU to allocate.")
    memory_limit_mb: int = Field(..., description="Memory limit for the container in MB.")

class InstanceID(BaseModel):
    """Data model for terminating an instance."""
    container_id: str = Field(..., description="The ID of the container to terminate.")

class InstanceInfo(BaseModel):
    """Data model for instance information."""
    id: str = Field(..., description="The container ID.")
    name: str = Field(..., description="The container name.")
