import json
import asyncio
import logging
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger('game.websocket')

# Redis connection for the entire module
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

# Global redis client for consumers
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'game_room'
        self.admin_notifications_group = 'admin_notifications'
        self.redis_task = None

        try:
            await self.accept()
            
            # 1. Join Channels groups (for admin notifications and legacy support)
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            
            user = self.scope.get('user')
            if user and getattr(user, 'is_staff', False):
                await self.channel_layer.group_add(self.admin_notifications_group, self.channel_name)
                logger.info(f"Admin {user.username} connected")

            # 2. Start high-speed Redis listener
            self.redis_task = asyncio.create_task(self.redis_listener())

            # 3. Send initial state IMMEDIATELY from Redis
            await self.send_initial_state()
            
            logger.info(f"WebSocket connected: {self.channel_name}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if self.redis_task:
            self.redis_task.cancel()
        
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        if hasattr(self, 'admin_notifications_group'):
            await self.channel_layer.group_discard(self.admin_notifications_group, self.channel_name)
        
        logger.info(f"WebSocket disconnected: {self.channel_name}")

    async def send_initial_state(self):
        """Fetch current state from Redis and send to client"""
        try:
            state = await redis_client.get('current_game_state')
            if state:
                await self.send(text_data=state)
            else:
                # If engine is not running, send a waiting state
                await self.send(text_data=json.dumps({
                    "type": "game_state",
                    "status": "WAITING",
                    "message": "Waiting for game engine..."
                }))
        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    async def redis_listener(self):
        """Listen for direct Redis Pub/Sub messages - NO POLLING"""
        pubsub = redis_client.pubsub()
        await pubsub.subscribe('game_room')
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    await self.send(text_data=message['data'])
        except asyncio.CancelledError:
            await pubsub.unsubscribe('game_room')
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        finally:
            await pubsub.close()

    async def receive(self, text_data):
        """Handle incoming messages (ping/pong)"""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except:
            pass

    # --- Handlers for channel_layer.group_send ---
    # These are still needed for admin notifications or manual broadcasts

    async def admin_notification(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_state(self, event):
        """Fallback for any group_send calls"""
        await self.send(text_data=json.dumps(event))

    async def timer(self, event):
        """Legacy support for timer events via group_send"""
        if 'payload' in event:
            await self.send(text_data=event['payload'])
        else:
            await self.send(text_data=json.dumps(event))
