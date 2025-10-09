# host-agent/agent/main.py
import asyncio
import logging

import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .api.commands import check_expired_rentals
from .api.commands import router as commands_router
from .core.config import settings
from .core.database import cleanup_database, init_database
from .core.hardware import report_resources
from .core.state import agent_instance_id, websocket_connections

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Host Agent")

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
    
    # Initialize database
    try:
        await init_database()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
    
    # Start resource reporting
    asyncio.create_task(report_resources(agent_instance_id))
    
    # Start rental monitoring
    asyncio.create_task(monitor_rentals())

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the application shuts down."""
    logging.info("Host Agent shutting down...")
    await cleanup_database()

async def monitor_rentals():
    """Monitor rentals for expiration and auto-termination."""
    while True:
        try:
            await check_expired_rentals()
            # Check every 5 minutes
            await asyncio.sleep(300)
        except Exception as e:
            logging.error(f"Error in rental monitoring: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retrying

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.agent_port)
