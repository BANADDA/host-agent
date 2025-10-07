# host-agent/agent/main.py
import asyncio
import logging
import uuid

import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .api.commands import router as commands_router
from .core.config import settings
from .core.hardware import report_resources

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Host Agent")

# Generate a unique ID for this specific agent instance on startup
agent_instance_id = str(uuid.uuid4())

# Store active WebSocket connections
websocket_connections = {}

app.include_router(commands_router)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections[agent_instance_id] = websocket
    logging.info(f"Agent {agent_instance_id} connected via WebSocket.")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if agent_instance_id in websocket_connections:
            del websocket_connections[agent_instance_id]
            logging.warning(f"Agent {agent_instance_id} disconnected.")
    except Exception as e:
        logging.error(f"WebSocket error for agent {agent_instance_id}: {e}")
        if agent_instance_id in websocket_connections:
            del websocket_connections[agent_instance_id]

@app.on_event("startup")
async def startup_event():
    logging.info(f"Host Agent {agent_instance_id} starting...")
    asyncio.create_task(report_resources(agent_instance_id))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.agent_port)
