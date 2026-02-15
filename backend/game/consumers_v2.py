import json
import asyncio
import logging
import msgpack
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger('game.websocket')

# Redis connection
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

# Global redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=False) # Binary for msgpack

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'game_room'
        self.redis_task = None

        try:
            await self.accept()
            
            # Start Redis listener
            self.redis_task = asyncio.create_task(self.redis_listener())

            # Send initial state
            await self.send_initial_state()
            
            logger.info(f"WebSocket connected: {self.channel_name}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if self.redis_task:
            self.redis_task.cancel()
        logger.info(f"WebSocket disconnected: {self.channel_name}")

    async def send_initial_state(self):
        try:
            # Try to get pre-serialized msgpack state first
            state_msgpack = await redis_client.get('current_game_state_msgpack')
            if state_msgpack:
                await self.send(bytes_data=state_msgpack)
            else:
                # Fallback to JSON if msgpack not ready
                state_json = await redis_client.get('current_game_state')
                if state_json:
                    data = json.loads(state_json)
                    await self.send(bytes_data=msgpack.packb(data))
        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    async def redis_listener(self):
        """Listen for direct Redis Pub/Sub messages in MessagePack format"""
        pubsub = redis_client.pubsub()
        await pubsub.subscribe('game_updates_msgpack')
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    # Send raw binary data directly to client
                    await self.send(bytes_data=message['data'])
        except asyncio.CancelledError:
            await pubsub.unsubscribe('game_updates_msgpack')
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        finally:
            await pubsub.close()

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming MessagePack messages"""
        try:
            if bytes_data:
                data = msgpack.unpackb(bytes_data)
            elif text_data:
                data = json.loads(text_data)
            else:
                return

            if data.get('type') == 'ping':
                await self.send(bytes_data=msgpack.packb({'type': 'pong'}))
            
            elif data.get('type') == 'place_bet':
                # Stateless: User ID should be in the JWT scope, not trusted from client
                user = self.scope.get('user')
                if not user or not user.is_authenticated:
                    await self.send(bytes_data=msgpack.packb({'type': 'error', 'message': 'Unauthorized'}))
                    return

                bet_data = {
                    'user_id': user.id,
                    'round_id': data.get('round_id'),
                    'number': data.get('number'),
                    'chip_amount': str(data.get('amount')),
                    'timestamp': datetime.utcnow().isoformat()
                }
                # Push to Redis Stream
                await redis_client.xadd('bet_stream', bet_data)
                await self.send(bytes_data=msgpack.packb({'type': 'bet_received', 'status': 'queued'}))

        except Exception as e:
            logger.error(f"Receive error: {e}")
