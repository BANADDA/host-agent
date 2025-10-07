# host-agent/agent/core/state.py
import uuid

# Generate a unique ID for this specific agent instance on startup
agent_instance_id = str(uuid.uuid4())

# Store active WebSocket connections
websocket_connections = {}
