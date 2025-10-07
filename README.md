# Host Agent for GPU Rental Platform

The Host Agent is a lightweight, containerized service designed to run on physical machines offered by hardware providers. Its primary function is to manage and report the host's resources to a central server, and to provision and terminate rental instances (Docker containers) based on commands from that server.

This README provides an overview of the agent's architecture, its key functionalities, and instructions for building and deploying it using GitHub Actions and the GitHub Container Registry (GHCR).

## Features

- **Resource Reporting**: Automatically detects and reports host hardware specifications (GPUs, memory) to the central server.
- **Instance Management**: Receives commands from the server to start and terminate isolated, GPU-enabled Docker containers.
- **Live Feedback**: Communicates real-time deployment and termination status to the server via WebSockets.
- **Containerized**: Built as a Docker container for easy, consistent, and reliable deployment on any provider machine.
- **Stateless**: The agent holds minimal in-memory state, relying on the central server's database as the single source of truth.

## Prerequisites

- **Docker**: The host machine must have Docker installed.
- **NVIDIA Container Toolkit**: The host machine must have the NVIDIA Container Toolkit installed to allow Docker containers to access the GPUs.
- **Unique ID**: The agent requires a unique ID, passed as an environment variable, to identify itself to the central server.
- **Central Server URL**: The URL of the central API server must be provided as an environment variable.

## Setup and Deployment

This project uses GitHub Actions to automate the build and push of the Docker image to GHCR.

### 1. Build and Push with GitHub Actions

The CI/CD workflow defined in `.github/workflows/ci.yml` is triggered automatically on every push to the `main` branch. It performs the following steps:

1. Builds the Docker image from the `host-agent` directory.
2. Tags the image with the Git commit SHA and `latest`.
3. Authenticates with GHCR using a Personal Access Token (PAT) stored as a repository secret.
4. Pushes the final image to `ghcr.io/<YOUR_GHCR_PATH>`.

### 2. Configure Environment Variables

Before running the agent, you need to set the following environment variables:

- `AGENT_ID`: A unique identifier for this host machine.
- `API_SERVER_URL`: The full URL of your central server (e.g., `https://api.yourplatform.com`).

Create a `.env` file in the `host-agent` directory for local development, or configure these variables directly in your deployment command.

### 3. Run the Host Agent

On the provider's machine, execute the following command to run the container. This command grants the agent necessary access to the host's Docker socket and GPU resources.

```bash
docker run -d \
  --name host-agent \
  --restart=unless-stopped \
  --gpus all \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e API_SERVER_URL="https://your-central-api-server.com" \
  ghcr.io/<YOUR_GHCR_PATH>:latest
```

## API Endpoints

The host agent exposes a minimal API for communication with the central server's scheduler. All endpoints are authenticated and should only be accessed by the trusted central server.

### POST `/start_instance`

Starts a new rental instance (Docker container).

- **Payload**: `InstanceData` schema
- **Returns**: `{"message": "Instance started successfully", "container_id": "..."}`

### POST `/terminate_instance`

Terminates a running container instance.

- **Payload**: `InstanceID` schema
- **Returns**: `{"message": "Instance terminated successfully"}`

### GET `/ws`

Establishes a WebSocket connection for live status updates during deployment and termination.

## Development

### Prerequisites

- Python 3.11+
- Docker
- pip and venv

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```

2. Navigate to the project:
   ```bash
   cd host-agent
   ```

3. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Run Locally

To run the agent locally for development, you can start it directly with uvicorn. Ensure your `.env` file is configured correctly.

```bash
uvicorn agent.main:app --reload
```

## Contributing

We welcome contributions! Please open an issue or submit a pull request with any improvements.

## License

This project is licensed under the MIT License. See the LICENSE file for details.