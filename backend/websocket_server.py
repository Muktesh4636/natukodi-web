import asyncio
import json
import logging
from typing import List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import redis.asyncio as redis

# Configuration
REDIS_URL = "redis://localhost:6379/0"
GAME_UPDATE_CHANNEL = "game_updates"
BETS_STREAM = "bets_stream"
GAME_STATE_KEY = "current_game_state"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebSocketServer")

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"New connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Connection closed. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        if not self.active_connections:
            return
        
        # Create tasks for all sends to handle them concurrently
        tasks = [connection.send_text(message) for connection in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)

manager = ConnectionManager()
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@app.on_event("startup")
async def startup_event():
    # Start the Redis Pub/Sub listener in the background
    asyncio.create_task(redis_listener())

async def redis_listener():
    """Listen for game updates from Game Engine and broadcast to all users"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(GAME_UPDATE_CHANNEL)
    
    logger.info(f"Subscribed to {GAME_UPDATE_CHANNEL}")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
    finally:
        await pubsub.unsubscribe(GAME_UPDATE_CHANNEL)

@app.websocket("/ws/game")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Send initial state immediately upon connection
    initial_state = await redis_client.get(GAME_STATE_KEY)
    if initial_state:
        await websocket.send_text(initial_state)

    try:
        while True:
            # Receive messages from the user (e.g., placing bets)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "place_bet":
                    # Push bet to Redis Stream for processing
                    bet_data = {
                        "user_id": message.get("user_id"),
                        "number": message.get("number"),
                        "amount": message.get("amount"),
                        "round_id": message.get("round_id")
                    }
                    await redis_client.xadd(BETS_STREAM, bet_data)
                    await websocket.send_text(json.dumps({"type": "bet_received", "status": "queued"}))
                
                elif message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
