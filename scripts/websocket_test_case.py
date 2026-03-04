import asyncio
import websockets
import json
import time
import logging
from collections import Counter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WS-Test-Case")

async def run_test():
    uri = "wss://gunduata.club/ws/game/"
    logger.info(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected successfully!")
            
            # Track message types received for the first few seconds
            received_types = []
            start_time = time.time()
            
            logger.info("Monitoring messages for 60 seconds to verify round transitions...")
            
            while time.time() - start_time < 60:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    m_type = data.get('type')
                    timer = data.get('timer')
                    status = data.get('status')
                    
                    logger.info(f"Received: type={m_type}, timer={timer}, status={status}")
                    
                    # Validation Logic
                    if timer == 1:
                        logger.info(f"--- NEW ROUND DETECTED (Round ID: {data.get('round_id')}) ---")
                    
                    if m_type == 'heartbeat':
                        logger.info("Heartbeat received.")
                    
                except websockets.ConnectionClosed:
                    logger.warning("Connection closed by server")
                    break
                except Exception as e:
                    logger.error(f"Error: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Failed to connect: {e}")

if __name__ == "__main__":
    # You may need to install websockets: pip install websockets
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.info("Test stopped by user")
