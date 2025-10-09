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

class RentalRequest(BaseModel):
    """Data model for rental requests from the server."""
    host_id: str = Field(..., description="The host ID.")
    gpu_type: str = Field(..., description="The GPU type requested.")
    os_image: str = Field(..., description="The OS image to deploy.")
    duration_hours: int = Field(..., description="Rental duration in hours.")
    auth_type: str = Field(..., description="Authentication type: 'password' or 'public_key'.")
    password: str = Field(None, description="Password for password auth.")
    ssh_key: str = Field(None, description="SSH public key for key auth.")
    instance_name: str = Field(..., description="Name for the rental instance.")
    environment_variables: dict = Field(default_factory=dict, description="Environment variables.")
    port_mappings: dict = Field(default_factory=dict, description="Port mappings for the container.")

class RentalResponse(BaseModel):
    """Response model for rental requests."""
    success: bool = Field(..., description="Whether the rental was successful.")
    message: str = Field(..., description="Response message.")
    container_id: str = Field(None, description="The container ID if successful.")
    ssh_port: int = Field(None, description="SSH port for the container.")
    web_port: int = Field(None, description="Web port for the container.")
    rental_id: str = Field(None, description="The rental ID for tracking.")
