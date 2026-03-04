import asyncio
import websockets
import json
import sys

async def test_websocket():
    uri = "wss://gunduata.club/ws/game/"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            # Wait for initial state
            response = await asyncio.wait_for(websocket.recv(), timeout=5)
            print(f"Received: {response}")
            
            # Wait for a few more messages
            for _ in range(3):
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"Received: {response}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
