import asyncio
import websockets
import json
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WS-Test")

async def test_websocket():
    uri = "wss://gunduata.club/ws/game/"
    logger.info(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected successfully!")
            
            message_count = 0
            start_time = time.time()
            
            while True:
                try:
                    message = await websocket.recv()
                    message_count += 1
                    data = json.loads(message)
                    
                    # Log the received message
                    logger.info(f"Message #{message_count}: {json.dumps(data)}")
                    
                    # Check for expected fields
                    if 'type' not in data:
                        logger.error(f"Missing 'type' in message: {message}")
                    
                    # Simple heartbeat check (optional)
                    if data.get('type') == 'heartbeat':
                        logger.info("Received heartbeat")
                        
                except websockets.ConnectionClosed:
                    logger.warning("Connection closed by server")
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
